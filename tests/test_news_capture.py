# Copyright (c) 2026 nm_health contributors
"""Reading a browser capture of a news article: the week, each listed place, red places' results; prose dropped.

Fixtures are invented places in the article's layout, never a real article's text.
"""

from datetime import date

import pytest

from nm_health.archive import Week
from nm_health.news import to_json
from nm_health.news_capture import (
    CAPTURE_KIND,
    capture_problems,
    read_capture,
    resolve_day,
    walk_lines,
    week_from_line,
)

HOSTS = ("www.example.test",)
URL = "https://www.example.test/business/three-red-tagged/123"
PUBLISHED = date(2026, 11, 19)
NOV = 11
DEC = 12
JAN = 1

LINES = [
    "These are summaries of city restaurant inspections.",
    "GREEN: Food establishment received a passing grade.",
    "RED: Food establishment had major violations.",
    "Nov. 8-14",
    "GREEN",
    "Test Cafe, 100 Central SE (Nov. 12)",
    "Acme Inc., 200 Gibson SE (Nov. 13) (Class B, Class C)",
    "Corner Store, 300 Lomas NE, Ste A (Nov. 9, 10)",
    "Plaza Kiosk, Coronado Center (Nov. 11)",
    "No Date Diner, 400 Menaul NE",
    "YELLOW",
    "Test Cafe, 100 Central SE (Nov. 12)",
    "RED",
    "Hot Wok, 500 Coors NW (Class C)",
    "Narrative about what the inspector found. It is never kept.",
    "Result: Closure (Nov. 9); re-inspection required (Nov. 9); unsatisfactory (Nov. 10)",
    "Bad Bistro, 600 Yale SE",
    "Result: Closure (Nov. 12)",
    "For more information, visit the city's website.",
]

CAPTURE: dict[str, object] = {
    "capture": CAPTURE_KIND,
    "url": URL,
    "headline": "Two businesses red-tagged",
    "published": "2026-11-19T13:00:00.000Z",
    "author": "Staff Report ",
    "captured_at": "2026-11-20T00:00:00Z",
    "lines": LINES,
}

EXPECTED_RECORD = {
    "url": URL,
    "source": "example.test",
    "headline": "Two businesses red-tagged",
    "published": "2026-11-19",
    "author": "Staff Report",
    "weeks": [{"start": "2026-11-08", "end": "2026-11-14"}],
    "entries": [
        {
            "color": "GREEN",
            "name": "Test Cafe",
            "address": "100 Central SE",
            "dates": ["2026-11-12"],
            "classes": [],
            "outcomes": [],
        },
        {
            "color": "GREEN",
            "name": "Acme Inc.",
            "address": "200 Gibson SE",
            "dates": ["2026-11-13"],
            "classes": ["Class B", "Class C"],
            "outcomes": [],
        },
        {
            "color": "GREEN",
            "name": "Corner Store",
            "address": "300 Lomas NE, Ste A",
            "dates": ["2026-11-09", "2026-11-10"],
            "classes": [],
            "outcomes": [],
        },
        {
            "color": "GREEN",
            "name": "Plaza Kiosk",
            "address": "Coronado Center",
            "dates": ["2026-11-11"],
            "classes": [],
            "outcomes": [],
        },
        {
            "color": "YELLOW",
            "name": "Test Cafe",
            "address": "100 Central SE",
            "dates": ["2026-11-12"],
            "classes": [],
            "outcomes": [],
        },
        {
            "color": "RED",
            "name": "Hot Wok",
            "address": "500 Coors NW",
            "dates": ["2026-11-09", "2026-11-10"],
            "classes": ["Class C"],
            "outcomes": [
                {"result": "Closure", "on": "2026-11-09"},
                {"result": "re-inspection required", "on": "2026-11-09"},
                {"result": "unsatisfactory", "on": "2026-11-10"},
            ],
        },
        {
            "color": "RED",
            "name": "Bad Bistro",
            "address": "600 Yale SE",
            "dates": ["2026-11-12"],
            "classes": [],
            "outcomes": [{"result": "Closure", "on": "2026-11-12"}],
        },
    ],
    "captured_at": "2026-11-20T00:00:00Z",
}

EXPECTED_WARNINGS = [
    "GREEN: no usable date in parentheses, skipped: No Date Diner, 400 Menaul NE",
    "RED: not a place line, skipped: For more information, visit the city's website.",
]


def test_capture_read_whole_record() -> None:
    """The whole record from a capture: citation, week, every place as printed; narrative and intro dropped."""
    read = read_capture(CAPTURE, HOSTS)
    assert read.link is not None
    assert to_json(read.link) == EXPECTED_RECORD
    assert read.warnings == EXPECTED_WARNINGS
    assert read.problems == []


