# Copyright (c) 2026 nm_health contributors
"""News links as inspections, for the weeks with no city report on file (docs/news-links.md).

The Albuquerque Journal's weekly article restates the city's weekly report. Measured on the two weeks both are on file
(Jan 4-10 and Sep 20-26, 2026): every inspection the city's report prints is in the article, and all 113 entry-days
carry the city's status for that day under the mapping below. Only entries no city report can contradict are used
(``news.usable_entries``), so a city report always wins.
"""

import re
from collections.abc import Iterable, Mapping
from datetime import date

from nm_health.model import Inspection, NewsSource
from nm_health.news import GREEN, YELLOW, Entry, NewsLink, usable_entries, week_days

APPROVED = "Approved"
CONDITIONAL = "Conditional Approved"
UNSATISFACTORY = "Unsatisfactory Re-Inspection required"
CLOSURE = "Closure Re-Inspection Required"
STATUS_BY_COLOR = {GREEN: APPROVED, YELLOW: CONDITIONAL}
# A red-listed place's results, in the Journal's words. "re-inspection required" is not here: it is the second half of
# the city's Unsatisfactory or Closure status, which the Journal prints as its own result on the same day.
STATUS_BY_RESULT = {
    "closure": CLOSURE,
    "unsatisfactory": UNSATISFACTORY,
    "conditionally approved": CONDITIONAL,
    "passed follow-up inspection": APPROVED,
}
# Same-day results, first to last: a failure comes before the conditional or approved visit that follows it (the city's
# reports print a place's same-day Conditional then its follow-up Approved; the Journal lists them GREEN first).
DAY_ORDER = {CLOSURE: 0, UNSATISFACTORY: 1, CONDITIONAL: 2, APPROVED: 3}
ID_PREFIX = "news-"
SAVED_DIR = "news"
NOT_SLUG = re.compile(r"[^a-z0-9]+")


def link_slug(link: NewsLink) -> str:
    """A short stable name for an article: its site and the last part of its URL, e.g. "abqjournal-3165262"."""
    site = link.source.split(".", 1)[0]
    last = link.url.rstrip("/").rsplit("/", 1)[-1]
    return NOT_SLUG.sub("-", f"{site}-{last}".lower()).strip("-")


def saved_page(link: NewsLink) -> str:
    """Where the site publishes our saved record of an article, relative to the site root."""
    return f"{SAVED_DIR}/{link_slug(link)}.html"


def source_of(link: NewsLink, outlet: str) -> NewsSource:
    """What a reader needs to check a statement against the article."""
    return NewsSource(
        outlet=outlet,
        url=link.url,
        published=link.published.isoformat(),
        saved=saved_page(link),
        archived=link.archived_url,
    )


def entry_statuses(entry: Entry) -> list[tuple[date, str]]:
    """Each (day, city status) the entry states: one per date for GREEN and YELLOW, one per result for RED."""
    if entry.color in STATUS_BY_COLOR:
        return [(day, STATUS_BY_COLOR[entry.color]) for day in entry.dates]
    results = [(outcome.on, outcome.result.lower()) for outcome in entry.outcomes]
    return [(day, STATUS_BY_RESULT[result]) for day, result in results if result in STATUS_BY_RESULT]


def _inspection(entry: Entry, day: date, status: str, source: NewsSource, inspection_id: str) -> Inspection:
    return Inspection(
        inspection_id=inspection_id,
        date=day.isoformat(),
        kind="",
        status=status,
        name=entry.name,
        address=entry.address,
        permit_number=None,
        permit_type=None,
        report_file="",
        page=None,
        has_details=False,
        news=source,
    )


def link_inspections(link: NewsLink, county: frozenset[date], outlet: str, since: date) -> list[Inspection]:
    """The article's usable entries as inspections, from `since` on; one per place, day and status.

    A place listed GREEN and also red-listed with "passed follow-up inspection" the same day is one Approved
    inspection, as the city's report prints it.
    """
    source = source_of(link, outlet)
    stated = [
        (entry, day, status)
        for entry in usable_entries(link, county)
        for day, status in entry_statuses(entry)
        if day >= since
    ]
    stated.sort(key=lambda found: (found[1], DAY_ORDER[found[2]]))
    found: dict[tuple[str, str, date, str], Inspection] = {}
    for entry, day, status in stated:
        key = (entry.name, entry.address, day, status)
        if key in found:
            continue
        found[key] = _inspection(entry, day, status, source, f"{ID_PREFIX}{link_slug(link)}-{len(found)}")
    return list(found.values())


def news_inspections(
    links: Iterable[NewsLink], county: frozenset[date], outlets: Mapping[str, str], since: date
) -> tuple[Inspection, ...]:
    """Every news link's usable entries as inspections, named by outlet (its domain when config names none)."""
    return tuple(
        inspection
        for link in links
        for inspection in link_inspections(link, county, outlets.get(link.source, link.source), since)
    )


def news_days(links: Iterable[NewsLink]) -> frozenset[str]:
    """Every day (ISO) of a week an article summarizes: on file, like a city report's week."""
    return frozenset(day.isoformat() for link in links for day in week_days(link))
