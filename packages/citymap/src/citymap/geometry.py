# Copyright (c) 2026 nm_health contributors
"""Plain-tuple geometry: points are (lon, lat), the GeoJSON order. Distances are approximate ground metres."""

import itertools
import math
from collections.abc import Sequence

type Point = tuple[float, float]
type Line = list[Point]

METERS_PER_DEGREE_LAT = 111_320.0  # mean length of one degree of latitude
MIN_RING_POINTS = 4  # a closed ring: three corners plus the repeated first point


def to_plane(points: Sequence[Point], mid_lat: float) -> Line:
    """Project (lon, lat) to a flat plane in metres (equirectangular, longitude scaled by cos(mid_lat))."""
    kx = math.cos(math.radians(mid_lat)) * METERS_PER_DEGREE_LAT
    return [(lon * kx, lat * METERS_PER_DEGREE_LAT) for lon, lat in points]


def length_m(line: Sequence[Point], mid_lat: float) -> float:
    """Approximate ground length of a polyline in metres."""
    flat = to_plane(line, mid_lat)
    return sum(math.dist(a, b) for a, b in itertools.pairwise(flat))


def ring_area_m2(ring: Sequence[Point], mid_lat: float) -> float:
    """Approximate area of a ring in square metres (shoelace formula; the ring may be open or closed)."""
    flat = to_plane(ring, mid_lat)
    twice = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(flat, flat[1:] + flat[:1], strict=True))
    return abs(twice) / 2


def round_line(line: Sequence[Point], digits: int) -> Line:
    """Round every coordinate and drop points that land on the one before them."""
    out: Line = []
    for lon, lat in line:
        point = (round(lon, digits), round(lat, digits))
        if out and out[-1] == point:
            continue
        out.append(point)
    return out


def is_closed(line: Sequence[Point]) -> bool:
    """True when the line ends where it starts and has room to enclose something."""
    return len(line) >= MIN_RING_POINTS and line[0] == line[-1]
