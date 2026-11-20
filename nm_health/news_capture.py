# Copyright (c) 2026 nm_health contributors
"""Read a page the browser extension saved (tools/news-capture) into a ``NewsLink``.

The capture holds the page's citation (URL, headline, publication time, author) and the article body's lines. Only
facts are kept: the week line ("Nov. 8-14"), each place listed under GREEN / YELLOW / RED ("Name, address (Nov. 12)"
with any "(Class B)" note) and each red-listed place's "Result:" line. Narrative paragraphs are dropped.
"""

import calendar
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlparse

from nm_health.archive import Week
from nm_health.news import COLORS, RED, Entry, NewsLink, Outcome

CAPTURE_KIND = "nm-health-news/1"
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS = {name: number for number, name in enumerate(MONTH_NAMES, start=1)}
MONTH_ABBREVIATION_LEN = 3
EN_DASH = "\u2013"
MONTH = r"((?:" + "|".join(MONTH_NAMES) + r")[a-z]*)\.?"
# "Nov. 8-14", "Nov. 30-Dec. 6", "Dec. 28-Jan. 3": groups are month, day, end month (optional), end day.
WEEK_LINE = re.compile(rf"^{MONTH} (\d{{1,2}}) ?[-{EN_DASH}] ?(?:{MONTH} )?(\d{{1,2}})$")
# Dates inside parentheses: "Nov. 12", "Nov. 12, 13"; a bare day keeps the month before it.
MONTH_DAY = re.compile(rf"(?:{MONTH}\s+)?(\d{{1,2}})\b")
TRAILING_PARENS = re.compile(r"\s*\(([^()]*)\)$")
HEAD_WITH_NUMBER = re.compile(r"^(.+?), (\d.*)$")
HEAD_ANY = re.compile(r"^(.+?), (.+)$")
OUTCOME = re.compile(rf"^(.+?)\s*\(({MONTH}\s+\d{{1,2}})\)$")
ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
RESULT_PREFIX = "Result:"
NONE_LINE = "NONE"
CLASS_PREFIX = "Class"
WWW = "www."
NOT_AN_OBJECT = "not a news capture (expected a JSON object)"
REQUIRED_TEXT = ("url", "headline", "published")
WARNING_CHARS = 80  # of a skipped line, quoted in a warning


@dataclass(frozen=True)
class _Head:
    name: str
    address: str
    classes: tuple[str, ...]
    dates_text: tuple[str, ...]


@dataclass
class _Walk:
    """Where the walk through the article's lines is: the current week and list, and a red place awaiting Result."""

    published: date
    week: Week | None = None
    color: str = ""
    pending: _Head | None = None
    weeks: list[Week] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _safe_date(year: int, month: int, day: int) -> date | None:
    if not 1 <= month <= len(MONTH_NAMES) or not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    return date(year, month, day)


def _iso_date(text: str) -> date | None:
    match = ISO_DATE.match(text)
    if match is None:
        return None
    return _safe_date(int(match[1]), int(match[2]), int(match[3]))


def _month(name: str) -> int:
    return MONTHS[name[:MONTH_ABBREVIATION_LEN]]


def week_from_line(line: str, published: date) -> Week | None:
    """The week a line like "Nov. 8-14" names: the latest such week ending on or before the publication date."""
    match = WEEK_LINE.match(line)
    if match is None:
        return None
    start_month, start_day, end_day = _month(match[1]), int(match[2]), int(match[4])
    end_month = _month(match[3]) if match[3] else start_month
    end = _safe_date(published.year, end_month, end_day)
    if end is not None and end > published:
        end = _safe_date(published.year - 1, end_month, end_day)
    if end is None:
        return None
    start_year = end.year if start_month <= end_month else end.year - 1
    start = _safe_date(start_year, start_month, start_day)
    return Week(start, end) if start is not None and start <= end else None


def resolve_day(month: int, day: int, week: Week) -> date | None:
    """A month and day printed without a year, placed in the year that puts it nearest the article's week."""
    years = (week.end.year - 1, week.end.year, week.end.year + 1)
    candidates = [found for year in years if (found := _safe_date(year, month, day)) is not None]
    return min(candidates, key=lambda found: abs((found - week.start).days), default=None)


