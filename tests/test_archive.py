# Copyright (c) 2026 nm_health contributors
"""Archive: week detection, naming, dedupe, and refusing what is not a report PDF."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from nm_health.archive import ArchiveError, Week, archive_bytes, archive_name, download, week_from_text
from nm_health.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_NAME = "2026-09-20_2026-09-26_4526d9bed974.pdf"
SAMPLE_PDF = ROOT / "data" / "archive" / SAMPLE_NAME
SEEN_AT = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
FAKE_SHA = "abcdef0123456789" * 4


def make_settings(tmp_path: Path) -> Settings:
    """Settings that write only inside tmp_path."""
    return Settings(
        report_url="https://example.test/report.pdf",
        user_agent="test",
        timeout_seconds=1,
        archive_dir=tmp_path / "archive",
        manifest=tmp_path / "manifest.jsonl",
        db=tmp_path / "db.sqlite",
        site_dir=tmp_path / "site",
        cdx_url="https://example.test/cdx",
        raw_url_template="https://example.test/{timestamp}/{url}",
        pdf_base_url="https://example.test/pdf/",
        feed_raw_dir=tmp_path / "feed",
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "Performed Week: October 25, 2026 to October 31,\n   2026 Report Amended",
            Week(date(2026, 10, 25), date(2026, 10, 31)),
            id="long_format_wrapped",
        ),
        pytest.param(
            "Inspections Performed Week: November 02, 2025 to November 08, 2025",
            Week(date(2025, 11, 2), date(2025, 11, 8)),
            id="long_format_zero_padded",
        ),
        pytest.param(
            "Consumer Health Protection Inspections Performed 7/10/2021 - 7/16/2021 SAMS CLUB",
            Week(date(2021, 7, 10), date(2021, 7, 16)),
            id="slashed_format",
        ),
        pytest.param("no dates on this page", None, id="no_week"),
    ],
)
def test_week_from_text(text: str, expected: Week | None) -> None:
    """Each first-page format the city has used gives its week."""
    assert week_from_text(text) == expected


def test_archive_name_with_and_without_week() -> None:
    """Known weeks name by week; unknown ones by the day they were seen."""
    week = Week(date(2026, 10, 25), date(2026, 10, 31))
    assert archive_name(week, SEEN_AT, FAKE_SHA) == "2026-10-25_2026-10-31_abcdef012345.pdf"
    assert archive_name(None, SEEN_AT, FAKE_SHA) == "unknown-week_2026-11-09_abcdef012345.pdf"


def test_non_pdf_rejected(tmp_path: Path) -> None:
    """A Cloudflare challenge page (HTML) is never archived."""
    settings = make_settings(tmp_path)
    with pytest.raises(ArchiveError, match="not a PDF"):
        archive_bytes(b"<!DOCTYPE html><title>Just a moment...</title>", "test", SEEN_AT, settings)
    assert not settings.manifest.exists()


def test_same_pdf_archived_once(tmp_path: Path) -> None:
    """The real sample is named by its week; archiving it again changes nothing."""
    settings = make_settings(tmp_path)
    body = SAMPLE_PDF.read_bytes()

    first = archive_bytes(body, "test", SEEN_AT, settings)
    second = archive_bytes(body, "test", SEEN_AT, settings)

    assert first.is_new
    assert first.path.name == SAMPLE_NAME
    assert not second.is_new
    assert second.path == first.path
    assert [p.name for p in settings.archive_dir.iterdir()] == [SAMPLE_NAME]
    lines = settings.manifest.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["file"] for line in lines] == [SAMPLE_NAME]
    assert json.loads(lines[0])["week_start"] == "2026-09-20"


def test_download_refuses_http() -> None:
    """Only https URLs are fetched."""
    with pytest.raises(ArchiveError, match="non-https"):
        download("http://example.test/report.pdf", "test", 1)
