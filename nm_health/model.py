# Copyright (c) 2026 nm_health contributors
"""One inspection record shape for every report format the city has used."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Violation:
    """One cited item."""

    category: str
    item: str
    rule: str
    observation: str
    tags: tuple[str, ...] = ()
    # Pest evidence state when a pest tag applies: "live", "dead", "droppings" or "not_stated".
    pest_state: str | None = None
    # Labelled fields the inspector filled in, in order, e.g. (("Pest Type", "Cockroaches"), ("Location", "...")).
    details: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Inspection:
    """One inspection as one weekly report states it."""

    inspection_id: str
    date: str  # ISO yyyy-mm-dd
    kind: str
    status: str
    name: str
    address: str
    permit_number: str | None
    permit_type: str | None
    report_file: str
    page: int | None
    violations: tuple[Violation, ...] = field(default_factory=tuple)
    # Legal name when `name` is a DBA ("Long Cao LLC" for "Dragon Sushi").
    legal_name: str | None = None
    # False for inspections known only from the city's status feed: status and counts, no violation text.
    has_details: bool = True
    # Count reported by the status feed; for detailed inspections len(violations) is authoritative.
    violation_count: int | None = None
    lat: float | None = None
    lng: float | None = None
    # The status an earlier report gave before a later (amended) report changed it.
    amended_from: str | None = None
