# Copyright (c) 2026 nm_health contributors
"""A spot-check packet for any LLM: what the site says about a few places, the city's records for them, and a prompt.

`nm-health spotcheck` prints one Markdown document to paste into a model of your choice ("are we out of our minds?").
Nothing is sent anywhere. Places are sampled so the packet always includes the hard cases (a reopening, a current
closure, pests, several results in one day) plus an ordinary place. Every statement is numbered so the answer can name
it, and the claims are built by the same functions that write the site. Inspector text passes through `redact`.
"""

import random
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from nm_health.feed import FeedRecord, load_records
from nm_health.model import Inspection, Violation
from nm_health.rebuild import rebuild, report_text
from nm_health.settings import ROOT, Settings
from nm_health.signals import is_closed
from nm_health.viewmodel import (
    MIDDOT,
    Coverage,
    Place,
    closed_text,
    closure_end,
    closure_start,
    coverage_line,
    covered_days,
    group_places,
    latest_result_text,
    other_pest_kinds,
    permit_line_text,
    permit_lines,
    pest_reading,
    plural,
    redact,
    reopened_flag,
    stated,
    violation_title,
    when_text,
)

ASSUMPTIONS_DOC = ROOT / "docs" / "assumptions.md"
PAGE_BREAK = "\f"
# Each inspection's details start "Date: 10/28/2026 - #: RT-FOODEST-084243-2026 - Inspection Result: ...", after
# two lines naming the place and its class; the next such header ends them.
DETAIL_HEADER = re.compile(r"^Date: \d{2}/\d{2}/\d{4} - #: (?P<id>\S+) - Inspection Result:", re.MULTILINE)
PLACE_LINES_BEFORE = 2
SUMMARY_MARKER = "Operational Status"  # each permit's line in the summary table, above its rows
PARAGRAPH = re.compile(r"\n\s*\n")
NO_LATER_APPROVAL = "No later approved inspection on record."
PROMPT = """You are spot-checking a small public website that republishes the City of Albuquerque's food-inspection
records. Below are (1) the rules the site uses, (2) for each sampled place, the statements the site makes, numbered,
and (3) the city's own records for that place: the text of the weekly PDF report pages and the rows of the city's
inspection-status feed. Emails and phone numbers were removed from the PDF text.

For every numbered statement, answer SUPPORTED, CONTRADICTED or CAN'T TELL, and quote the source line that decides
it. A table per place is fine: statement, verdict, deciding source line.

Then, briefly:
- Are any of the site's rules wrong or misleading, given these documents?
- Do the sources show anything important about these places that the statements leave out or get backwards?
- Would an ordinary reader of the statements come away believing something the records don't support?

Be specific. Don't explain supported statements at length; spend the words on anything that looks wrong."""


@dataclass(frozen=True)
class Sample:
    """One place in the packet and why it was picked."""

    reason: str
    place: Place


@dataclass(frozen=True)
class Sources:
    """The city's records the packet quotes: report text by report file, and feed rows by (number, date)."""

    reports: dict[str, str]
    feed: dict[tuple[str, str], FeedRecord]
    covered: Coverage = frozenset()  # dates a weekly report on file covers


# ---------- Sampling ----------


def _several_on_one_day(place: Place) -> bool:
    days = Counter(i.date for i in place.inspections)
    return any(count > 1 for count in days.values())


SAMPLES: tuple[tuple[str, Callable[[Place], bool]], ...] = (
    ("reopened after a closure", lambda p: any(s.end for s in p.spells)),
    ("latest result is a closure", lambda p: is_closed(p.latest.status)),
    ("roaches or rodents cited", lambda p: p.headline_pests),
    ("several results on one day", _several_on_one_day),
    ("no closure or unsatisfactory result", lambda p: not p.closures),
)
RANDOM_REASON = "picked at random"


def _with_notes_first(places: list[Place]) -> list[Place]:
    """Places with inspector notes on file, when there are any: their statements can be checked against the PDF."""
    return [p for p in places if p.with_notes] or places


