# Copyright (c) 2026 nm_health contributors
"""Which records make one place: the grouping, pinned end to end (characterization test).

One fixture holds a pair of records for every identity case in docs/place-identity.md. The golden is everything the
site derives from the grouping: places.json, the All time page, and every place page.

Regenerate only for a deliberate behaviour change, in that change's own commit:
    UPDATE_GOLDEN=1 uv run pytest tests/test_identity.py
"""

import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from nm_health.audit import audit_data, check_place_identity
from nm_health.identity import CANT_TELL, DIFFERENT, SAME, Key, establishment_slug, match
from nm_health.model import Inspection
from nm_health.rebuild import Rebuilt, Report
from nm_health.site import FLAG_MAYBE_SAME, FLAG_MERGED_BY_PERMIT, places_json
from nm_health.site_html import site_data
from nm_health.site_pages import ALL_RANGE, place_page, range_page
from nm_health.spotcheck import claims
from nm_health.viewmodel import Place, covered_days, group_places, maybe_same_text, reopened_flag
from tests.test_archive import make_settings
from tests.test_viewmodel import CLOSED, FAILED, visit

TODAY = date(2026, 11, 9)
GOLDEN = Path(__file__).resolve().parent / "golden"
LEGACY_2021 = Report("2021-11-06_2021-11-12_abc.pdf", "abc", "2021-11-06", "2021-11-12", "test", "x", "legacy", 1)
LEGACY_2025 = Report("2025-01-27_2025-01-31_abc.pdf", "abc", "2025-01-27", "2025-01-31", "test", "x", "legacy", 1)
OCTOBER = Report("2026-10-25_2026-10-31_abc.pdf", "abc", "2026-10-25", "2026-10-31", "test", "x", "current", 1)
NOVEMBER = Report("2026-11-01_2026-11-07_abc.pdf", "abc", "2026-11-01", "2026-11-07", "test", "x", "current", 1)
CURLY_APOSTROPHE = "\u2019"
EL_BRANCO = "El Branco Restaurant"
FLAGS_INDEX = 7  # places.json row: [slug, name, legal, address, strip, history, more, flags, ...]
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
    feed_name: str | None = None,
) -> Inspection:
    """One inspection as a report printed it; `number` defaults to a new-style ID (not a permit)."""
    found = visit(day, status=status, number=number or f"RT-FOODEST-{day}-{name[:3]}")
    return replace(
        found, name=name, address=address, permit_number=permit, report_file=source.file, feed_name=feed_name
    )


