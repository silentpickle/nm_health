# Copyright (c) 2026 nm_health contributors
"""Static site for GitHub Pages: This week, Last month, All time, Places, Map, About, and one page per place.

Every page is plain HTML that reads without JavaScript. places.js adds search, filters and strips to the place list
from places.json; map.js draws the map with packages/citymap (copied in at build time, never forked). Text from the
PDFs is untrusted: site_html escapes everything, and inspector text arrives already redacted (viewmodel.published).
"""

import json
import shutil
from datetime import date
from pathlib import Path

from nm_health import feed
from nm_health.rebuild import Rebuilt
from nm_health.settings import ROOT, Settings
from nm_health.site_html import (
    PLACE_DIR,
    REPORTS_DIR,
    SiteData,
    page_html,
    site_data,
    unsourced,
)
from nm_health.site_pages import (
    RANGES,
    about_page,
    data_page,
    map_page,
    place_page,
    places_page,
    range_page,
    range_reopenings,
)
from nm_health.viewmodel import (
    ARIA_LIST_MAX,
    Place,
    Reopening,
    level,
    reopened_flag,
    select_period,
    strip_cells,
    strip_code,
    unbroken,
)

STATIC_DIR = Path(__file__).resolve().parent / "site_static"
STATIC_FILES = ("style.css", "shared.js", "places.js", "map.js")
CITYMAP_DIR = ROOT / "packages" / "citymap"
# Copied as-is from packages/citymap: (source inside the package, name in the site).
CITYMAP_FILES = (
    ("citymap.js", "citymap.js"),
    ("citymap.css", "citymap.css"),
    ("data/albuquerque.geojson", "albuquerque.geojson"),
)
ROBOTS_NOINDEX = "User-agent: *\nDisallow: /\n"
COORD_DIGITS = 5  # about a metre
FLAG_HEADLINE_PESTS = 1
FLAG_EMPLOYEE_ITEMS = 2
FLAG_CLOSURE_IN_FORCE = 4
FLAG_MAYBE_SAME = 8  # the records can't tell this place apart from another: kept apart, flagged
FLAG_MERGED_BY_PERMIT = 16  # records under different names joined by permit: due a review (docs/place-identity.md)
EXAMPLES = 5  # unsourced inspections named in the error
JSON_SEPARATORS = (",", ":")


class UnsourcedError(Exception):
    """An inspection the site would describe has no weekly report on file."""


# ---------- places.json ----------


def _flags(place: Place) -> int:
    pests = FLAG_HEADLINE_PESTS if place.headline_pests else 0
    closed = FLAG_CLOSURE_IN_FORCE if place.closure_in_force else 0
    merged = FLAG_MERGED_BY_PERMIT if place.merged_by_permit else 0
    maybe = FLAG_MAYBE_SAME if place.maybe_same else 0
    return pests | closed | merged | maybe | (FLAG_EMPLOYEE_ITEMS if place.employee_items else 0)


def _lat_lng(place: Place) -> list[float] | None:
    if place.lat_lng is None:
        return None
    lat, lng = place.lat_lng
    return [round(lat, COORD_DIGITS), round(lng, COORD_DIGITS)]


def _place_row(data: SiteData, place: Place, statuses: dict[str, int]) -> list[object]:
    today = data.today
    history = [
        [(today - date.fromisoformat(i.date)).days, statuses.setdefault(i.status, len(statuses))]
        for i in place.inspections[:ARIA_LIST_MAX]
    ]
    closure = place.closures[-1].episode.start if place.closures else ""
    return [
        place.slug,
        place.name,
        place.legal_name,
        place.address,
        strip_code(strip_cells(place.inspections, today, data.settings.strip_weeks)),
        history,
        max(len(place.inspections) - ARIA_LIST_MAX, 0),
        _flags(place),
        closure,
        _lat_lng(place),
        reopened_flag(place, data.covered),
    ]


