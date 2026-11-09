# Copyright (c) 2026 nm_health contributors
"""Clipping, joining, rounding and measuring."""

import pytest

from citymap.bbox import BBox
from citymap.clip import clip_line, clip_ring, clip_segment
from citymap.geometry import is_closed, length_m, ring_area_m2, round_line
from citymap.merge import merge_lines

BOX = BBox(south=0.0, west=0.0, north=10.0, east=10.0)
EQUATOR = 0.0
ONE_DEGREE_M = 111_320.0
DIGITS = 5


def test_clip_segment_inside_is_untouched() -> None:
    """Clip segment inside is untouched."""
    assert clip_segment((1.0, 1.0), (9.0, 9.0), BOX) == ((1.0, 1.0), (9.0, 9.0))


def test_clip_segment_outside_is_none() -> None:
    """Clip segment outside is none."""
    assert clip_segment((-5.0, -5.0), (-1.0, 20.0), BOX) is None


def test_clip_segment_crossing_is_cut_at_the_edges() -> None:
    """Clip segment crossing is cut at the edges."""
    assert clip_segment((-5.0, 5.0), (15.0, 5.0), BOX) == ((0.0, 5.0), (10.0, 5.0))


def test_clip_segment_parallel_outside_is_none() -> None:
    """Clip segment parallel outside is none."""
    assert clip_segment((-1.0, 0.0), (-1.0, 10.0), BOX) is None


def test_clip_line_that_leaves_and_returns_splits_in_two() -> None:
    """Clip line that leaves and returns splits in two."""
    line = [(1.0, 5.0), (15.0, 5.0), (15.0, 8.0), (1.0, 8.0)]
    assert clip_line(line, BOX) == [[(1.0, 5.0), (10.0, 5.0)], [(10.0, 8.0), (1.0, 8.0)]]


def test_clip_line_fully_inside_stays_one_piece() -> None:
    """Clip line fully inside stays one piece."""
    line = [(1.0, 1.0), (2.0, 2.0), (3.0, 1.0)]
    assert clip_line(line, BOX) == [line]


def test_clip_line_fully_outside_is_empty() -> None:
    """Clip line fully outside is empty."""
    assert clip_line([(20.0, 20.0), (30.0, 30.0)], BOX) == []


def test_clip_ring_cuts_off_the_outside_corner() -> None:
    """Clip ring cuts off the outside corner."""
    ring = [(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0)]
    clipped = clip_ring(ring, BOX)
    assert sorted(clipped) == [(5.0, 5.0), (5.0, 10.0), (10.0, 5.0), (10.0, 10.0)]  # same corners, any start


def test_clip_ring_outside_is_empty() -> None:
    """Clip ring outside is empty."""
    assert clip_ring([(20.0, 20.0), (30.0, 20.0), (30.0, 30.0)], BOX) == []


def test_merge_joins_lines_end_to_end_reversing_as_needed() -> None:
    """Merge joins lines end to end reversing as needed."""
    merged = merge_lines([[(0.0, 0.0), (1.0, 0.0)], [(2.0, 0.0), (1.0, 0.0)], [(2.0, 0.0), (3.0, 0.0)]])
    assert merged == [[(3.0, 0.0), (2.0, 0.0), (1.0, 0.0), (0.0, 0.0)]]


def test_merge_keeps_disconnected_lines_apart() -> None:
    """Merge keeps disconnected lines apart."""
    a, b = [(0.0, 0.0), (1.0, 0.0)], [(5.0, 5.0), (6.0, 5.0)]
    assert merge_lines([a, b]) == [list(reversed(a)), list(reversed(b))]


def test_merge_rebuilds_a_ring_from_two_halves() -> None:
    """Merge rebuilds a ring from two halves."""
    merged = merge_lines([[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], [(1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]])
    assert len(merged) == 1
    assert is_closed(merged[0])


def test_merge_drops_single_point_lines() -> None:
    """Merge drops single point lines."""
    assert merge_lines([[(0.0, 0.0)]]) == []


def test_round_line_rounds_and_drops_repeats() -> None:
    """Round line rounds and drops repeats."""
    line = [(-106.123456, 35.000001), (-106.123459, 35.000004), (-106.2, 35.1)]
    assert round_line(line, DIGITS) == [(-106.12346, 35.0), (-106.2, 35.1)]


def test_length_of_one_degree_of_latitude() -> None:
    """Length of one degree of latitude."""
    assert length_m([(0.0, 0.0), (0.0, 1.0)], EQUATOR) == pytest.approx(ONE_DEGREE_M)


def test_area_of_a_square_degree_at_the_equator() -> None:
    """Area of a square degree at the equator."""
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    assert ring_area_m2(square, EQUATOR) == pytest.approx(ONE_DEGREE_M**2)


def test_open_or_short_lines_are_not_closed() -> None:
    """Open or short lines are not closed."""
    assert not is_closed([(0.0, 0.0), (1.0, 0.0), (0.0, 0.0)])
    assert not is_closed([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
