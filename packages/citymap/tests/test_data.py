# Copyright (c) 2026 nm_health contributors
"""The committed Albuquerque basemap stays small, attributed, rounded and inside its bbox."""

import json
from pathlib import Path
from typing import cast

from citymap.convert import ATTRIBUTION, COORD_DIGITS, LINE_KINDS, Collection, point_count
from citymap.geometry import Point

DATA = Path(__file__).parent.parent / "data" / "albuquerque.geojson"
MAX_BYTES = 300 * 1024
ABQ_BBOX = [-106.89, 34.94, -106.46, 35.22]
KINDS = {*LINE_KINDS, "water"}


def _collection() -> Collection:
    return cast("Collection", json.loads(DATA.read_text(encoding="utf-8")))


def _points(collection: Collection) -> list[Point]:
    out: list[Point] = []
    for feature in collection["features"]:
        geometry = feature["geometry"]
        rings = geometry["coordinates"]
        if geometry["type"] == "MultiPolygon":
            rings = [ring for polygon in cast("list[list[list[Point]]]", rings) for ring in polygon]
        out.extend(point for ring in cast("list[list[Point]]", rings) for point in ring)
    return out


def test_albuquerque_under_size_budget() -> None:
    """The basemap a page downloads stays under 300 KB."""
    assert DATA.stat().st_size < MAX_BYTES


def test_albuquerque_attribution_and_bbox() -> None:
    """ODbL attribution and the bbox (GeoJSON order) ride along with the data."""
    collection = _collection()
    assert collection["attribution"] == ATTRIBUTION
    assert collection["bbox"] == ABQ_BBOX


def test_albuquerque_has_every_layer() -> None:
    """Roads, river, water and the city boundary are all present, and nothing else."""
    kinds = {f["properties"]["kind"] for f in _collection()["features"]}
    assert kinds == KINDS - {"road_medium"}


def test_albuquerque_coordinates_rounded_and_inside_bbox() -> None:
    """Every coordinate has at most 5 decimals and lies within the bbox (clipping worked)."""
    collection = _collection()
    points = _points(collection)
    west, south, east, north = ABQ_BBOX
    assert len(points) == point_count(collection)
    assert all(round(lon, COORD_DIGITS) == lon and round(lat, COORD_DIGITS) == lat for lon, lat in points)
    assert all(west <= lon <= east and south <= lat <= north for lon, lat in points)
