# Copyright (c) 2026 nm_health contributors
"""Detail levels: which roads a basemap keeps and how hard it simplifies them."""

from dataclasses import dataclass

MAJOR_HIGHWAYS = ("motorway", "trunk", "primary")
MEDIUM_HIGHWAYS = ("secondary",)


@dataclass(frozen=True, slots=True)
class Detail:
    """What one detail level keeps.

    Attributes:
        highways: OSM highway=* values to fetch.
        tolerance_m: RDP tolerance in ground metres.
        min_length_m: Drop line pieces shorter than this after simplifying.
        min_water_area_m2: Drop water polygons smaller than this.
    """

    highways: tuple[str, ...]
    tolerance_m: float
    min_length_m: float
    min_water_area_m2: float


DETAILS: dict[str, Detail] = {
    "major": Detail(
        highways=MAJOR_HIGHWAYS,
        tolerance_m=10.0,
        min_length_m=60.0,
        min_water_area_m2=40_000.0,
    ),
    "medium": Detail(
        highways=MAJOR_HIGHWAYS + MEDIUM_HIGHWAYS,
        tolerance_m=6.0,
        min_length_m=40.0,
        min_water_area_m2=20_000.0,
    ),
}


def road_kind(highway: str) -> str:
    """The feature kind for a highway=* value the builder fetched."""
    return "road_major" if highway in MAJOR_HIGHWAYS else "road_medium"
