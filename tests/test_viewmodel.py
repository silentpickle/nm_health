# Copyright (c) 2026 nm_health contributors
"""What the site states: redaction, pest quotes, coverage, closure lines, strip cells and the week shown."""

from dataclasses import replace
from datetime import date

import pytest

from nm_health.model import Inspection, Violation
from nm_health.rebuild import Report
from nm_health.viewmodel import (
    ELLIPSIS,
    MONTH_SPAN_DAYS,
    QUOTE_CHARS,
    WEEKS,
    Cell,
    Place,
    build_place,
    cell_code,
    cites_headline_pests,
    clock,
    closed_text,
    closure_end,
    closure_start,
    coverage_line,
    covered_days,
    group_places,
    latest_result_text,
    level,
    month_ticks,
    notice_count_text,
    permit_line_text,
    permit_lines,
    pest_reading,
    published,
    quote_for,
    recent_text,
    redact,
    reopened_flag,
    select_period,
    select_week,
    stated,
    strip_caption,
    strip_cells,
    strip_code,
    strip_label,
    strip_start,
    unbroken,
    violation_lead,
)

TODAY = date(2026, 11, 9)  # a Monday
APPROVED = "Approved"
CONDITIONAL = "Conditional Approved"
CLOSED = "Closure Re-Inspection Required"
FAILED = "Unsatisfactory Re-Inspection required"
ROACHES = Violation(
    "Pest Control",
    "Controlling Pests, If Present: Treatment",
    "",
    "Observed pests. Location: kitchen Pest Type: Cockroach Pest Condition: Live",
    ("roaches", "pest_control"),
    "live",
    (("Location", "kitchen"), ("Pest Type", "Cockroach"), ("Pest Condition", "Live")),
)
FLIES = Violation("Pest Control", "Insect Control", "", "Observed flies near the door.", ("flies",), "live")
OTHER = Violation("Plumbing", "System Maintained in Good Repair", "", "Observed leak.")
LAST_COLUMN = WEEKS - 1
NO_INSPECTION_WEEK = "." * WEEKS
STRIP_FIRST_DAY = "2025-11-11"  # 52 weeks back from TODAY, less a day


def visit(day: str, *violations: Violation, status: str = APPROVED, number: str = "", notes: bool = True) -> Inspection:
    """One inspection of the test place."""
    return Inspection(
        inspection_id=number or f"PT-{day}-{status[:4]}",
        date=day,
        kind="Routine Food Establishment Inspection",
        status=status,
        name="TEST CAFE",
        address="100 CENTRAL AVE SW",
        permit_number="PT1",
        permit_type="Food Establishment",
        report_file="2026-10-25_2026-10-31_abc.pdf" if notes else "",
        page=3 if notes else None,
        violations=violations,
        has_details=notes,
        violation_count=None if notes else len(violations),
    )


def place(*inspections: Inspection) -> Place:
    """The test place (inspections in any order)."""
    return build_place("test-cafe-100-central-ave-sw", list(inspections))


def report(start: str, end: str) -> Report:
    """An archived weekly report covering start..end."""
    return Report(f"{start}_{end}_abc.pdf", "abc", start, end, "test", end, "current", 1)


# ---------- Redaction ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "Send photos to jane.doe+ehd@cabq.gov by Friday.",
            "Send photos to [email removed] by Friday.",
            id="email_address",
        ),
        pytest.param("Call 505-768-2738 to reschedule.", "Call [phone removed] to reschedule.", id="phone_dashes"),
        pytest.param("Call (505) 768-2738.", "Call [phone removed].", id="phone_parentheses"),
        pytest.param("Call 505.768.2738 now", "Call [phone removed] now", id="phone_dots"),
        pytest.param(
            "Sanitizer at 400ppm on 11/03/26; chicken at 135 F; permit PT0144025; 2026-10-29.",
            "Sanitizer at 400ppm on 11/03/26; chicken at 135 F; permit PT0144025; 2026-10-29.",
            id="nothing_else",
        ),
        pytest.param(
            "Re-inspection RT-FOODEST-102027-2026 follows COM-FOODES-101632-2026.",
            "Re-inspection RT-FOODEST-102027-2026 follows COM-FOODES-101632-2026.",
            id="inspection_ids_kept",
        ),
    ],
)
def test_redact(text: str, expected: str) -> None:
    """Email addresses and phone numbers go; dates, temperatures, permit numbers and readings stay."""
    assert redact(text) == expected


