# Copyright (c) 2026 nm_health contributors
"""Pin the parser branches the real reports never reach, on small hand-made pages."""

from pathlib import Path
from typing import Any

import pytest

from nm_health.ingest.parser import InspectionReportParser, _block_end, _drop_layout_lines

ARCHIVE = Path(__file__).resolve().parent.parent / "data" / "archive"
ANY_PDF = ARCHIVE / "2026-10-25_2026-10-31_0e0b9708501f.pdf"
SUMMARY_PAGE_LIMIT = 8  # the parser treats a page as a summary page by its row headers only below this index

EST_LINE = "TEST CAFE - 100 CENTRAL AVE SW"
PERMIT_LINE = "Food Establishment (Permit # - PT0000001) - Operational Status - Open"
HEADER_LINE = "Inspection Date     Inspection ID Number     Inspection Type     Inspection Status     Page #"
ROW_LINE = "  10/29/2026     PT0000001     Routine Food Establishment Inspection     Approved     Pg. 2"
DETAIL_PAGE = (
    "TEST CAFE - 100 CENTRAL AVE SW\n"
    "Date: 10/28/2026 - #: PT0000001 - Inspection Result: Approved\n"
    "Violation: Plumbing\n"
    " • System Maintained in Good Repair\n"
    "  - Plumbing shall be maintained.\n"
    "  Observed leak at hand sink.\n"
    "Violation:   \n"
    "   \n"
)


def parse_pages(pages: list[str], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Run the parser on hand-made page texts instead of a PDF's."""
    parser = InspectionReportParser(ANY_PDF)
    monkeypatch.setattr(parser, "extract_text_pages", lambda: pages)
    return parser.parse()


def test_missing_pdf_rejected(tmp_path: Path) -> None:
    """A path that does not exist fails at construction."""
    with pytest.raises(FileNotFoundError):
        InspectionReportParser(tmp_path / "missing.pdf")


def test_unreadable_pdf_raises_runtime_error(tmp_path: Path) -> None:
    """A non-PDF makes pdftotext fail, which surfaces as RuntimeError."""
    bogus = tmp_path / "bogus.pdf"
    bogus.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Failed to extract text"):
        InspectionReportParser(bogus).extract_text_pages()


def test_row_without_permit_and_detail_matched_by_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """No permit line: permit fields default; a detail block dated differently still matches by inspection ID."""
    summary = f"Summary Table\n{EST_LINE}\n{HEADER_LINE}\n{ROW_LINE}"
    parsed = parse_pages([summary, DETAIL_PAGE], monkeypatch)

    (inspection,) = parsed["inspections"]
    assert inspection["permit_number"] is None
    assert inspection["operational_status"] == "Open"
    assert inspection["inspection_date"] == "2026-10-29"
    assert inspection["violation_count"] == 1
    assert inspection["violations"][0]["item_title"] == "System Maintained in Good Repair"
    assert inspection["violations"][0]["observation"] == "Observed leak at hand sink."


def test_metadata_title_without_amendment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A first page with a Media Report title and no amendment line."""
    first = "Summary Table\nMedia Report 10.25.2026-10.31.2026\nWeek: October 25, 2026 to October 31, 2026"
    meta = parse_pages([first], monkeypatch)["metadata"]
    assert meta["raw_title"] == "Media Report 10.25.2026-10.31.2026"
    assert meta["amendment_notes"] == ""
    assert meta["week_range_str"] == "October 25, 2026 to October 31, 2026"


def test_unrecognised_date_kept_as_is() -> None:
    """Only MM/DD/YYYY is reformatted."""
    parser = InspectionReportParser(ANY_PDF)
    assert parser._format_date(" 10/29/2026 ") == "2026-10-29"  # noqa: SLF001 - pinning a private helper
    assert parser._format_date(" 2026-10-29 ") == "2026-10-29"  # noqa: SLF001 - pinning a private helper


@pytest.mark.parametrize(
    ("index", "is_summary"),
    [
        pytest.param(SUMMARY_PAGE_LIMIT - 1, True, id="last_summary_index"),
        pytest.param(SUMMARY_PAGE_LIMIT, False, id="first_detail_index"),
    ],
)
def test_summary_page_index_limit(index: int, *, is_summary: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """Row headers alone mark a summary page only on pages before the limit."""
    filler = ["filler page"] * index
    rows_page = f"{EST_LINE}\n{PERMIT_LINE}\n{HEADER_LINE}\n{ROW_LINE}"
    parsed = parse_pages([*filler, rows_page], monkeypatch)
    assert (parsed["total_inspections"] == 1) is is_summary


NEXT_DATE = "Date: 10/29/2026 - #: PT2 - Inspection Result: Approved"


@pytest.mark.parametrize(
    ("before_next_date", "kept"),
    [
        pytest.param("  Observed leak.\n", "  Observed leak.\n", id="no_class_line"),
        pytest.param(
            "  Observed leak.\n   NEXT CAFE - 1 MAIN ST NE - Approved\nNEXT CAFE - 1 MAIN ST NE\nFood Establishment Class C\n",
            "  Observed leak.",
            id="heading_name_and_class",
        ),
        pytest.param(
            "  Observed leak.\nOTHER - 2 MAIN ST\nNEXT CAFE - 1 MAIN ST NE\nFood Establishment Class C\n",
            "  Observed leak.\nOTHER - 2 MAIN ST",
            id="unrelated_line_kept",
        ),
        pytest.param(
            "  Observed leak.\nNEXT CAFE - 1 MAIN ST NE\nRetail Food Establishment Class 5\n\n\x0c",
            "  Observed leak.",
            id="page_break_before_date",
        ),
    ],
)
def test_block_end_trims_next_heading(before_next_date: str, kept: str) -> None:
    """An inspection's text stops before the next block's heading, name and class lines."""
    text = before_next_date + NEXT_DATE
    assert text[: _block_end(text, len(before_next_date))] == kept


def test_footer_lines_dropped() -> None:
    """Page footers never reach violation text."""
    assert _drop_layout_lines("a\n      Page 5 of 44\nb") == "a\nb"
