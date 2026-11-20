# Copyright (c) 2026 nm_health contributors
"""News links: newspaper write-ups of the city's weekly reports, kept apart from the county archive.

They hold history the archive lacks (weeks whose PDF nobody saved). A news link never supersedes a county report:
an entry is usable only when none of its dates falls in a week an archived PDF covers (``usable_entries``). Each
record is a citation (URL, headline, publication date) plus the facts the article lists: the week, and each place's
color, name, address, dates and results. Never the article's prose. See docs/news-links.md.
"""

import json
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import cast

from nm_health.archive import Week
from nm_health.settings import DAYS_PER_WEEK

GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"
COLORS = (GREEN, YELLOW, RED)
NEW = "NEW"
UPDATED = "UPDATED"
SAME = "same"
WEEK_SPAN = timedelta(days=DAYS_PER_WEEK - 1)  # first day to last day of a week


@dataclass(frozen=True)
class Outcome:
    """One result an article prints for a red-listed place, e.g. "Closure (Nov. 9)"."""

    result: str
    on: date


@dataclass(frozen=True)
class Entry:
    """One place an article lists under GREEN, YELLOW or RED, as printed."""

    color: str
    name: str
    address: str
    # Inspection dates: the parenthesised dates for GREEN and YELLOW, the Result line's dates for RED.
    dates: tuple[date, ...]
    # Notes such as "Class B" printed after the place.
    classes: tuple[str, ...] = ()
    outcomes: tuple[Outcome, ...] = ()


@dataclass(frozen=True)
class NewsLink:
    """One news article: where it is, what week(s) it reports on, and the places it lists."""

    url: str
    # The site's domain without "www.", e.g. "abqjournal.com".
    source: str
    headline: str
    published: date
    author: str
    weeks: tuple[Week, ...]
    entries: tuple[Entry, ...]
    captured_at: str


def _outcome_json(outcome: Outcome) -> dict[str, str]:
    return {"result": outcome.result, "on": outcome.on.isoformat()}


def _entry_json(entry: Entry) -> dict[str, object]:
    return {
        "color": entry.color,
        "name": entry.name,
        "address": entry.address,
        "dates": [day.isoformat() for day in entry.dates],
        "classes": list(entry.classes),
        "outcomes": [_outcome_json(outcome) for outcome in entry.outcomes],
    }


def to_json(link: NewsLink) -> dict[str, object]:
    """The record as written to the links file."""
    return {
        "url": link.url,
        "source": link.source,
        "headline": link.headline,
        "published": link.published.isoformat(),
        "author": link.author,
        "weeks": [{"start": week.start.isoformat(), "end": week.end.isoformat()} for week in link.weeks],
        "entries": [_entry_json(entry) for entry in link.entries],
        "captured_at": link.captured_at,
    }


def _entry_from(data: dict[str, object]) -> Entry:
    outcomes = cast("list[dict[str, str]]", data["outcomes"])
    return Entry(
        color=str(data["color"]),
        name=str(data["name"]),
        address=str(data["address"]),
        dates=tuple(date.fromisoformat(day) for day in cast("list[str]", data["dates"])),
        classes=tuple(cast("list[str]", data["classes"])),
        outcomes=tuple(Outcome(o["result"], date.fromisoformat(o["on"])) for o in outcomes),
    )


def from_json(data: dict[str, object]) -> NewsLink:
    """A record read back from the links file (written by ``to_json``)."""
    weeks = cast("list[dict[str, str]]", data["weeks"])
    return NewsLink(
        url=str(data["url"]),
        source=str(data["source"]),
        headline=str(data["headline"]),
        published=date.fromisoformat(str(data["published"])),
        author=str(data["author"]),
        weeks=tuple(Week(date.fromisoformat(w["start"]), date.fromisoformat(w["end"])) for w in weeks),
        entries=tuple(_entry_from(entry) for entry in cast("list[dict[str, object]]", data["entries"])),
        captured_at=str(data["captured_at"]),
    )


def _order(link: NewsLink) -> tuple[date, str]:
    first = min((week.start for week in link.weeks), default=link.published)
    return first, link.url


def load_links(path: Path) -> list[NewsLink]:
    """Every news link on file, oldest week first; none when the file doesn't exist yet."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return sorted((from_json(json.loads(line)) for line in lines if line.strip()), key=_order)


def save_links(path: Path, links: list[NewsLink]) -> None:
    """Write one JSON line per link, oldest week first, so the file diffs cleanly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [json.dumps(to_json(link), ensure_ascii=False, sort_keys=True) for link in sorted(links, key=_order)]
    path.write_text("".join(row + "\n" for row in rows), encoding="utf-8")


def upsert(links: list[NewsLink], link: NewsLink) -> tuple[list[NewsLink], str]:
    """Add a link, or replace the one with its URL; says NEW, UPDATED, or same (only the capture time differs)."""
    others = [old for old in links if old.url != link.url]
    previous = next((old for old in links if old.url == link.url), None)
    if previous is None:
        return [*others, link], NEW
    if replace(previous, captured_at=link.captured_at) == link:
        return links, SAME
    return [*others, link], UPDATED


def _days(week: Week) -> list[date]:
    return [week.start + timedelta(days=offset) for offset in range((week.end - week.start).days + 1)]


def county_days(manifest: Path) -> frozenset[date]:
    """Every day inside a week an archived county PDF covers (from manifest.jsonl)."""
    covered: set[date] = set()
    if not manifest.exists():
        return frozenset()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("week_start") is None or row.get("week_end") is None:
            continue
        covered.update(_days(Week(date.fromisoformat(row["week_start"]), date.fromisoformat(row["week_end"]))))
    return frozenset(covered)


def unknown_week_files(manifest: Path) -> list[str]:
    """Archived PDFs with no week on file: their days can't count as covered, so check those by hand."""
    if not manifest.exists():
        return []
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    return [str(row["file"]) for row in rows if row.get("week_start") is None]


def week_days(link: NewsLink) -> list[date]:
    """Every day of the week(s) the article reports on."""
    return sorted({day for week in link.weeks for day in _days(week)})


def entry_days(link: NewsLink, entry: Entry) -> list[date]:
    """The entry's own dates; an entry printed with none stands for every day of the article's week(s)."""
    return list(entry.dates) if entry.dates else week_days(link)


def usable_entries(link: NewsLink, county: frozenset[date]) -> list[Entry]:
    """Entries no county report can contradict: none of their days is in a week an archived PDF covers."""
    return [entry for entry in link.entries if not any(day in county for day in entry_days(link, entry))]


def _runs(weeks: list[Week]) -> list[Week]:
    """Back-to-back weeks merged into one span."""
    spans: list[Week] = []
    for week in weeks:
        if spans and week.start - spans[-1].end == timedelta(days=1):
            spans[-1] = Week(spans[-1].start, week.end)
            continue
        spans.append(week)
    return spans


def missing_weeks(links: list[NewsLink], county: frozenset[date]) -> list[Week]:
    """Spans with no county PDF and no news link, from the first news link's week to the last county day."""
    if not links or not county:
        return []
    known = county | {day for link in links for day in week_days(link)}
    start = min(week.start for link in links for week in link.weeks)
    offsets = range(0, (max(county) - start).days + 1, DAYS_PER_WEEK)
    weeks = [Week(start + timedelta(days=offset), start + timedelta(days=offset) + WEEK_SPAN) for offset in offsets]
    return _runs([week for week in weeks if not any(day in known for day in _days(week))])
