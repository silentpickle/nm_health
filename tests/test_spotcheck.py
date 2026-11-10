# Copyright (c) 2026 nm_health contributors
"""The LLM spot-check packet: sampling, the site's statements, cutting the city's records, and the document."""

from dataclasses import replace

from nm_health.feed import FeedRecord
from nm_health.model import Inspection, Violation
from nm_health.spotcheck import (
    PROMPT,
    RANDOM_REASON,
    SAMPLES,
    Sample,
    Sources,
    choose,
    claims,
    detail_block,
    excerpts,
    packet,
    summary_block,
)
from nm_health.viewmodel import Place, build_place

APPROVED = "Approved"
CLOSED = "Closure Re-Inspection Required"
REPORT = "2026-10-25_2026-10-31_abc.pdf"
SEED = 7
SEEDS_TRIED = 20
ROACHES = Violation("Pest Control", "Controlling Pests", "", "Observed live roaches.", ("roaches",), "live")
TEXT = (
    "NAAN & DOSA - 6501 WYOMING BLVD NE, B\n"
    "Inspection Date     Inspection ID Number     Inspection Type     Inspection Status    Page #\n"
    "Food Establishment (Permit # - PT1) - Operational Status - Open\n"
    "  10/28/2026    CAC-1    Corrective Action Compliance    Approved    Pg. 2\n"
    "  10/27/2026    PT1    Routine Food Establishment Inspection    Closure Re-Inspection Required    Pg. 2\n"
    "\n"
    "\fNAAN & DOSA - 6501 WYOMING BLVD NE, B\n"
    "Food Establishment Class C\n"
    "Date: 10/28/2026 - #: CAC-1 - Inspection Result: Approved\n"
    "Corrective action taken. Call 505-768-2738.\n"
    "NAAN & DOSA - 6501 WYOMING BLVD NE, B\n"
    "Food Establishment Class C\n"
    "Date: 10/27/2026 - #: PT1 - Inspection Result: Closure Re-Inspection Required\n"
    "Violation: Pest Control\n"
    "\fcontinued on the next page\n"
)
CAC_DETAILS = (
    "NAAN & DOSA - 6501 WYOMING BLVD NE, B\n"
    "Food Establishment Class C\n"
    "Date: 10/28/2026 - #: CAC-1 - Inspection Result: Approved\n"
    "Corrective action taken. Call 505-768-2738.\n"
)


def visit(day: str, status: str, number: str, *violations: Violation, name: str = "TEST CAFE") -> Inspection:
    """One inspection with notes from the test report."""
    return Inspection(
        inspection_id=number,
        date=day,
        kind="Routine Food Establishment Inspection",
        status=status,
        name=name,
        address="100 CENTRAL AVE SW",
        permit_number="PT1",
        permit_type=None,
        report_file=REPORT,
        page=1,
        violations=violations,
    )


def place(name: str, *inspections: Inspection) -> Place:
    """A place named `name` from these inspections."""
    return build_place(name.lower(), [replace(i, name=name) for i in inspections])


# ---------- Sampling ----------

REOPENED = place("REOPENED", visit("2026-10-01", CLOSED, "A"), visit("2026-10-03", APPROVED, "B"))
CLOSED_NOW = place("CLOSED", visit("2026-10-02", CLOSED, "C"))
PESTS = place("PESTS", visit("2026-10-02", APPROVED, "D", ROACHES))
PLAIN = place("PLAIN", visit("2026-10-02", APPROVED, "E"))
FEED_ONLY = place("FEED ONLY", replace(visit("2026-10-02", APPROVED, "F"), has_details=False, report_file=""))


def test_choose_takes_one_hard_case_each_then_random() -> None:
    """A place per hard case that has one, never the same place twice, filled up at random; the seed repeats it."""
    places = [REOPENED, CLOSED_NOW, PESTS, PLAIN, FEED_ONLY]
    picked = choose(places, len(places), SEED)
    reasons = {s.reason: s.place.name for s in picked}
    assert reasons[SAMPLES[0][0]] == "REOPENED"
    assert reasons["closed today"] == "CLOSED"
    assert reasons["roaches or rodents cited"] == "PESTS"
    assert len({s.place.name for s in picked}) == len(picked) == len(places)
    assert RANDOM_REASON in reasons
    assert choose(places, len(places), SEED) == picked


