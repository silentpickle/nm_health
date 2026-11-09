# Copyright (c) 2026 nm_health contributors
"""Which inspections belong to the same place: normalized name + normalized address."""

import re

from nm_health.ingest.normalizer import normalize_address, normalize_establishment_name

NON_ALNUM = re.compile(r"[^a-z0-9]+")


def establishment_slug(name: str, address: str) -> str:
    """Stable key for a place, e.g. 'acapulco-taco-840-san-mateo-blvd-se'.

    Same rule as the prototype store, so the CLI and the site agree. A renamed business is a new place.
    """
    name_part = NON_ALNUM.sub("-", normalize_establishment_name(name).lower()).strip("-")
    address_part = str(normalize_address(address)["slug"])
    return f"{name_part}-{address_part}"


def normalized_address(address: str) -> str:
    """Canonical street address ('1415 4TH ST SW, Unit H')."""
    return str(normalize_address(address)["normalized_address"])
