import re  # noqa: CPY001, D100, I001
from typing import Dict, Any, Optional  # noqa: UP035

QUADRANTS = {"NE", "NW", "SE", "SW"}

STREET_TYPES = {
    "AVENUE": "AVE",
    "AVE": "AVE",
    "BOULEVARD": "BLVD",
    "BLVD": "BLVD",
    "STREET": "ST",
    "ST": "ST",
    "ROAD": "RD",
    "RD": "RD",
    "DRIVE": "DR",
    "DR": "DR",
    "LANE": "LN",
    "LN": "LN",
    "COURT": "CT",
    "CT": "CT",
    "PLACE": "PL",
    "PL": "PL",
    "WAY": "WAY",
    "FREEWAY": "FWY",
    "FWY": "FWY",
    "CIRCLE": "CIR",
    "CIR": "CIR",
    "HIGHWAY": "HWY",
    "HWY": "HWY",
    "TRAIL": "TRL",
    "TRL": "TRL",
    "PARKWAY": "PKWY",
    "PKWY": "PKWY",
}


def clean_text(s: Optional[str]) -> str:  # noqa: D103, UP045
    if not s:
        return ""
    # Replace multiple whitespaces and trim
    return re.sub(r"\s+", " ", s).strip()


def normalize_establishment_name(name: str) -> str:
    """Normalize restaurant name for consistent matching."""
    name = clean_text(name).upper()
    # Strip trailing punctuation
    name = re.sub(r"[\.,\-]+$", "", name).strip()
    return name  # noqa: RET504


def normalize_address(raw_address: str) -> Dict[str, Any]:  # noqa: UP006
    """
    Parses and normalizes Albuquerque addresses.
    Examples:
      '1700 TOWNE CENTER LN SE' -> street_num='1700', street_name='TOWNE CENTER LN', quad='SE'
      '1415 4TH ST SW, H' -> street_num='1415', street_name='4TH ST', quad='SW', unit='H'
      '1405 N RENAISSANCE NE, A-B' -> unit='A-B', quad='NE'
      '5701 Gibson BLVD SE' -> street_num='5701', street_name='GIBSON BLVD', quad='SE'
    """  # noqa: D205, D212, D411, D415
    raw = clean_text(raw_address).upper()
    unit = ""

    # Extract unit/suite after comma or # or STE/SUITE
    unit_match = re.search(r"(?:,\s*|\s+#|\s+STE\.?\s*|\s+SUITE\s*)([A-Z0-9\-]+)$", raw, re.IGNORECASE)
    if unit_match:
        unit = unit_match.group(1).strip()
        base = raw[: unit_match.start()].strip()
    else:
        base = raw

    # Detect quadrant (NE, NW, SE, SW)
    tokens = base.split()
    quad = ""
    if tokens and tokens[-1] in QUADRANTS:
        quad = tokens.pop()

    # Normalize street tokens
    norm_tokens = []
    street_num = ""
    if tokens and re.match(r"^\d+[\-A-Za-z0-9]*$", tokens[0]):
        street_num = tokens.pop(0)

    for tok in tokens:
        clean_tok = tok.rstrip(".,")
        if clean_tok in STREET_TYPES:
            norm_tokens.append(STREET_TYPES[clean_tok])
        else:
            norm_tokens.append(clean_tok)

    street_name = " ".join(norm_tokens)

    # Reassemble canonical normalized address
    parts = []
    if street_num:
        parts.append(street_num)
    if street_name:
        parts.append(street_name)
    if quad:
        parts.append(quad)

    canonical_street = " ".join(parts)
    full_normalized = f"{canonical_street}, Unit {unit}" if unit else canonical_street

    # Generate a canonical slug for ID lookups (e.g. 1415-4th-st-sw)
    slug = re.sub(r"[^a-z0-9]+", "-", full_normalized.lower()).strip("-")

    return {
        "raw_address": raw_address.strip(),
        "normalized_address": full_normalized,
        "street_number": street_num,
        "street_name": street_name,
        "quadrant": quad,
        "unit": unit,
        "city": "Albuquerque",
        "state": "NM",
        "slug": slug,
    }