def test_choose_prefers_places_with_notes_and_respects_the_count() -> None:
    """Two places reopened after a closure: whatever the seed, the one with notes on file is picked."""
    no_notes = place(
        "NO NOTES",
        *(
            replace(i, has_details=False, report_file="")
            for i in (visit("2026-10-01", CLOSED, "G"), visit("2026-10-03", APPROVED, "H"))
        ),
    )
    picks = {seed: choose([no_notes, REOPENED], 1, seed) for seed in range(SEEDS_TRIED)}
    assert all(picked == [Sample(SAMPLES[0][0], REOPENED)] for picked in picks.values())


# ---------- Statements ----------


def test_claims_cover_status_closure_pests_and_every_inspection() -> None:
    """Status today, the flag, the closure length, the pest reading and one line per inspection."""
    found = claims(place("REOPENED", visit("2026-10-01", CLOSED, "A", ROACHES), visit("2026-10-03", APPROVED, "B")))
    assert found[1] == "Status today: Open · Approved, per the Oct 3, 2026 inspection."
    assert "List flag: Closed 2 days, reopened Oct 3." in found
    assert "Closed 2 days: Oct 1 to Oct 3, 2026, reopened as Approved." in found
    assert '2026-10-01: Roaches, live, quoting the inspector: "Observed live roaches."' in found
    assert found[-1] == (
        "Inspection Oct 1, 2026: Closure Re-Inspection Required (Routine Food Establishment Inspection); "
        "1 violations listed in the weekly report."
    )


# ---------- The city's records ----------


def test_detail_block_runs_to_the_next_inspection_and_across_pages() -> None:
    """From the place's name to the next inspection's; the last one runs to the end of the text."""
    assert (detail_block(TEXT, "CAC-1") or "").lstrip("\f") == CAC_DETAILS
    last = detail_block(TEXT, "PT1")
    assert last is not None
    assert last.endswith("continued on the next page\n")
    assert detail_block(TEXT, "NOT-THERE") is None


def test_summary_block_is_the_permit_paragraph() -> None:
    """The place's permit line with every row under it."""
    block = summary_block(TEXT, "PT1")
    assert block is not None
    assert block.startswith("NAAN & DOSA")
    assert "Operational Status - Open" in block
    assert "CAC-1" in block


def test_excerpts_fall_back_to_the_recorded_page() -> None:
    """An inspection whose ID isn't in the text (a made-up legacy ID) gets its recorded page."""
    legacy = replace(visit("2026-10-27", CLOSED, "legacy-9"), page=2)
    ((heading, block),) = excerpts(legacy, TEXT)
    assert heading == f"{REPORT}: page 2"
    assert block.startswith("NAAN & DOSA")


# ---------- The packet ----------


def test_packet_holds_prompt_rules_statements_and_redacted_records() -> None:
    """The prompt, the rules, numbered statements, feed rows, and PDF text with phone numbers removed."""
    cac = replace(visit("2026-10-28", APPROVED, "CAC-1"), time="15:00")
    sample = Sample("picked for the test", place("NAAN & DOSA", cac))
    record = FeedRecord(
        "CAC-1", "2026-10-28", "Corrective", APPROVED, "NAAN & DOSA", None, "6501 WYOMING", None, None, 0, None, "15:00"
    )
    text = packet([sample], Sources({REPORT: TEXT}, {("CAC-1", "2026-10-28"): record}), SEED, "RULES")
    assert PROMPT in text
    assert "RULES" in text
    assert f"--seed {SEED}" in text
    assert "## Place 1: NAAN & DOSA (picked for the test)" in text
    assert "1.2. Status today: Open · Approved, per the Oct 28, 2026, 3:00 pm inspection." in text
    assert "- CAC-1 · 2026-10-28 15:00 · Corrective · Approved · violations: 0" in text
    assert "Call [phone removed]." in text
    assert "505-768-2738" not in text
