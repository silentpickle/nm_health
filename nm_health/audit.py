# Copyright (c) 2026 nm_health contributors
"""Check the site's assumptions against the city's own records, and report where they disagree.

Each check is one small function that asks one question of the real archive and status feed, and returns how many
cases it looked at and the ones that disagree (docs/assumptions.md lists the assumptions). The audit reports; it
never fails the build, because the city's records disagree with themselves now and then and a person has to judge.

The PDF's permit lines ("Food Establishment (Permit # - PT0156723) - Operational Status - Open") are read straight from
the text here, not through the parser, which fills a missing status with "Open": the audit needs the city's words.
"""

import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime

from nm_health.feed import FeedRecord, load_records
from nm_health.model import Inspection
from nm_health.rebuild import rebuild, report_text
from nm_health.settings import Settings
from nm_health.signals import FOLLOW_UP_WORD, chronological, is_closed, is_open, is_red, permit_of
from nm_health.viewmodel import Place, group_places

EXAMPLES_MAX = 8  # disagreements printed per check
PDF_DATE_FORMAT = "%m/%d/%Y"
CLOSED_WORD = "closed"
MIDNIGHT = "00:00"  # a feed time of exactly midnight is likely a placeholder, not when the inspector arrived
YEAR_LEN = len("2026")
PERMIT_LINE = re.compile(
    r"\(Permit\s*#\s*-\s*(?P<permit>[A-Za-z0-9]+)\)\s*-\s*Operational\s*Status\s*[-\u2013]\s*(?P<state>[A-Za-z]+)",
    re.IGNORECASE,
)
# Any other non-blank line (a page header, the next place's name) ends a permit's rows: rows that continue after a
# page break are dropped rather than filed under the wrong permit.
ROW_LINE = re.compile(r"^\s*(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<id>[A-Za-z0-9-]+)\s+.+?\s(?:Pg\.|Page)\s*\d+\s*$")


@dataclass(frozen=True)
class PermitBlock:
    """One permit's line in a weekly report's summary table and the inspections listed under it."""

    report: str
    permit: str
    state: str  # the city's Operational Status: "Open" or "Closed"
    rows: tuple[tuple[str, str], ...]  # (inspection ID, ISO date), the key rebuild uses

    @property
    def closed(self) -> bool:
        """The city lists the permit as closed."""
        return self.state.lower() == CLOSED_WORD


@dataclass(frozen=True)
class AuditData:
    """Everything the checks read: rebuilt inspections, places, the PDFs' permit blocks and the feed."""

    inspections: tuple[Inspection, ...]
    places: list[Place]
    blocks: tuple[PermitBlock, ...]
    feed: tuple[FeedRecord, ...]


@dataclass(frozen=True)
class CheckResult:
    """How many cases a check looked at, how they split, and the ones that disagree."""

    name: str
    question: str
    checked: int
    disagreements: tuple[str, ...]
    tally: tuple[tuple[str, int], ...] = ()


# ---------- Reading permit blocks ----------


def _iso(pdf_date: str) -> str:
    return datetime.strptime(pdf_date, PDF_DATE_FORMAT).date().isoformat()  # noqa: DTZ007 - a calendar date


def _close(block: PermitBlock | None, found: list[PermitBlock]) -> None:
    if block is not None and block.rows:
        found.append(block)


def permit_blocks(text: str, report: str) -> list[PermitBlock]:
    """Every permit line in a report's summary table with the inspection rows that follow it."""
    found: list[PermitBlock] = []
    block: PermitBlock | None = None
    for line in text.splitlines():
        permit, row = PERMIT_LINE.search(line), ROW_LINE.match(line)
        if row and block is not None:
            block = PermitBlock(report, block.permit, block.state, (*block.rows, (row["id"], _iso(row["date"]))))
            continue
        if line.strip() and not row:
            _close(block, found)
            block = PermitBlock(report, permit["permit"], permit["state"], ()) if permit else None
    _close(block, found)
    return found


# ---------- Checks ----------


def _by_key(inspections: Iterable[Inspection]) -> dict[tuple[str, str], Inspection]:
    return {(i.inspection_id, i.date): i for i in inspections}


def _label(inspection: Inspection) -> str:
    time = f" {inspection.time}" if inspection.time else ""
    return f"{inspection.date}{time} {inspection.status}"


def _key(inspection: Inspection) -> tuple[str, str]:
    return (inspection.inspection_id, inspection.date)


def _places_by_key(places: list[Place]) -> dict[tuple[str, str], Place]:
    return {_key(i): place for place in places for i in place.inspections}


