# Copyright (c) 2026 nm_health contributors
"""The site says only what the archive shows, escapes what the PDFs say, and writes every page."""

from dataclasses import replace
from pathlib import Path

import pytest

from nm_health.model import Inspection, Violation
from nm_health.rebuild import Rebuilt, Report
from nm_health.site import (
    Place,
    group_places,
    pest_line,
    red_line,
    render_index,
    render_place,
    status_level,
    write_site,
)
from tests.test_archive import make_settings

PESTS = Violation("Pest Control", "Removing Dead or Trapped", "", "Observed roaches.", ("roaches", "pest_control"))
OTHER = Violation("Plumbing", "System Maintained in Good Repair", "", "Observed leak.", ())
REPORT_FILE = "2026-10-25_2026-10-31_abc.pdf"


def visit(day: str, *violations: Violation, status: str = "Approved", inspection_id: str = "PT1") -> Inspection:
    """One inspection of the test place."""
    return Inspection(
        inspection_id=inspection_id,
        date=day,
        kind="Routine Food Establishment Inspection",
        status=status,
        name="TEST CAFE",
        address="100 CENTRAL AVE SW",
        permit_number="PT1",
        permit_type="Food Establishment",
        report_file=REPORT_FILE,
        page=3,
        violations=violations,
    )


def place(*inspections: Inspection) -> Place:
    """The test place with the given inspections (newest first, as group_places orders them)."""
    (only,) = group_places(inspections)
    return only


@pytest.mark.parametrize(
    ("inspections", "expected"),
    [
        pytest.param(
            (visit("2026-10-29", OTHER),),
            ("No pest citations in 1 archived inspection(s) (Oct 29, 2026).", False),
            id="no_pests_one_date",
        ),
        pytest.param(
            (visit("2026-04-01"), visit("2026-10-29", OTHER)),
            ("No pest citations in 2 archived inspection(s) (Apr 1, 2026 \u2013 Oct 29, 2026).", False),
            id="no_pests_range",
        ),
        pytest.param(
            (visit("2026-04-01"), visit("2026-10-29", PESTS)),
            ("Pests cited on Oct 29, 2026, the latest inspection date in the archive.", True),
            id="pests_latest",
        ),
        pytest.param(
            (visit("2026-04-01", PESTS), visit("2026-05-01"), visit("2026-10-29")),
            ("Last pest citation Apr 1, 2026 \u00b7 inspected 2 times since, most recently Oct 29, 2026.", False),
            id="pests_then_clean",
        ),
        pytest.param(
            (visit("2026-04-01", PESTS), visit("2026-04-02", inspection_id="CAC-1")),
            ("Last pest citation Apr 1, 2026 \u00b7 inspected 1 time since, most recently Apr 2, 2026.", False),
            id="one_follow_up",
        ),
    ],
)
def test_pest_line(inspections: tuple[Inspection, ...], expected: tuple[str, bool]) -> None:
    """Pest wording is limited to archived inspections and never claims 'pest-free'."""
    assert pest_line(place(*inspections)) == expected


@pytest.mark.parametrize(
    ("status", "level"),
    [
        pytest.param("Unsatisfactory Re-Inspection required", "red", id="unsatisfactory"),
        pytest.param("Immediate Closure - Imminent Health Hazard", "red", id="closure"),
        pytest.param("Conditional Approved", "yellow", id="conditional"),
        pytest.param("Approved", "green", id="approved"),
        pytest.param("Non-Graded", "gray", id="other"),
    ],
)
def test_status_level(status: str, level: str) -> None:
    """Red is checked before yellow and green, so 'Conditional' never hides a closure."""
    assert status_level(status) == level


def test_red_line_names_latest_failure() -> None:
    """The most recent closed/failed inspection is called out; none means no line."""
    assert red_line(place(visit("2026-10-29"))) is None
    failed = place(
        visit("2026-01-05", status="Immediate Closure"),
        visit("2026-06-05", status="Unsatisfactory Re-Inspection required", inspection_id="PT2"),
        visit("2026-10-29"),
    )
    assert red_line(failed) == "Last closed or failed: Jun 5, 2026 (Unsatisfactory Re-Inspection required)."


def test_text_from_pdfs_is_escaped(tmp_path: Path) -> None:
    """Names and observations are text, never markup."""
    hostile = replace(visit("2026-10-29", replace(OTHER, observation="<script>x()</script>")), name="<b>CAFE</b>")
    rebuilt = Rebuilt((hostile,), ())
    html = render_place(place(hostile), rebuilt, make_settings(tmp_path))
    assert "<script>x()" not in html
    assert "&lt;script&gt;x()&lt;/script&gt;" in html
    assert "&lt;b&gt;CAFE&lt;/b&gt;" in html


def test_write_site_writes_every_page(tmp_path: Path) -> None:
    """Index, reports list, one page per place, static assets, data.json."""
    settings = make_settings(tmp_path)
    other_place = replace(visit("2026-10-28"), name="OTHER DINER", address="5 MAIN ST NE")
    report = Report(REPORT_FILE, "abc", "2026-10-25", "2026-10-31", "test", "2026-11-04", "current", 2)
    count = write_site(Rebuilt((visit("2026-10-29", PESTS), other_place), (report,)), settings)

    assert count == len(["TEST CAFE", "OTHER DINER"])
    written = sorted(p.relative_to(settings.site_dir).as_posix() for p in settings.site_dir.rglob("*") if p.is_file())
    assert written == [
        ".nojekyll",
        "data.json",
        "index.html",
        "place/other-diner-5-main-st-ne.html",
        "place/test-cafe-100-central-ave-sw.html",
        "reports.html",
        "search.js",
        "style.css",
    ]
    index = (settings.site_dir / "index.html").read_text(encoding="utf-8")
    assert 'data-flags="pest_control pests roaches"' in index
    assert "Oct 25, 2026" in (settings.site_dir / "reports.html").read_text(encoding="utf-8")


def test_empty_archive_and_synthetic_ids(tmp_path: Path) -> None:
    """No reports yet says so; IDs made up for old layouts are never shown; a bare category stands alone."""
    old = visit(
        "2024-05-08",
        Violation("S56 Immediate Closure", "", "", "NO WATER", ()),
        status="Unsatisfactory - Immediate Closure",
        inspection_id="legacy-2024-x",
    )
    rebuilt = Rebuilt((old,), ())
    index = render_index(group_places(rebuilt.inspections), rebuilt)
    assert "No reports archived yet." in index
    assert 'data-flags="red"' in index
    html = render_place(place(old), rebuilt, make_settings(tmp_path))
    assert "legacy-2024-x" not in html
    assert '<span class="v-title">S56 Immediate Closure</span><p' in html
