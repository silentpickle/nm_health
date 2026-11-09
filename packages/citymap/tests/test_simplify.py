# Copyright (c) 2026 nm_health contributors
"""Ramer-Douglas-Peucker: endpoints survive, collinear points go, the tolerance itself is exclusive."""

import pytest

from citymap.geometry import Point
from citymap.simplify import rdp, rdp_indices, segment_distance, simplify_lonlat

TOLERANCE = 1.0
JUST_OVER = 1.000001
ABQ_LAT = 35.08
TEN_M_TOLERANCE = 10.0
NINE_M_IN_DEGREES = 0.0001  # longitude at ABQ_LAT: about 9.1 m
LONG_LINE_POINTS = 1_500  # deeper than Python's default recursion limit (1000)


def test_empty_and_single_point_unchanged() -> None:
    """Empty and single point unchanged."""
    assert rdp([], TOLERANCE) == []
    assert rdp([(0.0, 0.0)], TOLERANCE) == [(0.0, 0.0)]


def test_two_points_unchanged_even_with_huge_tolerance() -> None:
    """Two points unchanged even with huge tolerance."""
    line = [(0.0, 0.0), (5.0, 5.0)]
    assert rdp(line, 1e9) == line


def test_collinear_points_reduce_to_endpoints() -> None:
    """Collinear points reduce to endpoints."""
    line = [(float(x), 2.0 * x) for x in range(10)]
    assert rdp(line, TOLERANCE) == [line[0], line[-1]]


def test_zero_tolerance_still_drops_exactly_collinear_points() -> None:
    """Zero tolerance still drops exactly collinear points."""
    line = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    assert rdp(line, 0.0) == [(0.0, 0.0), (2.0, 0.0)]


def test_point_exactly_at_tolerance_dropped() -> None:
    """Point exactly at tolerance dropped."""
    line = [(0.0, 0.0), (5.0, TOLERANCE), (10.0, 0.0)]
    assert rdp(line, TOLERANCE) == [(0.0, 0.0), (10.0, 0.0)]


def test_point_just_over_tolerance_kept() -> None:
    """Point just over tolerance kept."""
    line = [(0.0, 0.0), (5.0, JUST_OVER), (10.0, 0.0)]
    assert rdp(line, TOLERANCE) == line


def test_keeps_the_corner_and_recurses_on_both_sides() -> None:
    """Keeps the corner and recurses on both sides."""
    line: list[Point] = [(0.0, 0.0), (1.0, 0.1), (2.0, 0.0), (2.0, 5.0), (2.1, 6.0), (2.0, 10.0)]
    assert rdp_indices(line, TOLERANCE) == [0, 2, 5]


def test_closed_ring_keeps_its_closing_point() -> None:
    """Closed ring keeps its closing point."""
    ring = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)]
    assert rdp(ring, TOLERANCE) == ring


def test_long_line_does_not_overflow_the_stack() -> None:
    """Long line does not overflow the stack."""
    zigzag = [(float(i), float(i % 2) * 2 * TOLERANCE) for i in range(LONG_LINE_POINTS)]
    assert len(rdp(zigzag, TOLERANCE)) == LONG_LINE_POINTS


@pytest.mark.parametrize(
    ("p", "expected"),
    [((0.0, 3.0), 3.0), ((-4.0, 3.0), 5.0), ((14.0, 3.0), 5.0)],
    ids=["beside_segment", "before_start", "past_end"],
)
def test_segment_distance_clamps_to_the_segment(p: Point, expected: float) -> None:
    """Segment distance clamps to the segment."""
    assert segment_distance(p, (0.0, 0.0), (10.0, 0.0)) == pytest.approx(expected)


def test_segment_distance_to_a_degenerate_segment_is_point_distance() -> None:
    """Segment distance to a degenerate segment is point distance."""
    assert segment_distance((3.0, 4.0), (0.0, 0.0), (0.0, 0.0)) == pytest.approx(5.0)


def test_lonlat_tolerance_is_in_ground_metres() -> None:
    """Lonlat tolerance is in ground metres."""
    bend = [(-106.65, 35.01), (-106.65 + NINE_M_IN_DEGREES, 35.05), (-106.65, 35.07)]
    assert simplify_lonlat(bend, TEN_M_TOLERANCE, ABQ_LAT) == [bend[0], bend[-1]]
    assert simplify_lonlat(bend, TEN_M_TOLERANCE / 2, ABQ_LAT) == bend
