# Copyright (c) 2026 nm_health contributors
"""CLI wording: never call an inspection clean when its text isn't on file."""

from nm_health.cli import no_violations_line


def test_no_violations_only_when_report_on_file() -> None:
    """A PDF-backed inspection with no violations says so; a feed-only one says what's missing."""
    assert "No violations recorded." in no_violations_line({"report_filename": "r.pdf"})
    feed_only = no_violations_line({"report_filename": None, "violation_count": 28})
    assert "Details not on file (city status feed: 28 violations)." in feed_only
    assert "No violations" not in feed_only