def _reopened_row(data: SiteData, reopened: Reopening) -> list[object]:
    spell = reopened.spell
    return [
        reopened.place.slug,
        spell.start,
        spell.end,
        spell.days,
        spell.end_status,
        unbroken(spell.start, spell.end or spell.start, data.covered),
    ]


def reopened_json(data: SiteData) -> dict[str, list[list[object]]]:
    """Each time-range page's "Reopened" section, by page name: what the pages list, for tracking over time."""
    found: dict[str, list[list[object]]] = {}
    for time_range in RANGES:
        period = select_period(data.places, data.reports, time_range.span_days)
        reopened = range_reopenings(data, time_range, period) if period else []
        found[time_range.file] = [_reopened_row(data, r) for r in reopened]
    return found


def places_json(data: SiteData) -> str:
    """The slim index places.js and map.js read.

    Each place is [slug, name, legal name, address, strip code (one char per week, settings.strip_weeks), [[days before today, status index], ...]
    newest first (up to 8), how many more inspections, flags (1 roaches/rodents, 2 employee items, 4 a closure in force, 8 may be the same business as another place, 16 merged by permit with names that differ), latest closure start or "",
    [lat, lng] or null, reopened flag text or "" (viewmodel.reopened_flag)]. `statuses` lists [status, level] by index.
    `reopened` lists each time-range page's Reopened section, keyed by page file: [slug, closure date, reopening date,
    days closed, reopening status, every day between in a report on file (else it may have reopened sooner)].
    """
    statuses: dict[str, int] = {}
    rows = [_place_row(data, p, statuses) for p in data.places]
    body = {
        "today": data.today.isoformat(),
        "statuses": [[status, level(status)] for status in statuses],
        "inspections": data.total,
        "withNotes": data.with_notes,
        "places": rows,
        "reopened": reopened_json(data),
    }
    return json.dumps(body, ensure_ascii=False, separators=JSON_SEPARATORS)


# ---------- Writing ----------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copy_assets(out: Path) -> None:
    for name in STATIC_FILES:
        shutil.copy(STATIC_DIR / name, out / name)
    for source, name in CITYMAP_FILES:
        shutil.copy(CITYMAP_DIR / source, out / name)


def _write_pages(data: SiteData, out: Path) -> None:
    pages = {
        **{r.file: range_page(data, r) for r in RANGES},
        "places.html": places_page(data),
        "map.html": map_page(data),
        "about.html": about_page(data),
        "data.html": data_page(data),
    }
    for name, page in pages.items():
        _write(out / name, page_html(data, page))
    for place in data.places:
        _write(out / PLACE_DIR / f"{place.slug}.html", page_html(data, place_page(data, place), depth=1))


# ---------- What we downloaded ----------


def _require_sources(data: SiteData) -> None:
    """Refuse to publish a statement the city's own documents don't back."""
    missing = unsourced(data)
    if missing:
        named = ", ".join(f"{i.name} {i.inspection_id} {i.date}" for i in missing[:EXAMPLES])
        msg = f"{len(missing)} inspections have no weekly report on file: {named}"
        raise UnsourcedError(msg)


def _copy_reports(data: SiteData, out: Path) -> None:
    files = {i.report_file for p in data.places for i in p.inspections if i.report_file} | {
        r.file for r in data.all_reports
    }
    (out / REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    for name in files:
        shutil.copy(data.settings.archive_dir / name, out / REPORTS_DIR / name)


def write_site(rebuilt: Rebuilt, settings: Settings) -> int:
    """Replace the site folder with freshly rendered pages; returns how many place pages were written."""
    data = site_data(rebuilt, settings, feed.today_utc().date())
    _require_sources(data)
    out = settings.site_dir
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    _write_pages(data, out)
    _copy_assets(out)
    _copy_reports(data, out)
    _write(out / "places.json", places_json(data))
    _write(out / ".nojekyll", "")
    if not settings.indexable:
        _write(out / "robots.txt", ROBOTS_NOINDEX)
    return len(data.places)