def test_record_keeps_no_prose() -> None:
    """No narrative sentence reaches the record."""
    read = read_capture(CAPTURE, HOSTS)
    assert read.link is not None
    assert "inspector" not in str(to_json(read.link))


@pytest.mark.parametrize(
    ("line", "published", "expected"),
    [
        pytest.param("Nov. 8-14", PUBLISHED, Week(date(2026, NOV, 8), date(2026, NOV, 14)), id="same_month"),
        pytest.param("Nov. 8\N{EN DASH}14", PUBLISHED, Week(date(2026, NOV, 8), date(2026, NOV, 14)), id="en_dash"),
        pytest.param(
            "Nov. 30-Dec. 6", date(2025, DEC, 12), Week(date(2025, NOV, 30), date(2025, DEC, 6)), id="across_months"
        ),
        pytest.param(
            "Dec. 28-Jan. 3", date(2026, JAN, 8), Week(date(2025, DEC, 28), date(2026, JAN, 3)), id="across_years"
        ),
        pytest.param(
            "Dec. 21-27", date(2026, JAN, 2), Week(date(2025, DEC, 21), date(2025, DEC, 27)), id="last_year_week"
        ),
        pytest.param(
            "May 10-16", date(2026, 5, 21), Week(date(2026, 5, 10), date(2026, 5, 16)), id="month_unabbreviated"
        ),
        pytest.param("Sept. 7-13", date(2026, 9, 18), Week(date(2026, 9, 7), date(2026, 9, 13)), id="sept_spelling"),
        pytest.param(
            "Nov. 8-14", date(2026, NOV, 14), Week(date(2026, NOV, 8), date(2026, NOV, 14)), id="published_end_day"
        ),
        pytest.param(
            "Nov. 8-14", date(2026, NOV, 13), Week(date(2025, NOV, 8), date(2025, NOV, 14)), id="published_before_end"
        ),
        pytest.param("Nov. 31-Dec. 6", PUBLISHED, None, id="not_a_day"),
        pytest.param("Nov. 14-8", PUBLISHED, None, id="end_before_start"),
        pytest.param("GREEN", PUBLISHED, None, id="a_heading"),
    ],
)
def test_week_line_read(line: str, published: date, expected: Week | None) -> None:
    """The latest week the line can name that ends on or before the article's publication date."""
    assert week_from_line(line, published) == expected


@pytest.mark.parametrize(
    ("month", "day", "expected"),
    [
        pytest.param(JAN, 2, date(2026, JAN, 2), id="january_after_new_year"),
        pytest.param(DEC, 30, date(2025, DEC, 30), id="december_before_new_year"),
    ],
)
def test_day_placed_in_nearest_year(month: int, day: int, expected: date) -> None:
    """A date printed without a year goes in the year nearest the article's week."""
    assert resolve_day(month, day, Week(date(2025, DEC, 28), date(2026, JAN, 3))) == expected


def test_red_none_lists_nothing() -> None:
    """RED followed by NONE: no red places, no warnings."""
    assert walk_lines(["Nov. 8-14", "RED", "NONE"], PUBLISHED) == (
        [Week(date(2026, NOV, 8), date(2026, NOV, 14))],
        [],
        [],
    )


def test_result_without_place_warned() -> None:
    """A Result line with no place line before it is skipped and reported."""
    _, entries, warnings = walk_lines(["Nov. 8-14", "RED", "Result: Closure (Nov. 9)"], PUBLISHED)
    assert entries == []
    assert warnings == ["RED: a Result line with no place line before it, skipped: Result: Closure (Nov. 9)"]


def test_red_place_without_result_kept_undated() -> None:
    """A red place whose Result line never comes is kept with no dates, and reported."""
    _, entries, warnings = walk_lines(["Nov. 8-14", "RED", "Hot Wok, 500 Coors NW", "GREEN"], PUBLISHED)
    assert [(entry.name, entry.dates) for entry in entries] == [("Hot Wok", ())]
    assert warnings == ["RED: no Result line for Hot Wok; kept without dates"]


def test_unread_result_part_warned() -> None:
    """A result part with no date is left out of the outcomes and reported."""
    lines = ["Nov. 8-14", "RED", "Hot Wok, 500 Coors NW", "Result: Closure (Nov. 9); pending"]
    _, entries, warnings = walk_lines(lines, PUBLISHED)
    assert [outcome.result for outcome in entries[0].outcomes] == ["Closure"]
    assert warnings == ["RED: Hot Wok: result not read: pending"]


def test_impossible_date_skipped() -> None:
    """A place whose parentheses name a day that doesn't exist is skipped and reported."""
    _, entries, warnings = walk_lines(["Nov. 8-14", "GREEN", "Test Cafe, 100 Central SE (Nov. 31)"], PUBLISHED)
    assert entries == []
    assert warnings == ["GREEN: no usable date in parentheses, skipped: Test Cafe, 100 Central SE (Nov. 31)"]


