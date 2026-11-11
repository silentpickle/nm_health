# Copyright (c) 2026 nm_health contributors
"""The static site: which files it writes, what every page carries, escaping, noindex, and the real archive."""

import html
import json
import re
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from nm_health import feed
from nm_health.identity import establishment_slug
from nm_health.model import Inspection, Violation
from nm_health.rebuild import Rebuilt, Report, rebuild
from nm_health.settings import Settings, load
from nm_health.site import FLAG_CLOSURE_IN_FORCE, UnsourcedError, write_site
from nm_health.site_html import NO_SOURCE
from tests.test_archive import make_settings

TODAY = datetime(2026, 11, 9, 12, tzinfo=UTC)
REPORT_FILE = "2026-10-25_2026-10-31_abc.pdf"
REPORT = Report(REPORT_FILE, "abc", "2026-10-25", "2026-10-31", "test", "2026-11-04", "current", 2)
ROACHES = Violation(
    "Pest Control",
    "Controlling Pests, If Present: Treatment",
    "",
    "Observed pests. Pest Type: Cockroach",
    ("roaches", "pest_control"),
    "live",
    (("Pest Type", "Cockroach"),),
)
PLACES_JSON_LIMIT = 300_000  # bytes
TOP_PAGES = ("index.html", "places.html", "map.html", "about.html")
H1 = re.compile(r"<h1\b")
PDF_LINK = re.compile(r'href="([^"]+\.pdf)(?:#page=\d+)?"')
PDF_BYTES = b"%PDF-1.4 test report"
FEED_DEFAULT_TIME = "09:00"


def visit(day: str, *violations: Violation, status: str = "Approved", name: str = "TEST CAFE") -> Inspection:
    """One inspection with notes from the archived report."""
    return Inspection(
        inspection_id=f"PT-{name[:4]}-{day}",
        date=day,
        kind="Routine Food Establishment Inspection",
        status=status,
        name=name,
        address="100 CENTRAL AVE SW",
        permit_number="PT1",
        permit_type="Food Establishment",
        report_file=REPORT_FILE,
        page=3,
        violations=violations,
    )


def feed_only(day: str, name: str = "FEED DINER") -> Inspection:
    """An inspection known only from the city's status feed."""
    return replace(
        visit(day, name=name, status="Closure Re-Inspection Required"),
        address="5 MAIN ST NE",
        report_file="",
        page=None,
        has_details=False,
        violation_count=4,
        lat=35.08,
        lng=-106.65,
    )


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """The site's 52-week strips end on a known day."""
    monkeypatch.setattr(feed, "today_utc", lambda: TODAY)


def feed_row(inspection: Inspection) -> dict[str, object]:
    """The city's feed row for an inspection, as the feed would return it."""
    return {
        "category": inspection.kind,
        "ticket_id": inspection.inspection_id,
        "street_address": inspection.address,
        feed.NUMBER: inspection.inspection_id,
        feed.COMPANY: inspection.name,
        feed.STATUS: inspection.status,
        feed.ACTUAL_START: f"{inspection.date}T{inspection.time or FEED_DEFAULT_TIME}:00.000",
        feed.VIOLATIONS: str(inspection.violation_count or 0),
    }


def save_sources(settings: Settings, inspections: tuple[Inspection, ...]) -> None:
    """What the build links to: the weekly PDF, and a saved feed response with each feed-only inspection's row."""
    settings.archive_dir.mkdir(parents=True, exist_ok=True)
    (settings.archive_dir / REPORT_FILE).write_bytes(PDF_BYTES)
    rows = [feed_row(i) for i in inspections if not i.has_details]
    body = json.dumps({"api_data": {"records": rows}}).encode()
    feed.save_raw(settings, TODAY.year, body, TODAY)


def build(tmp_path: Path, *inspections: Inspection, settings: Settings | None = None) -> Path:
    """Write the site for these inspections, with their sources on file; returns the site folder."""
    chosen = settings or make_settings(tmp_path)
    save_sources(chosen, inspections)
    write_site(Rebuilt(inspections, (REPORT,)), chosen)
    return chosen.site_dir


def read(site: Path, name: str) -> str:
    """One written file's text."""
    return (site / name).read_text(encoding="utf-8")


