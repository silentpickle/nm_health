# Copyright (c) 2026 nm_health contributors
"""What the site shows, as plain values: places, strip cells, coverage and pest lines, and the week's inspections.

Statuses are always the city's own words. Nothing here infers a duration or a clean record from what an inspection
did not cite. Every inspector text the site publishes passes through `redact` (email addresses and phone numbers).
"""

import re
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta

from nm_health.identity import establishment_slug, normalized_address
from nm_health.model import Inspection, Violation
from nm_health.rebuild import Report
from nm_health.signals import (
    ALL_PESTS,
    HEADLINE_PESTS,
    Episode,
    chronological,
    cleared_on,
    closure_episodes,
    is_pass,
    is_red,
)

WEEKS = 52
DAYS_PER_WEEK = 7
WEEK_SPAN_DAYS = 6  # "this week" is the newest inspection date and the six days before it
ARIA_LIST_MAX = 8  # dated statuses spelled out in a strip's accessible name
RECENT_MAX = 3  # dated statuses in a row's phone-width text list
QUOTE_CHARS = 180  # an observation quoted without labelled fields is cut at this length, on a word
MONTH_TICK_LEAD = 3  # no month name over the first columns: it would hang off the left edge
MONTH_TICK_EVERY = 3  # every third month name stays visible on phones
RED_GROUP = "Closure or unsatisfactory"
REDACTED_EMAIL = "[email removed]"
REDACTED_PHONE = "[phone removed]"
ELLIPSIS = "\u2026"
MIDDOT = "\u00b7"
SYNTHETIC_ID_PREFIX = "legacy-"  # made up by legacy_parser; meaningless to readers

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\(?\b\d{3}\)?[-. ]?\d{3}[-. ]\d{4}\b")
QUOTE_LABELS = ("Pest Type", "Pest Condition", "Number of Pests Present", "Location")
QUOTE_INSTRUCTION = re.compile(r"\s+(?:instructed|instruct|advised|discussed)\b.*$", re.IGNORECASE)
# Where the form's stock sentence ends and the labelled fields (shown separately) begin.
LEAD_END = re.compile(r"\s(?:Location|Pest Type|Food Items|Equipment Type|Type of Equipment):")

PEST_LABEL = {
    "roaches": "Roaches",
    "rodents": "Rodents",
    "flies": "Flies",
    "other_pests": "Other pests",
    "pests_unspecified": "Pests, type not stated",
}
STATE_LABEL = {"live": "live", "dead": "dead", "droppings": "droppings", "not_stated": "condition not stated"}
TAG_LABEL = {
    **PEST_LABEL,
    "pest_control": "Pest control",
    "employee_items": "Employee items",
    "food_temperature": "Food temperature",
    "handwashing": "Handwashing",
    "sanitizer": "Sanitizer",
    "date_marking": "Date marking",
    "permit": "Permit",
    "training": "Training",
}
EMPLOYEE_TAG = "employee_items"

# Status levels: r = closure or unsatisfactory, y = conditional, g = approved, n = any other status.
LEVEL_RED, LEVEL_CONDITIONAL, LEVEL_APPROVED, LEVEL_OTHER, LEVEL_NONE = "r", "y", "g", "n", ""
CONDITIONAL_WORD = "conditional"
# A week's cell shows its worst status. Any status outranks "no inspection".
LEVEL_RANK = {LEVEL_NONE: 0, LEVEL_OTHER: 1, LEVEL_APPROVED: 2, LEVEL_CONDITIONAL: 3, LEVEL_RED: 4}
# One character per strip cell (places.json; places.js decodes it with the same table).
# Lowercase: inspector notes on file. Uppercase: status only. Digit: roaches or rodents cited (notes always on file).
NO_INSPECTION_CODE = "."
NOTES_CODES = {LEVEL_APPROVED: "g", LEVEL_CONDITIONAL: "y", LEVEL_RED: "r", LEVEL_OTHER: "n"}
STATUS_ONLY_CODES = {LEVEL_APPROVED: "G", LEVEL_CONDITIONAL: "Y", LEVEL_RED: "R", LEVEL_OTHER: "N"}
PEST_CODES = {LEVEL_APPROVED: "1", LEVEL_CONDITIONAL: "2", LEVEL_RED: "3", LEVEL_OTHER: "0"}
CELL_CLASSES = {
    NO_INSPECTION_CODE: "",
    "g": "g",
    "y": "y",
    "r": "r",
    "n": "n2",
    "G": "g so",
    "Y": "y so",
    "R": "r so",
    "N": "n2 so",
    "1": "g p",
    "2": "y p",
    "3": "r p",
    "0": "n2 p",
}


