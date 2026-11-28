# Copyright (c) 2026 nm_health contributors
"""Pin the summary-table records of every archived report (characterization test).

The summary table says which place and permit each inspection belongs to; this pins that reading for every report
we hold, so a change to how place headers are found shows up as a diff here.

Regenerate only for a deliberate behaviour change, in that change's own commit:
    UPDATE_GOLDEN=1 uv run pytest tests/test_summary_golden.py
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from nm_health.ingest.parser import InspectionReportParser

ARCHIVE = Path(__file__).resolve().parent.parent / "data" / "archive"
GOLDEN = Path(__file__).resolve().parent / "golden" / "summary_records"
REPORTS = sorted(path.name for path in ARCHIVE.glob("*.pdf"))
SUMMARY_PAGE_LIMIT = 8  # parse() takes a page with the column headers as a summary page only below this index


def is_summary_page(index: int, page: str) -> bool:
    """The page selection parse() makes, restated so the pin does not depend on it."""
    has_headers = "Inspection Date" in page and "Inspection ID Number" in page
    return "Summary Table" in page or (index < SUMMARY_PAGE_LIMIT and has_headers)


def summary_records(report: str) -> list[dict[str, Any]]:
    """The summary-table records the parser reads from one archived report."""
    parser = InspectionReportParser(ARCHIVE / report)
    pages = enumerate(parser.extract_text_pages())
    summary_pages = [(index + 1, page) for index, page in pages if is_summary_page(index, page)]
    return [dict(record) for record in parser._parse_summary_pages(summary_pages)]  # noqa: SLF001 - the code being pinned


@pytest.mark.parametrize("report", REPORTS)
def test_summary_records_unchanged(report: str) -> None:
    """Each report's summary records match the committed snapshot."""
    actual = summary_records(report)
    path = GOLDEN / report.replace(".pdf", ".json")
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(actual, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected
