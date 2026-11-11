# Copyright (c) 2026 nm_health contributors
"""Rebuild: every archived PDF, oldest first, later reports win; then the SQLite file the CLI reads."""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from nm_health import rebuild as rebuild_module
from nm_health.database import write_database
from nm_health.db.local_store import LocalStore
from nm_health.feed import FeedRecord
from nm_health.identity import split_dba, strip_city
from nm_health.model import Inspection, Violation
from nm_health.rebuild import (
    LAYOUT_CURRENT,
    LAYOUT_UNREADABLE,
    merge_feed,
    parse_report,
    permit_line_pages,
    read_manifest,
    rebuild,
)
from nm_health.settings import Settings
from tests.test_archive import make_settings

ARCHIVE = Path(__file__).resolve().parent.parent / "data" / "archive"
EXPECTED_REPORT_INSPECTIONS = {
    "2025-01-27_2025-01-31_d4feb78541ce.pdf": 35,
    "2026-09-20_2026-09-26_4526d9bed974.pdf": 80,
    "2026-10-25_2026-10-31_0e0b9708501f.pdf": 64,
}


def write_manifest(settings: Settings, entries: list[dict[str, str]]) -> None:
    """A manifest with the given entries (plus a blank line, which is ignored)."""
    settings.manifest.write_text("\n".join(json.dumps(e) for e in entries) + "\n\n", encoding="utf-8")


def inspection(status: str, report_file: str) -> Inspection:
    """The same inspection (ID and date) as some report states it."""
    return Inspection(
        inspection_id="PT0000001",
        date="2026-10-29",
        kind="Routine Food Establishment Inspection",
        status=status,
        name="TEST CAFE",
        address="100 CENTRAL AVE SW",
        permit_number="PT0000001",
        permit_type="Food Establishment",
        report_file=report_file,
        page=1,
        violations=(Violation("Pest Control", "Removing Dead or Trapped", "", "Observed roaches."),),
    )


def test_manifest_keeps_first_entry_per_file(tmp_path: Path) -> None:
    """A file archived twice keeps the time it was first seen."""
    settings = make_settings(tmp_path)
    first = {"file": "a.pdf", "seen_at": "2026-01-01"}
    write_manifest(settings, [first, {"file": "a.pdf", "seen_at": "2026-02-02"}])
    assert read_manifest(settings.manifest) == {"a.pdf": first}


def test_later_report_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An amended re-issue (later week_end/seen_at) replaces the earlier statement of the same inspection."""
    settings = make_settings(tmp_path)
    write_manifest(
        settings,
        [
            {"file": "amended.pdf", "sha256": "b", "week_end": "2026-10-31", "seen_at": "2026-11-04"},
            {"file": "first.pdf", "sha256": "a", "week_end": "2026-10-31", "seen_at": "2026-11-02"},
        ],
    )
    statuses = {"first.pdf": "Approved", "amended.pdf": "Unsatisfactory Re-Inspection required"}
    monkeypatch.setattr(
        rebuild_module,
        "parse_report",
        lambda pdf: (LAYOUT_CURRENT, [inspection(statuses[pdf.name], pdf.name)]),
    )

    rebuilt = rebuild(settings)

    (only,) = rebuilt.inspections
    assert (only.status, only.report_file) == ("Unsatisfactory Re-Inspection required", "amended.pdf")
    assert only.violations[0].tags == ("roaches", "pest_control")
    assert [r.file for r in rebuilt.reports] == ["first.pdf", "amended.pdf"]


def test_unknown_layout_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A PDF that is neither layout yields no inspections and is reported as unreadable."""
    monkeypatch.setattr(rebuild_module, "report_text", lambda _pdf: "a menu, not an inspection report")
    assert parse_report(tmp_path / "menu.pdf") == (LAYOUT_UNREADABLE, [])


def test_real_archive_end_to_end(tmp_path: Path) -> None:
    """Every archived report parses with its layout, and the database answers CLI queries."""
    settings = make_settings(tmp_path)
    pinned = [
        line
        for line in (ARCHIVE / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line)["file"] in EXPECTED_REPORT_INSPECTIONS
    ]
    settings.manifest.write_text("\n".join(pinned) + "\n", encoding="utf-8")
    settings = Settings(**{**settings.__dict__, "archive_dir": ARCHIVE})

    rebuilt = rebuild(settings)
    write_database(rebuilt, settings.db, settings.archive_dir)

    assert {r.file: r.inspections for r in rebuilt.reports} == EXPECTED_REPORT_INSPECTIONS
    assert len({(i.inspection_id, i.date) for i in rebuilt.inspections}) == len(rebuilt.inspections)
    store = LocalStore(db_path=settings.db)
    (place,) = store.search_establishments("ALBUQ GRAND SENIOR")
    assert place["has_pest_history"] == 1
    assert store.get_stats()["total_inspections"] == len(rebuilt.inspections)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Long Cao LLC DBA Dragon Sushi", ("Dragon Sushi", "Long Cao LLC"), id="dba_upper"),
        pytest.param("AN BE LLC dba Saigon Restaurant", ("Saigon Restaurant", "AN BE LLC"), id="dba_lower"),
        pytest.param("Acme Inc d/b/a Taco Spot", ("Taco Spot", "Acme Inc"), id="dba_slashed"),
        pytest.param("BAMBOO", ("BAMBOO", None), id="no_dba"),
        pytest.param("DBA HOLDINGS", ("DBA HOLDINGS", None), id="dba_word_first"),
    ],
)
def test_split_dba(raw: str, expected: tuple[str, str | None]) -> None:
    """The name people know is shown; the legal name is kept separately."""
    assert split_dba(raw) == expected


def test_strip_city() -> None:
    """Feed addresses end with the city, state and ZIP; PDFs don't."""
    assert strip_city("7202 MENAUL BLVD NE ALBUQUERQUE, NM 87110 ") == "7202 MENAUL BLVD NE"
    assert strip_city("6902 MENAUL BLVD NE Albuquerque, NM 87110-1234") == "6902 MENAUL BLVD NE"
    assert strip_city("840 SAN MATEO BLVD SE") == "840 SAN MATEO BLVD SE"


def feed_record(number: str, day: str, status: str = "Approved", violations: int = 2) -> FeedRecord:
    """A status-feed record at the test cafe's address."""
    return FeedRecord(
        number=number,
        date=day,
        kind="Routine Food Establishment Inspection",
        status=status,
        name="TEST CAFE",
        legal_name=None,
        address="100 CENTRAL AVE SW",
        lat=35.08,
        lng=-106.65,
        violations=violations,
        risk="3",
        time="14:20",
    )


def test_merge_feed() -> None:
    """A matching record adds coordinates and the count; an unmatched one becomes a status-only inspection."""
    detailed = inspection("Approved", "r.pdf")
    merged = merge_feed(
        [detailed],
        [feed_record("PT0000001", "2026-10-29", violations=1), feed_record("RT-9", "2026-06-08", "Closure", 28)],
    )
    enriched, feed_only = merged
    assert (enriched.lat, enriched.lng, enriched.violation_count, enriched.has_details) == (35.08, -106.65, 1, True)
    assert (enriched.time, feed_only.time) == ("14:20", "14:20")
    assert (feed_only.inspection_id, feed_only.status, feed_only.violation_count) == ("RT-9", "Closure", 28)
    assert (feed_only.has_details, feed_only.violations, feed_only.report_file) == (False, (), "")


def test_unmatched_inspection_gets_coordinates_by_address() -> None:
    """A follow-up the feed doesn't carry still lands on the map via its address."""
    follow_up = replace(inspection("Approved", "r.pdf"), inspection_id="CAC-1")
    (enriched, _feed_only) = merge_feed([follow_up], [feed_record("RT-9", "2026-06-08")])
    assert (enriched.lat, enriched.violation_count, enriched.time) == (35.08, None, None)


def test_amended_status_and_dba_and_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A later report's changed status keeps the first one; DBA names split; `since` drops older inspections."""
    settings = make_settings(tmp_path)
    write_manifest(
        settings,
        [
            {"file": "first.pdf", "sha256": "a", "week_end": "2026-10-31", "seen_at": "2026-11-02"},
            {"file": "amended.pdf", "sha256": "b", "week_end": "2026-10-31", "seen_at": "2026-11-04"},
        ],
    )
    old = replace(inspection("Approved", "first.pdf"), inspection_id="OLD", date="2025-01-02")
    statuses = {"first.pdf": "Approved", "amended.pdf": "Conditional Approved"}

    def parsed(pdf: Path) -> tuple[str, list[Inspection]]:
        current = replace(inspection(statuses[pdf.name], pdf.name), name="ACME LLC DBA TEST CAFE")
        return LAYOUT_CURRENT, [current, old]

    monkeypatch.setattr(rebuild_module, "parse_report", parsed)
    (only,) = rebuild(settings, date(2025, 11, 9)).inspections
    assert (only.status, only.amended_from) == ("Conditional Approved", "Approved")
    assert (only.name, only.legal_name) == ("TEST CAFE", "ACME LLC")


def test_permit_line_pages() -> None:
    """Each permit's Operational Status line, by the page (1-based) that first prints it; hyphenated numbers too."""
    text = (
        "Summary Table\nFood Establishment (Permit # - PT0156723) - Operational Status \u2013 Open\n"
        "\fFood Establishment (Permit # - FOODEST-2025-00423) - Operational Status - Closed\n"
        "\fDate: 10/28/2026 - #: PT0156723 - Inspection Result: Approved\n"
    )
    assert permit_line_pages(text) == {"PT0156723": 1, "FOODEST-2025-00423": 2}
