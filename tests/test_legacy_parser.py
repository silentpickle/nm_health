# Copyright (c) 2026 nm_health contributors
"""The pre-2025 layout: establishments, sub-permits, statuses, code-line items, pages."""

from nm_health.legacy_parser import is_legacy, parse_legacy

REPORT = """\
                    Consumer Health Protection Inspections Performed 5/4/2024 - 5/10/2024
                       Report amended on 05/15/2024 due to clerical errors
TIA BETTY BLUES - 1248 SAN MATEO BLVD SE
  Description - TIA BETTY BLUES (Food Service Establishment)
  Activity Date - 05/08/2024 (Service - ROUTINE FOOD INSPECTION / Result - IN COMPLIANCE / Action - APPROVED

   09 OUT OF COMPLIANCE
    S36 Insects, rodents, and animals not present
     6-202.15 Outer Openings, Protected

     OBSERVED SCREEN DOORS OPEN.
     6-501.111 Controlling Pests
     OBSERVED TWO DEAD AMERICAN ROACHES.
COSTCO WHOLESALE CORPORATION - 500 EUBANK BLVD SE
 Description - COSTCO FOOD COURT (Food Service Establishment)
  Activity Date - 05/10/2024 (Service - HIGH RISK / Result - IN COMPLIANCE / Action - APPROVED

  Description - COSTCO BAKERY (Retail-Bakery)
  Activity Date - 05/10/2024 (Service - ROUTINE FOOD INSPECTION / Result - IN COMPLIANCE / Action - APPROVED
\f                                                                  Page 2 of 3
QUALITY INN & SUITES - 1315 MENAUL BLVD NE
 Description - QUALITY INN & SUITES FOOD (Food Service Establishment)
  Activity Date - 05/08/2024 (Service - ROUTINE FOOD INSPECTION / Result - IMMEDIATE CLOSURE / Action - UNSATISFACTORY
    S56 Immediate Closure - Imminent Health Hazard
     IMMEDIATE CLOSURE DUE TO NO WATER INSIDE FACILITY
"""


def test_detects_layout() -> None:
    """Only the old layout has Activity Date lines."""
    assert is_legacy(REPORT)
    assert not is_legacy("Date: 10/29/2026 - #: PT1 - Inspection Result: Approved")


def test_parses_every_inspection() -> None:
    """Four inspections: one with two code items, two Costco sub-permits, and a closure on page 2."""
    tia, food_court, bakery, quality = parse_legacy(REPORT, "r.pdf")

    assert (tia.name, tia.address, tia.date, tia.status) == (
        "TIA BETTY BLUES",
        "1248 SAN MATEO BLVD SE",
        "2024-05-08",
        "Approved",
    )
    assert tia.kind == "Routine Food Inspection"
    assert [(x.item, x.observation) for x in tia.violations] == [
        ("6-202.15 Outer Openings, Protected", "OBSERVED SCREEN DOORS OPEN."),
        ("6-501.111 Controlling Pests", "OBSERVED TWO DEAD AMERICAN ROACHES."),
    ]
    assert {x.category for x in tia.violations} == {"S36 Insects, rodents, and animals not present"}

    assert (food_court.name, food_court.permit_type) == ("COSTCO WHOLESALE CORPORATION", "Food Service Establishment")
    assert (bakery.name, bakery.permit_type) == ("COSTCO WHOLESALE CORPORATION", "Retail-Bakery")
    assert food_court.inspection_id == "legacy-2024-05-10-costco-wholesale-corporation-500-eubank-blvd-se"
    assert bakery.inspection_id == f"{food_court.inspection_id}-2"
    assert food_court.violations == bakery.violations == ()

    assert quality.status == "Unsatisfactory - Immediate Closure"
    assert quality.page == 2
    assert quality.violations[0].observation == "IMMEDIATE CLOSURE DUE TO NO WATER INSIDE FACILITY"
    assert {i.report_file for i in (tia, food_court, bakery, quality)} == {"r.pdf"}


def test_stray_lines_before_any_inspection_ignored() -> None:
    """Violations, text and malformed Activity lines with no inspection open are dropped, not crashes."""
    text = (
        "    S14 Food-contact surfaces: cleaned and sanitized\n"
        "     OBSERVED SOMETHING.\n"
        "NO DATE CAFE - 1 MAIN ST NE\n"
        "  Description - NO DATE CAFE (Food Service Establishment)\n"
        "  Activity Date - sometime (Service - ROUTINE)\n"
        "    S14 Food-contact surfaces: cleaned and sanitized\n"
    )
    assert parse_legacy(text, "r.pdf") == []
