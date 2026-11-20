# Copyright (c) 2026 nm_health contributors
"""News summaries folded into the site: statuses, places, links, and the city report always winning."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from nm_health.archive import Week
from nm_health.identity import Group, begins, group, name_core, same_core, street_words
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
        pytest.param("905 Yale SE", "905 Yale Blvd SE BLVD SE", id="printed_twice"),
    ],
)
def test_street_words_match_city_spelling(journal: str, city: str) -> None:
    """The Journal drops street types and units; both spellings are one address."""
    assert street_words(journal) == street_words(city)


@pytest.mark.parametrize(
    ("one", "other"),
    [
        pytest.param("2400 Central SE", "2400 Central NE", id="other_quadrant"),
        pytest.param("2937 San Mateo NE", "2937 San Pedro NE", id="other_street_same_first_word"),
        pytest.param("2937 San Mateo NE", "2939 San Mateo NE", id="other_number"),
    ],
)
def test_street_words_tell_addresses_apart(one: str, other: str) -> None:
    """Another quadrant, street (even one starting with the same word) or number is another address."""
    assert street_words(one) != street_words(other)


@pytest.mark.parametrize(
    ("one", "other"),
    [
        pytest.param("TACO BELL #31822", "Taco Bell", id="store_number"),
        pytest.param("LITTLE CAESARS 511", "Little Caesars", id="bare_store_number"),
        pytest.param("BJ\u2019s Restaurant & Brewhouse", "BJS RESTAURANT AND BREWHOUSE", id="and_restaurant"),
        pytest.param("Royal Buffet Restaurant", "Royal Buffet", id="restaurant"),
        pytest.param("ODELIA HEALTHCARE LLC", "Odelia Healthcare", id="llc"),
        pytest.param("WAL MART 824", "Walmart", id="spacing"),
    ],
)
def test_names_agree(one: str, other: str) -> None:
    """Store numbers, company forms, "the", "and", "restaurant" and spacing aside, one name."""
    assert same_core(name_core(one), name_core(other))


@pytest.mark.parametrize(
    ("one", "other", "starts"),
    [
        pytest.param("Walmart", "Walmart Supercenter", True, id="adds_words"),
        pytest.param("Blake\u2019s", "Blake\u2019s Lotaburger", True, id="short_form"),
        pytest.param("Albertsons", "AFC Sushi at Albertsons", False, id="ends_with"),
        pytest.param("Taco", "Tacos El Gordo", False, id="not_a_whole_word"),
        pytest.param("Subway", "Subway", False, id="same_name"),
    ],
)
def test_one_name_starts_another(one: str, other: str, starts: bool) -> None:  # noqa: FBT001 - parametrized
    """Word for word from the start, and longer: "Albertsons" doesn't start "AFC Sushi at Albertsons"."""
    assert begins(name_core(one), name_core(other)) is starts


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


def test_journal_latest_names_outlet_once(tmp_path: Path) -> None:
    """A Journal-only place's latest-record box names the paper once, after a plain label."""
    data, _ = site_with_news(tmp_path)
    hot_wok = next(p for p in data.places if p.name == "Hot Wok")
    body = place_page(data, hot_wok).body
    assert "Latest on file: a newspaper's summary of the city's weekly report</span> Albuquerque Journal," in body
    assert "Journal's summary of the city's weekly report</span> Albuquerque Journal" not in body


def test_data_page_says_why_none_used(tmp_path: Path) -> None:
    """An article on a week the city's report covers says why none of it is used."""
    data, _ = site_with_news(tmp_path)
    assert "none: the city&#x27;s report for that week is on file" in data_page(data).body


def test_passing_grade_says_why_no_notes(tmp_path: Path) -> None:
    """A Journal pass has no description; the place page and the saved record both say so."""
    data, article = site_with_news(tmp_path)
    frontier = next(p for p in data.places if p.name == "FRONTIER RESTAURANT")
    body = place_page(data, frontier).body
    assert "a passing or conditional result, or a follow-up, is listed with its date alone" in body
    assert "no notes are recorded for passing or conditional grades" in news_page(data, article).body


