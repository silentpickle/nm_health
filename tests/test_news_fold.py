# Copyright (c) 2026 nm_health contributors
"""News summaries folded into the site: statuses, places, links, and the city report always winning."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from nm_health.archive import Week
from nm_health.identity import group, street_key
from nm_health.model import Inspection
from nm_health.news import GREEN, RED, YELLOW, Entry, NewsLink, Outcome, upsert
from nm_health.news_fold import (
    APPROVED,
    CLOSURE,
    CONDITIONAL,
    UNSATISFACTORY,
    described_result,
    description_violations,
    entry_statuses,
    link_inspections,
    link_slug,
    news_inspections,
    saved_page,
)
from nm_health.rebuild import Rebuilt
from nm_health.site_html import SiteData, lede, site_data, source_links, unsourced
from nm_health.site_news import news_page
from nm_health.site_pages import about_page, data_page, place_page
from nm_health.viewmodel import coverage_line, group_places
from tests.test_archive import make_settings
from tests.test_identity import NOVEMBER, rec

JOURNAL = "Albuquerque Journal"
URL = "https://www.abqjournal.com/business/two-red-tagged/3014687"
ARCHIVED = "https://web.archive.org/web/20261112222012/" + URL
GAP_WEEK = Week(date(2026, 10, 18), date(2026, 10, 24))
NOVEMBER_WEEK = Week(date(2026, 11, 1), date(2026, 11, 7))
TODAY = date(2026, 11, 9)
SINCE = date(2025, 11, 9)
ONE_DAY = timedelta(days=1)
NO_COUNTY: frozenset[date] = frozenset()
OUTLETS = (("abqjournal.com", JOURNAL),)


def day(offset: int) -> date:
    """A day of the gap week."""
    return GAP_WEEK.start + ONE_DAY * offset


def entry(color: str, name: str, *outcomes: Outcome, dates: tuple[date, ...] = ()) -> Entry:
    """A listed place on Central; red ones dated by their results."""
    days = dates or tuple(sorted({o.on for o in outcomes}))
    return Entry(color, name, "2400 Central SE", days, (), outcomes)


def link(*entries: Entry, week: Week = GAP_WEEK) -> NewsLink:
    """An article on the given week."""
    return NewsLink(URL, "abqjournal.com", "Two red-tagged", week.end + ONE_DAY * 4, "Staff", (week,), entries, "x")


RED_PLACE = entry(
    RED,
    "Hot Wok",
    Outcome("Closure", day(1)),
    Outcome("re-inspection required", day(1)),
    Outcome("unsatisfactory", day(3)),
    Outcome("re-inspection required", day(3)),
    Outcome("passed follow-up inspection", day(4)),
)


def test_colors_and_results_read_as_city_statuses() -> None:
    """GREEN is Approved, YELLOW Conditional; a red result plus "re-inspection required" is the city's one status."""
    assert entry_statuses(entry(GREEN, "Cafe", dates=(day(2),))) == [(day(2), APPROVED)]
    assert entry_statuses(entry(YELLOW, "Cafe", dates=(day(2),))) == [(day(2), CONDITIONAL)]
    assert entry_statuses(RED_PLACE) == [(day(1), CLOSURE), (day(3), UNSATISFACTORY), (day(4), APPROVED)]


def test_county_week_never_used() -> None:
    """Every day of the article's week is in a city report on file: nothing from the article is used."""
    county = frozenset(day(n) for n in range(7))
    assert link_inspections(link(RED_PLACE), county, JOURNAL, SINCE) == []


def test_same_day_merged_and_failure_first() -> None:
    """GREEN and "passed follow-up" the same day are one Approved; a same-day Conditional comes before it."""
    green = entry(GREEN, "Hot Wok", dates=(day(4),))
    yellow = entry(YELLOW, "Hot Wok", dates=(day(4),))
    found = link_inspections(link(green, yellow, RED_PLACE), NO_COUNTY, JOURNAL, SINCE)
    assert [(i.date, i.status) for i in found] == [
        (day(1).isoformat(), CLOSURE),
        (day(3).isoformat(), UNSATISFACTORY),
        (day(4).isoformat(), CONDITIONAL),
        (day(4).isoformat(), APPROVED),
    ]
    assert {i.news.saved for i in found if i.news} == {"news/abqjournal-3014687.html"}


