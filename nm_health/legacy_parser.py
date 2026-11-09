# Copyright (c) 2026 nm_health contributors
"""Parse the two "Activity Date" layouts the city used before late 2025.

Through 2024:

    SAMS CLUB 6672 - 300 EUBANK BLVD NE
      Description - SAMS CLUB 6672 GROCERY (Retail -Grocery)
      Activity Date - 07/15/2021 (Service - ROUTINE FOOD INSPECTION / Result - IN COMPLIANCE / Action - APPROVED
       09 OUT OF COMPLIANCE
        S11 Food in good condition, safe, and unadulterated
          3-101.11 Safe, Unadulterated, and Honestly Presented
          OBSERVED ...

Early 2025 (en dashes, current-style violation headings):

    Taylor Ranch Community Center \u2013 4900 Kachina NW
    Description \u2013Food Service Establishment
    Activity Date \u2013 1/27/2025 Service- HIGH RISK/ Result-IN COMPLIANCE/ Action- APPROVED
    Violation: Maintenance and Operation
    - Good Repair and Proper Adjustment-Equipment
          - 4-501.11
    Observed equipment not maintained in good repair. ...

Neither layout has inspection or permit numbers, so each inspection gets a stable synthetic ID.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from nm_health.model import Inspection, Violation

DASH = "[-\u2013]"
MARKER_RE = re.compile(rf"Activity Date {DASH} ")
ACTIVITY_RE = re.compile(
    rf"Activity Date {DASH} (\d{{1,2}}/\d{{1,2}}/\d{{4}}) \(?Service\s*-\s*(.+?)\s*/\s*Result\s*-\s*(.+?)\s*/\s*"
    r"Action\s*-\s*([^)]+?)\)?\s*$"
)
DESCRIPTION_RE = re.compile(rf"^\s*Description\s*{DASH}\s*(.*)$")
# Name, then the address from the last dash before a street number ("Sheraton ... \u2013 Bar \u2013 2910 Yale Blvd SE").
ESTABLISHMENT_RE = re.compile(rf"^(\S.*) {DASH} (\d.*)$")
ESTABLISHMENT_ANY_RE = re.compile(rf"^(\S.*?) {DASH} (\S.*)$")
TYPE_RE = re.compile(r"\(([^()]*)\)\s*$")
VIOLATION_RE = re.compile(r"^\s*(S\d+\s+.+)$")
VIOLATION_HEADING_RE = re.compile(r"^\s*Violation:\s*(\S.*)$")
DASH_LINE_RE = re.compile(r"^\s*-\s*(\S.*)$")
OBSERVED_RE = re.compile(r"^\s*Observed\b", re.IGNORECASE)
CODE_RE = re.compile(r"^\s*\d-\d{3}\.\d+")  # FDA Food Code section, e.g. 6-501.111
SKIP_RE = re.compile(
    r"^\s*(?:\d+ OUT OF COMPLIANCE|Violations Observed|Page \d+ of \d+"
    r"|Consumer Health Protection Inspections Performed.*|Report amended.*)\s*$",
    re.IGNORECASE,
)
QUIET_RESULTS = frozenset({"IN COMPLIANCE", "NOT APPLICABLE"})
SLUG_RE = re.compile(r"[^a-z0-9]+")


def is_legacy(text: str) -> bool:
    """True for either "Activity Date" layout."""
    return MARKER_RE.search(text) is not None


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
    if result.strip().upper() in QUIET_RESULTS or result.strip().title() == status:
        return status
    return f"{status} - {result.strip().title()}"


def _synthetic_id(state: _State, date: str) -> str:
    base = SLUG_RE.sub("-", f"{state.name} {state.address}".lower()).strip("-")
    key = f"legacy-{date}-{base}"
    state.seen_ids[key] = state.seen_ids.get(key, 0) + 1
    count = state.seen_ids[key]
    return key if count == 1 else f"{key}-{count}"


def _split_establishment(line: str) -> tuple[str, str] | None:
    found = ESTABLISHMENT_RE.match(line) or ESTABLISHMENT_ANY_RE.match(line)
    return (found[1].strip(), found[2].strip()) if found else None


def _on_establishment(state: _State, line: str) -> None:
    split = _split_establishment(line.strip())
    if split is None:
        return
    (state.name, state.address), state.permit_type = split, None


def _on_description(state: _State, line: str) -> None:
    found = DESCRIPTION_RE.match(line)
    rest = found[1].strip() if found else ""
    in_parens = TYPE_RE.search(rest)
    state.permit_type = (in_parens[1].strip() if in_parens else rest) or None


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


def _open_violation(state: _State, category: str) -> None:
    draft = state.current()
    if draft is None:
        return
    draft.violations.append(Violation(category=" ".join(category.split()), item="", rule="", observation=""))


def _on_violation(state: _State, line: str) -> None:
    """A 2024-style 'S36 Insects, rodents, ...' line."""
    _open_violation(state, line)


def _on_violation_heading(state: _State, line: str) -> None:
    """A 2025-style 'Violation: Pest Control' line."""
    found = VIOLATION_HEADING_RE.match(line)
    if found is not None:
        _open_violation(state, found[1])


def _last_violation(state: _State) -> _Draft | None:
    draft = state.current()
    return draft if draft is not None and draft.violations else None


def _on_code(draft: _Draft, text: str) -> None:
    """An FDA code line: the item of the current violation, or a new item under the same category."""
    last = draft.violations[-1]
    if not last.item:
        draft.violations[-1] = replace(last, item=text)
        return
    draft.violations.append(Violation(category=last.category, item=text, rule="", observation=""))


def _on_dash(state: _State, line: str) -> None:
    """2025-style '- item', '- 4-501.11' and '- rule text' lines."""
    draft = _last_violation(state)
    found = DASH_LINE_RE.match(line)
    if draft is None or found is None:
        return
    text, last = " ".join(found[1].split()), draft.violations[-1]
    if not last.item:
        draft.violations[-1] = replace(last, item=text)
    elif CODE_RE.match(text):
        draft.violations[-1] = replace(last, item=f"{text} {last.item}")
    else:
        draft.violations[-1] = replace(last, rule=f"{last.rule} {text}".strip())


def _on_text(state: _State, line: str) -> None:
    """Free text: an FDA code item, rule text continuing, or the inspector's observation."""
    draft = _last_violation(state)
    if draft is None:
        return
    text = " ".join(line.split())
    if CODE_RE.match(line):
        _on_code(draft, text)
        return
    last = draft.violations[-1]
    if last.rule and not last.observation and not OBSERVED_RE.match(line):
        draft.violations[-1] = replace(last, rule=f"{last.rule} {text}")
        return
    draft.violations[-1] = replace(last, observation=f"{last.observation} {text}".strip())


LINE_HANDLERS: tuple[tuple[re.Pattern[str], Callable[[_State, str], None]], ...] = (
    (DESCRIPTION_RE, _on_description),
    (MARKER_RE, _on_activity),
    (VIOLATION_RE, _on_violation),
    (VIOLATION_HEADING_RE, _on_violation_heading),
    (DASH_LINE_RE, _on_dash),
)


def _looks_like_header(line: str) -> bool:
    """Establishment headers start at column 0 as 'NAME - ADDRESS'."""
    return bool(line[:1].strip()) and not MARKER_RE.search(line) and _split_establishment(line.strip()) is not None


def _header_lines(lines: list[str]) -> set[int]:
    """Indexes of establishment header lines: the last non-blank line before a Description line, if header-shaped.

    One establishment can list several Description/Activity pairs (Costco: food court, bakery, deli).
    """
    headers: set[int] = set()
    previous = -1
    for index, line in enumerate(lines):
        if DESCRIPTION_RE.match(line) and previous >= 0 and _looks_like_header(lines[previous]):
            headers.add(previous)
        if line.strip():
            previous = index
    return headers


def _handle(state: _State, line: str) -> None:
    for pattern, handler in LINE_HANDLERS:
        if pattern.search(line):
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
