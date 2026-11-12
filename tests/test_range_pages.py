# Copyright (c) 2026 nm_health contributors
"""The time-range pages (This week, and the longer ranges): their whole HTML body, pinned (characterization test).

Regenerate only for a deliberate behaviour change, in that change's own commit:
    UPDATE_GOLDEN=1 uv run pytest tests/test_range_pages.py
"""

import os
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from nm_health.model import Inspection
from nm_health.rebuild import Rebuilt, Report
from nm_health.site_html import SiteData, site_data
from nm_health.site_pages import ALL_RANGE, MONTH_RANGE, PAGE_SIZE, TimeRange, range_page, week_page
from nm_health.viewmodel import RED_GROUP
from tests.test_archive import make_settings
from tests.test_viewmodel import CLOSED, CONDITIONAL, FAILED, ROACHES, report, visit

TODAY = date(2026, 11, 9)
GOLDEN = Path(__file__).resolve().parent / "golden"
COVERING = report("2026-10-25", "2026-10-31")
OLDER = report("2026-10-18", "2026-10-24")
LATE_SEPTEMBER = report("2026-09-27", "2026-10-03")
UNDATED = Report("unknown-week_2026-11-08_abc.pdf", "abc", None, None, "test", "2026-11-08", "current", 1)


def at(inspection: Inspection, name: str, source: Report) -> Inspection:
    """The inspection at a place of its own, printed in the given report."""
    return replace(inspection, name=name, address=f"{len(name)} {name} ST", report_file=source.file)


def covered_week() -> Rebuilt:
    """The newest date is in a report on file: closures, pests and other inspections from the same seven days."""
    inspections = (
        at(visit("2026-10-30", ROACHES), "BUGS", COVERING),
        at(visit("2026-10-29", status=CLOSED), "SHUT", COVERING),
        at(visit("2026-10-28", status=FAILED), "FAILED", COVERING),
        at(visit("2026-10-27", status=CONDITIONAL), "MAYBE", COVERING),
        at(visit("2026-10-26"), "FINE", COVERING),
        at(visit("2026-10-24", ROACHES), "FIRST DAY", OLDER),
        at(visit("2026-10-23", ROACHES), "DAY BEFORE", OLDER),
        at(visit("2026-10-22", status=CLOSED), "BEFORE", OLDER),
    )
    return Rebuilt(inspections, (OLDER, COVERING))


def latest_report_week() -> Rebuilt:
    """The newest date is in a report with no stated week: banner, pests from the latest dated report."""
    inspections = (
        at(visit("2026-11-06"), "NEWEST", UNDATED),
        at(visit("2026-10-28", ROACHES), "BUGS", COVERING),
        at(visit("2026-10-20", ROACHES), "OLDER BUGS", OLDER),
    )
    return Rebuilt(inspections, (OLDER, COVERING, UNDATED))


def quiet_week() -> Rebuilt:
    """Covered, with nothing red and no pests cited: both card sections say so."""
    return Rebuilt((at(visit("2026-10-30"), "FINE", COVERING),), (COVERING,))


def no_report_week() -> Rebuilt:
    """No dated report on file at all: banner, and pest citations can't be shown."""
    return Rebuilt((at(visit("2026-11-06", ROACHES), "NEWEST", UNDATED),), (UNDATED,))


def no_inspections() -> Rebuilt:
    """Nothing on file yet."""
    return Rebuilt((), ())


def month_edges() -> Rebuilt:
    """Newest Oct 30: Oct 1 is the month's first day, Sep 30 the day before it; roaches on both."""
    inspections = (
        at(visit("2026-10-30"), "NEWEST", COVERING),
        at(visit("2026-10-01", ROACHES), "FIRST DAY", LATE_SEPTEMBER),
        at(visit("2026-09-30", ROACHES, status=CLOSED), "DAY BEFORE", LATE_SEPTEMBER),
    )
    return Rebuilt(inspections, (LATE_SEPTEMBER, COVERING))


SCENARIOS = {
    "covered_week": covered_week,
    "quiet_week": quiet_week,
    "latest_report": latest_report_week,
    "no_report": no_report_week,
    "no_inspections": no_inspections,
}


def data_for(tmp_path: Path, rebuilt: Rebuilt) -> SiteData:
    """What the pages are rendered from, on the fixed day."""
    return site_data(rebuilt, make_settings(tmp_path), TODAY)


def check_golden(name: str, actual: str) -> None:
    """Compare against the committed snapshot, writing it first when UPDATE_GOLDEN is set."""
    path = GOLDEN / f"{name}.html"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(actual, encoding="utf-8")
    assert actual == path.read_text(encoding="utf-8")


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_week_page_unchanged(tmp_path: Path, scenario: str) -> None:
    """index.html's whole body for each case matches the committed snapshot."""
    page = week_page(data_for(tmp_path, SCENARIOS[scenario]()))
    assert (page.title, page.active) == ("This week", "week")
    check_golden(f"week_page_{scenario}", page.body)


LONGER_RANGES = {"month": MONTH_RANGE, "all": ALL_RANGE}
LONGER_SCENARIOS = {**SCENARIOS, "month_edges": month_edges}


@pytest.mark.parametrize("scenario", list(LONGER_SCENARIOS))
@pytest.mark.parametrize("range_name", list(LONGER_RANGES))
def test_longer_range_pages_unchanged(tmp_path: Path, range_name: str, scenario: str) -> None:
    """month.html and all.html: the same sections as This week over a longer span, pinned for each case."""
    time_range = LONGER_RANGES[range_name]
    page = range_page(data_for(tmp_path, LONGER_SCENARIOS[scenario]()), time_range)
    assert (page.title, page.active) == (time_range.title, "week")
    check_golden(f"{range_name}_page_{scenario}", page.body)


def body_for(tmp_path: Path, rebuilt: Rebuilt, time_range: TimeRange) -> str:
    """One range page's body."""
    return range_page(data_for(tmp_path, rebuilt), time_range).body


def test_month_page_keeps_thirty_days(tmp_path: Path) -> None:
    """Last month is the newest date and the 29 days before it: Oct 1 is in, Sep 30 is not."""
    body = body_for(tmp_path, month_edges(), MONTH_RANGE)
    assert "Inspections Oct 1 \u2013 Oct 30, 2026</p>" in body
    assert "FIRST DAY" in body
    assert "DAY BEFORE" not in body


def test_all_time_page_lists_older_closures(tmp_path: Path) -> None:
    """All time reaches the oldest inspection on file, closures and pest citations included."""
    body = body_for(tmp_path, month_edges(), ALL_RANGE)
    assert "Inspections Sep 30 \u2013 Oct 30, 2026</p>" in body
    assert f'{RED_GROUP}<span class="n">1</span>' in body
    assert 'Roaches or rodents cited<span class="n">2</span>' in body


def test_month_pests_come_from_its_own_inspections(tmp_path: Path) -> None:
    """With no report covering the newest date, a month still cites pests from every inspection in it with notes."""
    body = body_for(tmp_path, latest_report_week(), MONTH_RANGE)
    assert "OLDER BUGS" in body
    assert "week of" not in body
    assert "isn&#x27;t on file yet" in body
    assert 'Roaches or rodents cited<span class="n">2</span>' in body


def test_range_cards_capped(tmp_path: Path) -> None:
    """More closures than PAGE_SIZE: the newest PAGE_SIZE cards, the full count, and a pointer to Places."""
    many = tuple(at(visit("2026-10-30", status=CLOSED), f"PLACE {n:03d}", COVERING) for n in range(PAGE_SIZE + 1))
    body = body_for(tmp_path, Rebuilt(many, (COVERING,)), ALL_RANGE)
    assert body.count('<a class="notice"') == PAGE_SIZE
    assert f'{RED_GROUP}<span class="n">{PAGE_SIZE + 1}</span>' in body
    assert f'<p class="note">Newest {PAGE_SIZE} shown.' in body


def test_range_cards_at_page_size_have_no_note(tmp_path: Path) -> None:
    """Exactly PAGE_SIZE closures: all shown, no pointer to Places."""
    many = tuple(at(visit("2026-10-30", status=CLOSED), f"PLACE {n:03d}", COVERING) for n in range(PAGE_SIZE))
    body = body_for(tmp_path, Rebuilt(many, (COVERING,)), ALL_RANGE)
    assert body.count('<a class="notice"') == PAGE_SIZE
    assert "shown." not in body


def test_week_page_rows_capped(tmp_path: Path) -> None:
    """Other inspections list one row per place, at most PAGE_SIZE of them; the heading counts every visit."""
    many = tuple(at(visit("2026-10-30"), f"PLACE {n:03d}", COVERING) for n in range(PAGE_SIZE + 1))
    body = week_page(data_for(tmp_path, Rebuilt(many, (COVERING,)))).body
    assert body.count('<a class="row"') == PAGE_SIZE
    assert f'Other inspections<span class="n">{PAGE_SIZE + 1}</span>' in body


def test_week_across_new_year_names_both_years(tmp_path: Path) -> None:
    """A week that starts in December says which year it starts in."""
    new_year = report("2025-12-28", "2026-01-03")
    rebuilt = Rebuilt((at(visit("2026-01-02"), "JANUARY", new_year),), (new_year,))
    body = week_page(data_for(tmp_path, rebuilt)).body
    assert "Inspections Dec 27, 2025 \u2013 Jan 2, 2026</p>" in body
