# Copyright (c) 2026 nm_health contributors
"""What a place's record positively shows: closure episodes, pest evidence, and pest citations later cleared.

Absence proves nothing (inspectors never certify a place pest-free), so nothing here is computed from what an
inspection did NOT cite.
"""

import re
from dataclasses import dataclass
from datetime import date

from nm_health.model import Inspection

RED_WORDS = ("closure", "unsatisfactory")
CLOSURE_WORD = "closure"  # only a closure shuts the doors: an unsatisfactory place stays open under a red sticker
APPROVED_WORD = "approved"  # "Approved" and "Conditional Approved" both reopen a place
# An untimed corrective-action visit follows the routine inspection it corrects; other untimed visits sort first.
FOLLOW_UP_WORD = "corrective action"
START_OF_DAY = ""
# Routine inspections from before the late-2025 numbering reuse the permit number as their ID.
PERMIT_ID = re.compile(r"PT\d+")
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
class ClosedSpell:
    """From a closure to the inspection that reopened the place (any graded result that isn't a closure)."""

    start: str
    start_time: str | None
    end: str | None  # None while still closed
    end_time: str | None
    end_status: str | None
    closures: int  # closure results in a row

    @property
    def days(self) -> int | None:
        """Calendar days from the closure to the reopening inspection (0 = reopened the same day)."""
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


def is_closed(status: str) -> bool:
    """The place was ordered closed."""
    return CLOSURE_WORD in status.lower()


def is_open(status: str) -> bool:
    """A graded result that lets the place operate: approved, conditional or unsatisfactory."""
    return (is_pass(status) or is_red(status)) and not is_closed(status)


def is_follow_up(inspection: Inspection) -> bool:
    """A corrective-action visit: its notes recap what was corrected since an earlier inspection, not new findings."""
    return FOLLOW_UP_WORD in inspection.kind.lower()


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


def permit_of(inspection: Inspection) -> str | None:
    """The permit an inspection covers: an old-style ID that is the permit number, else the PDF's summary table.

    The ID wins: the summary table occasionally files a row under the wrong permit (Quick Track 93, Jan 2026).
    """
    if PERMIT_ID.fullmatch(inspection.inspection_id):
        return inspection.inspection_id
    return inspection.permit_number


def _supersedes(later: str | None, earlier: str | None) -> bool:
    """A later inspection replaces an earlier result unless both name different permits.

    One with no permit number is usually the re-inspection of whatever failed, so it replaces everything before it.
    """
    return later is None or earlier is None or later == earlier


def standing(inspections: tuple[Inspection, ...]) -> list[Inspection]:
    """The results still in force, oldest first: each permit's latest, as far as the records tell permits apart."""
    current: list[Inspection] = []
    for inspection in chronological(inspections):
        permit = permit_of(inspection)
        current = [i for i in current if not _supersedes(permit, permit_of(i))]
        current.append(inspection)
    return current


def _spell(closure: Inspection, reopening: Inspection | None, closures: int) -> ClosedSpell:
    return ClosedSpell(
        start=closure.date,
        start_time=closure.time,
        end=reopening.date if reopening else None,
        end_time=reopening.time if reopening else None,
        end_status=reopening.status if reopening else None,
        closures=closures,
    )


def closed_spells(inspections: tuple[Inspection, ...]) -> list[ClosedSpell]:
    """Every closure and what reopened it, oldest first; the last may still be closed."""
    spells: list[ClosedSpell] = []
    first: Inspection | None = None
    closures = 0
    for inspection in chronological(inspections):
        if is_closed(inspection.status):
            first, closures = first or inspection, closures + 1
            continue
        if first is not None and is_open(inspection.status):
            spells.append(_spell(first, inspection, closures))
            first, closures = None, 0
    if first is not None:
        spells.append(_spell(first, None, closures))
    return spells


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
