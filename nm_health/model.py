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