def _dates(text: str, week: Week) -> list[date] | None:
    """Dates in text like "Nov. 12, 13", or None when one of them isn't a real day."""
    found: list[date] = []
    month = 0
    for match in MONTH_DAY.finditer(text):
        month = _month(match[1]) if match[1] else month
        day = resolve_day(month, int(match[2]), week) if month else None
        if day is None:
            return None
        found.append(day)
    return sorted(set(found))


def _split_head(text: str) -> tuple[str, str]:
    """Name and address: split before the first number after a comma ("Kenric Inc., 2000 Gibson SE")."""
    match = HEAD_WITH_NUMBER.match(text) or HEAD_ANY.match(text)
    if match is None:
        return text, ""
    return match[1].strip(), match[2].strip()


def parse_head(line: str) -> _Head:
    """A place line: "Name, address (Nov. 12) (Class B, Class C)", parentheses peeled off from the end."""
    rest = line.strip()
    classes: list[str] = []
    dates_text: list[str] = []
    while (match := TRAILING_PARENS.search(rest)) is not None:
        inside = match[1].strip()
        if inside.startswith(CLASS_PREFIX):
            classes[:0] = [note.strip() for note in inside.split(",")]
        else:
            dates_text.insert(0, inside)
        rest = rest[: match.start()]
    name, address = _split_head(rest)
    return _Head(name, address, tuple(classes), tuple(dates_text))


def looks_like_place(line: str) -> bool:
    """A place line has a comma before its address and is not a sentence (no closing period)."""
    return HEAD_ANY.match(line) is not None and not line.endswith(".")


def _listed_line(walk: _Walk, week: Week, line: str) -> None:
    """A GREEN or YELLOW place: kept when its parentheses hold at least one date, all of them real days."""
    head = parse_head(line)
    days = _dates(" ".join(head.dates_text), week)
    if not days:
        walk.warnings.append(f"{walk.color}: no usable date in parentheses, skipped: {line}")
        return
    walk.entries.append(Entry(walk.color, head.name, head.address, tuple(days), head.classes))


def parse_outcomes(line: str, week: Week) -> tuple[list[Outcome], list[str]]:
    """Outcomes from "Result: Closure (Nov. 9); re-inspection required (Nov. 9)", and any part that didn't read."""
    outcomes: list[Outcome] = []
    unread: list[str] = []
    for part in line.removeprefix(RESULT_PREFIX).split(";"):
        match = OUTCOME.match(part.strip())
        days = _dates(match[2], week) if match else None
        if match is None or not days:
            unread.append(part.strip())
            continue
        outcomes.append(Outcome(match[1].strip(), days[0]))
    return outcomes, unread


def _flush_pending(walk: _Walk) -> None:
    """A red place whose Result line never came is kept, with no dates (it stands for its whole week)."""
    if walk.pending is None:
        return
    walk.warnings.append(f"RED: no Result line for {walk.pending.name}; kept without dates")
    walk.entries.append(Entry(RED, walk.pending.name, walk.pending.address, (), walk.pending.classes))
    walk.pending = None


def _result_line(walk: _Walk, week: Week, line: str) -> None:
    if walk.pending is None:
        walk.warnings.append(f"RED: a Result line with no place line before it, skipped: {line}")
        return
    outcomes, unread = parse_outcomes(line, week)
    walk.warnings.extend(f"RED: {walk.pending.name}: result not read: {part}" for part in unread)
    days = tuple(sorted({outcome.on for outcome in outcomes}))
    head = walk.pending
    walk.entries.append(Entry(RED, head.name, head.address, days, head.classes, tuple(outcomes)))
    walk.pending = None


def _red_line(walk: _Walk, week: Week, line: str) -> None:
    """Under RED: a place line, its narrative (dropped), then its Result line."""
    if line.startswith(RESULT_PREFIX):
        _result_line(walk, week, line)
        return
    if walk.pending is not None:
        return  # narrative: never kept
    if not looks_like_place(line):
        walk.warnings.append(f"RED: not a place line, skipped: {line[:WARNING_CHARS]}")
        return
    walk.pending = parse_head(line)


