# Copyright (c) 2026 nm_health contributors
"""Read the summary table: which place and permit each inspection row belongs to.

A place's header is found by position, not by the characters in its name: it is the line just above each
"Inspection Date  Inspection ID Number ..." column header (permit lines in between are passed over). Names have broken a character whitelist twice (curly
apostrophes, then parentheses); the layout has not changed. A line in that position that is not "NAME - ADDRESS", or
a row before any place, raises SummaryLayoutError instead of filing rows under the wrong place.
"""

import re
from collections.abc import Iterable, Iterator
from typing import TypedDict

COLUMN_HEADER_RE = re.compile(r"^\s*Inspection Date\s+Inspection ID Number")
# The name runs to the first " - " that is followed by a street number: "7 - ELEVEN - 123 MAIN" keeps "7 - ELEVEN".
PLACE_RE = re.compile(r"^(?P<name>\S.*?)\s+-\s+(?P<address>\d.*)$")
PERMIT_RE = re.compile(
    r"^(.*?)\(Permit\s*#\s*-\s*([A-Za-z0-9-]+)\)\s*-\s*Operational\s*Status\s*[-–]\s*([A-Za-z]+)",  # noqa: RUF001 - the PDF prints an en dash
    re.IGNORECASE,
)
ROW_RE = re.compile(
    r"^\s*(\d{2}/\d{2}/\d{4})\s+([A-Za-z0-9\-]+)\s+(.+?)\s{2,}([A-Za-z\s\-]+?)\s+(?:Pg\.\s*(\d+)|Page\s*(\d+)|(\d+))\s*$",
    re.IGNORECASE,
)
# Letterhead and table-title lines: never a permit or a row.
LETTERHEAD = (
    "City of Albuquerque",
    "Environmental Health",
    "Consumer Health",
    "Summary Table",
    "Inspection Date",
    "Page ",
    "This report includes",
)
PAGE_GROUPS = (5, 6, 7)  # ROW_RE's three spellings of the page number: "Pg. 4", "Page 4", "4"


class SummaryLayoutError(ValueError):
    """The summary table is laid out in a way the reader does not know; the message quotes the line."""


class SummaryPlace(TypedDict):
    """A place header: 'NAME - ADDRESS'."""

    name: str
    address: str


class SummaryPermit(TypedDict):
    """A permit line under a place."""

    permit_type: str
    permit_number: str
    operational_status: str


class SummaryRecord(TypedDict):
    """One inspection row, with the place and permit listed above it."""

    establishment: SummaryPlace
    permit: SummaryPermit | None
    date: str
    id_num: str
    type: str
    status: str
    page_str: str
    page_num: int | None
    raw: str


def place_from(line: str, source: str = "") -> SummaryPlace:
    """The place named by the line above a column header; `source` names the report in the error."""
    match = PLACE_RE.match(line.strip())
    if match is None:
        msg = f"{source}: Line above a column header is not 'NAME - ADDRESS': {line.strip()!r}"
        raise SummaryLayoutError(msg)
    return {"name": match["name"].strip(), "address": match["address"].strip()}


def permit_from(line: str) -> SummaryPermit | None:
    """The permit a line announces, or None when it is not a permit line."""
    match = PERMIT_RE.match(line.strip())
    if match is None:
        return None
    return {
        "permit_type": match.group(1).strip(),
        "permit_number": match.group(2).strip(),
        "operational_status": match.group(3).strip(),
    }


def record_from(
    row: re.Match[str], place: SummaryPlace | None, permit: SummaryPermit | None, source: str = ""
) -> SummaryRecord:
    """One inspection row's record; a row with no place above it is a layout error."""
    if place is None:
        msg = f"{source}: Inspection row before any place header: {row.string.strip()!r}"
        raise SummaryLayoutError(msg)
    target_pg = next((row.group(group) for group in PAGE_GROUPS if row.group(group)), "")
    return {
        "establishment": place,
        "permit": permit,
        "date": row.group(1),
        "id_num": row.group(2).strip(),
        "type": row.group(3).strip(),
        "status": row.group(4).strip(),
        "page_str": f"Pg. {target_pg}",
        "page_num": int(target_pg) if target_pg.isdigit() else None,
        "raw": row.string.strip(),
    }


def _lines(pages: Iterable[str]) -> Iterator[str]:
    """Every non-blank line of the summary pages, right-trimmed, in order."""
    for page in pages:
        yield from (line.rstrip() for line in page.split("\n") if line.strip())


def read_summary(pages: Iterable[str], source: str = "") -> list[SummaryRecord]:
    """The inspection rows of the summary pages, each with its place and the permit listed above it.

    `source` (the report's file name) starts every SummaryLayoutError message, so a failed run names the PDF.

    A permit stays in force until the next permit line, across place headers, as the prototype parser did.
    """
    records: list[SummaryRecord] = []
    place: SummaryPlace | None = None
    permit: SummaryPermit | None = None
    previous = ""
    for line in _lines(pages):
        if COLUMN_HEADER_RE.match(line):
            place = place_from(previous, source)
            continue
        line_permit = permit_from(line)
        if line_permit is not None:
            permit = line_permit
            continue
        previous = line  # permit lines are skipped: a permit may sit between a place and its column header
        if any(marker in line for marker in LETTERHEAD):
            continue
        row = ROW_RE.match(line)
        if row is not None:
            records.append(record_from(row, place, permit, source))
    return records