def test_published_redacts_every_inspector_text() -> None:
    """Observation, rule and every labelled field are redacted; the form's headings are left alone."""
    raw = Violation(
        "Pest Control",
        "Controlling Pests",
        "Email ehd@cabq.gov",
        "Call 505-768-2738. Location: back",
        details=(("Location", "back, ask 505 768 2738"),),
    )
    out = published(raw)
    assert out.observation == "Call [phone removed]. Location: back"
    assert out.rule == "Email [email removed]"
    assert out.details == (("Location", "back, ask [phone removed]"),)
    assert (out.category, out.item) == (raw.category, raw.item)


# ---------- Pest quotes ----------


def test_quote_uses_labelled_fields_with_instructions_cut() -> None:
    """Only the pest fields, joined by middots; an instruction to the operator is cut off."""
    v = replace(
        ROACHES,
        details=(
            ("Location", "dry storage"),
            ("Food Items", "rice"),
            ("Pest Type", "Mouse droppings"),
            ("Number of Pests Present", "20 instructed PIC to clean and email ehd@cabq.gov"),
        ),
    )
    assert quote_for(v) == "Location: dry storage \u00b7 Pest Type: Mouse droppings \u00b7 Number of Pests Present: 20"


def test_quote_falls_back_to_the_observation_cut_on_a_word() -> None:
    """Without labelled fields the observation is quoted; past the limit it is cut on a word with an ellipsis."""
    short = replace(ROACHES, details=(), observation="Observed live roaches, call 505-768-2738.")
    assert quote_for(short) == "Observed live roaches, call [phone removed]."
    long_text = "Observed " + "roach droppings " * 20
    quote = quote_for(replace(ROACHES, details=(), observation=long_text))
    assert quote.endswith(ELLIPSIS)
    cut = quote.removesuffix(ELLIPSIS)
    assert long_text.startswith(cut)
    assert long_text[len(cut)] == " "
    assert len(quote) <= QUOTE_CHARS + len(ELLIPSIS)
    exact = "x" * QUOTE_CHARS
    assert quote_for(replace(ROACHES, details=(), observation=exact)) == exact


def test_violation_lead_stops_at_the_labelled_fields() -> None:
    """The stock sentence is shown above the fields; without fields the whole observation is."""
    assert violation_lead(ROACHES) == "Observed pests."
    assert violation_lead(OTHER) == "Observed leak."


# ---------- Coverage and closure lines ----------


@pytest.mark.parametrize(
    ("inspections", "expected"),
    [
        pytest.param(
            (visit("2026-10-01", notes=False), visit("2026-05-01", notes=False)),
            "Inspector notes on file for none of its 2 inspections in this period, so pest citations can't be shown.",
            id="no_notes",
        ),
        pytest.param(
            (visit("2026-10-01", OTHER), visit("2026-05-01", notes=False)),
            "Inspector notes on file for 1 of 2 inspections. None of those notes mention roaches or rodents.",
            id="some_notes",
        ),
        pytest.param(
            (visit("2026-10-01", ROACHES), visit("2026-05-01", OTHER)),
            "Inspector notes on file for 2 of 2 inspections.",
            id="all_notes",
        ),
        pytest.param(
            (visit("2026-10-01", notes=False),),
            "Inspector notes on file for none of its 1 inspection in this period, so pest citations can't be shown.",
            id="one_inspection",
        ),
    ],
)
def test_coverage_line(inspections: tuple[Inspection, ...], expected: str) -> None:
    """Every place states its notes coverage and never implies it is pest-free."""
    assert coverage_line(place(*inspections)) == expected


