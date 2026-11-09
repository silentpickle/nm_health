# Copyright (c) 2026 nm_health contributors
"""Ramer-Douglas-Peucker line simplification, in pure Python.

A point survives when it sits farther than the tolerance from the segment joining the points kept on either side of it.
A point exactly at the tolerance is dropped. Endpoints always survive, so closed rings stay closed.
"""

import math
from collections.abc import Sequence

from citymap.geometry import Line, Point, to_plane

MIN_POINTS_TO_SIMPLIFY = 3  # two points are already as simple as a line gets


def segment_distance(p: Point, a: Point, b: Point) -> float:
    """Distance from p to the segment a-b (to a itself when a and b coincide)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    span = dx * dx + dy * dy
    if span == 0:
        return math.dist(p, a)
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / span
    t = min(1.0, max(0.0, t))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def _farthest(points: Sequence[Point], first: int, last: int) -> tuple[int, float]:
    """The index strictly between first and last farthest from segment first-last, and its distance."""
    best_index, best_distance = first, 0.0
    for i in range(first + 1, last):
        d = segment_distance(points[i], points[first], points[last])
        if d > best_distance:
            best_index, best_distance = i, d
    return best_index, best_distance


def rdp_indices(points: Sequence[Point], tolerance: float) -> list[int]:
    """Indices of the points RDP keeps, in order. Iterative, so long lines cannot overflow the stack."""
    n = len(points)
    if n < MIN_POINTS_TO_SIMPLIFY:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        index, distance = _farthest(points, first, last)
        if distance <= tolerance:
            continue
        keep[index] = True
        stack.extend(((first, index), (index, last)))
    return [i for i, kept in enumerate(keep) if kept]


def rdp(points: Sequence[Point], tolerance: float) -> Line:
    """The points RDP keeps, measured in the points' own units."""
    return [points[i] for i in rdp_indices(points, tolerance)]


def simplify_lonlat(line: Sequence[Point], tolerance_m: float, mid_lat: float) -> Line:
    """Simplify a (lon, lat) line with a tolerance in ground metres; returns original (unprojected) points."""
    return [line[i] for i in rdp_indices(to_plane(line, mid_lat), tolerance_m)]
