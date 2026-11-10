# Copyright (c) 2026 nm_health contributors
"""The assumption audit: reading permit blocks, each check on made-up records, and the printed report."""

from dataclasses import replace
from datetime import date

import pytest

from nm_health.audit import (
    EXAMPLES_MAX,
    AuditData,
    CheckResult,
    PermitBlock,
    audit_data,
    check_feed_status,
    check_feed_times,
    check_follow_up_order,
    check_operational_status,
    check_same_minute,
    check_untimed_order,
    permit_blocks,
    report_lines,
)
from nm_health.feed import FeedRecord
from nm_health.model import Inspection

APPROVED = "Approved"
CONDITIONAL = "Conditional Approved"
CLOSED = "Closure Re-Inspection Required"
FAILED = "Unsatisfactory Re-Inspection required"
FOLLOW_UP = "Corrective Action Compliance"
REPORT = "2026-10-25_2026-10-31_abc.pdf"
SUMMARY = """NAAN & DOSA - 6501 WYOMING BLVD NE, B
Inspection Date     Inspection ID Number               Inspection Type                         Inspection Status    Page #
Food Establishment (Permit # - PT0156723) - Operational Status \u2013 Open
  10/28/2026       CAC-Food-102040-2026         Corrective Action Compliance                     Approved      Pg. 27
  10/27/2026            PT0156723           Routine Food Establishment Inspection      Closure Re-Inspection Required   Pg. 28

RED ROOF INN - 1801 YALE BLVD SE
Retail Food Establishment- EHD (Permit # - PT0000002) - Operational Status - Closed
  10/28/2026            PT0000002           Routine Retail Food Inspection      Closure Re-Inspection Required   Pg. 30
                                                                                              Page 3 of 44
  10/29/2026            PT0000003           Routine Retail Food Inspection      Approved   Pg. 31
Food Establishment (Permit # - PT0000009) - Operational Status - Open
"""
AFTER_PAGE_BREAK = ("PT0000003", "2026-10-29")


def visit(day: str, status: str, number: str, time: str | None = None, **changes: object) -> Inspection:
    """One inspection of the test place."""
    found = Inspection(
        inspection_id=number,
        date=day,
        kind="Routine Food Establishment Inspection",
        status=status,
        name="TEST CAFE",
        address="100 CENTRAL AVE SW",
        permit_number=None,
        permit_type=None,
        report_file=REPORT,
        page=1,
        time=time,
    )
    return replace(found, **changes)  # type: ignore[arg-type]


def data(
    *inspections: Inspection, blocks: tuple[PermitBlock, ...] = (), feed: tuple[FeedRecord, ...] = ()
) -> AuditData:
    """Audit data for these records."""
    return audit_data(inspections, blocks, feed)


def block(state: str, *rows: Inspection) -> PermitBlock:
    """A permit block listing these inspections."""
    return PermitBlock(REPORT, "PT1", state, tuple((i.inspection_id, i.date) for i in rows))


# ---------- Reading permit blocks ----------


def test_permit_blocks_read_the_city_words() -> None:
    """Both dash styles; rows after a page break and a permit with no rows are dropped, never misfiled."""
    naan, red_roof = permit_blocks(SUMMARY, REPORT)
    assert naan == PermitBlock(
        REPORT, "PT0156723", "Open", (("CAC-Food-102040-2026", "2026-10-28"), ("PT0156723", "2026-10-27"))
    )
    assert (red_roof.permit, red_roof.closed, red_roof.rows) == ("PT0000002", True, (("PT0000002", "2026-10-28"),))
    assert AFTER_PAGE_BREAK not in naan.rows + red_roof.rows


# ---------- Checks ----------


def test_operational_status_agrees_and_disagrees() -> None:
    """Unsatisfactory listed Open agrees; a closure listed Open disagrees and names the later reopening."""
    failed = visit("2026-10-01", FAILED, "A", "10:00")
    closure = visit("2026-10-02", CLOSED, "B", "11:00")
    reopened = visit("2026-10-05", APPROVED, "C", "09:00")
    result = check_operational_status(
        data(failed, closure, reopened, blocks=(block("Open", failed), block("Open", closure)))
    )
    assert result.checked == len(["A", "B"])
    assert result.tally == (
        (f"latest {CLOSED} -> city says Open", 1),
        (f"latest {FAILED} -> city says Open", 1),
    )
    (line,) = result.disagreements
    assert line.endswith("reopened 2026-10-05 09:00 Approved on record (the PDF may have been generated after that)")


def test_operational_status_closed_without_reopening() -> None:
    """A closure listed Closed agrees; one listed Open with nothing after it is a plain disagreement."""
    closure = visit("2026-10-02", CLOSED, "B")
    agrees = check_operational_status(data(closure, blocks=(block("Closed", closure),)))
    differs = check_operational_status(data(closure, blocks=(block("Open", closure),)))
    assert (agrees.disagreements, differs.disagreements) == (
        (),
        (f"{REPORT} permit PT1: city says Open; latest listed 2026-10-02 Closure Re-Inspection Required",),
    )


