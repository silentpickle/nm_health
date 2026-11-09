# Copyright (c) 2026 nm_health contributors
"""Which inspections belong to the same place: normalized name + normalized address."""

import re

from nm_health.ingest.normalizer import normalize_address, normalize_establishment_name

NON_ALNUM = re.compile(r"[^a-z0-9]+")
DBA_RE = re.compile(r"\s+D\.?/?B\.?/?A\.?:?\s+", re.IGNORECASE)  # "Long Cao LLC DBA Dragon Sushi", "X d/b/a Y"
CITY_SUFFIX_RE = re.compile(r",?\s+ALBUQUERQUE,?\s*NM\s*\d{5}(?:-\d{4})?\s*$", re.IGNORECASE)


def split_dba(name: str) -> tuple[str, str | None]:
    """(name people know, legal name or None): 'Long Cao LLC DBA Dragon Sushi' -> ('Dragon Sushi', 'Long Cao LLC')."""
    parts = DBA_RE.split(name.strip(), maxsplit=1)
    if len(parts) == 1 or not parts[1].strip():
        return name.strip(), None
    return parts[1].strip(), parts[0].strip()


def strip_city(address: str) -> str:
    """Drop a trailing 'ALBUQUERQUE, NM 87110' from a feed address."""
    return CITY_SUFFIX_RE.sub("", address.strip())


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