@pytest.mark.parametrize(
    ("since", "kept"),
    [pytest.param(day(1), 3, id="since_closure_day"), pytest.param(day(2), 2, id="day_after_closure")],
)
def test_window_start_edges(since: date, kept: int) -> None:
    """Results dated on the window's first day are kept; the day before it isn't."""
    assert len(link_inspections(link(RED_PLACE), NO_COUNTY, JOURNAL, since)) == kept


def test_link_names() -> None:
    """An article's slug and saved page come from its site and the end of its URL."""
    assert link_slug(link()) == "abqjournal-3014687"
    assert saved_page(link()) == "news/abqjournal-3014687.html"


@pytest.mark.parametrize(
    ("journal", "city"),
    [
        pytest.param("2100 Louisiana NE", "2100 LOUISIANA BLVD NE", id="street_type"),
        pytest.param("2622 Central SE", "2622 CENTRAL AVE SE, #A", id="unit"),
        pytest.param("2906 Juan Tabo NE", "2906A JUAN TABO NE", id="number_letter"),
    ],
)
def test_street_key_matches_city_spelling(journal: str, city: str) -> None:
    """The Journal drops street types and units; both spellings give one key."""
    assert street_key(journal) == street_key(city)


def test_street_key_quadrant_differs() -> None:
    """Another quadrant is another street."""
    assert street_key("2400 Central SE") != street_key("2400 Central NE")


def journal_visit(name: str, address: str) -> Inspection:
    """One inspection only the Journal prints."""
    found = link_inspections(link(entry(GREEN, name, dates=(day(2),))), NO_COUNTY, JOURNAL, SINCE)[0]
    return replace(found, name=name, address=address)


def test_journal_joins_city_place() -> None:
    """Same name, same street key: one place, shown under the city's printing."""
    city = rec("2026-11-03", "FRONTIER RESTAURANT", "2400 CENTRAL AVE SE", "PT0043548", NOVEMBER)
    groups = group((city, journal_visit("Frontier Restaurant", "2400 Central SE")))
    assert len(groups) == 1


def test_journal_other_name_stays_apart() -> None:
    """One address, another name: two places, nothing flagged."""
    city = rec("2026-11-03", "BJS RESTAURANT", "2100 LOUISIANA BLVD NE", "PT1", NOVEMBER)
    groups = group((city, journal_visit("Dave & Busters", "2100 Louisiana NE")))
    assert [len(g.inspections) for g in groups] == [1, 1]
    assert all(not g.maybe_same for g in groups)


def test_journal_between_two_city_places_joins_neither() -> None:
    """A Journal place matching two places the city's records keep apart joins neither: both flagged can't tell."""
    street = rec("2026-11-03", "TACO CASA", "100 MAIN ST NE", "PT1", NOVEMBER)
    avenue = rec("2026-11-04", "TACO CASA", "100 MAIN AVE NE", "PT2", NOVEMBER)
    groups = group((street, avenue, journal_visit("Taco Casa", "100 Main NE")))
    assert len(groups) == len((street, avenue, "journal"))
    journal = next(g for g in groups if g.inspections[0].news)
    assert len(journal.maybe_same) == len((street, avenue))


def test_recapture_keeps_archived_copy() -> None:
    """Saving an article again doesn't lose the archived copy already found."""
    old = replace(link(), archived_url=ARCHIVED)
    links, _ = upsert([old], replace(link(), captured_at="later"))
    assert links[0].archived_url == ARCHIVED


def site_with_news(tmp_path: Path) -> tuple[SiteData, NewsLink]:
    """A site with one city inspection (November) and one Journal article on a week no report covers."""
    settings = replace(make_settings(tmp_path), news_outlets=OUTLETS)
    city = rec("2026-11-03", "FRONTIER RESTAURANT", "2400 CENTRAL AVE SE", "PT0043548", NOVEMBER)
    covered = link(entry(GREEN, "Frontier Restaurant", dates=(NOVEMBER_WEEK.start,)), week=NOVEMBER_WEEK)
    article = replace(link(RED_PLACE, entry(GREEN, "Frontier Restaurant", dates=(day(2),))), archived_url=ARCHIVED)
    report = replace(NOVEMBER, seen_at="2026-11-08T00:00:00+00:00")
    data = site_data(Rebuilt((city,), (report,)), settings, TODAY, (article, replace(covered, url=URL + "-nov")))
    return data, article