def test_closure_lines_ended_and_open() -> None:
    """An ended run names the next inspection in the city's words; an open one has no end line."""
    ended = place(
        visit("2026-03-02", status=CLOSED),
        visit("2026-03-04", status=FAILED),
        visit("2026-03-09", status=CONDITIONAL),
        visit("2026-10-01", status=CLOSED),
    )
    old, new = ended.closures
    assert closure_start(old) == f"Mar 2, 2026: {CLOSED} (2 inspections in a row with this kind of result)"
    assert closure_end(old) == f"Next inspection: {CONDITIONAL}, Mar 9, 2026."
    assert closure_start(new) == f"Oct 1, 2026: {CLOSED}"
    assert closure_end(new) is None


def test_corrective_action_recap_is_not_a_pest_citation() -> None:
    """California Del Norte, Sep 25 2026: a follow-up's notes recap the closure's mice; they aren't new citations."""
    recap = replace(visit("2026-09-25", ROACHES), kind="Corrective Action Compliance")
    recapped = place(visit("2026-09-21", ROACHES, status=CLOSED), recap)
    assert [c.date for c in recapped.pests] == ["2026-09-21"]
    assert not cites_headline_pests(recap)
    assert recapped.inspections[0].violations == recap.violations  # still listed on the timeline


def test_pest_citations_name_reading_status_and_next_approval() -> None:
    """Each citation carries the site's reading, the status that day and the next approved inspection."""
    p = place(visit("2026-10-01", ROACHES, FLIES, status=CONDITIONAL), visit("2026-10-20"))
    flies, roaches = sorted(p.pests, key=lambda c: c.kinds)
    assert (roaches.kinds, flies.kinds) == (("roaches",), ("flies",))
    assert pest_reading(roaches) == "Roaches, live"
    assert (roaches.status, roaches.cleared, roaches.index) == (CONDITIONAL, "2026-10-20", 1)
    assert p.headline_pests
    assert not place(visit("2026-10-01", FLIES)).headline_pests


@pytest.mark.parametrize(
    ("inspection", "expected"),
    [
        pytest.param(visit("2026-10-01", OTHER, OTHER), "2 violations listed", id="notes_many"),
        pytest.param(visit("2026-10-01", OTHER), "1 violation listed", id="notes_one"),
        pytest.param(
            visit("2026-10-01", OTHER, notes=False), "1 violations (inspector notes not on file)", id="feed_count"
        ),
        pytest.param(
            replace(visit("2026-10-01", notes=False), violation_count=None),
            "Unknown number of violations (inspector notes not on file)",
            id="feed_unknown",
        ),
    ],
)
def test_notice_count_text(inspection: Inspection, expected: str) -> None:
    """A This-week card says how many violations, and when the notes aren't on file."""
    assert notice_count_text(inspection) == expected


# ---------- Strip ----------