@pytest.mark.parametrize(
    ("follow_up_time", "label", "flagged"),
    [
        pytest.param(None, "no feed time for one side: order can't be checked", 0, id="untimed_unchecked"),
        pytest.param("15:00", "timed, after the others", 0, id="timed_after"),
        pytest.param("09:00", "timed, before another", 1, id="timed_before"),
    ],
)
def test_follow_up_order(follow_up_time: str | None, label: str, flagged: int) -> None:
    """A corrective-action visit is checked against that day's timed routine inspection."""
    routine = visit("2026-10-27", CLOSED, "PT1", "13:00")
    follow_up = visit("2026-10-27", APPROVED, "CAC-1", follow_up_time, kind=FOLLOW_UP)
    result = check_follow_up_order(data(routine, follow_up))
    assert (result.tally, len(result.disagreements)) == (((label, 1),), flagged)


@pytest.mark.parametrize(
    ("permits", "verdict", "flagged"),
    [
        pytest.param(("PT1", "PT2"), "different permits", 0, id="separate_permits"),
        pytest.param(("PT1", "PT1"), "same permit", 1, id="same_permit"),
        pytest.param(("PT1", None), "permit not known for every record", 1, id="permit_unknown"),
    ],
)
def test_same_minute(permits: tuple[str | None, str | None], verdict: str, flagged: int) -> None:
    """A failure and a pass at one minute: separate permits agree; the same or an unknown permit needs a look."""
    first, second = permits
    closure = visit("2026-09-17", CLOSED, "RT-1", "11:30", permit_number=first)
    passed = visit("2026-09-17", CONDITIONAL, "RT-2", "11:30", permit_number=second)
    result = check_same_minute(data(closure, passed))
    assert (result.tally, len(result.disagreements)) == (((verdict, 1),), flagged)


def test_same_minute_reads_the_permit_from_an_old_style_id() -> None:
    """Routine inspections before late 2025 use the permit number as their ID."""
    closure = visit("2024-01-08", CLOSED, "PT0160313", "11:10")
    passed = visit("2024-01-08", APPROVED, "PT0160314", "11:10")
    assert check_same_minute(data(closure, passed)).tally == (("different permits", 1),)


def test_untimed_order_flags_only_a_guessed_mixed_day() -> None:
    """A pass and a failure on one day with no time is a guess; an all-pass day or a timed day is not."""
    guessed = (visit("2026-09-21", APPROVED, "A"), visit("2026-09-21", FAILED, "B"))
    timed = (visit("2026-09-22", APPROVED, "C", "14:00"), visit("2026-09-22", CLOSED, "D", "11:00"))
    calm = (visit("2026-09-23", APPROVED, "E"), visit("2026-09-23", APPROVED, "F"))
    result = check_untimed_order(data(*guessed, *timed, *calm))
    assert result.checked == len([guessed, timed, calm])
    assert result.disagreements == (
        "TEST CAFE: 2026-09-21 Approved / 2026-09-21 Unsatisfactory Re-Inspection required",
    )


def test_feed_times_flags_midnight() -> None:
    """A 00:00 time is listed and counted by year; untimed inspections aren't checked."""
    result = check_feed_times(
        data(visit("2024-05-01", APPROVED, "A", "00:00"), visit("2026-05-01", APPROVED, "B", "10:15"))
    )
    assert (result.checked, result.disagreements, result.tally) == (
        len(["A", "B"]),
        ("TEST CAFE: 2024-05-01 00:00 Approved",),
        (("00:00 in 2024", 1),),
    )


def test_feed_status_compares_matching_records() -> None:
    """Same inspection, same status (spacing and case aside) agrees; a different status disagrees."""
    inspection = visit("2026-10-27", CLOSED, "PT1")

    def record(number: str, status: str) -> FeedRecord:
        return FeedRecord(
            number, "2026-10-27", "Routine", status, "TEST CAFE", None, "100 CENTRAL", None, None, 1, None
        )

    result = check_feed_status(
        data(
            inspection,
            visit("2026-10-27", APPROVED, "PT2"),
            feed=(record("PT1", "closure  re-inspection required"), record("PT2", FAILED), record("PT9", APPROVED)),
        )
    )
    assert result.checked == len(["PT1", "PT2"])
    assert result.disagreements == (f"TEST CAFE PT2 2026-10-27: PDF Approved; feed {FAILED}",)


# ---------- Report ----------


def test_report_lines_cap_the_examples() -> None:
    """Question, count, tally, then at most EXAMPLES_MAX examples and how many more."""
    extra = 2
    result = CheckResult(
        "demo", "Is it so?", 10, tuple(f"case {n}" for n in range(EXAMPLES_MAX + extra)), (("label", 1),)
    )
    lines = report_lines([result], date(2026, 11, 10))
    assert lines[:5] == [
        "Assumption audit, 2026-11-10",
        "",
        "[demo] Is it so?",
        f"  {EXAMPLES_MAX + extra} of 10 checked disagree or need a look",
        "  label: 1",
    ]
    assert lines[-1] == f"  ... and {extra} more"
    assert len(lines) == len(["title", "blank", "question", "count", "tally", "more"]) + EXAMPLES_MAX
