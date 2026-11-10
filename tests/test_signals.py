# Copyright (c) 2026 nm_health contributors
"""Signals: closure episodes, pest sightings, and citations later cleared."""

from dataclasses import replace

import pytest

from nm_health.model import Inspection, Violation
from nm_health.signals import (
    ClosedSpell,
    Episode,
    chronological,
    cleared_on,
    closed_spells,
    closure_episodes,
    is_closed,
    is_open,
    is_pass,
    is_red,
    pest_sightings,
)

CLOSED = "Closure Re-Inspection Required"
FAILED = "Unsatisfactory Re-Inspection required"
CONDITIONAL = "Conditional Approved"
APPROVED = "Approved"
ROACHES_LIVE = Violation("Pest Control", "Controlling Pests", "", "Observed live roaches.", ("roaches",), "live")
FLIES = Violation("Pest Control", "Insect Control Devices", "", "Observed flies.", ("flies",), "live")
OTHER = Violation("Plumbing", "Good Repair", "", "Observed leak.")
EPISODE_DAYS = 39
FOLLOW_UP = "Corrective Action Compliance"
SIX_DAYS = 6


def visit(day: str, status: str, *violations: Violation, number: str = "") -> Inspection:
    """One inspection of the test place."""
    return Inspection(
        inspection_id=number or f"N-{day}-{status[:4]}",
        date=day,
        kind="Routine Food Establishment Inspection",
        status=status,
        name="BAMBOO",
        address="7202 MENAUL BLVD NE",
        permit_number=None,
        permit_type=None,
        report_file="",
        page=None,
        violations=violations,
    )


@pytest.mark.parametrize(
    ("status", "red", "passed"),
    [
        pytest.param(CLOSED, True, False, id="closure_red"),
        pytest.param(FAILED, True, False, id="unsatisfactory_red"),
        pytest.param(CONDITIONAL, False, True, id="conditional_pass"),
        pytest.param(APPROVED, False, True, id="approved_pass"),
        pytest.param("Non-Graded", False, False, id="other_neither"),
    ],
)
def test_status_classes(status: str, *, red: bool, passed: bool) -> None:
    """Closed/failed vs passed; anything else is neither."""
    assert (is_red(status), is_pass(status)) == (red, passed)


def test_bamboo_2026_episode() -> None:
    """Two closures then a conditional pass: one episode, 39 days (Jun 8 -> Jul 17, 2026)."""
    history = (visit("2026-07-17", CONDITIONAL), visit("2026-06-16", CLOSED), visit("2026-06-08", CLOSED))
    (episode,) = closure_episodes(history)
    assert episode == Episode("2026-06-08", "2026-07-17", 2, CONDITIONAL)
    assert episode.days == EPISODE_DAYS


def test_same_day_reopening_and_open_episode() -> None:
    """A same-day re-inspection pass ends that day's closure; a closure with no pass yet stays open."""
    history = (
        visit("2026-06-15", APPROVED),
        visit("2026-06-15", CLOSED),
        visit("2026-07-01", "Non-Graded"),
        visit("2026-07-13", CLOSED),
    )
    reopened, still_closed = closure_episodes(history)
    assert (reopened.start, reopened.end, reopened.days) == ("2026-06-15", "2026-06-15", 0)
    assert (still_closed.start, still_closed.end, still_closed.days, still_closed.end_status) == (
        "2026-07-13",
        None,
        None,
        None,
    )


def test_no_episodes_without_failures() -> None:
    """A clean status history has no episodes (and says nothing else)."""
    assert closure_episodes((visit("2026-01-02", APPROVED),)) == []


def test_pest_sightings_filter_and_order() -> None:
    """Newest first; the headline kinds exclude flies; missing state reads not_stated."""
    unstated = replace(ROACHES_LIVE, pest_state=None)
    history = (
        visit("2026-01-05", APPROVED, unstated),
        visit("2026-06-08", CLOSED, ROACHES_LIVE, FLIES, OTHER),
    )
    every = pest_sightings(history)
    assert [(s.date, s.pests, s.state) for s in every] == [
        ("2026-06-08", ("roaches",), "live"),
        ("2026-06-08", ("flies",), "live"),
        ("2026-01-05", ("roaches",), "not_stated"),
    ]
    headline = pest_sightings(history, ("roaches", "rodents"))
    assert [s.pests for s in headline] == [("roaches",), ("roaches",)]