@pytest.mark.parametrize(
    ("inspections", "code"),
    [
        pytest.param((visit("2026-11-09", OTHER),), "g", id="approved_notes"),
        pytest.param((visit("2026-11-09", status=CONDITIONAL),), "y", id="conditional_notes"),
        pytest.param((visit("2026-11-09", status=CLOSED),), "r", id="closure_notes"),
        pytest.param((visit("2026-11-09", status="Non-Graded"),), "n", id="other_status"),
        pytest.param((visit("2026-11-09", notes=False),), "G", id="approved_feed"),
        pytest.param((visit("2026-11-09", status=FAILED, notes=False),), "O", id="unsatisfactory_feed"),
        pytest.param((visit("2026-11-09", ROACHES),), "1", id="approved_pests"),
        pytest.param((visit("2026-11-09", ROACHES, status=CLOSED),), "3", id="closure_pests"),
        pytest.param((visit("2026-11-09", FLIES),), "g", id="flies_unmarked"),
        pytest.param(
            (visit("2026-11-03", status=CLOSED, notes=False), visit("2026-11-05")),
            "r",
            id="worst_wins",
        ),
        pytest.param(
            (visit("2026-11-03", notes=False), visit("2026-11-05", status=CONDITIONAL, notes=False)),
            "Y",
            id="feed_week",
        ),
    ],
)
def test_strip_cell_shapes(inspections: tuple[Inspection, ...], code: str) -> None:
    """This week's cell: worst status, status-only when no notes that week, a digit when roaches/rodents cited."""
    cells = strip_cells(inspections, TODAY)
    assert cell_code(cells[LAST_COLUMN]) == code
    assert strip_code(cells) == NO_INSPECTION_WEEK[:LAST_COLUMN] + code


@pytest.mark.parametrize(
    ("day", "column"),
    [
        pytest.param("2026-11-09", LAST_COLUMN, id="today_last"),
        pytest.param("2026-11-03", LAST_COLUMN, id="six_days"),
        pytest.param("2026-11-02", LAST_COLUMN - 1, id="seven_days"),
        pytest.param("2025-11-11", 0, id="oldest_week"),
        pytest.param("2025-11-10", None, id="past_window"),
        pytest.param("2026-11-10", None, id="future_date"),
    ],
)
def test_strip_week_edges(day: str, column: int | None) -> None:
    """Weeks count back from today; 52 weeks and beyond (or a future date) leave the strip empty."""
    code = strip_code(strip_cells((visit(day),), TODAY))
    expected = NO_INSPECTION_WEEK if column is None else "." * column + "g" + "." * (LAST_COLUMN - column)
    assert code == expected


def test_empty_cell_code() -> None:
    """A week with no inspection."""
    assert cell_code(Cell()) == "."


def test_strip_label_and_recent_text() -> None:
    """The accessible name lists the newest eight dated statuses, then how many more; phones get three."""
    days = [f"2026-0{month}-01" for month in range(1, 10)]
    p = place(*(visit(day) for day in days))
    label = strip_label(p.inspections)
    assert label.startswith("Inspections in the last 52 weeks: Sep 1, 2026: Approved; Aug 1, 2026: Approved;")
    assert label.endswith("Feb 1, 2026: Approved; and 1 more")
    assert recent_text(p.inspections) == "Sep 1 Approved \u00b7 Aug 1 Approved \u00b7 Jul 1 Approved"
    assert not strip_label(p.inspections[:2]).endswith("more")


@pytest.mark.parametrize(
    ("day", "column"),
    [
        pytest.param("2025-11-11", 0, id="start_day"),
        pytest.param("2025-11-10", None, id="day_before"),
    ],
)
def test_strip_start_is_first_day_shown(day: str, column: int | None) -> None:
    """The axis's first day is the oldest day the leftmost cell takes; the day before is off the strip."""
    assert strip_start(TODAY).isoformat() == STRIP_FIRST_DAY
    code = strip_code(strip_cells((visit(day),), TODAY))
    assert (code.find("g") if "g" in code else None) == column


@pytest.mark.parametrize(
    ("weeks", "caption"),
    [
        pytest.param(1, "Past 1 week \u00b7 one tick per week", id="one_week"),
        pytest.param(WEEKS, "Past 52 weeks \u00b7 one tick per week", id="default_weeks"),
    ],
)
def test_strip_caption_names_weeks(weeks: int, caption: str) -> None:
    """The caption over strips says how many weeks and that each tick is one week."""
    assert strip_caption(weeks) == caption