def test_two_weeks_in_one_article() -> None:
    """A holiday article covering two weeks: each place is dated in its own week's year."""
    lines = [
        "Dec. 21-27",
        "GREEN",
        "Test Cafe, 100 Central SE (Dec. 22)",
        "Dec. 28-Jan. 3",
        "GREEN",
        "Acme, 2 4th NW (Jan. 2)",
    ]
    weeks, entries, _ = walk_lines(lines, date(2026, JAN, 8))
    assert weeks == [Week(date(2025, DEC, 21), date(2025, DEC, 27)), Week(date(2025, DEC, 28), date(2026, JAN, 3))]
    assert [entry.dates for entry in entries] == [(date(2025, DEC, 22),), (date(2026, JAN, 2),)]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        pytest.param(
            {"capture": "other/1"},
            ["not a news capture (capture is 'other/1', expected 'nm-health-news/1')"],
            id="wrong_kind",
        ),
        pytest.param({"headline": ""}, ["missing headline"], id="missing_headline"),
        pytest.param(
            {"url": "https://elsewhere.test/a/1"},
            ["elsewhere.test is not in [news] hosts in config.toml"],
            id="other_host",
        ),
        pytest.param({"published": "Nov 19"}, ["published is not a date: 'Nov 19'"], id="bad_published"),
        pytest.param(
            {"lines": ["GREEN", "Test Cafe, 100 Central SE (Nov. 12)"]},
            ['no week line (like "Nov. 8-14") in the article body'],
            id="no_week",
        ),
    ],
)
def test_capture_problems_named(change: dict[str, object], expected: list[str]) -> None:
    """A capture that can't be read says why, one problem per check."""
    assert capture_problems({**CAPTURE, **change}, HOSTS) == expected


def test_non_object_capture_refused() -> None:
    """A JSON file that isn't an object is no capture."""
    read = read_capture(["not", "a", "capture"], HOSTS)
    assert (read.link, read.problems) == (None, ["not a news capture (expected a JSON object)"])


def test_outcome_paren_typos_read() -> None:
    """A Result part missing either parenthesis still reads, and its date is kept."""
    lines = [
        "Sept. 27-Oct. 3",
        "RED",
        "Rising Star, 1 Main NE",
        "Result: Closure (Sept. 28; re-inspection required Sept. 28); passed follow-up inspection (Oct. 1)",
    ]
    _, entries, warnings = walk_lines(lines, date(2026, 10, 8))
    assert [(outcome.result, outcome.on) for outcome in entries[0].outcomes] == [
        ("Closure", date(2026, 9, 28)),
        ("re-inspection required", date(2026, 9, 28)),
        ("passed follow-up inspection", date(2026, 10, 1)),
    ]
    assert warnings == []


def test_class_note_missing_open_paren() -> None:
    """A class note that lost its "(" ("(July 29) Class C)") is still a class note, and the date still reads."""
    lines = ["July 26-Aug. 1", "YELLOW", "Desert Grill, 5200 Eubank NE (July 29) Class C)"]
    _, entries, warnings = walk_lines(lines, date(2026, 8, 6))
    assert [(e.name, e.address, e.dates, e.classes) for e in entries] == [
        ("Desert Grill", "5200 Eubank NE", (date(2026, 7, 29),), ("Class C",))
    ]
    assert warnings == []


def test_editor_note_skipped_quietly() -> None:
    """An "Editor\u2019s note" line after the lists is no fact and no warning."""
    lines = [
        "Nov. 8-14",
        "RED",
        "Bad Bistro, 600 Yale SE",
        "Result: Closure (Nov. 12)",
        "Editor\u2019s note: This story was updated.",
    ]
    _, entries, warnings = walk_lines(lines, PUBLISHED)
    assert [entry.name for entry in entries] == ["Bad Bistro"]
    assert warnings == []


def test_empty_capture_explained() -> None:
    """A capture with no article text (the paywall hid it) says so, not that the week line is missing."""
    assert capture_problems({**CAPTURE, "lines": []}, HOSTS) == [
        "the capture holds no article text (the paywall may have hidden it): save it again once the article shows"
    ]


def test_results_split_by_comma_or_colon() -> None:
    """Results the Journal joined with "), " or "): " instead of ";" are still separate results, each dated."""
    lines = [
        "Aug. 2-8",
        "RED",
        "Hot Wok, 500 Coors NW",
        "Result: Closure (Aug. 3), re-inspection required (Aug. 3); unsatisfactory (Aug. 5): re-inspection required (Aug. 5)",
    ]
    _, entries, warnings = walk_lines(lines, date(2026, 8, 12))
    assert [(outcome.result, outcome.on.day) for outcome in entries[0].outcomes] == [
        ("Closure", 3),
        ("re-inspection required", 3),
        ("unsatisfactory", 5),
        ("re-inspection required", 5),
    ]
    assert warnings == []