def test_cleared_on() -> None:
    """The first later pass clears a citation; a same-day pass or a later failure does not."""
    history = (
        visit("2026-06-08", CLOSED, ROACHES_LIVE),
        visit("2026-06-08", APPROVED, number="SAME-DAY"),
        visit("2026-06-16", CLOSED),
        visit("2026-07-17", CONDITIONAL),
    )
    assert cleared_on(history, "2026-06-08") == "2026-07-17"
    assert cleared_on(history, "2026-07-17") is None


@pytest.mark.parametrize(
    ("status", "closed", "open_"),
    [
        pytest.param(CLOSED, True, False, id="closure_closed"),
        pytest.param(FAILED, False, True, id="unsatisfactory_open"),
        pytest.param(CONDITIONAL, False, True, id="conditional_open"),
        pytest.param(APPROVED, False, True, id="approved_open"),
        pytest.param("Non-Graded", False, False, id="other_neither"),
    ],
)
def test_closed_and_open(status: str, *, closed: bool, open_: bool) -> None:
    """Only a closure shuts the place: an unsatisfactory place operates under a red sticker."""
    assert (is_closed(status), is_open(status)) == (closed, open_)


def at(day: str, time: str | None, status: str, number: str, kind: str = "") -> Inspection:
    """An inspection with the feed's start time."""
    found = visit(day, status, number=number)
    return replace(found, time=time, kind=kind or found.kind)


def test_same_day_order_follows_the_feed_time() -> None:
    """Ojos Locos, Oct 9 2026: closed 11:30, approved 16:00, conditional 16:30, whatever the IDs say."""
    history = (
        at("2026-10-09", "16:30", CONDITIONAL, "RT-096598"),
        at("2026-10-09", "16:00", APPROVED, "RT-097595"),
        at("2026-10-09", "11:30", CLOSED, "RT-097628"),
    )
    assert [i.time for i in chronological(history)] == ["11:30", "16:00", "16:30"]


def test_same_time_failure_stands() -> None:
    """Two permits inspected together at 11:10: the closure sorts last, so the place reads closed."""
    history = (at("2026-01-08", "11:10", CLOSED, "PT-A"), at("2026-01-08", "11:10", APPROVED, "PT-B"))
    assert [i.status for i in chronological(history)] == [APPROVED, CLOSED]


def test_untimed_follow_up_comes_after_the_routine() -> None:
    """A corrective-action visit the feed doesn't list follows that day's timed routine inspection."""
    history = (
        at("2025-12-18", None, APPROVED, "CAC-1", FOLLOW_UP),
        at("2025-12-18", "10:10", FAILED, "PT-1"),
    )
    assert [i.inspection_id for i in chronological(history)] == ["PT-1", "CAC-1"]


def test_closed_spells() -> None:
    """Reopened under a red sticker the same day; closed twice then reopened 6 days later; still closed."""
    history = (
        at("2026-09-23", "11:00", CLOSED, "A"),
        at("2026-09-23", "15:00", FAILED, "B"),
        at("2026-10-01", "09:00", APPROVED, "C"),
        at("2026-10-03", "10:00", CLOSED, "D"),
        at("2026-10-05", "10:00", CLOSED, "E"),
        at("2026-10-09", "12:00", CONDITIONAL, "F"),
        at("2026-11-03", "09:15", CLOSED, "G"),
    )
    same_day, six_days, current = closed_spells(history)
    assert same_day == ClosedSpell("2026-09-23", "11:00", "2026-09-23", "15:00", FAILED, 1)
    assert (same_day.days, six_days.days, six_days.closures, six_days.end_status) == (0, SIX_DAYS, 2, CONDITIONAL)
    assert (current.start, current.end, current.days) == ("2026-11-03", None, None)


def test_no_spell_without_a_closure() -> None:
    """Unsatisfactory then approved is a red episode but never a closure."""
    assert closed_spells((visit("2026-01-02", FAILED), visit("2026-01-09", APPROVED))) == []
