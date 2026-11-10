# Copyright (c) 2026 nm_health contributors
"""What the site states: redaction, pest quotes, coverage, closure lines, strip cells and the week shown."""

from dataclasses import replace
from datetime import date

import pytest

from nm_health.model import Inspection, Violation
from nm_health.rebuild import Report
from nm_health.viewmodel import (
    ELLIPSIS,
    QUOTE_CHARS,
    WEEKS,
    Cell,
    Place,
    build_place,
    cell_code,
    closure_end,
    closure_start,
    coverage_line,
    feed_only_text,
    group_places,
    level,
    month_ticks,
    notice_count_text,
    pest_reading,
    published,
    quote_for,
    recent_text,
    redact,
    select_week,
    strip_cells,
    strip_code,
    strip_label,
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


def test_feed_only_text_states_the_feed_count() -> None:
    """Feed-only inspections say the notes aren't on file and give the feed's count."""
    one = feed_only_text(visit("2026-10-01", OTHER, notes=False))
    assert one.endswith("The city's status feed lists 1 violation.")
    assert one.startswith("Inspector notes not on file")
    unknown = feed_only_text(replace(visit("2026-10-01", notes=False), violation_count=None))
    assert unknown.endswith("lists an unknown number of violations.")


# ---------- Strip ----------


@pytest.mark.parametrize(
    ("inspections", "code"),
    [
        pytest.param((visit("2026-11-09", OTHER),), "g", id="approved_notes"),
        pytest.param((visit("2026-11-09", status=CONDITIONAL),), "y", id="conditional_notes"),
        pytest.param((visit("2026-11-09", status=CLOSED),), "r", id="closure_notes"),
        pytest.param((visit("2026-11-09", status="Non-Graded"),), "n", id="other_status"),
        pytest.param((visit("2026-11-09", notes=False),), "G", id="approved_feed"),
        pytest.param((visit("2026-11-09", status=FAILED, notes=False),), "R", id="unsatisfactory_feed"),
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


def test_month_ticks_skip_the_first_columns() -> None:
    """A month name where a month starts, none over the first three columns, every third one kept on phones."""
    ticks = month_ticks(TODAY)
    assert len(ticks) == WEEKS
    assert ticks[:3] == [("", False)] * 3
    names = [(text, quiet) for text, quiet in ticks if text]
    assert names[:4] == [("Jan", False), ("Feb", True), ("Mar", True), ("Apr", False)]
    assert names[-1] == ("Nov", True)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        pytest.param(FAILED, "r", id="unsatisfactory"),
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
