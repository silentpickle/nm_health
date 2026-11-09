# Copyright (c) 2026 nm_health contributors
"""Turn an Overpass `out geom` response into small GeoJSON features.

Pipeline, per (kind, name) group: join ways end to end, clip to the box, simplify (RDP), round to COORD_DIGITS, then
drop what is too small to see. Lines come out as one MultiLineString per group, water as one MultiPolygon per group
(outer rings only: holes such as river islands are left filled, which is invisible at city scale).
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, NotRequired, TypedDict, cast

from citymap.bbox import BBox
from citymap.clip import clip_line, clip_ring
from citymap.detail import Detail, road_kind
from citymap.geometry import MIN_RING_POINTS, Line, Point, is_closed, length_m, ring_area_m2, round_line
from citymap.merge import merge_lines
from citymap.simplify import simplify_lonlat

COORD_DIGITS = 5  # about 1 m on the ground: finer than any screen pixel at city scale
ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
INNER_ROLE = "inner"
MIN_LINE_POINTS = 2
YES = "yes"
EXCLUDED_WATER = frozenset({"basin", "ditch", "drain", "wastewater"})  # water=* values that are works, not landmarks

type Kind = Literal["road_major", "road_medium", "river", "water", "boundary"]
LINE_KINDS: tuple[Kind, ...] = ("road_major", "road_medium", "river", "boundary")


class GeomPoint(TypedDict):
    """One vertex of an Overpass `out geom` way."""

    lat: float
    lon: float


class Member(TypedDict):
    """One relation member, with geometry when it is a way."""

    type: str
    role: str
    geometry: NotRequired[list[GeomPoint | None]]


class Element(TypedDict):
    """One Overpass element (way or relation) as `out geom` prints it."""

    type: str
    id: int
    tags: NotRequired[dict[str, str]]
    geometry: NotRequired[list[GeomPoint | None]]
    members: NotRequired[list[Member]]


class Properties(TypedDict):
    """The properties every output feature carries."""

    kind: Kind
    name: NotRequired[str]


class Geometry(TypedDict):
    """A GeoJSON MultiLineString or MultiPolygon."""

    type: Literal["MultiLineString", "MultiPolygon"]
    coordinates: list[Line] | list[list[Line]]


class Feature(TypedDict):
    """One GeoJSON feature."""

    type: Literal["Feature"]
    properties: Properties
    geometry: Geometry


class Collection(TypedDict):
    """The basemap: a GeoJSON FeatureCollection with the bbox and the attribution ODbL requires."""

    type: Literal["FeatureCollection"]
    attribution: str
    bbox: list[float]
    features: list[Feature]


type GroupKey = tuple[Kind, str | None]


@dataclass
class Collected:
    """Raw geometry sorted into groups: lines to join, rings that are already closed."""

    lines: dict[GroupKey, list[Line]] = field(default_factory=lambda: defaultdict(list))
    rings: dict[GroupKey, list[Line]] = field(default_factory=lambda: defaultdict(list))


# --- Classification: one small rule per kind, run in order; the first that answers wins. ---

type Rule = Callable[[Element, Detail], Kind | None]


def _tags(element: Element) -> dict[str, str]:
    return element.get("tags", {})


def _road(element: Element, detail: Detail) -> Kind | None:
    highway = _tags(element).get("highway")
    if element["type"] != "way" or highway not in detail.highways:
        return None
    return cast("Kind", road_kind(highway))


def is_permanent_water(tags: dict[str, str]) -> bool:
    """False for dry washes and works: intermittent or seasonal water, drains, ditches, basins, wastewater ponds.

    In arid cities most waterway=river ways are arroyos (intermittent=yes); without this they bury the real river.
    """
    seasonal = YES in {tags.get("intermittent"), tags.get("seasonal")}
    return not seasonal and tags.get("water") not in EXCLUDED_WATER


def _river(element: Element, _detail: Detail) -> Kind | None:
    tags = _tags(element)
    is_river = element["type"] == "way" and tags.get("waterway") == "river"
    return "river" if is_river and is_permanent_water(tags) else None


def _water(element: Element, _detail: Detail) -> Kind | None:
    tags = _tags(element)
    return "water" if tags.get("natural") == "water" and is_permanent_water(tags) else None


def _boundary(element: Element, _detail: Detail) -> Kind | None:
    is_admin = _tags(element).get("boundary") == "administrative"
    return "boundary" if element["type"] == "relation" and is_admin else None


RULES: tuple[Rule, ...] = (_road, _river, _water, _boundary)


def classify(element: Element, detail: Detail) -> Kind | None:
    """The feature kind of an element, or None when the basemap does not keep it."""
    return next((kind for rule in RULES if (kind := rule(element, detail))), None)


# --- Geometry extraction ---


def _line(points: Iterable[GeomPoint | None]) -> Line:
    """(lon, lat) points from Overpass vertices, skipping the nulls `out geom` prints for vertices it lacks."""
    return [(p["lon"], p["lat"]) for p in points if p is not None]


def element_lines(element: Element) -> list[Line]:
    """A way's line, or a relation's way members (outer and untagged roles; inner rings are skipped)."""
    if element["type"] == "way":
        return [_line(element.get("geometry", []))]
    members = element.get("members", [])
    return [_line(m.get("geometry", [])) for m in members if m["type"] == "way" and m["role"] != INNER_ROLE]


def _name(element: Element) -> str | None:
    tags = _tags(element)
    return tags.get("name") or tags.get("ref")


def collect(elements: Iterable[Element], detail: Detail) -> Collected:
    """Sort every kept element's geometry into (kind, name) groups."""
    out = Collected()
    for element in elements:
        kind = classify(element, detail)
        if kind is None:
            continue
        key: GroupKey = (kind, _name(element))
        lines = element_lines(element)
        if kind != "water":
            out.lines[key].extend(lines)
            continue
        out.rings[key].extend(ring for ring in merge_lines(lines) if is_closed(ring))
    return out