def place_names(groups: list[Group]) -> list[list[str]]:
    """Each group's names, sorted, for comparing groupings."""
    return sorted(sorted({i.name for i in g.inspections}) for g in groups)


def test_store_number_and_restaurant_joined() -> None:
    """Church's Chicken #5341 and the Journal's Church's Chicken, Royal Buffet and Royal Buffet Restaurant: one each."""
    church = rec("2026-11-03", "Church's Chicken #5341", "401 Louisiana BLVD SE", "PT1", NOVEMBER)
    groups = group(
        (
            church,
            journal_visit("Church\u2019s Chicken", "401 Louisiana SE"),
            journal_visit("Royal Buffet Restaurant", "6111 San Mateo NE"),
            journal_visit("Royal Buffet", "6111 San Mateo NE"),
        )
    )
    assert place_names(groups) == [
        ["Church's Chicken #5341", "Church\u2019s Chicken"],
        ["Royal Buffet", "Royal Buffet Restaurant"],
    ]


def test_starting_name_joins_after_exact() -> None:
    """Walmart (Journal) joins WAL MART 824 (city); Walmart Supercenter (Journal) then joins that one place."""
    city = rec("2026-11-03", "WAL MART 824", "8000 ACADEMY RD NE", "PT1", NOVEMBER)
    groups = group(
        (city, journal_visit("Walmart", "8000 Academy NE"), journal_visit("Walmart Supercenter", "8000 Academy NE"))
    )
    assert place_names(groups) == [["WAL MART 824", "Walmart", "Walmart Supercenter"]]


def test_name_starting_several_joins_none() -> None:
    """A name starting two kitchens' names that are apart (Clyde Hotel) joins neither, and is flagged against both."""
    hotel = journal_visit("Clyde Hotel", "330 Tijeras NW")
    groups = group(
        (
            hotel,
            journal_visit("Clyde Hotel Mercantile", "330 Tijeras NW"),
            journal_visit("Clyde Hotel Banquet Kitchen", "330 Tijeras NW"),
        )
    )
    assert len(groups) == len(("hotel", "mercantile", "banquet"))
    assert len(next(g for g in groups if g.inspections[0].name == "Clyde Hotel").maybe_same) == len(
        ("mercantile", "banquet")
    )


def test_counter_inside_a_store_stays_apart() -> None:
    """AFC Sushi at Albertsons is its own place; the Journal's Albertsons joins the city's ALBERTSONS #911."""
    city = rec("2026-11-03", "ALBERTSONS #911", "2801 EUBANK BLVD NE, A", "PT1", NOVEMBER)
    groups = group(
        (
            city,
            journal_visit("Albertsons", "2801 Eubank NE"),
            journal_visit("AFC Sushi at Albertsons", "2801 Eubank NE"),
        )
    )
    assert place_names(groups) == [["AFC Sushi at Albertsons"], ["ALBERTSONS #911", "Albertsons"]]


def test_same_name_other_quadrant_flagged() -> None:
    """One name, one number and street, two quadrants: a likely typo, kept apart and flagged."""
    groups = group(
        (journal_visit("McDonald\u2019s", "2305 Central NW"), journal_visit("McDonald\u2019s", "2305 Central SW"))
    )
    assert [len(g.maybe_same) for g in groups] == [1, 1]


def test_place_page_shows_the_journal_spelling(tmp_path: Path) -> None:
    """A place joined to a Journal entry under another name says how the paper printed it, linked, as a guess."""
    data, _ = site_with_news(tmp_path)
    church = rec("2026-11-03", "Church's Chicken #5341", "401 Louisiana BLVD SE", "PT1", NOVEMBER)
    joined = (church, journal_visit("Church\u2019s Chicken", "401 Louisiana SE"))
    data = replace(data, places=group_places(joined))
    body = place_page(data, data.places[0]).body
    assert 'The Albuquerque Journal printed it as: <a href="#insp-1">Church\u2019s Chicken</a>' in body
    assert "Joined by address and name; check it against the article." in body
