# Copyright (c) 2026 nm_health contributors
"""The bounding box a basemap covers, in the order Overpass uses (south, west, north, east)."""

import math
from dataclasses import dataclass

LAT_LIMIT = 90.0
LON_LIMIT = 180.0
BBOX_PARTS = 4


@dataclass(frozen=True, slots=True)
class BBox:
    """A latitude/longitude rectangle. Validated on creation: south < north, west < east, all within the globe."""

    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        """Reject boxes that are empty, inverted or off the globe."""
        if not all(math.isfinite(v) for v in (self.south, self.west, self.north, self.east)):
            msg = "bbox values must be finite numbers"
            raise ValueError(msg)
        if not -LAT_LIMIT <= self.south < self.north <= LAT_LIMIT:
            msg = f"bbox needs -90 <= south < north <= 90, got south={self.south} north={self.north}"
            raise ValueError(msg)
        if not -LON_LIMIT <= self.west < self.east <= LON_LIMIT:
            msg = f"bbox needs -180 <= west < east <= 180, got west={self.west} east={self.east}"
            raise ValueError(msg)

    @classmethod
    def parse(cls, text: str) -> "BBox":
        """Read "south,west,north,east" (the CLI and Overpass order)."""
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != BBOX_PARTS:
            msg = f"bbox must be south,west,north,east (4 numbers), got {text!r}"
            raise ValueError(msg)
        south, west, north, east = (float(p) for p in parts)
        return cls(south=south, west=west, north=north, east=east)

    @property
    def mid_lat(self) -> float:
        """The latitude halfway between south and north, used to scale longitude to ground distance."""
        return (self.south + self.north) / 2

    def overpass(self) -> str:
        """The box as an Overpass QL bbox filter body: south,west,north,east."""
        return f"{self.south},{self.west},{self.north},{self.east}"

    def geojson(self) -> list[float]:
        """The box as a GeoJSON bbox (RFC 7946): [west, south, east, north]."""
        return [self.west, self.south, self.east, self.north]