def test_site_states_journal_results_with_links(tmp_path: Path) -> None:
    """Journal results join the places, link the article, our saved record and the archived copy; none unsourced."""
    data, _ = site_with_news(tmp_path)
    assert unsourced(data) == []
    frontier = next(p for p in data.places if p.name == "FRONTIER RESTAURANT")
    journal = next(i for i in frontier.inspections if i.news)
    links = source_links(data, journal, "../")
    assert f'href="{URL}"' in links
    assert 'href="../news/abqjournal-3014687.html" aria-label="Our saved record of Albuquerque Journal, ' in links
    assert ">saved record</a>" in links
    assert f'href="{ARCHIVED}" aria-label="Archived copy of Albuquerque Journal, ' in links
    assert day(2).isoformat() in data.covered


def test_saved_record_marks_used_entries(tmp_path: Path) -> None:
    """The saved record lists every entry; one dated in a week a city report covers is marked not used."""
    data, article = site_with_news(tmp_path)
    page = news_page(data, article).body
    assert page.count(">Used here</a>") == len(article.entries)
    november = next(n for n in data.news_links if n.url.endswith("-nov"))
    assert f'Not used: <a href="../reports/{NOVEMBER.file}">the city&#x27;s report' in news_page(data, november).body


def test_about_and_data_name_the_journal(tmp_path: Path) -> None:
    """With news summaries on file, About explains them and Data lists each one."""
    data, _ = site_with_news(tmp_path)
    assert "Albuquerque Journal&#x27;s weekly summary" not in about_page(data).body
    assert "Albuquerque Journal's weekly summary" in about_page(data).body
    assert "abqjournal-3014687" in data_page(data).body
    assert "For 1 week whose city report wasn" in about_page(data).body  # the November article is covered: not counted


def test_no_news_adds_nothing() -> None:
    """Without news links, the fold adds nothing (the golden pages pin the rest)."""
    assert news_inspections((), NO_COUNTY, dict(OUTLETS), SINCE) == ()


DESCRIBED = replace(RED_PLACE, notes=("A live mouse ran under the prep table. The hand sink was blocked by boxes.",))


def test_description_on_first_failing_result() -> None:
    """The description goes with the result it explains, the place's first failing one; later results stay bare."""
    found = link_inspections(link(DESCRIBED), NO_COUNTY, JOURNAL, SINCE)
    described = [(i.date, i.status) for i in found if i.violations]
    assert described == [(day(1).isoformat(), CLOSURE)]
    assert described_result(DESCRIBED) == (day(1), CLOSURE)


def test_description_tagged_like_notes() -> None:
    """Each sentence is tagged as an inspector's observation would be: rodents (live) and handwashing here."""
    violations = description_violations(DESCRIBED)
    assert [v.observation for v in violations] == [
        "A live mouse ran under the prep table.",
        "The hand sink was blocked by boxes.",
    ]
    assert [(v.tags, v.pest_state) for v in violations] == [(("rodents",), "live"), (("handwashing",), None)]


def test_place_page_quotes_description_with_attribution(tmp_path: Path) -> None:
    """The place page quotes the paper's words, says whose they are, and credits the pest reading to the paper."""
    data, _ = site_with_news(tmp_path)
    data = replace(data, places=group_places(tuple(link_inspections(link(DESCRIBED), NO_COUNTY, JOURNAL, SINCE))))
    hot_wok = next(p for p in data.places if p.name == "Hot Wok")
    body = place_page(data, hot_wok).body
    assert "Albuquerque Journal&#x27;s summary of it describes this inspection, in the paper&#x27;s words" in body
    assert "A live mouse ran under the prep table. The hand sink was blocked by boxes." in body
    assert "title=\"This site's reading of the Albuquerque Journal's words\"" in body
    assert "as the Albuquerque Journal reported the city&#x27;s result" in body
    assert "The Albuquerque Journal described 1 other in its own words." in coverage_line(hot_wok)


def test_lede_and_about_count_journal_weeks(tmp_path: Path) -> None:
    """With Journal summaries, the lede says what fills in, and About counts reports and summaries apart."""
    data, _ = site_with_news(tmp_path)
    assert lede(data).endswith(
        "For 1 other week, whose report wasn't saved, the Albuquerque Journal's summaries fill in."
    )
    assert "1 weekly report and 1 Albuquerque Journal summary of weeks whose report wasn" in about_page(data).body
