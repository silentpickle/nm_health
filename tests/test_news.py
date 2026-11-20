# Copyright (c) 2026 nm_health contributors
"""News links: the links file, and the rule that a county report always wins where dates overlap."""

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from nm_health.archive import Week
from nm_health.news import (
    NEW,
    SAME,
    UPDATED,
    Entry,
    NewsLink,
    Outcome,
    county_days,
    load_links,
    save_links,
    unknown_week_files,
    upsert,
    usable_entries,
)

COUNTY_WEEK = Week(date(2026, 11, 8), date(2026, 11, 14))
DAYS_IN_WEEK = 7
ONE_DAY = timedelta(days=1)
NEXT_WEEK = Week(COUNTY_WEEK.end + ONE_DAY, COUNTY_WEEK.end + ONE_DAY * DAYS_IN_WEEK)


def make_link(url: str, week: Week, entries: tuple[Entry, ...] = ()) -> NewsLink:
    """A news link with one week and the given entries."""
    return NewsLink(
        url=url,
        source="example.test",
        headline="Businesses red-tagged",
        published=week.end + ONE_DAY,
        author="Staff Report",
        weeks=(week,),
        entries=entries,
        captured_at="2026-11-20T00:00:00Z",
    )


def entry_on(*days: date) -> Entry:
    """A red entry dated on the given days."""
    return Entry("RED", "Hot Wok", "500 Coors NW", days, ("Class C",), tuple(Outcome("Closure", day) for day in days))


def write_manifest(path: Path) -> Path:
    """A manifest with one dated county PDF and one with no week."""
    rows = [
        {"file": "a.pdf", "week_start": COUNTY_WEEK.start.isoformat(), "week_end": COUNTY_WEEK.end.isoformat()},
        {"file": "unknown-week_b.pdf", "week_start": None, "week_end": None},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_links_file_round_trip(tmp_path: Path) -> None:
    """Saved links read back equal, oldest week first, one line each."""
    newer = make_link("https://www.example.test/b/2", NEXT_WEEK, (entry_on(NEXT_WEEK.start),))
    older = make_link("https://www.example.test/a/1", COUNTY_WEEK, (entry_on(COUNTY_WEEK.start),))
    path = tmp_path / "news" / "links.jsonl"
    save_links(path, [newer, older])
    assert load_links(path) == [older, newer]
    assert len(path.read_text(encoding="utf-8").splitlines()) == len([older, newer])


def test_missing_links_file_empty(tmp_path: Path) -> None:
    """No links file yet: no links."""
    assert load_links(tmp_path / "links.jsonl") == []


def test_upsert_new_same_updated() -> None:
    """A new URL is NEW; the same facts captured again are same; changed facts replace the old record."""
    link = make_link("https://www.example.test/a/1", COUNTY_WEEK)
    links, status = upsert([], link)
    assert (links, status) == ([link], NEW)
    recaptured = replace(link, captured_at="2026-11-21T00:00:00Z")
    assert upsert(links, recaptured) == ([link], SAME)
    changed = replace(link, headline="Corrected headline")
    assert upsert(links, changed) == ([changed], UPDATED)


def test_county_days_edges(tmp_path: Path) -> None:
    """Every day of an archived week counts, its first and last included; the days either side don't."""
    covered = county_days(write_manifest(tmp_path / "manifest.jsonl"))
    assert COUNTY_WEEK.start in covered
    assert COUNTY_WEEK.end in covered
    assert COUNTY_WEEK.start - ONE_DAY not in covered
    assert COUNTY_WEEK.end + ONE_DAY not in covered
    assert len(covered) == DAYS_IN_WEEK


def test_missing_manifest_covers_nothing(tmp_path: Path) -> None:
    """No manifest: no day is covered and no file lacks a week."""
    assert county_days(tmp_path / "manifest.jsonl") == frozenset()
    assert unknown_week_files(tmp_path / "manifest.jsonl") == []


def test_unknown_week_files_listed(tmp_path: Path) -> None:
    """Archived PDFs with no week on file are named, so their days can be checked by hand."""
    assert unknown_week_files(write_manifest(tmp_path / "manifest.jsonl")) == ["unknown-week_b.pdf"]


@pytest.mark.parametrize(
    ("week", "days", "usable"),
    [
        pytest.param(COUNTY_WEEK, (COUNTY_WEEK.end,), False, id="county_last_day"),
        pytest.param(NEXT_WEEK, (COUNTY_WEEK.end + ONE_DAY,), True, id="day_after_county"),
        pytest.param(NEXT_WEEK, (COUNTY_WEEK.end, NEXT_WEEK.start + ONE_DAY), False, id="one_day_inside"),
        pytest.param(Week(COUNTY_WEEK.end, NEXT_WEEK.start), (), False, id="undated_partly_covered"),
        pytest.param(NEXT_WEEK, (), True, id="undated_uncovered_week"),
    ],
)
def test_county_report_always_wins(tmp_path: Path, week: Week, days: tuple[date, ...], *, usable: bool) -> None:
    """An entry is usable only when none of its days (or, undated, its week's days) is in a county PDF's week."""
    covered = county_days(write_manifest(tmp_path / "manifest.jsonl"))
    entry = entry_on(*days)
    expected = [entry] if usable else []
    assert usable_entries(make_link("https://www.example.test/a/1", week, (entry,)), covered) == expected