# --- Shaping: clip, simplify, round, filter ---


def shape_piece(piece: Line, box: BBox, detail: Detail) -> Line | None:
    """Simplify and round one clipped piece; None when it ends up shorter than detail.min_length_m."""
    simple = round_line(simplify_lonlat(piece, detail.tolerance_m, box.mid_lat), COORD_DIGITS)
    if len(simple) < MIN_LINE_POINTS or length_m(simple, box.mid_lat) < detail.min_length_m:
        return None
    return simple


def shape_lines(lines: Sequence[Line], box: BBox, detail: Detail) -> list[Line]:
    """Join, clip, simplify and round one group's lines, keeping the pieces long enough to see."""
    pieces = [piece for joined in merge_lines(lines) for piece in clip_line(joined, box)]
    return [shaped for shaped in (shape_piece(p, box, detail) for p in pieces) if shaped is not None]


def shape_ring(ring: Line, box: BBox, detail: Detail) -> Line | None:
    """Clip, simplify and round one closed ring; None when too little of it is left to see."""
    clipped = clip_ring(ring[:-1], box)
    if not clipped:
        return None
    closed = [*clipped, clipped[0]]
    simple = round_line(simplify_lonlat(closed, detail.tolerance_m, box.mid_lat), COORD_DIGITS)
    if len(simple) < MIN_RING_POINTS or simple[0] != simple[-1]:
        return None
    return simple if ring_area_m2(simple, box.mid_lat) >= detail.min_water_area_m2 else None


def _feature(key: GroupKey, geometry: Geometry) -> Feature:
    kind, name = key
    properties: Properties = {"kind": kind}
    if name:
        properties["name"] = name
    return {"type": "Feature", "properties": properties, "geometry": geometry}


def line_features(collected: Collected, box: BBox, detail: Detail) -> list[Feature]:
    """One MultiLineString per (kind, name) group that has anything left after shaping."""
    features: list[Feature] = []
    for key, lines in collected.lines.items():
        shaped = shape_lines(lines, box, detail)
        if shaped:
            features.append(_feature(key, {"type": "MultiLineString", "coordinates": shaped}))
    return features


def water_features(collected: Collected, box: BBox, detail: Detail) -> list[Feature]:
    """One MultiPolygon per named (or unnamed) group of water rings big enough to see."""
    features: list[Feature] = []
    for key, rings in collected.rings.items():
        shaped = [[r] for r in (shape_ring(ring, box, detail) for ring in rings) if r is not None]
        if shaped:
            features.append(_feature(key, {"type": "MultiPolygon", "coordinates": shaped}))
    return features


KIND_ORDER: dict[Kind, int] = {"water": 0, "river": 1, "road_medium": 2, "road_major": 3, "boundary": 4}


def _sort_key(feature: Feature) -> tuple[int, str]:
    properties = feature["properties"]
    return KIND_ORDER[properties["kind"]], properties.get("name", "")


def convert(response: dict[str, object], box: BBox, detail: Detail) -> Collection:
    """The whole basemap from one Overpass response, features sorted by drawing order then name."""
    elements = response.get("elements")
    if not isinstance(elements, list):
        msg = "Overpass response has no 'elements' list"
        raise TypeError(msg)
    collected = collect(cast("list[Element]", elements), detail)
    features = water_features(collected, box, detail) + line_features(collected, box, detail)
    features.sort(key=_sort_key)
    return {"type": "FeatureCollection", "attribution": ATTRIBUTION, "bbox": box.geojson(), "features": features}


def point_count(collection: Collection) -> int:
    """How many coordinate pairs the collection holds (a size gauge for reports and tests)."""
    total = 0
    for feature in collection["features"]:
        geometry = feature["geometry"]
        parts = cast("list[list[Point]]", geometry["coordinates"])
        if geometry["type"] == "MultiPolygon":
            parts = [ring for polygon in cast("list[list[Line]]", geometry["coordinates"]) for ring in polygon]
        total += sum(len(part) for part in parts)
    return total
