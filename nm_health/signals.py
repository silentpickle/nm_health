# Copyright (c) 2026 nm_health contributors
"""What a place's record positively shows: closure episodes, pest evidence, and pest citations later cleared.

Absence proves nothing (inspectors never certify a place pest-free), so nothing here is computed from what an
inspection did NOT cite.
"""

from dataclasses import dataclass
from datetime import date

from nm_health.model import Inspection

RED_WORDS = ("closure", "unsatisfactory")
APPROVED_WORD = "approved"  # "Approved" and "Conditional Approved" both reopen a place
# An untimed corrective-action visit follows the routine inspection it corrects; other untimed visits sort first.
FOLLOW_UP_WORD = "corrective action"
START_OF_DAY = ""
END_OF_DAY = "24:00"
HEADLINE_PESTS = ("roaches", "rodents")
ALL_PESTS = ("roaches", "rodents", "flies", "other_pests", "pests_unspecified")


@dataclass(frozen=True)
class Episode:
    """A run of closed/failed inspections and what ended it."""

    start: str
    end: str | None  # date of the first passing inspection; None while still closed/failed
    failed_inspections: int
    end_status: str | None

    @property
    def days(self) -> int | None:
        """Calendar days from the first failure to the pass."""
        if self.end is None:
            return None
        return (date.fromisoformat(self.end) - date.fromisoformat(self.start)).days


@dataclass(frozen=True)
class PestSighting:
    """One violation's pest evidence."""

    date: str
    pests: tuple[str, ...]  # pest tags, in ALL_PESTS order
    state: str  # live / dead / droppings / not_stated
    inspection_id: str
    observation: str


def is_red(status: str) -> bool:
    """Closed or failed."""
    lower = status.lower()
    return any(word in lower for word in RED_WORDS)


def is_pass(status: str) -> bool:
    """Approved or conditionally approved (and not red)."""
    return APPROVED_WORD in status.lower() and not is_red(status)


def _clock(inspection: Inspection) -> str:
    if inspection.time:
        return inspection.time
    return END_OF_DAY if FOLLOW_UP_WORD in inspection.kind.lower() else START_OF_DAY


def _tie_rank(inspection: Inspection) -> bool:
    """At one recorded time (several permits inspected together) the failure sorts last, so it stands.

    With no time, a failure sorts first: a same-day re-inspection is what usually follows it.
    """
    red = is_red(inspection.status)
    return red if inspection.time else not red


def chronological(inspections: tuple[Inspection, ...]) -> list[Inspection]:
    """Oldest first: by date, then the feed's start time, then `_tie_rank`."""
    return sorted(inspections, key=lambda i: (i.date, _clock(i), _tie_rank(i), i.inspection_id))


def closure_episodes(inspections: tuple[Inspection, ...]) -> list[Episode]:
    """Every closed/failed run, oldest first."""
    episodes: list[Episode] = []
    start, failed = "", 0
    for inspection in chronological(inspections):
        if is_red(inspection.status):
            start, failed = start or inspection.date, failed + 1
            continue
        if failed and is_pass(inspection.status):
            episodes.append(Episode(start, inspection.date, failed, inspection.status))
            start, failed = "", 0
    if failed:
        episodes.append(Episode(start, None, failed, None))
    return episodes


def pest_sightings(inspections: tuple[Inspection, ...], kinds: tuple[str, ...] = ALL_PESTS) -> list[PestSighting]:
    """Violations carrying any of the given pest tags, newest first."""
    sightings = [
        PestSighting(
            date=inspection.date,
            pests=tuple(tag for tag in ALL_PESTS if tag in violation.tags and tag in kinds),
            state=violation.pest_state or "not_stated",
            inspection_id=inspection.inspection_id,
            observation=violation.observation,
        )
        for inspection in inspections
        for violation in inspection.violations
        if any(tag in violation.tags for tag in kinds)
    ]
    return sorted(sightings, key=lambda s: s.date, reverse=True)


def cleared_on(inspections: tuple[Inspection, ...], cited: str) -> str | None:
    """First date after `cited` on which the place passed an inspection: the inspector looked again and passed it."""
    later = (i for i in chronological(inspections) if i.date > cited and is_pass(i.status))
    return next((i.date for i in later), None)
