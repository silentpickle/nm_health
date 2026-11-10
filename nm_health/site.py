# Copyright (c) 2026 nm_health contributors
"""Static site for GitHub Pages: This week, Places, Map, About, and one page per place.

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
from nm_health.site_html import PLACE_DIR, SiteData, page_html, site_data
from nm_health.site_pages import about_page, map_page, place_page, places_page, week_page
from nm_health.viewmodel import ARIA_LIST_MAX, Place, level, strip_cells, strip_code

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
JSON_SEPARATORS = (",", ":")


# ---------- places.json ----------


def _flags(place: Place) -> int:
    pests = FLAG_HEADLINE_PESTS if place.headline_pests else 0
    return pests | (FLAG_EMPLOYEE_ITEMS if place.employee_items else 0)


def _lat_lng(place: Place) -> list[float] | None:
    if place.lat_lng is None:
        return None
    lat, lng = place.lat_lng
    return [round(lat, COORD_DIGITS), round(lng, COORD_DIGITS)]


def _place_row(place: Place, today: date, statuses: dict[str, int]) -> list[object]:
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
        strip_code(strip_cells(place.inspections, today)),
        history,
        max(len(place.inspections) - ARIA_LIST_MAX, 0),
        _flags(place),
        closure,
        _lat_lng(place),
    ]


def places_json(data: SiteData) -> str:
    """The slim index places.js and map.js read.

    Each place is [slug, name, legal name, address, strip code (52 chars), [[days before today, status index], ...]
    newest first (up to 8), how many more inspections, flags (1 roaches/rodents, 2 employee items), latest closure start or "",
    [lat, lng] or null]. `statuses` lists [status, level] by index.
    """
    statuses: dict[str, int] = {}
    rows = [_place_row(p, data.today, statuses) for p in data.places]
    body = {
        "today": data.today.isoformat(),
        "statuses": [[status, level(status)] for status in statuses],
        "inspections": data.total,
        "withNotes": data.with_notes,
        "places": rows,
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
        "index.html": week_page(data),
        "places.html": places_page(data),
        "map.html": map_page(data),
        "about.html": about_page(data),
    }
    for name, page in pages.items():
        _write(out / name, page_html(data, page))
    for place in data.places:
        _write(out / PLACE_DIR / f"{place.slug}.html", page_html(data, place_page(data, place), depth=1))


def write_site(rebuilt: Rebuilt, settings: Settings) -> int:
    """Replace the site folder with freshly rendered pages; returns how many place pages were written."""
    out = settings.site_dir
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    data = site_data(rebuilt, settings, feed.today_utc().date())
    _write_pages(data, out)
    _copy_assets(out)
    _write(out / "places.json", places_json(data))
    _write(out / ".nojekyll", "")
    if not settings.indexable:
        _write(out / "robots.txt", ROBOTS_NOINDEX)
    return len(data.places)