# ---------- Published text ----------


def redact(text: str) -> str:
    """Inspectors sometimes write their own email or phone into a report; the site doesn't republish them."""
    return PHONE.sub(REDACTED_PHONE, EMAIL.sub(REDACTED_EMAIL, text))


def published(v: Violation) -> Violation:
    """The violation as the site may publish it: observation, rule and every labelled field redacted."""
    return replace(
        v,
        observation=redact(v.observation),
        rule=redact(v.rule),
        details=tuple((label, redact(value)) for label, value in v.details),
    )


def truncate(text: str, limit: int = QUOTE_CHARS) -> str:
    """Text up to `limit` characters, cut on a word with an ellipsis when longer."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + ELLIPSIS


def quote_for(v: Violation) -> str:
    """The inspector's own words about the pests: their labelled pest fields, else the start of the observation."""
    fields = [f"{label}: {QUOTE_INSTRUCTION.sub('', value)}" for label, value in v.details if label in QUOTE_LABELS]
    if fields:
        return redact(f" {MIDDOT} ".join(fields))
    return truncate(redact(v.observation))


def violation_lead(v: Violation) -> str:
    """The observation's opening sentence when its labelled fields are listed separately, else all of it."""
    if not v.details:
        return v.observation
    return LEAD_END.split(v.observation, maxsplit=1)[0]


def violation_title(v: Violation) -> str:
    """The item cited, or the category when the item is missing or repeats it."""
    return v.item if v.item and v.item != v.category else v.category


def report_text(inspection: Inspection) -> str:
    """Everything the report says about an inspection's violations, one paragraph per violation."""
    parts = ("\n".join(p for p in (v.category, v.item, v.rule, v.observation) if p) for v in inspection.violations)
    return "\n\n".join(parts)


# ---------- Dates and numbers ----------


def nice_date(iso: str) -> str:
    """'2026-10-29' -> 'Oct 29, 2026'."""
    day = date.fromisoformat(iso)
    return f"{day:%b} {day.day}, {day.year}"


def short_date(iso: str) -> str:
    """'2026-10-29' -> 'Oct 29'."""
    day = date.fromisoformat(iso)
    return f"{day:%b} {day.day}"


def plural(count: int, one: str, many: str) -> str:
    """'1 inspection', '3 inspections'."""
    return f"{count} {one if count == 1 else many}"


def thousands(count: int) -> str:
    """'1,426'."""
    return f"{count:,}"


# ---------- Places ----------


def level(status: str) -> str:
    """The status's placard level: r (closure/unsatisfactory), y (conditional), g (approved), n (other)."""
    if is_red(status):
        return LEVEL_RED
    if CONDITIONAL_WORD in status.lower():
        return LEVEL_CONDITIONAL
    if is_pass(status):
        return LEVEL_APPROVED
    return LEVEL_OTHER


def has_headline_pest(kinds: tuple[str, ...]) -> bool:
    """Roaches or rodents among the pest tags."""
    return any(kind in HEADLINE_PESTS for kind in kinds)


def cites_headline_pests(inspection: Inspection) -> bool:
    """Any violation in the inspection cites roaches or rodents."""
    return any(has_headline_pest(v.tags) for v in inspection.violations)


def public_id(inspection: Inspection) -> str:
    """The city's inspection number, or '' when the parser had to make one up."""
    return "" if inspection.inspection_id.startswith(SYNTHETIC_ID_PREFIX) else inspection.inspection_id


@dataclass(frozen=True)
class PestCitation:
    """One violation citing pests, as the place page states it."""

    date: str
    kinds: tuple[str, ...]  # pest tags, in ALL_PESTS order
    state: str  # live / dead / droppings / not_stated
    cleared: str | None  # next approved inspection, if any
    quote: str
    index: int  # the inspection's position in the place's timeline (newest first)
    status: str  # the status that day, as issued by the city

    @property
    def headline(self) -> bool:
        """Roaches or rodents."""
        return has_headline_pest(self.kinds)