def _section_line(walk: _Walk, line: str) -> bool:
    """A week line or a GREEN / YELLOW / RED heading starts a new section; says whether the line was one."""
    week = week_from_line(line, walk.published)
    if week is None and line not in COLORS:
        return False
    _flush_pending(walk)
    if week is not None:
        walk.week, walk.color = week, ""
        walk.weeks.append(week)
        return True
    walk.color = line
    return True


def _step(walk: _Walk, line: str) -> None:
    if not line or _section_line(walk, line):
        return
    if walk.week is None or not walk.color or line == NONE_LINE:
        return  # the introduction and color legend come before the first list
    if walk.color == RED:
        _red_line(walk, walk.week, line)
        return
    _listed_line(walk, walk.week, line)


def walk_lines(lines: Collection[str], published: date) -> tuple[list[Week], list[Entry], list[str]]:
    """The weeks, the listed places, and warnings about lines that looked like facts but didn't read."""
    walk = _Walk(published)
    for line in lines:
        _step(walk, line.strip())
    _flush_pending(walk)
    return walk.weeks, walk.entries, walk.warnings


def _text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _lines(data: dict[str, object]) -> list[str]:
    value = data.get("lines")
    return [line for line in value if isinstance(line, str)] if isinstance(value, list) else []


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _check_kind(data: dict[str, object], _hosts: Collection[str]) -> str | None:
    kind = data.get("capture")
    return None if kind == CAPTURE_KIND else f"not a news capture (capture is {kind!r}, expected {CAPTURE_KIND!r})"


def _check_text(data: dict[str, object], _hosts: Collection[str]) -> str | None:
    missing = [key for key in REQUIRED_TEXT if not _text(data, key)]
    return f"missing {', '.join(missing)}" if missing else None


def _check_host(data: dict[str, object], hosts: Collection[str]) -> str | None:
    host = _host(_text(data, "url"))
    return None if host in hosts else f"{host or 'no host'} is not in [news] hosts in config.toml"


def _check_published(data: dict[str, object], _hosts: Collection[str]) -> str | None:
    published = _text(data, "published")
    return None if _iso_date(published) else f"published is not a date: {published!r}"


def _check_week(data: dict[str, object], _hosts: Collection[str]) -> str | None:
    published = _iso_date(_text(data, "published"))
    if published is None:
        return None  # reported by _check_published
    found = any(week_from_line(line.strip(), published) for line in _lines(data))
    return None if found else 'no week line (like "Nov. 8-14") in the article body'


CHECKS: tuple[Callable[[dict[str, object], Collection[str]], str | None], ...] = (
    _check_kind,
    _check_text,
    _check_host,
    _check_published,
    _check_week,
)


def capture_problems(data: dict[str, object], hosts: Collection[str]) -> list[str]:
    """Why a capture can't be read (empty when it can)."""
    return [problem for check in CHECKS if (problem := check(data, hosts)) is not None]


def parse_capture(data: dict[str, object]) -> tuple[NewsLink, list[str]]:
    """A capture with no ``capture_problems`` as a news link, with warnings about lines that didn't read."""
    published = _iso_date(_text(data, "published")) or date.min
    weeks, entries, warnings = walk_lines(_lines(data), published)
    url = _text(data, "url")
    link = NewsLink(
        url=url,
        source=_host(url).removeprefix(WWW),
        headline=_text(data, "headline"),
        published=published,
        author=_text(data, "author"),
        weeks=tuple(weeks),
        entries=tuple(entries),
        captured_at=_text(data, "captured_at"),
    )
    return link, warnings


@dataclass(frozen=True)
class CaptureRead:
    """What reading one capture gave: a link, or the problems that stopped it; and warnings about skipped lines."""

    link: NewsLink | None
    problems: list[str]
    warnings: list[str]


def read_capture(data: object, hosts: Collection[str]) -> CaptureRead:
    """Check a capture (JSON the extension saved), then read it."""
    if not isinstance(data, dict):
        return CaptureRead(None, [NOT_AN_OBJECT], [])
    problems = capture_problems(data, hosts)
    if problems:
        return CaptureRead(None, problems, [])
    link, warnings = parse_capture(data)
    return CaptureRead(link, [], warnings)