def test_month_ticks_skip_the_first_columns() -> None:
    """A month name where a month starts, none over the first three columns, every third one kept on phones."""
    ticks = month_ticks(TODAY)
    assert len(ticks) == WEEKS
    assert ticks[:3] == [("", False)] * 3
    names = [(text, quiet) for text, quiet in ticks if text]
    assert names[:4] == [("Jan", False), ("Feb", True), ("Mar", True), ("Apr", False)]
    assert names[-1] == ("Nov", True)


@pytest.mark.parametrize(
    ("today", "row"),
    [
        pytest.param(
            TODAY,
            "- - - - - - - Jan - - - Feb? - - - Mar? - - - - Apr - - - May? - - - Jun? - - - - Jul - - - Aug? - - - "
            "- Sep? - - - Oct - - - Nov? -",
            id="month_mid_lead",
        ),
        pytest.param(
            date(2026, 11, 4),
            "- - - Dec - - - - Jan? - - - Feb? - - - Mar - - - Apr? - - - - May? - - - Jun - - - Jul? - - - - Aug? - "
            "- - Sep - - - - Oct? - - - Nov?",
            id="month_after_lead",
        ),
    ],
)
def test_month_ticks_whole_row(today: date, row: str) -> None:
    """Every column's tick ('-' none, '?' hidden on phones), including a month that starts just past the lead."""
    ticks = month_ticks(today)
    assert " ".join((text or "-") + ("?" if quiet else "") for text, quiet in ticks) == row


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        pytest.param(FAILED, "o", id="unsatisfactory"),
        pytest.param("Immediate Closure - Imminent Health Hazard", "r", id="closure"),
        pytest.param(CONDITIONAL, "y", id="conditional"),
        pytest.param(APPROVED, "g", id="approved"),
        pytest.param("Non-Graded", "n", id="other"),
    ],
)
def test_level(status: str, expected: str) -> None:
    """Red is checked first, so 'Conditional' never hides a closure."""
    assert level(status) == expected


# ---------- Places and the week ----------


def test_group_places_keeps_legal_name_and_orders_newest_first() -> None:
    """One place per name+address; the legal name survives; the most recently inspected place comes first."""
    cafe = replace(visit("2026-10-01", OTHER), legal_name="Cafe LLC")
    diner = replace(visit("2026-10-05"), name="DINER", address="5 MAIN ST NE")
    first, second = group_places((cafe, replace(cafe, date="2026-04-01", legal_name=None), diner))
    assert (first.name, second.name) == ("DINER", "TEST CAFE")
    assert second.legal_name == "Cafe LLC"
    assert len(second.inspections) == len(["Oct 1", "Apr 1"])


def test_week_with_a_covering_report() -> None:
    """The newest date is in an archived report: no banner, pest citations from the same seven days."""
    places = group_places(
        (
            visit("2026-10-30", ROACHES),
            replace(visit("2026-10-24", ROACHES), name="OLD", address="1 A ST"),
            replace(visit("2026-10-27", status=CLOSED), name="SHUT", address="2 B ST"),
        )
    )
    week = select_week(places, (report("2026-10-25", "2026-10-31"),))
    assert week is not None
    assert (week.start, week.end, week.covered, week.pest_report) == ("2026-10-24", "2026-10-30", True, None)
    assert [p.name for p, _ in week.pest_visits] == ["TEST CAFE", "OLD"]
    assert [p.name for p, _ in week.red] == ["SHUT"]


def test_week_without_a_covering_report_uses_the_latest_report() -> None:
    """Newest inspections are feed-only: banner, and pest citations from the latest report on file."""
    places = group_places(
        (
            visit("2026-11-06", notes=False),
            replace(visit("2026-10-28", ROACHES), name="BUGS", address="3 C ST"),
            replace(visit("2026-10-03", ROACHES), name="OLDER", address="4 D ST"),
        )
    )
    reports = (report("2026-09-27", "2026-10-03"), report("2026-10-25", "2026-10-31"))
    week = select_week(places, reports)
    assert week is not None
    assert (week.start, week.end, week.covered) == ("2026-10-31", "2026-11-06", False)
    assert week.pest_report == reports[1]
    assert [p.name for p, _ in week.pest_visits] == ["BUGS"]
    assert [p.name for p, _ in week.other] == ["TEST CAFE"]