@dataclass(frozen=True)
class ClosureRun:
    """A closure episode with the status that started it."""

    episode: Episode
    start_status: str


@dataclass(frozen=True)
class Place:
    """Every inspection of one establishment in the window, newest first, with inspector text redacted."""

    slug: str
    name: str
    legal_name: str | None
    address: str
    lat_lng: tuple[float, float] | None
    inspections: tuple[Inspection, ...]
    closures: tuple[ClosureRun, ...]  # oldest first
    pests: tuple[PestCitation, ...]  # newest first

    @property
    def latest(self) -> Inspection:
        """The most recent inspection."""
        return self.inspections[0]

    @property
    def with_notes(self) -> int:
        """How many inspections have inspector notes on file."""
        return sum(i.has_details for i in self.inspections)

    @property
    def headline_pests(self) -> bool:
        """Roaches or rodents cited in any notes on file."""
        return any(p.headline for p in self.pests)

    @property
    def employee_items(self) -> bool:
        """Employee items cited in any notes on file."""
        return any(EMPLOYEE_TAG in v.tags for i in self.inspections for v in i.violations)


def _redacted(inspection: Inspection) -> Inspection:
    return replace(inspection, violations=tuple(published(v) for v in inspection.violations))


def _citations(inspections: tuple[Inspection, ...]) -> tuple[PestCitation, ...]:
    found = [
        PestCitation(
            date=inspection.date,
            kinds=tuple(tag for tag in v.tags if tag in ALL_PESTS),
            state=v.pest_state or "not_stated",
            cleared=cleared_on(inspections, inspection.date),
            quote=quote_for(v),
            index=index,
            status=inspection.status,
        )
        for index, inspection in enumerate(inspections)
        for v in inspection.violations
        if any(tag in ALL_PESTS for tag in v.tags)
    ]
    return tuple(sorted(found, key=lambda c: c.date, reverse=True))


def _closures(inspections: tuple[Inspection, ...]) -> tuple[ClosureRun, ...]:
    def start_status(episode: Episode) -> str:
        return next(i.status for i in inspections if i.date == episode.start and is_red(i.status))

    return tuple(ClosureRun(e, start_status(e)) for e in closure_episodes(inspections))


def _lat_lng(inspections: tuple[Inspection, ...]) -> tuple[float, float] | None:
    return next(((i.lat, i.lng) for i in inspections if i.lat is not None and i.lng is not None), None)


def build_place(slug: str, inspections: list[Inspection]) -> Place:
    """One place from its inspections (any order); newest first, same-day ones by the feed's time."""
    ordered = tuple(_redacted(i) for i in reversed(chronological(tuple(inspections))))
    latest = ordered[0]
    return Place(
        slug=slug,
        name=latest.name,
        legal_name=next((i.legal_name for i in ordered if i.legal_name), None),
        address=normalized_address(latest.address),
        lat_lng=_lat_lng(ordered),
        inspections=ordered,
        closures=_closures(ordered),
        pests=_citations(ordered),
    )


def group_places(inspections: tuple[Inspection, ...]) -> list[Place]:
    """Inspections grouped by place (identity.establishment_slug); most recently inspected first, then by name."""
    by_slug: dict[str, list[Inspection]] = defaultdict(list)
    for inspection in inspections:
        by_slug[establishment_slug(inspection.name, inspection.address)].append(inspection)
    places = [build_place(slug, found) for slug, found in by_slug.items()]
    places.sort(key=lambda p: p.name.casefold())
    places.sort(key=lambda p: p.latest.date, reverse=True)
    return places


# ---------- 52-week strip ----------


@dataclass(frozen=True)
class Cell:
    """One week of the strip: its worst status level, whether only the status is known, and roaches/rodents."""

    level: str = LEVEL_NONE
    status_only: bool = True
    pest: bool = False


def week_index(today: date, iso: str) -> int:
    """Whole weeks between the inspection and today (0 = this week)."""
    return (today - date.fromisoformat(iso)).days // DAYS_PER_WEEK


def _add(cell: Cell, inspection: Inspection) -> Cell:
    worst = level(inspection.status)
    return Cell(
        level=worst if LEVEL_RANK[worst] > LEVEL_RANK[cell.level] else cell.level,
        status_only=cell.status_only and not inspection.has_details,
        pest=cell.pest or cites_headline_pests(inspection),
    )


