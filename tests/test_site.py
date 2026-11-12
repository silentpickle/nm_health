# Copyright (c) 2026 nm_health contributors
"""The static site: which files it writes, what every page carries, escaping, noindex, and the real archive."""

import html
import json
import re
import shutil
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from nm_health import feed, site
from nm_health.identity import establishment_slug
from nm_health.model import Inspection, Violation
from nm_health.rebuild import Rebuilt, Report, rebuild
from nm_health.settings import Settings, load
from nm_health.site import UnsourcedError, write_site
from nm_health.site_html import NO_SOURCE, site_data
from nm_health.viewmodel import build_place, stated
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
TOP_PAGES = ("index.html", "places.html", "map.html", "data.html", "about.html")
H1 = re.compile(r"<h1\b")
PDF_LINK = re.compile(r'href="([^"]+\.pdf)(?:#page=\d+)?"')
# A real weekly report stands in for the test report, so the build can read its text as it does in production.
STAND_IN_PDF = Path(__file__).resolve().parent.parent / "data" / "archive" / "2026-10-25_2026-10-31_0e0b9708501f.pdf"
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
        operational_status="Open",
    )


def feed_only(day: str, name: str = "FEED DINER", address: str = "5 MAIN ST NE") -> Inspection:
    """An inspection known only from the city's status feed (no weekly report on file)."""
    return replace(
        visit(day, name=name, status="Closure Re-Inspection Required"),
        address=address,
        operational_status=None,
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
    shutil.copy(STAND_IN_PDF, settings.archive_dir / REPORT_FILE)
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
        "data.html",
        "index.html",
        "map.html",
        "map.js",
        "place/test-cafe-100-central-ave-sw.html",
        "places.html",
        "places.js",
        "places.json",
        f"reports/{REPORT_FILE}",
        "robots.txt",
        "shared.js",
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
    inspection = replace(visit("2026-10-30", hostile, status="Closure Re-Inspection Required"), name="<b>CAFE</b>")
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
    """The city's permit line, strip, coverage, the pest quote and each inspection's report page."""
    site = build(tmp_path, visit("2026-10-29", ROACHES), visit("2026-10-26", name="TEST CAFE"))
    text = read(site, "place/test-cafe-100-central-ave-sw.html")
    assert 'class="strip big" role="img" aria-label="Inspections in the last 52 weeks: Oct 29, 2026: Approved;' in text
    assert "Inspector notes on file for 2 of 2 inspections." in text
    assert """<span class="reading" title="This site's reading of the inspector's words">Roaches, live""" in text
    assert "<q>Pest Type: Cockroach</q>" in text
    assert "Status that day, as issued by the city: Approved." in text
    assert "No later approved inspection in the weekly reports on file." in text
    permit_line = "Food Establishment (Permit # PT1): Operational Status \u2013 Open"
    assert f'<q>{permit_line}</q> <a href="../reports/{REPORT_FILE}">PDF</a>' in text  # PT1: not in the stand-in
    assert "Latest result in the weekly reports on file: Approved, Oct 29, 2026" in text
    assert '<a class="jump" href="#insp-0">Oct 29, 2026</a>: ' in text
    assert '<li class="g" id="insp-0">' in text
    assert f'<a href="../reports/{REPORT_FILE}#page=3">Week of Oct 25 report (PDF, p. 3)</a>' in text
    assert "<summary>Show everything the report says</summary>" in text


def test_feed_only_inspections_stay_off_the_site(tmp_path: Path) -> None:
    """No weekly report, no statement: a feed-only place gets no page, and a newer feed record is not even noted."""
    newer = feed_only("2026-11-06", name="TEST CAFE", address="100 CENTRAL AVE SW")
    site = build(tmp_path, visit("2026-10-29", ROACHES), newer, feed_only("2026-11-06"))
    assert not (site / "place" / "feed-diner-5-main-st-ne.html").exists()
    assert not (site / "sources").exists()
    place = read(site, "place/test-cafe-100-central-ave-sw.html")
    assert "later inspection" not in place
    assert "Closure Re-Inspection Required" not in place
    index = read(site, "index.html")
    assert "FEED DINER" not in index
    assert "isn&#x27;t on file yet" not in index


def test_covered_week_has_no_banner(tmp_path: Path) -> None:
    """When an archived report covers the newest date, no banner and pests come from the same week."""
    index = read(build(tmp_path, visit("2026-10-29", ROACHES)), "index.html")
    assert "isn&#x27;t on file yet" not in index
    assert "Roaches or rodents cited<span" in index


def test_landing_page_disclaimer_and_latest(tmp_path: Path) -> None:
    """The landing page carries the red not-endorsed notice and the newest report's week."""
    index = read(build(tmp_path, visit("2026-10-29", ROACHES)), "index.html")
    assert 'class="disclaimer"' in index
    assert "not endorsed by" in index
    assert "Latest weekly report on file: week ending" in index


def test_data_page_lists_reports_and_front_page_links_it(tmp_path: Path) -> None:
    """data.html lists every archived PDF with its header check; the landing page links to it."""
    site = build(tmp_path, visit("2026-10-29", ROACHES))
    assert 'href="data.html"' in read(site, "index.html")
    data = read(site, "data.html")
    assert REPORT_FILE in data
    assert "No department letterhead" in data


def test_places_page_lists_every_place_without_javascript(tmp_path: Path) -> None:
    """Every place is a plain link with its latest status; the search tools stay hidden until places.js runs."""
    site = build(tmp_path, visit("2026-10-29"), feed_only("2026-11-06"))
    text = read(site, "places.html")
    assert text.count('<a class="row" href="place/') == len(["TEST CAFE"])
    assert '<div class="search" id="tools" hidden>' in text
    assert '<script type="module" src="places.js"></script>' in text


def test_places_json_shape(tmp_path: Path) -> None:
    """One row per place: slug, names, address, strip, statuses, flags, closure start, coordinates, reopened."""
    site = build(tmp_path, visit("2026-10-29", ROACHES), feed_only("2026-11-06"))
    data = json.loads(read(site, "places.json"))
    assert data["statuses"] == [["Approved", "g"]]
    assert (data["today"], data["inspections"], data["withNotes"]) == ("2026-11-09", 1, 1)
    (cafe_row,) = data["places"]
    assert cafe_row == [
        "test-cafe-100-central-ave-sw",
        "TEST CAFE",
        None,
        "100 CENTRAL AVE SW",
        "." * 50 + "1.",
        [[11, 0]],
        0,
        1,
        "",
        None,
        "",
    ]


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
    for inspection in stated(rebuilt.inspections, rebuilt.reports):
        if inspection.report_file:
            slug = establishment_slug(inspection.name, inspection.address)
            expected[slug].add(html.escape(f"../reports/{inspection.report_file}"))
    for slug, links in expected.items():
        page = read(site, f"place/{slug}.html")
        assert links <= set(PDF_LINK.findall(page)), slug
    assert not [p.name for p in (site / "place").glob("*.html") if NO_SOURCE in p.read_text(encoding="utf-8")]


def test_same_day_reopening_states_the_reports(tmp_path: Path) -> None:
    """Closed 1:06 pm, conditional 2:07 pm the same day: the row flag and the place page state both, from the report."""
    closed = replace(
        visit("2026-10-30", status="Closure Re-Inspection Required"),
        inspection_id="PT0156723",
        time="13:06",
        permit_number="PT0156723",
    )
    reopened = replace(
        visit("2026-10-30", status="Conditional Approved"),
        inspection_id="RT-FOODEST-101632-2026",
        time="14:07",
        permit_number="PT0156723",
    )
    site = build(tmp_path, closed, reopened)
    index = read(site, "index.html")
    assert '<span class="flag">Closed and reopened Oct 30</span>' in index
    assert "Status today" not in index
    page = read(site, "place/test-cafe-100-central-ave-sw.html")
    assert "Latest result in the weekly reports on file: Conditional Approved, Oct 30, 2026, 2:07 pm" in page
    assert "Closed and reopened the same day (1:06 pm \u2192 2:07 pm): Conditional Approved." in page
    assert '<span class="d">Oct 30, 2026, 2:07 pm</span>' in page
    assert json.loads(read(site, "places.json"))["places"][0][-1] == "Closed and reopened Oct 30"
    assert 'data-f="reopened"' in read(site, "places.html")


def test_build_refuses_an_unsourced_inspection(tmp_path: Path) -> None:
    """The last guard: an inspection that slipped past stated() with no weekly report never reaches the site."""
    settings = make_settings(tmp_path)
    save_sources(settings, ())
    orphan = replace(visit("2026-10-29"), report_file="")
    data = site_data(Rebuilt((visit("2026-10-29"),), (REPORT,)), settings, TODAY.date())
    with pytest.raises(UnsourcedError, match="PT-TEST-2026-10-29"):
        site._require_sources(replace(data, places=[build_place("orphan", [orphan])]))  # noqa: SLF001 - the guard itself