def pages(site: Path) -> list[Path]:
    """Every HTML page written."""
    return sorted(site.rglob("*.html"))


def test_write_site_writes_every_page(tmp_path: Path) -> None:
    """Top pages, place pages, assets, places.json, robots.txt, and the city documents the pages cite."""
    site = build(tmp_path, visit("2026-10-29", ROACHES), feed_only("2026-11-06"))
    written = sorted(p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file())
    assert written == [
        ".nojekyll",
        "about.html",
        "albuquerque.geojson",
        "citymap.css",
        "citymap.js",
        "index.html",
        "map.html",
        "map.js",
        "place/feed-diner-5-main-st-ne.html",
        "place/test-cafe-100-central-ave-sw.html",
        "places.html",
        "places.js",
        "places.json",
        f"reports/{REPORT_FILE}",
        "robots.txt",
        "shared.js",
        "sources/feed/PT-FEED-2026-11-06_2026-11-06.json",
        "style.css",
    ]


def test_every_page_has_one_h1_lang_title_and_site_name(tmp_path: Path) -> None:
    """One h1 per page, lang="en", a page title ending in the site name from settings, the name in the header."""
    settings = replace(make_settings(tmp_path), site_name="Burque <Bites>")
    site = build(tmp_path, visit("2026-10-29"), settings=settings)
    for page in pages(site):
        text = page.read_text(encoding="utf-8")
        assert len(H1.findall(text)) == 1, page.name
        assert '<html lang="en">' in text
        assert re.search(r"<title>[^<]+ \u2013 Burque &lt;Bites&gt;</title>", text), page.name
        assert '">Burque &lt;Bites&gt;</a>' in text
    assert "<title>DINER" not in read(site, "index.html")


@pytest.mark.parametrize(
    ("indexable", "robots_meta"),
    [pytest.param(False, True, id="not_indexable"), pytest.param(True, False, id="indexable_site")],
)
def test_noindex_follows_settings(tmp_path: Path, *, indexable: bool, robots_meta: bool) -> None:
    """Not indexable: every page says noindex and robots.txt disallows all. Indexable: neither."""
    settings = replace(make_settings(tmp_path), indexable=indexable)
    site = build(tmp_path, visit("2026-10-29"), settings=settings)
    meta = '<meta name="robots" content="noindex, nofollow">'
    assert all((meta in p.read_text(encoding="utf-8")) == robots_meta for p in pages(site))
    assert (site / "robots.txt").exists() == robots_meta
    if robots_meta:
        assert read(site, "robots.txt") == "User-agent: *\nDisallow: /\n"


def test_text_from_pdfs_is_escaped(tmp_path: Path) -> None:
    """Hostile names, addresses and observations are text everywhere, never markup."""
    hostile = Violation(
        "Plumbing",
        "<img src=x onerror=alert(1)>",
        "",
        '<script>x()</script> Location: "><b>bold</b>',
        details=(("Location", '"><b>bold</b>'),),
    )
    inspection = replace(visit("2026-11-06", hostile, status="Closure Re-Inspection Required"), name="<b>CAFE</b>")
    site = build(tmp_path, replace(inspection, address="1 <i>A</i> ST"))
    for page in pages(site):
        text = page.read_text(encoding="utf-8")
        assert "<script>x()" not in text
        assert "<b>" not in text
        assert "<img src=x" not in text
    place = read(site, next(p.relative_to(site).as_posix() for p in pages(site) if "place/" in p.as_posix()))
    assert "&lt;script&gt;x()&lt;/script&gt;" in place
    assert "&lt;b&gt;CAFE&lt;/b&gt;" in place
    assert "&lt;b&gt;CAFE&lt;/b&gt;" in read(site, "index.html")


def test_email_and_phone_never_published(tmp_path: Path) -> None:
    """Inspector text on every page and in places.json has email addresses and phone numbers removed."""
    leak = Violation(
        "Pest Control",
        "Controlling Pests",
        "Call 505-768-2738",
        "Observed roaches. Send photos to inspector@cabq.gov. Pest Type: Cockroach call 505 768 2738",
        ("roaches",),
        "live",
        (("Pest Type", "Cockroach call 505 768 2738"),),
    )
    site = build(tmp_path, visit("2026-10-29", leak))
    for path in [*pages(site), site / "places.json"]:
        text = path.read_text(encoding="utf-8")
        assert "cabq.gov" not in text
        assert "768" not in text
    assert "[email removed]" in read(site, "place/test-cafe-100-central-ave-sw.html")