def records() -> tuple[Inspection, ...]:
    """A pair (or more) of records for each identity case."""
    return (
        # Same permit, same address, unrelated names: the owner's name printed for the re-inspection.
        rec("2026-10-30", "El Branco Restaurant", "100 Coors AVE SW", "FOODEST-1", OCTOBER, status=FAILED),
        rec("2026-11-03", "Maria Cabrera", "100 Coors AVE SW", "FOODEST-1", NOVEMBER, feed_name=EL_BRANCO),
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


# ---------- Rules, names and the review marker ----------


def key(*inspections: Inspection) -> Key:
    """One name + address key."""
    first = inspections[0]
    return Key(establishment_slug(first.name, first.address), inspections)


def places_of(*inspections: Inspection) -> list[Place]:
    """The places the site would build from these inspections."""
    return group_places(inspections)


EL_BRANCO_FAILED = rec("2026-10-30", EL_BRANCO, "100 Coors AVE SW", "FOODEST-1", OCTOBER, status=FAILED)
MARIA_CABRERA = rec("2026-11-03", "Maria Cabrera", "100 Coors AVE SW", "FOODEST-1", NOVEMBER, feed_name=EL_BRANCO)


def test_M1_shared_permit() -> None:  # noqa: N802 - test ID keeps its code
    """The same permit at the same address is the same place, whatever the names."""
    assert match(key(EL_BRANCO_FAILED), key(MARIA_CABRERA)) == SAME


@pytest.mark.parametrize(
    ("other", "expected"),
    [
        pytest.param(replace(MARIA_CABRERA, address="101 Coors AVE SW"), CANT_TELL, id="other_address"),
        pytest.param(replace(MARIA_CABRERA, permit_number="FOODEST-9"), DIFFERENT, id="other_permit"),
        pytest.param(replace(MARIA_CABRERA, permit_number=None), CANT_TELL, id="no_permit"),
    ],
)
def test_M1_shared_permit_edges(other: Inspection, expected: str) -> None:  # noqa: N802 - test ID keeps its code
    """Only both together join: the permit elsewhere (M2) or no permit (M7) can't tell; another permit (M6) differs."""
    assert match(key(EL_BRANCO_FAILED), key(other)) == expected


def test_el_branco_merged_and_resolved() -> None:
    """The owner's name on the re-inspection: one place, shown under the trade name, the failure resolved."""
    (merged,) = places_of(EL_BRANCO_FAILED, MARIA_CABRERA)
    assert (merged.slug, merged.name) == ("el-branco-restaurant-100-coors-ave-sw", EL_BRANCO)
    assert [i.name for i in merged.also_listed] == ["Maria Cabrera"]
    assert merged.merged_by_permit
    assert [(i.date, i.status) for i in merged.standing] == [("2026-11-03", "Approved")]


def test_display_name_prefers_feed_dba() -> None:
    """The feed's trade name picks among printed names; without it, the most recent printed name, as before."""
    assert places_of(EL_BRANCO_FAILED, MARIA_CABRERA)[0].name == EL_BRANCO
    assert places_of(EL_BRANCO_FAILED, replace(MARIA_CABRERA, feed_name=None))[0].name == "Maria Cabrera"
    assert places_of(EL_BRANCO_FAILED, replace(MARIA_CABRERA, feed_name="Other Name"))[0].name == "Maria Cabrera"


def test_merged_closure_reopens() -> None:
    """Had the Oct 30 result been a closure, the merged place reopened Nov 3 (both weeks on file)."""
    (merged,) = places_of(replace(EL_BRANCO_FAILED, status=CLOSED), MARIA_CABRERA)
    covered = covered_days((OCTOBER, NOVEMBER))
    assert reopened_flag(merged, covered) == "Closed 4 days, reopened Nov 3"
    assert not merged.closure_in_force


def test_punctuation_only_not_marked() -> None:
    """PAPA JOHN'S and PAPA JOHNS under one permit are one place with nothing to review."""
    curly = rec("2026-10-28", f"PAPA JOHN{CURLY_APOSTROPHE}S PIZZA", "7000 Lomas BLVD NE", "PT0000060", OCTOBER)
    plain = rec("2026-11-02", "PAPA JOHNS PIZZA", "7000 Lomas BLVD NE", "PT0000060", NOVEMBER)
    (merged,) = places_of(curly, plain)
    assert (merged.also_listed, merged.merged_by_permit) == ((), False)


def test_review_marker_in_places_json_audit_and_spotcheck(tmp_path: Path) -> None:
    """The merge is marked where it will be found again: places.json bit 16, the audit, the spot-check packet."""
    data = site_data(Rebuilt((EL_BRANCO_FAILED, MARIA_CABRERA), REPORTS), make_settings(tmp_path), TODAY)
    (row,) = json.loads(places_json(data))["places"]
    assert row[FLAGS_INDEX] & FLAG_MERGED_BY_PERMIT
    result = check_place_identity(audit_data((EL_BRANCO_FAILED, MARIA_CABRERA), (), ()))
    assert result.disagreements == (
        "El Branco Restaurant, 100 COORS AVE SW (permit FOODEST-1): the reports also print Maria Cabrera (2026-11-03)",
    )
    (merged,) = data.places
    assert any("merged by permit; names differ" in line for line in claims(merged, data.covered))


# ---------- CAN'T TELL ----------

TACO_LEGACY = rec("2025-01-30", "Taco Bell", "4901 Gibson BLVD SE", None, LEGACY_2025, number="legacy-c")
TACO_NOW = rec("2026-10-27", "TACO BELL 2926", "4901 Gibson BLVD SE", "PT0000030", OCTOBER, number="PT0000030")


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        pytest.param(
            rec("2026-10-29", "Fuel Ignited", "9250 Golf Course RD NW, B", "PT0000050", OCTOBER),
            rec("2026-11-05", "PAPA JOHNS PIZZA", "9500 Montgomery BLVD NE, 11", "PT0000050", NOVEMBER),
            CANT_TELL,
            id="M2_permit_elsewhere",
        ),
        pytest.param(
            rec("2021-11-10", "GOOD FELLAS PIZZERIA", "5844 Osuna RD NW", None, LEGACY_2021, number="legacy-d"),
            rec("2026-10-28", "Good Fellas Pizzeria", "5844 Osuna RD NE", "PT0000040", OCTOBER),
            CANT_TELL,
            id="M3_quadrant_typo",
        ),
        pytest.param(
            rec("2021-11-10", "GOOD FELLAS PIZZERIA", "5845 Osuna RD NW", None, LEGACY_2021, number="legacy-d"),
            rec("2026-10-28", "Good Fellas Pizzeria", "5844 Osuna RD NE", "PT0000040", OCTOBER),
            DIFFERENT,
            id="M4_other_address",
        ),
        pytest.param(
            rec("2025-01-29", "Sheraton - Bar", "2910 Yale BLVD SE", None, LEGACY_2025, number="legacy-a"),
            rec("2025-01-29", "Sheraton - Kitchen", "2910 Yale BLVD SE", None, LEGACY_2025, number="legacy-b"),
            DIFFERENT,
            id="M5_listed_together",
        ),
        pytest.param(
            rec("2026-10-26", "TWISTERS #14", "425 Eubank BLVD NE", "PT0000020", OCTOBER),
            rec("2026-11-04", "WINGSTOP 714", "425 Eubank BLVD NE", "PT0000021", NOVEMBER),
            DIFFERENT,
            id="M6_distinct_permits",
        ),
        pytest.param(TACO_LEGACY, TACO_NOW, CANT_TELL, id="M7_no_permit"),
        pytest.param(replace(TACO_LEGACY, report_file="", has_details=False), TACO_NOW, DIFFERENT, id="M8_feed_only"),
        pytest.param(
            replace(MARIA_CABRERA, report_file="", has_details=False), EL_BRANCO_FAILED, SAME, id="M8_feed_permit"
        ),
    ],
)
def test_matcher_rules(a: Inspection, b: Inspection, expected: str) -> None:
    """Each rule's case decides as docs/place-identity.md section 3.2 says, both ways round."""
    assert match(key(a), key(b)) == match(key(b), key(a)) == expected


