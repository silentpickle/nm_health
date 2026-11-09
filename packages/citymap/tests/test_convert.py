# Copyright (c) 2026 nm_health contributors
"""Overpass JSON to GeoJSON, from a small committed fixture (no network)."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from citymap.bbox import BBox
from citymap.cli import main
from citymap.convert import (
    ATTRIBUTION,
    COORD_DIGITS,
    Collection,
    Element,
    classify,
    convert,
    point_count,
    shape_piece,
    shape_ring,
)
from citymap.detail import DETAILS
from citymap.geometry import length_m, ring_area_m2
from citymap.writer import dumps

FIXTURES = Path(__file__).parent / "fixtures"
RESPONSE = FIXTURES / "overpass_small.json"
BOX = BBox(south=35.0, west=-106.7, north=35.1, east=-106.6)
MAJOR_FEATURES = 6
MAJOR_POINTS = 22
EPSILON = 1e-9


def _response() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(RESPONSE.read_text(encoding="utf-8")))


def _expected(detail: str) -> object:
    return json.loads((FIXTURES / f"expected_{detail}.geojson").read_text(encoding="utf-8"))


def _names(collection: Collection) -> list[tuple[str, str | None]]:
    return [(f["properties"]["kind"], f["properties"].get("name")) for f in collection["features"]]


@pytest.mark.parametrize("detail", ["major", "medium"])
def test_fixture_converts_to_the_golden_output(detail: str) -> None:
    """Fixture converts to the golden output."""
    collection = convert(_response(), BOX, DETAILS[detail])
    assert json.loads(dumps(collection)) == _expected(detail)


def test_major_keeps_the_landmarks_and_drops_the_clutter() -> None:
    """Major keeps the landmarks and drops the clutter."""
    collection = convert(_response(), BOX, DETAILS["major"])
    assert _names(collection) == [
        ("water", "Big Pond"),
        ("water", "Rio Grande"),
        ("river", "Rio Grande"),
        ("road_major", "Central Avenue"),
        ("road_major", "I 25"),
        ("boundary", "Testville"),
    ]
    assert point_count(collection) == MAJOR_POINTS


def test_medium_adds_secondary_roads() -> None:
    """Medium adds secondary roads."""
    names = _names(convert(_response(), BOX, DETAILS["medium"]))
    assert ("road_medium", "Lomas Boulevard") in names
    assert len(names) == MAJOR_FEATURES + 1


def test_collection_carries_attribution_and_geojson_bbox() -> None:
    """Collection carries attribution and geojson bbox."""
    collection = convert(_response(), BOX, DETAILS["major"])
    assert collection["attribution"] == ATTRIBUTION
    assert collection["bbox"] == [BOX.west, BOX.south, BOX.east, BOX.north]


def test_ways_split_into_pieces_are_joined_and_simplified() -> None:
    """Ways split into pieces are joined and simplified."""
    collection = convert(_response(), BOX, DETAILS["major"])
    i25 = next(f for f in collection["features"] if f["properties"].get("name") == "I 25")
    assert i25["geometry"]["coordinates"] == [[(-106.65, 35.07), (-106.65, 35.01)]]


def test_lines_are_clipped_to_the_bbox() -> None:
    """Lines are clipped to the bbox."""
    collection = convert(_response(), BOX, DETAILS["major"])
    central = next(f for f in collection["features"] if f["properties"].get("name") == "Central Avenue")
    assert central["geometry"]["coordinates"] == [[(-106.62, 35.05), (BOX.west, 35.05)]]


def test_every_coordinate_is_rounded() -> None:
    """Every coordinate is rounded."""
    text = dumps(convert(_response(), BOX, DETAILS["medium"]))
    numbers = text.split('"features":[', 1)[1].replace("[", ",").replace("]", ",").split(",")
    decimals = [n.split(".")[1] for n in numbers if "." in n and n.lstrip("-")[:1].isdigit()]
    assert decimals
    assert all(len(d) <= COORD_DIGITS for d in decimals)


@pytest.mark.parametrize(
    ("tags", "element_type", "expected"),
    [
        ({"highway": "motorway"}, "way", "road_major"),
        ({"highway": "secondary"}, "way", None),
        ({"highway": "residential"}, "way", None),
        ({"waterway": "river"}, "way", "river"),
        ({"waterway": "river", "intermittent": "yes"}, "way", None),
        ({"waterway": "river", "seasonal": "yes"}, "way", None),
        ({"natural": "water", "water": "basin"}, "way", None),
        ({"natural": "water", "water": "lake"}, "relation", "water"),
        ({"boundary": "administrative"}, "relation", "boundary"),
        ({"boundary": "administrative"}, "way", None),
        ({}, "way", None),
    ],
    ids=[
        "motorway",
        "secondary_at_major",
        "residential",
        "river",
        "intermittent_river",
        "seasonal_river",
        "detention_basin",
        "lake_relation",
        "admin_relation",
        "admin_way",
        "untagged",
    ],
)
def test_classify(tags: dict[str, str], element_type: str, expected: str | None) -> None:
    """Classify."""
    element: Element = {"type": element_type, "id": 1, "tags": tags}
    assert classify(element, DETAILS["major"]) == expected


def test_response_without_elements_is_rejected() -> None:
    """Response without elements is rejected."""
    with pytest.raises(TypeError, match="elements"):
        convert({"remark": "nothing"}, BOX, DETAILS["major"])


def test_cli_builds_from_a_saved_response(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Cli builds from a saved response."""
    out = tmp_path / "nested" / "map.geojson"
    argv = ["build", "--bbox", "35.0,-106.7,35.1,-106.6", "--out", str(out), "--from-response", str(RESPONSE)]
    assert main(argv) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == _expected("major")
    assert f"{MAJOR_FEATURES} features, {MAJOR_POINTS} points" in capsys.readouterr().out


def test_piece_exactly_min_length_kept_and_longer_limit_drops_it() -> None:
    """A piece exactly detail.min_length_m long survives; raise the limit a hair and it is dropped."""
    piece = [(-106.65, 35.05), (-106.65, 35.051)]
    exact = length_m(piece, BOX.mid_lat)
    assert shape_piece(piece, BOX, replace(DETAILS["major"], min_length_m=exact)) == piece
    assert shape_piece(piece, BOX, replace(DETAILS["major"], min_length_m=exact * (1 + EPSILON))) is None


def test_ring_exactly_min_area_kept_and_larger_limit_drops_it() -> None:
    """A water ring exactly detail.min_water_area_m2 in area survives; raise the limit a hair and it is dropped."""
    ring = [(-106.64, 35.06), (-106.636, 35.06), (-106.636, 35.064), (-106.64, 35.064), (-106.64, 35.06)]
    exact = ring_area_m2(ring, BOX.mid_lat)
    assert shape_ring(ring, BOX, replace(DETAILS["major"], min_water_area_m2=exact)) == ring
    assert shape_ring(ring, BOX, replace(DETAILS["major"], min_water_area_m2=exact * (1 + EPSILON))) is None


def test_ring_outside_the_box_is_dropped() -> None:
    """A water ring wholly outside the box leaves nothing to draw."""
    ring = [(-107.0, 36.0), (-106.9, 36.0), (-106.9, 36.1), (-107.0, 36.0)]
    assert shape_ring(ring, BOX, DETAILS["major"]) is None
