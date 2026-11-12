# Copyright (c) 2026 nm_health contributors
"""Which records make one place: the grouping, pinned end to end (characterization test).

One fixture holds a pair of records for every identity case in docs/place-identity.md. The golden is everything the
site derives from the grouping: places.json, the All time page, and every place page.

Regenerate only for a deliberate behaviour change, in that change's own commit:
    UPDATE_GOLDEN=1 uv run pytest tests/test_identity.py
"""

import os
from dataclasses import replace
from datetime import date
from pathlib import Path

from nm_health.model import Inspection
from nm_health.rebuild import Rebuilt, Report
from nm_health.site import places_json
from nm_health.site_html import site_data
from nm_health.site_pages import ALL_RANGE, place_page, range_page
from tests.test_archive import make_settings
from tests.test_viewmodel import CLOSED, FAILED, visit

TODAY = date(2026, 11, 9)
GOLDEN = Path(__file__).resolve().parent / "golden"
LEGACY_2021 = Report("2021-11-06_2021-11-12_abc.pdf", "abc", "2021-11-06", "2021-11-12", "test", "x", "legacy", 1)
LEGACY_2025 = Report("2025-01-27_2025-01-31_abc.pdf", "abc", "2025-01-27", "2025-01-31", "test", "x", "legacy", 1)
OCTOBER = Report("2026-10-25_2026-10-31_abc.pdf", "abc", "2026-10-25", "2026-10-31", "test", "x", "current", 1)
NOVEMBER = Report("2026-11-01_2026-11-07_abc.pdf", "abc", "2026-11-01", "2026-11-07", "test", "x", "current", 1)
CURLY_APOSTROPHE = "\u2019"
REPORTS = (LEGACY_2021, LEGACY_2025, OCTOBER, NOVEMBER)


def rec(  # noqa: PLR0913 - one fixture row: every field that decides identity, by name
    day: str,
    name: str,
    address: str,
    permit: str | None,
    source: Report,
    *,
    status: str = "Approved",
    number: str = "",
) -> Inspection:
    """One inspection as a report printed it; `number` defaults to a new-style ID (not a permit)."""
    found = visit(day, status=status, number=number or f"RT-FOODEST-{day}-{name[:3]}")
    return replace(found, name=name, address=address, permit_number=permit, report_file=source.file)


def records() -> tuple[Inspection, ...]:
    """A pair (or more) of records for each identity case."""
    return (
        # Same permit, same address, unrelated names: the owner's name printed for the re-inspection.
        rec("2026-10-30", "El Branco Restaurant", "100 Coors AVE SW", "FOODEST-1", OCTOBER, status=FAILED),
        rec("2026-11-03", "Maria Cabrera", "100 Coors AVE SW", "FOODEST-1", NOVEMBER),
        # The same, had the first been a closure: the merged place reopened.
        rec("2026-10-30", "Shut Cafe", "200 Main ST NE", "FOODEST-2", OCTOBER, status=CLOSED),
        rec("2026-11-03", "Shut Cafe LLC Owner", "200 Main ST NE", "FOODEST-2", NOVEMBER),
        # One key, several permits inspected the same day (a grocery's departments).
        rec("2026-10-27", "ALBERTSONS #911", "300 Juan Tabo BLVD NE", "PT0000010", OCTOBER, status=CLOSED),
        rec("2026-10-27", "ALBERTSONS #911", "300 Juan Tabo BLVD NE", "PT0000011", OCTOBER),
        # Same address, different permits, different names: two businesses in one centre.
        rec("2026-10-26", "TWISTERS #14", "425 Eubank BLVD NE", "PT0000020", OCTOBER),
        rec("2026-11-04", "WINGSTOP 714", "425 Eubank BLVD NE", "PT0000021", NOVEMBER),
        # Listed side by side in one report, no permits (old layout): two operations.
        rec("2025-01-29", "Sheraton - Bar", "2910 Yale BLVD SE", None, LEGACY_2025, number="legacy-a"),
        rec("2025-01-29", "Sheraton - Kitchen", "2910 Yale BLVD SE", None, LEGACY_2025, number="legacy-b"),
        # Same address, no permit on one side: can't tell.
        rec("2025-01-30", "Taco Bell", "4901 Gibson BLVD SE", None, LEGACY_2025, number="legacy-c"),
        rec("2026-10-27", "TACO BELL 2926", "4901 Gibson BLVD SE", "PT0000030", OCTOBER, number="PT0000030"),
        # Same name, the address differs only by quadrant: can't tell.
        rec("2021-11-10", "GOOD FELLAS PIZZERIA", "5844 Osuna RD NW", None, LEGACY_2021, number="legacy-d"),
        rec("2026-10-28", "Good Fellas Pizzeria", "5844 Osuna RD NE", "PT0000040", OCTOBER),
        # Same permit at two addresses (a misfiled summary row): can't tell, never merged.
        rec("2026-10-29", "Fuel Ignited by Sparks LLC", "9250 Golf Course RD NW, B", "PT0000050", OCTOBER),
        rec("2026-11-05", "PAPA JOHNS PIZZA", "9500 Montgomery BLVD NE, 11", "PT0000050", NOVEMBER),
        # Same permit, same address, the name spelled with and without an apostrophe.
        rec(
            "2026-10-28",
            f"PAPA JOHN{CURLY_APOSTROPHE}S PIZZA",
            "7000 Lomas BLVD NE",
            "PT0000060",
            OCTOBER,
            number="PT0000060",
        ),
        rec("2026-11-02", "PAPA JOHNS PIZZA", "7000 Lomas BLVD NE", "PT0000060", NOVEMBER),
        # An ordinary place, one name throughout.
        rec("2026-10-26", "PLAIN DINER", "1 Central AVE SW", "PT0000070", OCTOBER),
        rec("2026-11-02", "PLAIN DINER", "1 Central AVE SW", "PT0000070", NOVEMBER),
    )


def check_golden(name: str, actual: str) -> None:
    """Compare against the committed snapshot, writing it first when UPDATE_GOLDEN is set."""
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(actual, encoding="utf-8")
    assert actual == path.read_text(encoding="utf-8")


def test_grouping_unchanged(tmp_path: Path) -> None:
    """places.json, the All time page and every place page, for the identity fixture, match the snapshot."""
    data = site_data(Rebuilt(records(), REPORTS), make_settings(tmp_path), TODAY)
    pages = [f"=== {p.slug}\n{place_page(data, p).body}" for p in data.places]
    check_golden("identity_places.json", places_json(data) + "\n")
    check_golden("identity_pages.html", range_page(data, ALL_RANGE).body + "\n" + "\n".join(pages) + "\n")
