# Copyright (c) 2026 nm_health contributors
"""Reading the summary table by position: any name reads, and an unknown layout raises instead of misfiling."""

import pytest

from nm_health.ingest.summary import SummaryLayoutError, read_summary

COLUMNS = "Inspection Date     Inspection ID Number     Inspection Type     Inspection Status     Page #"
PERMIT = "Food Establishment (Permit # - PT0000001) - Operational Status - Open"
ROW = "  11/16/2026     RT-FOODEST-107750-2026     Routine Food Establishment Inspection     Approved     Pg. 4"


def places(*headers: str) -> list[tuple[str, str]]:
    """The (name, address) each row is filed under, one place block per header."""
    page = "\n\n".join(f"{header}\n{COLUMNS}\n{PERMIT}\n{ROW}" for header in headers)
    return [(r["establishment"]["name"], r["establishment"]["address"]) for r in read_summary([page])]


@pytest.mark.parametrize(
    ("header", "name", "address"),
    [
        pytest.param("CAFÉ PARIS - 100 CENTRAL AVE SW", "CAFÉ PARIS", "100 CENTRAL AVE SW", id="accent"),
        pytest.param("BURGERS @ 5TH / GOLD - 500 GOLD AVE SW", "BURGERS @ 5TH / GOLD", "500 GOLD AVE SW", id="symbols"),
        pytest.param("SALT + SMOKE! - 9 MAIN ST", "SALT + SMOKE!", "9 MAIN ST", id="punctuation"),
        pytest.param("7 - ELEVEN #3 - 123 MAIN ST NE", "7 - ELEVEN #3", "123 MAIN ST NE", id="dash_in_name"),
    ],
)
def test_S1_any_name(header: str, name: str, address: str) -> None:  # noqa: N802 - test ID keeps its code
    """A header reads by its position above the column header, whatever characters the name holds."""
    assert places(header) == [(name, address)]


def test_S2_unreadable_header() -> None:  # noqa: N802 - test ID keeps its code
    """A line above a column header that is not 'NAME - ADDRESS' raises, quoting it, instead of reusing the last place."""
    page = f"GOOD CAFE - 1 MAIN ST\n{COLUMNS}\n{ROW}\n\nNO ADDRESS HERE\n{COLUMNS}\n{ROW}"
    with pytest.raises(SummaryLayoutError, match="'NO ADDRESS HERE'"):
        read_summary([page])


def test_S3_orphan_row() -> None:  # noqa: N802 - test ID keeps its code
    """A row before any place header raises, quoting the row (the Nov 2026 crash was a bare TypeError)."""
    with pytest.raises(SummaryLayoutError, match=r"^week\.pdf: .*RT-FOODEST-107750-2026"):
        read_summary([f"{PERMIT}\n{ROW}"], "week.pdf")


def test_S4_split_header() -> None:  # noqa: N802 - test ID keeps its code
    """A place header at the foot of one page still names the rows under the column header atop the next."""
    assert [r["establishment"]["name"] for r in read_summary(["GOOD CAFE - 1 MAIN ST\n\n", f"{COLUMNS}\n{ROW}"])] == [
        "GOOD CAFE"
    ]
