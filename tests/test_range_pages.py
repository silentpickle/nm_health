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
from nm_health.site_pages import PAGE_SIZE, week_page
from tests.test_archive import make_settings
from tests.test_viewmodel import CLOSED, CONDITIONAL, FAILED, ROACHES, report, visit

TODAY = date(2026, 11, 9)
GOLDEN = Path(__file__).resolve().parent / "golden"
COVERING = report("2026-10-25", "2026-10-31")
OLDER = report("2026-10-18", "2026-10-24")
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
