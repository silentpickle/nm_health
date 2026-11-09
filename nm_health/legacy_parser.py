# Copyright (c) 2026 nm_health contributors
"""Parse the report layout the city used through 2024.

    SAMS CLUB 6672 - 300 EUBANK BLVD NE
      Description - SAMS CLUB 6672 GROCERY (Retail -Grocery)
      Activity Date - 07/15/2021 (Service - ROUTINE FOOD INSPECTION / Result - IN COMPLIANCE / Action - APPROVED
       09 OUT OF COMPLIANCE
        S11 Food in good condition, safe, and unadulterated
          3-101.11 Safe, Unadulterated, and Honestly Presented
          OBSERVED ...

That layout has no inspection or permit numbers, so each inspection gets a stable synthetic ID.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from nm_health.model import Inspection, Violation

MARKER = "Activity Date - "
DESCRIPTION = "Description -"
ACTIVITY_RE = re.compile(
    r"Activity Date - (\d{2}/\d{2}/\d{4}) \(Service - (.+?) / Result - (.+?) / Action - ([^)]+?)\)?\s*$"
)
ESTABLISHMENT_RE = re.compile(r"^(\S.*?) - (\S.*)$")
TYPE_RE = re.compile(r"\(([^()]*)\)\s*$")
VIOLATION_RE = re.compile(r"^\s*(S\d+\s+.+)$")
CODE_RE = re.compile(r"^\s*\d-\d{3}\.\d+")  # FDA Food Code section, e.g. 6-501.111
SKIP_RE = re.compile(
    r"^\s*(?:\d+ OUT OF COMPLIANCE|Page \d+ of \d+|Consumer Health Protection Inspections Performed.*|Report amended.*)\s*$",
    re.IGNORECASE,
)
QUIET_RESULTS = frozenset({"IN COMPLIANCE", "NOT APPLICABLE"})
SLUG_RE = re.compile(r"[^a-z0-9]+")


def is_legacy(text: str) -> bool:
    """True for the pre-2025 layout."""
    return MARKER in text


@dataclass
class _Draft:
    """An inspection being assembled."""

    inspection: Inspection
    violations: list[Violation] = field(default_factory=list)


@dataclass
class _State:
    """Parser state while walking the lines of one report."""

    report_file: str
    name: str = ""
    address: str = ""
    permit_type: str | None = None
    page: int = 1
    drafts: list[_Draft] = field(default_factory=list)
    seen_ids: dict[str, int] = field(default_factory=dict)

    def current(self) -> _Draft | None:
        return self.drafts[-1] if self.drafts else None


def _iso(us_date: str) -> str:
    return datetime.strptime(us_date, "%m/%d/%Y").replace(tzinfo=UTC).date().isoformat()


def _status(result: str, action: str) -> str:
    status = action.strip().title()
    if result.strip().upper() in QUIET_RESULTS:
        return status
    return f"{status} - {result.strip().title()}"


def _synthetic_id(state: _State, date: str) -> str:
    base = SLUG_RE.sub("-", f"{state.name} {state.address}".lower()).strip("-")
    key = f"legacy-{date}-{base}"
    state.seen_ids[key] = state.seen_ids.get(key, 0) + 1
    count = state.seen_ids[key]
    return key if count == 1 else f"{key}-{count}"


def _on_establishment(state: _State, line: str) -> None:
    found = ESTABLISHMENT_RE.match(line.strip())
    if found is None:
        return
    state.name, state.address, state.permit_type = found[1].strip(), found[2].strip(), None


def _on_description(state: _State, line: str) -> None:
    found = TYPE_RE.search(line)
    state.permit_type = found[1].strip() if found else None


def _on_activity(state: _State, line: str) -> None:
    found = ACTIVITY_RE.search(line)
    if found is None:
        return
    date = _iso(found[1])
    inspection = Inspection(
        inspection_id=_synthetic_id(state, date),
        date=date,
        kind=found[2].strip().title(),
        status=_status(found[3], found[4]),
        name=state.name,
        address=state.address,
        permit_number=None,
        permit_type=state.permit_type,
        report_file=state.report_file,
        page=state.page,
    )
    state.drafts.append(_Draft(inspection))


def _on_violation(state: _State, line: str) -> None:
    draft = state.current()
    if draft is None:
        return
    draft.violations.append(Violation(category=" ".join(line.split()), item="", rule="", observation=""))


def _on_code(draft: _Draft, text: str) -> None:
    """An FDA code line: the item of the current violation, or a new item under the same category."""
    last = draft.violations[-1]
    if not last.item:
        draft.violations[-1] = replace(last, item=text)
        return
    draft.violations.append(Violation(category=last.category, item=text, rule="", observation=""))


def _on_text(state: _State, line: str) -> None:
    draft = state.current()
    if draft is None or not draft.violations:
        return
    text = " ".join(line.split())
    if CODE_RE.match(line):
        _on_code(draft, text)
        return
    last = draft.violations[-1]
    joined = f"{last.observation} {text}" if last.observation else text
    draft.violations[-1] = replace(last, observation=joined)


LINE_HANDLERS: tuple[tuple[Callable[[str], bool], Callable[[_State, str], None]], ...] = (
    (lambda line: line.strip().startswith(DESCRIPTION), _on_description),
    (lambda line: MARKER in line, _on_activity),
    (lambda line: VIOLATION_RE.match(line) is not None, _on_violation),
)


def _looks_like_header(line: str) -> bool:
    """Establishment headers start at column 0 as 'NAME - ADDRESS'."""
    return bool(line[:1].strip()) and MARKER not in line and ESTABLISHMENT_RE.match(line.strip()) is not None


def _header_lines(lines: list[str]) -> set[int]:
    """Indexes of establishment header lines: the last non-blank line before a Description line, if header-shaped.

    One establishment can list several Description/Activity pairs (Costco: food court, bakery, deli).
    """
    headers: set[int] = set()
    previous = -1
    for index, line in enumerate(lines):
        if line.strip().startswith(DESCRIPTION) and previous >= 0 and _looks_like_header(lines[previous]):
            headers.add(previous)
        if line.strip():
            previous = index
    return headers


def _handle(state: _State, line: str) -> None:
    for matches, handler in LINE_HANDLERS:
        if matches(line):
            handler(state, line)
            return
    _on_text(state, line)


def _walk(state: _State, lines: list[str], pages: list[int]) -> None:
    headers = _header_lines(lines)
    for index, line in enumerate(lines):
        state.page = pages[index]
        if not line.strip() or SKIP_RE.match(line):
            continue
        if index in headers:
            _on_establishment(state, line)
            continue
        _handle(state, line)


def parse_legacy(text: str, report_file: str) -> list[Inspection]:
    """Every inspection in a pre-2025 report's text (pages separated by form feeds)."""
    lines: list[str] = []
    pages: list[int] = []
    for page_number, page in enumerate(text.split("\f"), start=1):
        page_lines = page.split("\n")
        lines.extend(page_lines)
        pages.extend([page_number] * len(page_lines))
    state = _State(report_file=report_file)
    _walk(state, lines, pages)
    return [replace(d.inspection, violations=tuple(d.violations)) for d in state.drafts]