def _reopening_after(place: Place | None, inspection: Inspection) -> Inspection | None:
    """The first open result the place had after this inspection, if any is on record."""
    if place is None:
        return None
    ordered = chronological(place.inspections)
    keys = [_key(i) for i in ordered]
    if _key(inspection) not in keys:
        return None
    return next((i for i in ordered[keys.index(_key(inspection)) + 1 :] if is_open(i.status)), None)


def _status_disagreement(block: PermitBlock, latest: Inspection, place: Place | None) -> str:
    line = f"{block.report} permit {block.permit}: city says {block.state}; latest listed {_label(latest)}"
    later = _reopening_after(place, latest) if not block.closed else None
    if later is None:
        return line
    return f"{line}; reopened {_label(later)} on record (the PDF may have been generated after that)"


def check_operational_status(data: AuditData) -> CheckResult:
    """Does 'only a Closure means closed' match the city's Open/Closed for each permit?"""
    known = _by_key(data.inspections)
    places = _places_by_key(data.places)
    tally: dict[str, int] = defaultdict(int)
    disagree: list[str] = []
    for block in data.blocks:
        listed = tuple(known[key] for key in block.rows if key in known)
        if not listed:
            continue
        latest = chronological(listed)[-1]
        tally[f"latest {latest.status} -> city says {block.state}"] += 1
        if is_closed(latest.status) != block.closed:
            disagree.append(_status_disagreement(block, latest, places.get(_key(latest))))
    return CheckResult(
        "operational_status",
        "Only a Closure means closed (the PDF's Operational Status per permit)",
        sum(tally.values()),
        tuple(disagree),
        tuple(sorted(tally.items())),
    )


def _same_day(place: Place) -> list[list[Inspection]]:
    days: dict[str, list[Inspection]] = defaultdict(list)
    for inspection in place.inspections:
        days[inspection.date].append(inspection)
    return [group for group in days.values() if len(group) > 1]


def _same_day_groups(places: list[Place]) -> Iterator[tuple[Place, list[Inspection]]]:
    """Every day on which a place had more than one inspection."""
    return ((place, group) for place in places for group in _same_day(place))


def _is_follow_up(inspection: Inspection) -> bool:
    return FOLLOW_UP_WORD in inspection.kind.lower()


def _follow_up_verdict(follow_up: Inspection, group: list[Inspection]) -> tuple[str, str | None]:
    """(tally label, the latest other time when the follow-up came before it)."""
    others = [i.time for i in group if not _is_follow_up(i) and i.time]
    if follow_up.time is None or not others:
        return "no feed time for one side: order can't be checked", None
    if follow_up.time >= max(others):
        return "timed, after the others", None
    return "timed, before another", max(others)


def check_follow_up_order(data: AuditData) -> CheckResult:
    """Does a corrective-action visit come after that day's other inspections, when the feed times both?"""
    tally: dict[str, int] = defaultdict(int)
    disagree: list[str] = []
    cases = ((place, f, group) for place, group in _same_day_groups(data.places) for f in group if _is_follow_up(f))
    for place, follow_up, group in cases:
        label, later = _follow_up_verdict(follow_up, group)
        tally[label] += 1
        if later is not None:
            disagree.append(f"{place.name}: {_label(follow_up)} before {later}")
    return CheckResult(
        "follow_up_order",
        "An untimed corrective-action visit came after that day's routine inspection",
        sum(tally.values()),
        tuple(disagree),
        tuple(sorted(tally.items())),
    )


def _moments(place: Place) -> list[list[Inspection]]:
    """The place's timed inspections that share a minute and include both a failure and something else."""
    moments: dict[tuple[str, str], list[Inspection]] = defaultdict(list)
    for inspection in place.inspections:
        if inspection.time:
            moments[(inspection.date, inspection.time)].append(inspection)
    return [group for group in moments.values() if len({is_red(i.status) for i in group}) > 1]


def _permit_verdict(group: list[Inspection]) -> str:
    permits = [permit_of(i) for i in group]
    if None in permits:
        return "permit not known for every record"
    return "different permits" if len(set(permits)) == len(permits) else "same permit"


def check_same_minute(data: AuditData) -> CheckResult:
    """Two results at one minute with a failure among them: are they really separate permits?"""
    tally: dict[str, int] = defaultdict(int)
    disagree: list[str] = []
    for place, group in ((p, g) for p in data.places for g in _moments(p)):
        verdict = _permit_verdict(group)
        tally[verdict] += 1
        if verdict != "different permits":
            disagree.append(f"{verdict}: {place.name}: " + " / ".join(_label(i) for i in group))
    return CheckResult(
        "same_minute",
        "Results at the same minute (with a failure among them) are separate permits, so the failure stands",
        sum(tally.values()),
        tuple(disagree),
        tuple(sorted(tally.items())),
    )