def test_week_without_any_report_or_inspection() -> None:
    """No report at all: no pest source; no inspections at all: no week."""
    week = select_week(group_places((visit("2026-11-06", notes=False),)), ())
    assert week is not None
    assert (week.covered, week.pest_report, week.pest_visits) == (False, None, ())
    assert select_week([], ()) is None


def test_month_without_a_covering_report_cites_its_own_pests() -> None:
    """Longer than a week: pest citations from the period's own inspections, even when the newest isn't covered."""
    places = group_places(
        (
            visit("2026-11-06", notes=False),
            replace(visit("2026-10-28", ROACHES), name="BUGS", address="3 C ST"),
            replace(visit("2026-10-03", ROACHES), name="OLDER", address="4 D ST"),
        )
    )
    month = select_period(places, (report("2026-10-25", "2026-10-31"),), MONTH_SPAN_DAYS)
    assert month is not None
    assert (month.start, month.end, month.covered, month.own_pests) == ("2026-10-08", "2026-11-06", False, True)
    assert (month.pest_report, [p.name for p, _ in month.pest_visits]) == (None, ["BUGS"])


def test_all_time_starts_at_the_oldest_inspection() -> None:
    """No span: every inspection on file, pests from all of them."""
    places = group_places((visit("2026-10-30"), replace(visit("2021-07-12", ROACHES), name="OLD", address="1 A ST")))
    everything = select_period(places, (report("2026-10-25", "2026-10-31"),), None)
    assert everything is not None
    assert (everything.start, everything.end, everything.own_pests) == ("2021-07-12", "2026-10-30", True)
    assert [p.name for p, _ in everything.pest_visits] == ["OLD"]


# ---------- Status today and closures ----------


def timed(day: str, time: str | None, status: str, number: str) -> Inspection:
    """An inspection with the feed's start time."""
    return replace(visit(day, status=status, number=number), time=time)


# A reopening inspection has a new-style ID with no permit number; an old-style ID is the permit number itself.
SAME_DAY_REOPEN = tuple(
    replace(i, permit_number="PT0156723")  # the report files both under the place's one permit
    for i in (
        timed("2026-10-27", "13:06", CLOSED, "PT0156723"),
        timed("2026-10-27", "14:07", CONDITIONAL, "RT-FOODEST-101632-2026"),
    )
)


@pytest.mark.parametrize(
    ("time", "expected"),
    [
        pytest.param("16:30", "4:30 pm", id="afternoon_pm"),
        pytest.param("12:00", "12:00 pm", id="noon_pm"),
        pytest.param("00:05", "12:05 am", id="midnight_am"),
        pytest.param("09:15", "9:15 am", id="morning_am"),
    ],
)
def test_clock(time: str, expected: str) -> None:
    """24-hour feed times read as 12-hour clock times."""
    assert clock(time) == expected


# Every day of October 2026 is in a weekly report on file, except Oct 11-17.
OCTOBER = frozenset(f"2026-10-{day:02d}" for day in range(1, 32) if not 11 <= day <= 17)


def test_same_day_reopening_is_the_latest() -> None:
    """Naan & Dosa, Oct 27 2026: closed 1:06 pm, conditional at 2:07 pm; the ID order would say closed."""
    reopened = place(*SAME_DAY_REOPEN)
    assert reopened.latest.status == CONDITIONAL
    assert latest_result_text(reopened) == (
        "Latest result in the weekly reports on file: Conditional Approved, Oct 27, 2026, 2:07 pm "
        "(Routine Food Establishment Inspection)"
    )
    assert reopened_flag(reopened, OCTOBER) == "Closed and reopened Oct 27"
    (run,) = reopened.closures
    (spell,) = run.closed
    assert closed_text(spell, OCTOBER) == (
        "Closed and reopened the same day (1:06 pm \u2192 2:07 pm): Conditional Approved."
    )