def strip_cells(inspections: tuple[Inspection, ...], today: date) -> tuple[Cell, ...]:
    """The last 52 weeks, oldest on the left, newest (this week) on the right."""
    cells = [Cell() for _ in range(WEEKS)]
    for inspection in inspections:
        weeks_ago = week_index(today, inspection.date)
        if not 0 <= weeks_ago < WEEKS:
            continue
        column = WEEKS - 1 - weeks_ago
        cells[column] = _add(cells[column], inspection)
    return tuple(cells)


def cell_code(cell: Cell) -> str:
    """One character for the cell (see CELL_CLASSES)."""
    if cell.level == LEVEL_NONE:
        return NO_INSPECTION_CODE
    if cell.pest:
        return PEST_CODES[cell.level]
    return (STATUS_ONLY_CODES if cell.status_only else NOTES_CODES)[cell.level]


def strip_code(cells: tuple[Cell, ...]) -> str:
    """The whole strip as one character per week."""
    return "".join(cell_code(c) for c in cells)


def strip_label(inspections: tuple[Inspection, ...]) -> str:
    """The strip's accessible name: the newest dated statuses, then how many more."""
    listed = "; ".join(f"{nice_date(i.date)}: {i.status}" for i in inspections[:ARIA_LIST_MAX])
    extra = len(inspections) - ARIA_LIST_MAX
    more = f"; and {extra} more" if extra > 0 else ""
    return f"Inspections in the last 52 weeks: {listed}{more}"


def recent_text(inspections: tuple[Inspection, ...]) -> str:
    """The newest dated statuses as one line, for phones where the strip is hidden."""
    return f" {MIDDOT} ".join(f"{short_date(i.date)} {i.status}" for i in inspections[:RECENT_MAX])


def month_ticks(today: date) -> list[tuple[str, bool]]:
    """(month name or '', hidden on phones) for each strip column: a name where a new month starts."""
    ticks: list[tuple[str, bool]] = []
    last_month, shown = 0, 0
    for column in range(WEEKS):
        day = today - timedelta(days=(WEEKS - 1 - column) * DAYS_PER_WEEK)
        fresh, last_month = day.month != last_month, day.month
        if column < MONTH_TICK_LEAD or not fresh:
            ticks.append(("", False))
            continue
        ticks.append((f"{day:%b}", shown % MONTH_TICK_EVERY != 0))
        shown += 1
    return ticks


# ---------- Place page lines ----------


def coverage_line(place: Place) -> str:
    """How many inspections have inspector notes on file; never a claim that the place is pest-free."""
    total = plural(len(place.inspections), "inspection", "inspections")
    if not place.with_notes:
        return f"Inspector notes on file for none of its {total} in this period, so pest citations can't be shown."
    line = f"Inspector notes on file for {place.with_notes} of {total}."
    return line if place.headline_pests else f"{line} None of those notes mention roaches or rodents."


def pest_reading(citation: PestCitation) -> str:
    """This site's reading of the inspector's words, e.g. 'Roaches, live'."""
    kinds = ", ".join(PEST_LABEL[k] for k in citation.kinds if k in HEADLINE_PESTS)
    return f"{kinds}, {STATE_LABEL[citation.state]}"


def other_pest_kinds(citation: PestCitation) -> str:
    """Every pest kind cited, e.g. 'Flies, Other pests'."""
    return ", ".join(PEST_LABEL[k] for k in citation.kinds)


def closure_start(run: ClosureRun) -> str:
    """'Oct 3, 2026: Closure Re-Inspection Required (2 inspections in a row with this kind of result)'."""
    count = run.episode.failed_inspections
    repeat = f" ({count} inspections in a row with this kind of result)" if count > 1 else ""
    return f"{nice_date(run.episode.start)}: {run.start_status}{repeat}"


def closure_end(run: ClosureRun) -> str | None:
    """'Next inspection: Approved, Oct 9, 2026.'; None while no later approved inspection is on record."""
    if run.episode.end is None:
        return None
    return f"Next inspection: {run.episode.end_status}, {nice_date(run.episode.end)}."


def feed_only_text(inspection: Inspection) -> str:
    """What the site can say about an inspection known only from the status feed."""
    count = inspection.violation_count
    number = "an unknown number of" if count is None else str(count)
    noun = "violation" if count == 1 else "violations"
    return (
        "Inspector notes not on file: the weekly report for this date wasn't saved. "
        f"The city's status feed lists {number} {noun}."
    )