def test_place_page_states_what_the_records_show(tmp_path: Path) -> None:
    """Strip, coverage, the pest quote with reading/status/next approval/jump link, and each inspection's source."""
    site = build(tmp_path, visit("2026-10-29", ROACHES), visit("2026-09-02", name="TEST CAFE"))
    text = read(site, "place/test-cafe-100-central-ave-sw.html")
    assert 'class="strip big" role="img" aria-label="Inspections in the last 52 weeks: Oct 29, 2026: Approved;' in text
    assert "Inspector notes on file for 2 of 2 inspections." in text
    assert """<span class="reading" title="This site's reading of the inspector's words">Roaches, live""" in text
    assert "<q>Pest Type: Cockroach</q>" in text
    assert "Status that day, as issued by the city: Approved." in text
    assert "No later approved inspection on record." in text
    assert '<a class="jump" href="#insp-0">Oct 29, 2026</a>: ' in text
    assert '<li class="g" id="insp-0">' in text
    assert f'<a href="../reports/{REPORT_FILE}#page=3">Week of Oct 25 report (PDF, p. 3)</a>' in text
    assert "<summary>Show everything the report says</summary>" in text


def test_feed_only_place_and_banner(tmp_path: Path) -> None:
    """Feed-only inspections say the notes aren't on file; no report covers the newest date, so the banner shows."""
    site = build(tmp_path, visit("2026-10-29", ROACHES), feed_only("2026-11-06"))
    place = read(site, "place/feed-diner-5-main-st-ne.html")
    assert "Inspector notes on file for none of its 1 inspection in this period" in place
    assert "the one covering this date isn&#x27;t in our archive." in place
    feed_link = '<a href="../sources/feed/PT-FEED-2026-11-06_2026-11-06.json">City status feed record</a>'
    assert feed_link in place
    record = json.loads(read(site, "sources/feed/PT-FEED-2026-11-06_2026-11-06.json"))
    assert record["record"] == feed_row(feed_only("2026-11-06"))  # the city's row, unchanged
    assert record["saved_response"].startswith(f"data/feed/raw/{TODAY.year}/")
    index = read(site, "index.html")
    assert "weekly report for this week isn&#x27;t on file yet" in index
    assert "Roaches or rodents cited, week of Oct 25" in index
    assert "Closure or unsatisfactory<span" in index
    assert ">Closed<" not in index


def test_covered_week_has_no_banner(tmp_path: Path) -> None:
    """When an archived report covers the newest date, no banner and pests come from the same week."""
    index = read(build(tmp_path, visit("2026-10-29", ROACHES)), "index.html")
    assert "isn&#x27;t on file yet" not in index
    assert "Roaches or rodents cited<span" in index


def test_places_page_lists_every_place_without_javascript(tmp_path: Path) -> None:
    """Every place is a plain link with its latest status; the search tools stay hidden until places.js runs."""
    site = build(tmp_path, visit("2026-10-29"), feed_only("2026-11-06"))
    text = read(site, "places.html")
    assert text.count('<a class="row" href="place/') == len(["TEST CAFE", "FEED DINER"])
    assert '<div class="search" id="tools" hidden>' in text
    assert '<script type="module" src="places.js"></script>' in text


def test_places_json_shape(tmp_path: Path) -> None:
    """One row per place: slug, names, address, strip, statuses, flags, closure start, coordinates, reopened."""
    site = build(tmp_path, visit("2026-10-29", ROACHES), feed_only("2026-11-06"))
    data = json.loads(read(site, "places.json"))
    assert data["statuses"] == [["Closure Re-Inspection Required", "r"], ["Approved", "g"]]
    assert (data["today"], data["inspections"], data["withNotes"]) == ("2026-11-09", 2, 1)
    feed_row, cafe_row = data["places"]
    assert feed_row == [
        "feed-diner-5-main-st-ne",
        "FEED DINER",
        None,
        "5 MAIN ST NE",
        "." * 51 + "R",
        [[3, 0]],
        0,
        FLAG_CLOSURE_IN_FORCE,
        "2026-11-06",
        [35.08, -106.65],
        "",
    ]
    assert cafe_row[4] == "." * 50 + "1."
    assert cafe_row[7] == 1


