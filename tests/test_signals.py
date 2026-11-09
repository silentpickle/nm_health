# Copyright (c) 2026 nm_health contributors
"""Signals: closure episodes, pest sightings, and citations later cleared."""

from dataclasses import replace

import pytest

from nm_health.model import Inspection, Violation
from nm_health.signals import Episode, cleared_on, closure_episodes, is_pass, is_red, pest_sightings

CLOSED = "Closure Re-Inspection Required"
FAILED = "Unsatisfactory Re-Inspection required"
CONDITIONAL = "Conditional Approved"
APPROVED = "Approved"
ROACHES_LIVE = Violation("Pest Control", "Controlling Pests", "", "Observed live roaches.", ("roaches",), "live")
FLIES = Violation("Pest Control", "Insect Control Devices", "", "Observed flies.", ("flies",), "live")
OTHER = Violation("Plumbing", "Good Repair", "", "Observed leak.")
EPISODE_DAYS = 39


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