def choose(places: list[Place], count: int, seed: int) -> list[Sample]:
    """One place per hard case (as far as `count` allows), then random places, never the same place twice."""
    rng = random.Random(seed)  # noqa: S311 - sampling for review, not security
    chosen: list[Sample] = []
    for reason, wanted in SAMPLES[:count]:
        eligible = _with_notes_first([p for p in places if wanted(p) and p not in (s.place for s in chosen)])
        if eligible:
            chosen.append(Sample(reason, rng.choice(eligible)))
    rest = [p for p in places if p not in (s.place for s in chosen)]
    extra = rng.sample(rest, min(count - len(chosen), len(rest)))
    return chosen + [Sample(RANDOM_REASON, p) for p in extra]


# ---------- What the site says ----------


def _cited(v: Violation) -> str:
    title = violation_title(v)
    return title if title == v.category else f"{title} ({v.category})"


def _notes(inspection: Inspection) -> str:
    """What the site says it knows about an inspection's violations, naming each one listed."""
    if not inspection.has_details:
        count = inspection.violation_count
        listed = "an unknown number of violations" if count is None else plural(count, "violation", "violations")
        return f"known only from the status feed, which lists {listed}"
    listed = plural(len(inspection.violations), "violation", "violations")
    names = "; ".join(_cited(v) for v in inspection.violations)
    return f"{listed} listed in the weekly report: {names}" if names else f"{listed} listed in the weekly report"


def _timeline_claim(inspection: Inspection) -> str:
    when = when_text(inspection.date, inspection.time)
    return f"Inspection {when}: {inspection.status} ({inspection.kind}); {_notes(inspection)}."


def _closure_claims(place: Place, covered: Coverage) -> list[str]:
    claims: list[str] = []
    for run in place.closures:
        claims.append(f"Closure or unsatisfactory result: {closure_start(run)}.")
        claims += [closed_text(spell, covered) for spell in run.closed]
        claims.append(closure_end(run) or NO_LATER_APPROVAL)
    return claims


def _pest_claims(place: Place) -> list[str]:
    return [
        f'{c.date}: {pest_reading(c) if c.headline else other_pest_kinds(c)}, quoting the inspector: "{c.quote}"'
        for c in place.pests
    ]


def claims(place: Place, covered: Coverage) -> list[str]:
    """Everything the site states about the place, in the order a reader meets it."""
    flag = reopened_flag(place, covered)
    return [
        f"Name and address: {place.name}, {place.address}.",
        *(f"The city's latest weekly report on file lists: {permit_line_text(line)}." for line in permit_lines(place)),
        f"{latest_result_text(place)}.",
        *([f"List flag: {flag}."] if flag else []),
        coverage_line(place),
        *_closure_claims(place, covered),
        *_pest_claims(place),
        *(_timeline_claim(i) for i in place.inspections),
    ]


# ---------- The city's records ----------


def _line_start(text: str, pos: int, lines_back: int) -> int:
    """Where the line `lines_back` lines above the one starting at `pos` begins."""
    for _ in range(lines_back):
        pos = text.rfind("\n", 0, max(pos - 1, 0)) + 1
    return pos


def detail_block(text: str, inspection_id: str) -> str | None:
    """The inspection's details, from the place's name to the next inspection's, across page breaks."""
    headers = list(DETAIL_HEADER.finditer(text))
    index = next((n for n, m in enumerate(headers) if m["id"] == inspection_id), None)
    if index is None:
        return None
    start = _line_start(text, headers[index].start(), PLACE_LINES_BEFORE)
    later = headers[index + 1 :]
    end = _line_start(text, later[0].start(), PLACE_LINES_BEFORE) if later else len(text)
    return text[start:end]


def summary_block(text: str, inspection_id: str) -> str | None:
    """The place's rows in the summary table (permit, Operational Status, every inspection that week)."""
    return next((p for p in PARAGRAPH.split(text) if SUMMARY_MARKER in p and inspection_id in p), None)