def test_cant_tell_kept_apart_and_flagged(tmp_path: Path) -> None:
    """Two places, each naming the other: row flag, places.json bit 8, the audit and the spot-check packet."""
    data = site_data(Rebuilt((TACO_LEGACY, TACO_NOW), REPORTS), make_settings(tmp_path), TODAY)
    legacy, now = sorted(data.places, key=lambda p: p.latest.date)
    assert legacy.maybe_same == ((now.slug, now.name),)
    assert now.maybe_same == ((legacy.slug, legacy.name),)
    assert maybe_same_text(now) == "May be the same business as Taco Bell"
    rows = json.loads(places_json(data))["places"]
    assert all(row[FLAGS_INDEX] & FLAG_MAYBE_SAME for row in rows)
    result = check_place_identity(audit_data((TACO_LEGACY, TACO_NOW), (), ()))
    assert result.disagreements == ("can't tell: TACO BELL 2926, 4901 GIBSON BLVD SE / Taco Bell, 4901 GIBSON BLVD SE",)
    assert any("may be the same business as Taco Bell" in line for line in claims(now, data.covered))


def test_cant_tell_never_joins_through_a_merge() -> None:
    """A key that can't be told apart from one member of a merged place stays its own place."""
    merged_a = rec("2026-10-30", "El Branco", "4901 Gibson BLVD SE", "PT0000030", OCTOBER)
    places = places_of(TACO_LEGACY, TACO_NOW, merged_a)
    assert len(places) == 2
    joined = next(p for p in places if len(p.inspections) == 2)
    assert [name for _, name in joined.maybe_same] == ["Taco Bell"]


def test_feed_only_names_never_shown_or_listed() -> None:
    """In the audit, a feed-only record joined by permit lends neither the shown name nor an "also listed" name."""
    feed_row = replace(MARIA_CABRERA, name="Feed Company LLC", report_file="", has_details=False, feed_name="X")
    (merged,) = places_of(EL_BRANCO_FAILED, feed_row)
    assert (merged.name, merged.also_listed) == (EL_BRANCO, ())