def notice_count_text(inspection: Inspection) -> str:
    """A This-week card's line when it isn't quoting pests."""
    if inspection.has_details:
        return plural(len(inspection.violations), "violation listed", "violations listed")
    count = "Unknown number of" if inspection.violation_count is None else str(inspection.violation_count)
    return f"{count} violations (inspector notes not on file)"


def amended_text(inspection: Inspection) -> str | None:
    """A note when a later report changed the status."""
    if inspection.amended_from is None:
        return None
    return f"First reported as \u201c{inspection.amended_from}\u201d; a later report changed it."


def source_label(inspection: Inspection, week_start: str | None) -> str:
    """'Week of Oct 25 report (PDF, p. 3)'."""
    week = f"Week of {short_date(week_start)}" if week_start else "Weekly"
    page = f", p. {inspection.page}" if inspection.page else ""
    return f"{week} report (PDF{page})"


def kind_line(inspection: Inspection) -> str:
    """'Routine Food Establishment Inspection - #12345 - '."""
    parts = [inspection.kind]
    if public_id(inspection):
        parts.append(f"#{public_id(inspection)}")
    return f" {MIDDOT} ".join(parts) + f" {MIDDOT} "


# ---------- Reports and this week ----------


def reports_in_window(reports: tuple[Report, ...], since: date) -> tuple[Report, ...]:
    """Weekly reports that end inside the window."""
    return tuple(r for r in reports if r.week_end and r.week_end >= since.isoformat())


def covering_report(reports: tuple[Report, ...], day: str) -> Report | None:
    """A report whose week includes the day."""
    return next((r for r in reports if r.week_start and r.week_end and r.week_start <= day <= r.week_end), None)


def latest_report(reports: tuple[Report, ...]) -> Report | None:
    """The report with the newest week."""
    dated = [r for r in reports if r.week_end and r.week_start]
    return max(dated, key=lambda r: r.week_end or "", default=None)


Visit = tuple[Place, Inspection]


def visits_between(places: list[Place], first: str, last: str) -> list[Visit]:
    """Every inspection dated first..last, newest first."""
    found = [(p, i) for p in places for i in p.inspections if first <= i.date <= last]
    return sorted(found, key=lambda v: v[1].date, reverse=True)


@dataclass(frozen=True)
class Week:
    """The newest seven days of inspections and where the pest citations come from."""

    start: str
    end: str
    visits: tuple[Visit, ...]
    covered: bool  # an archived weekly report covers the newest date
    pest_report: Report | None  # the report pest citations come from when not covered
    pest_visits: tuple[Visit, ...]

    @property
    def red(self) -> list[Visit]:
        """Closure or unsatisfactory results."""
        return [v for v in self.visits if level(v[1].status) == LEVEL_RED]

    @property
    def other(self) -> list[Visit]:
        """Every other result."""
        return [v for v in self.visits if level(v[1].status) != LEVEL_RED]


def select_week(places: list[Place], reports: tuple[Report, ...]) -> Week | None:
    """The newest 7 days; pest citations from that week if a report covers its newest date, else the latest report."""
    newest = max((p.latest.date for p in places), default=None)
    if newest is None:
        return None
    start = (date.fromisoformat(newest) - timedelta(days=WEEK_SPAN_DAYS)).isoformat()
    visits = visits_between(places, start, newest)
    covered = covering_report(reports, newest) is not None
    report = None if covered else latest_report(reports)
    pest_pool = visits if covered else _report_visits(places, report)
    pests = tuple(v for v in pest_pool if cites_headline_pests(v[1]))
    return Week(start, newest, tuple(visits), covered, report, pests)


def _report_visits(places: list[Place], report: Report | None) -> list[Visit]:
    if report is None or report.week_start is None or report.week_end is None:
        return []
    return visits_between(places, report.week_start, report.week_end)


def notice_quote(place: Place, inspection: Inspection) -> str | None:
    """The inspector's words about roaches or rodents that day, for a This-week card."""
    return next((c.quote for c in place.pests if c.date == inspection.date and c.headline), None)


def unique_places(visits: list[Visit]) -> list[Place]:
    """Each visit's place once, in visit order."""
    seen: dict[str, Place] = {}
    for place, _ in visits:
        seen.setdefault(place.slug, place)
    return list(seen.values())