def test_closure_length_only_across_covered_days() -> None:
    """Oct 3 to Oct 9, every day on file: 6 days. Oct 9 to Oct 20 spans the missing week: no length is claimed."""
    covered = place(visit("2026-10-03", status=CLOSED), visit("2026-10-09", status=APPROVED))
    (spell,) = covered.spells
    assert closed_text(spell, OCTOBER) == "Closed 6 days: Oct 3 to Oct 9, 2026, reopened as Approved."
    assert reopened_flag(covered, OCTOBER) == "Closed 6 days, reopened Oct 9"
    gap = place(visit("2026-10-09", status=CLOSED), visit("2026-10-20", status=APPROVED))
    (spell,) = gap.spells
    assert closed_text(spell, OCTOBER) == (
        "Closed Oct 9, 2026. The next inspection in the weekly reports on file, Oct 20, 2026, found Approved; "
        "reports for some days in between aren't on file, so it may have reopened sooner."
    )
    assert reopened_flag(gap, OCTOBER) == ""
    still = place(visit("2026-10-30", status=CLOSED))
    assert closed_text(still.spells[0], OCTOBER) == (
        "Closed Oct 30, 2026. No reopening inspection in the weekly reports on file."
    )
    assert reopened_flag(still, OCTOBER) == ""


@pytest.mark.parametrize(
    "inspections",
    [
        pytest.param((visit("2026-10-03", status=FAILED), visit("2026-10-09")), id="unsatisfactory_only"),
        pytest.param((visit("2026-10-03", status=CLOSED), visit("2026-10-09", status=FAILED)), id="still_red"),
        pytest.param((visit("2026-10-09"),), id="never_red"),
    ],
)
def test_no_reopened_flag(inspections: tuple[Inspection, ...]) -> None:
    """No closure, or the place still carries a red result: no "reopened" flag."""
    assert reopened_flag(place(*inspections), OCTOBER) == ""


def test_covered_days_and_unbroken() -> None:
    """A report covers every day of its week; a span is unbroken only if every day in it is covered."""
    days = covered_days((report("2026-10-25", "2026-10-31"),))
    assert len(days) == len(["25", "26", "27", "28", "29", "30", "31"])
    assert unbroken("2026-10-26", "2026-10-31", days)
    assert not unbroken("2026-10-24", "2026-10-26", days)


def test_permit_lines_quote_the_latest_report() -> None:
    """The city's own permit lines from the latest report listing the place, one per distinct line."""
    older = replace(visit("2026-09-25"), report_file="older.pdf", operational_status="Closed")
    food = replace(visit("2026-10-27"), operational_status="Open", permit_type="Food Establishment")
    follow_up = replace(
        visit("2026-10-28", number="CAC-1"), operational_status="Open", permit_type="Food Establishment"
    )
    no_line = replace(visit("2026-10-29", number="X"), operational_status=None)
    lines = permit_lines(place(older, food, follow_up, no_line))
    assert [permit_line_text(line) for line in lines] == [
        "Food Establishment (Permit # PT1): Operational Status \u2013 Open"
    ]


def test_stated_keeps_only_report_inspections_inside_their_week() -> None:
    """Feed-only inspections and a report's typo date (Simply Sweet, 1/29/2026 in a Jan 2025 report) stay off."""
    week = report("2026-10-25", "2026-10-31")
    inside = replace(visit("2026-10-27"), report_file=week.file)
    typo = replace(visit("2027-10-27", number="TYPO"), report_file=week.file)
    feed_only = visit("2026-10-28", number="FEED", notes=False)
    assert stated((inside, typo, feed_only), (week,)) == (inside,)