def _page(text: str, page: int | None) -> str | None:
    pages = text.split(PAGE_BREAK)
    return pages[page - 1] if page is not None and 0 < page <= len(pages) else None


def excerpts(inspection: Inspection, text: str) -> list[tuple[str, str]]:
    """(heading, report text) for one inspection: its summary rows and details, else its whole recorded page."""
    found = [
        (f"{inspection.report_file}: {title}", block)
        for title, block in (
            ("summary table", summary_block(text, inspection.inspection_id)),
            (f"details of {inspection.inspection_id}", detail_block(text, inspection.inspection_id)),
        )
        if block
    ]
    page = _page(text, inspection.page) if not found else None
    return found or ([(f"{inspection.report_file}: page {inspection.page}", page)] if page else [])


def _pdf_section(place: Place, sources: Sources) -> list[str]:
    wanted = dict.fromkeys(
        excerpt
        for i in place.inspections
        if i.report_file in sources.reports
        for excerpt in excerpts(i, sources.reports[i.report_file])
    )
    lines: list[str] = []
    for heading, block in wanted:
        lines += [f"#### {heading}", "```", redact(block.replace(PAGE_BREAK, "\n").strip()), "```"]
    return lines or ["(No weekly report on file for this place's inspections.)"]


def _feed_line(record: FeedRecord) -> str:
    count = "unknown" if record.violations is None else str(record.violations)
    fields = (
        record.number,
        f"{record.name}, {record.address}",
        f"{record.date} {record.time or '(no time)'}",
        record.kind,
        record.status,
        f"violations: {count}",
    )
    return "- " + f" {MIDDOT} ".join(fields)


def _feed_section(place: Place, sources: Sources) -> list[str]:
    rows = [
        sources.feed[(i.inspection_id, i.date)] for i in place.inspections if (i.inspection_id, i.date) in sources.feed
    ]
    return [_feed_line(r) for r in rows] or ["(No status-feed rows for this place.)"]


# ---------- The packet ----------


def place_section(number: int, sample: Sample, sources: Sources) -> list[str]:
    """One place: why it was picked, its numbered statements, then its records."""
    place = sample.place
    found = claims(place, sources.covered)
    statements = [f"{number}.{n}. {text}" for n, text in enumerate(found, start=1)]
    return [
        f"## Place {number}: {place.name} ({sample.reason})",
        "",
        "### What the site says",
        *statements,
        "",
        "### The city's status feed",
        *_feed_section(place, sources),
        "",
        "### The city's weekly PDF reports",
        *_pdf_section(place, sources),
        "",
    ]


def packet(samples: list[Sample], sources: Sources, seed: int, assumptions: str) -> str:
    """The whole document: prompt, rules, then each place."""
    head = [
        "# Spot-check: does the site say what the city's records say?",
        "",
        f"Sample seed {seed} (rerun with --seed {seed} to get the same places).",
        "",
        PROMPT,
        "",
        "## The site's rules (docs/assumptions.md)",
        "",
        assumptions.strip(),
        "",
    ]
    body = [line for n, sample in enumerate(samples, start=1) for line in place_section(n, sample, sources)]
    return "\n".join(head + body)


def read_assumptions(path: Path = ASSUMPTIONS_DOC) -> str:
    """The assumptions doc, quoted into the packet so the model sees the rules it is judging."""
    return path.read_text(encoding="utf-8")


def build(settings: Settings, since: date, count: int, seed: int) -> str:
    """Sample places the site states (weekly reports on file only) and gather their PDF pages and feed rows."""
    rebuilt = rebuild(settings, since)
    places = group_places(stated(rebuilt.inspections, rebuilt.reports))
    samples = choose(places, count, seed)
    files = sorted({i.report_file for s in samples for i in s.place.inspections if i.report_file})
    sources = Sources(
        reports={f: report_text(settings.archive_dir / f) for f in files},
        feed={(r.number, r.date): r for r in load_records(settings, since)},
        covered=covered_days(rebuilt.reports),
    )
    return packet(samples, sources, seed, read_assumptions())