def _guessed_order(group: list[Inspection]) -> bool:
    """A pass and a failure on one day, and a result (not a follow-up) the feed gives no time for."""
    mixed = len({is_red(i.status) for i in group}) > 1
    return mixed and any(i.time is None and not _is_follow_up(i) for i in group)


def check_untimed_order(data: AuditData) -> CheckResult:
    """Where a same-day order matters and a result has no time, the order is a guess: count those days."""
    tally: dict[str, int] = defaultdict(int)
    disagree: list[str] = []
    for place, group in _same_day_groups(data.places):
        tally["same-day groups"] += 1
        if _guessed_order(group):
            disagree.append(f"{place.name}: " + " / ".join(_label(i) for i in group))
    tally["no feed time (all inspections)"] = sum(i.time is None for i in data.inspections)
    return CheckResult(
        "untimed_order",
        "Same-day pass and failure with no feed time: the failure is assumed to come first",
        tally["same-day groups"],
        tuple(disagree),
        tuple(sorted(tally.items())),
    )


def check_feed_times(data: AuditData) -> CheckResult:
    """Are the feed's times real? A time of exactly midnight is likely a placeholder."""
    timed = [i for i in data.inspections if i.time]
    midnight = [i for i in timed if i.time == MIDNIGHT]
    by_year: dict[str, int] = defaultdict(int)
    for inspection in midnight:
        by_year[f"00:00 in {inspection.date[:YEAR_LEN]}"] += 1
    return CheckResult(
        "feed_times",
        "The feed's start times are real times, not a 00:00 placeholder",
        len(timed),
        tuple(f"{i.name}: {_label(i)}" for i in reversed(midnight)),
        tuple(sorted(by_year.items())),
    )


def _same_words(status: str) -> str:
    return " ".join(status.lower().split())


def check_feed_status(data: AuditData) -> CheckResult:
    """Do the PDF and the feed give the same status for the same inspection?"""
    known = _by_key(i for i in data.inspections if i.has_details)
    checked = 0
    disagree: list[str] = []
    for record in data.feed:
        detailed = known.get((record.number, record.date))
        if detailed is None:
            continue
        checked += 1
        if _same_words(detailed.status) != _same_words(record.status):
            disagree.append(f"{record.name} {record.number} {record.date}: PDF {detailed.status}; feed {record.status}")
    return CheckResult(
        "feed_status",
        "The PDF and the status feed agree on each inspection's status",
        checked,
        tuple(disagree),
    )


CHECKS: tuple[Callable[[AuditData], CheckResult], ...] = (
    check_operational_status,
    check_follow_up_order,
    check_same_minute,
    check_untimed_order,
    check_feed_times,
    check_feed_status,
)


def audit_data(
    inspections: tuple[Inspection, ...], blocks: tuple[PermitBlock, ...], feed: tuple[FeedRecord, ...]
) -> AuditData:
    """Group the inspections into places the way the site does."""
    return AuditData(inspections, group_places(inspections), blocks, feed)


def load(settings: Settings) -> AuditData:
    """The whole archive (every week, not just the site's window), its permit blocks and the whole feed."""
    rebuilt = rebuild(settings)
    blocks = tuple(
        block
        for report in rebuilt.reports
        for block in permit_blocks(report_text(settings.archive_dir / report.file), report.file)
    )
    return audit_data(rebuilt.inspections, blocks, tuple(load_records(settings, date.min)))


def run_checks(data: AuditData) -> list[CheckResult]:
    """Every check, in order."""
    return [check(data) for check in CHECKS]


def report_lines(results: list[CheckResult], today: date) -> list[str]:
    """The audit as plain text: per check, the question, how many disagree, the split, and some examples."""
    lines = [f"Assumption audit, {today.isoformat()}"]
    for result in results:
        lines += ["", f"[{result.name}] {result.question}"]
        lines.append(f"  {len(result.disagreements)} of {result.checked} checked disagree or need a look")
        lines += [f"  {label}: {count}" for label, count in result.tally]
        lines += [f"  - {example}" for example in result.disagreements[:EXAMPLES_MAX]]
        extra = len(result.disagreements) - EXAMPLES_MAX
        if extra > 0:
            lines.append(f"  ... and {extra} more")
    return lines