def test_map_and_about_pages(tmp_path: Path) -> None:
    """The map loads citymap through an import map; About links the reports and the error-report page."""
    site = build(tmp_path, visit("2026-10-29"))
    map_html = read(site, "map.html")
    assert '<script type="importmap">{"imports": {"citymap": "./citymap.js"}}</script>' in map_html
    assert '<link rel="stylesheet" href="citymap.css">' in map_html
    about = read(site, "about.html")
    assert '<a href="https://github.com/silentpickle/nm_health/issues">Report an error</a>' in about
    assert f'<a href="reports/{REPORT_FILE}">PDF</a>' in about
    assert f'<a href="https://example.test/pdf/{REPORT_FILE}">archive history</a>' in about


def test_real_archive(tmp_path: Path) -> None:
    """The committed archive: places.json under 300 KB, and every place page links each of its PDFs."""
    settings = replace(load(), site_dir=tmp_path / "site")
    rebuilt = rebuild(settings, date(2025, 11, 9))
    count = write_site(rebuilt, settings)
    site = settings.site_dir
    assert len(list((site / "place").glob("*.html"))) == count
    assert (site / "places.json").stat().st_size < PLACES_JSON_LIMIT
    assert len(json.loads(read(site, "places.json"))["places"]) == count
    expected: dict[str, set[str]] = defaultdict(set)
    for inspection in rebuilt.inspections:
        if inspection.report_file:
            slug = establishment_slug(inspection.name, inspection.address)
            expected[slug].add(html.escape(f"../reports/{inspection.report_file}"))
    for slug, links in expected.items():
        page = read(site, f"place/{slug}.html")
        assert links <= set(PDF_LINK.findall(page)), slug
    assert not [p.name for p in (site / "place").glob("*.html") if NO_SOURCE in p.read_text(encoding="utf-8")]


def test_same_day_reopening_shows_status_today(tmp_path: Path) -> None:
    """Closed 1:06 pm, conditional 2:07 pm: the card, the row and the place page all say it's open again."""
    closed = replace(
        visit("2026-11-06", status="Closure Re-Inspection Required"),
        inspection_id="PT0156723",
        time="13:06",
        permit_number="PT0156723",
    )
    reopened = replace(
        visit("2026-11-06", status="Conditional Approved"),
        inspection_id="RT-FOODEST-101632-2026",
        time="14:07",
        permit_number="PT0156723",
    )
    site = build(tmp_path, closed, reopened)
    today = "Open \u00b7 Conditional Approved, per the Nov 6, 2026, 2:07 pm inspection"
    index = read(site, "index.html")
    assert f'<span class="today">Status today: {html.escape(today)}</span>' in index
    assert '<span class="flag">Closed and reopened Nov 6</span>' in index
    page = read(site, "place/test-cafe-100-central-ave-sw.html")
    assert f'<span class="lbl">Status today</span> {html.escape(today)}</p>' in page
    assert "Closed and reopened the same day (1:06 pm \u2192 2:07 pm): Conditional Approved." in page
    assert '<span class="d">Nov 6, 2026, 2:07 pm</span>' in page
    assert json.loads(read(site, "places.json"))["places"][0][-1] == "Closed and reopened Nov 6"
    assert 'data-f="reopened"' in read(site, "places.html")


def test_build_refuses_an_unsourced_inspection(tmp_path: Path) -> None:
    """An inspection with neither a weekly report nor a feed row on file never reaches the site."""
    settings = make_settings(tmp_path)
    save_sources(settings, ())
    orphan = feed_only("2026-11-06")
    with pytest.raises(UnsourcedError, match="PT-FEED-2026-11-06"):
        write_site(Rebuilt((orphan,), (REPORT,)), settings)
    assert not settings.site_dir.exists()
