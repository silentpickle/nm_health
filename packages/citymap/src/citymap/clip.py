# Copyright (c) 2026 nm_health contributors
"""Clip lines (Liang-Barsky) and rings (Sutherland-Hodgman) to the basemap's bounding box.

Overpass returns whole ways and relations that touch the box; a river or riverbank can run for hundreds of kilometres
beyond it. Clipping keeps the output about the box and nothing else.
"""

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

from citymap.bbox import BBox
from citymap.geometry import Line, Point

LON, LAT = 0, 1  # index of each axis in a (lon, lat) point


def _narrow(t_range: tuple[float, float], p: float, q: float) -> tuple[float, float] | None:
    """One Liang-Barsky boundary test: shrink the visible parameter range, or None when nothing is left."""
    t0, t1 = t_range
    if p == 0:
        return t_range if q >= 0 else None
    r = q / p
    t0, t1 = (max(t0, r), t1) if p < 0 else (t0, min(t1, r))
    return (t0, t1) if t0 <= t1 else None


def _at(a: Point, b: Point, t: float) -> Point:
    """The point a fraction t of the way from a to b (exactly a or b at the ends)."""
    if t == 0:
        return a
    if t == 1:
        return b
    return (a[LON] + t * (b[LON] - a[LON]), a[LAT] + t * (b[LAT] - a[LAT]))


def clip_segment(a: Point, b: Point, box: BBox) -> tuple[Point, Point] | None:
    """The part of segment a-b inside the box, or None when it misses the box entirely."""
    dx, dy = b[LON] - a[LON], b[LAT] - a[LAT]
    tests = (
        (-dx, a[LON] - box.west),
        (dx, box.east - a[LON]),
        (-dy, a[LAT] - box.south),
        (dy, box.north - a[LAT]),
    )
    t_range: tuple[float, float] | None = (0.0, 1.0)
    for p, q in tests:
        t_range = _narrow(t_range, p, q) if t_range else None
    if t_range is None:
        return None
    return _at(a, b, t_range[0]), _at(a, b, t_range[1])


def clip_line(line: Sequence[Point], box: BBox) -> list[Line]:
    """The pieces of a polyline inside the box; a line that leaves and re-enters becomes several pieces."""
    pieces: list[Line] = []
    current: Line = []
    for a, b in itertools.pairwise(line):
        clipped = clip_segment(a, b, box)
        if clipped is None:
            current = _flush(pieces, current)
            continue
        if not current or current[-1] != clipped[0]:
            current = _flush(pieces, current)
            current.append(clipped[0])
        current.append(clipped[1])
        if clipped[1] != b:
            current = _flush(pieces, current)
    _flush(pieces, current)
    return pieces


def _flush(pieces: list[Line], current: Line) -> Line:
    """Keep the current piece when it is a real line; always hand back a fresh empty one."""
    if len(current) > 1:
        pieces.append(current)
    return []


@dataclass(frozen=True, slots=True)
class _Edge:
    """One side of the box: points with point[axis] on the kept side of value are inside."""

    axis: int
    value: float
    keep_greater: bool

    def inside(self, p: Point) -> bool:
        """True when p is on the kept side of this edge (the edge itself counts as inside)."""
        return p[self.axis] >= self.value if self.keep_greater else p[self.axis] <= self.value

    def crossing(self, a: Point, b: Point) -> Point:
        """Where segment a-b crosses this edge (only called when it does)."""
        t = (self.value - a[self.axis]) / (b[self.axis] - a[self.axis])
        return _at(a, b, t)


def _edges(box: BBox) -> tuple[_Edge, ...]:
    return (
        _Edge(LON, box.west, keep_greater=True),
        _Edge(LON, box.east, keep_greater=False),
        _Edge(LAT, box.south, keep_greater=True),
        _Edge(LAT, box.north, keep_greater=False),
    )


def _clip_against(ring: Sequence[Point], edge: _Edge) -> Line:
    """Sutherland-Hodgman against one edge. The ring is open (its last point is not a repeat of the first)."""
    out: Line = []
    for i, current in enumerate(ring):
        previous = ring[i - 1]
        if edge.inside(current) != edge.inside(previous):
            out.append(edge.crossing(previous, current))
        if edge.inside(current):
            out.append(current)
    return out


def clip_ring(ring: Sequence[Point], box: BBox) -> Line:
    """The part of an open ring inside the box, still open. Empty when the ring misses the box."""
    out: Line = list(ring)
    for edge in _edges(box):
        out = _clip_against(out, edge) if out else out
    return out
