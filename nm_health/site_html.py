# Copyright (c) 2026 nm_health contributors
"""The page frame and the pieces pages share: status chips, 52-week strips, place rows, This-week cards.

Every piece of text goes through `esc`: names, addresses and observations come from PDFs and are untrusted.
"""

import html
from dataclasses import dataclass
from datetime import date, timedelta

from nm_health.model import Inspection
from nm_health.rebuild import Rebuilt, Report
from nm_health.settings import Settings
from nm_health.viewmodel import (
    CELL_CLASSES,
    MIDDOT,
    RED_GROUP,
    Place,
    cell_code,
    group_places,
    level,
    month_ticks,
    nice_date,
    notice_count_text,
    notice_quote,
    recent_text,
    reports_in_window,
    row_flag,
    short_date,
    status_today,
    strip_cells,
    strip_label,
)

FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Mono:wght@400;500"
    "&display=swap"
)
EN_DASH = "\u2013"
LEFT_ARROW = "\u2190"
WHERE = f"Albuquerque, NM {MIDDOT} last 12 months"
TABS = (("week", "index.html", "This week"), ("places", "places.html", "Places"), ("map", "map.html", "Map"))
ABOUT_TAB = ("about", "about.html", "About")
FOOTER = (
    "Source: City of Albuquerque Environmental Health Department weekly inspection reports and its public "
    "inspection-status feed. Statuses are shown as the city issued them; inspector observations are quoted as "
    "published, with email addresses and phone numbers removed. Not affiliated with the City of Albuquerque."
)
NOINDEX = '<meta name="robots" content="noindex, nofollow">'
PLACE_DIR = "place"


@dataclass(frozen=True)
class SiteData:
    """Everything the pages are rendered from."""

    settings: Settings
    today: date
    places: list[Place]
    reports: tuple[Report, ...]  # weekly reports ending inside the window
    week_starts: dict[str, str | None]  # report file -> its week's first day

    @property
    def total(self) -> int:
        """Inspections in the window."""
        return sum(len(p.inspections) for p in self.places)

    @property
    def with_notes(self) -> int:
        """Inspections with inspector notes on file."""
        return sum(p.with_notes for p in self.places)


def site_data(rebuilt: Rebuilt, settings: Settings, today: date) -> SiteData:
    """Group the rebuilt inspections into places and keep the reports that fall in the window."""
    since = today - timedelta(days=settings.window_days)
    return SiteData(
        settings=settings,
        today=today,
        places=group_places(rebuilt.inspections),
        reports=reports_in_window(rebuilt.reports, since),
        week_starts={r.file: r.week_start for r in rebuilt.reports},
    )


@dataclass(frozen=True)
class Page:
    """One page before the frame goes round it."""

    title: str
    body: str
    active: str  # which tab is current
    head: str = ""  # extra tags for <head> (stylesheets, scripts)


def esc(text: str) -> str:
    """HTML-escape text for element content and attribute values."""
    return html.escape(text, quote=True)


# ---------- Frame ----------


def _tabs(active: str, up: str) -> str:
    links = [
        f'<a href="{up}{href}"{' aria-current="page"' if key == active else ""}>{label}</a>'
        for key, href, label in (*TABS, ABOUT_TAB)
    ]
    return f'<nav class="tabs" aria-label="Sections">{"".join(links)}</nav>'


def lede(data: SiteData) -> str:
    """The line under the site name, on every page."""
    return (
        "Food inspections in the City of Albuquerque's records for the last 12 months: every status the city issued, "
        f"and the inspector's notes for the {len(data.reports)} weekly reports saved so far. "
        "The city itself only shows the latest week."
    )


def page_html(data: SiteData, page: Page, depth: int = 0) -> str:
    """A whole HTML document; depth is how many folders below the site root the page sits."""
    up = "../" * depth
    name = esc(data.settings.site_name)
    robots = "" if data.settings.indexable else NOINDEX
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{robots}
<title>{esc(page.title)} {EN_DASH} {name}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS_URL}">
<link rel="stylesheet" href="{up}style.css">
{page.head}
</head>
<body>
<a class="skip" href="#view">Skip to content</a>
<div class="wrap">
<header class="mast"><a class="site" href="{up}index.html">{name}</a><span class="where">{WHERE}</span></header>
<p class="lede">{esc(lede(data))}</p>
{_tabs(page.active, up)}
<main id="view">
{page.body}
</main>
<footer>{esc(FOOTER)}</footer>
</div>
</body>
</html>
"""


# ---------- Shared pieces ----------


def chip(status: str) -> str:
    """The city's own status words, in placard colour with a shape cue."""
    return f'<span class="chip {level(status)}">{esc(status)}</span>'


def heading(text: str, count: int) -> str:
    """An h2 with a count beside it."""
    return f'<h2>{esc(text)}<span class="n">{count}</span></h2>'


def _cell(code: str) -> str:
    classes = CELL_CLASSES[code]
    return f'<i class="{classes}"></i>' if classes else "<i></i>"


def strip_html(place: Place, today: date, *, big: bool = False) -> str:
    """The 52-week strip, shape-coded, with every dated status in its accessible name."""
    cells = "".join(_cell(cell_code(c)) for c in strip_cells(place.inspections, today))
    size = " big" if big else ""
    label = esc(strip_label(place.inspections))
    return f'<div class="strip{size}" role="img" aria-label="{label}">{cells}</div>'


def months_html(today: date) -> str:
    """Month names under a big strip."""
    spans = "".join(
        f'<span class="q">{text}</span>' if quiet else f"<span>{text}</span>" for text, quiet in month_ticks(today)
    )
    return f'<div class="months" aria-hidden="true">{spans}</div>'


def _key(classes: str, label: str) -> str:
    cell = f'<i class="{classes}"></i>' if classes else "<i></i>"
    return f'<span><span class="k"><span class="strip">{cell}</span></span>{esc(label)}</span>'


def legend_html() -> str:
    """What each strip shape means."""
    keys = (
        ("g", "Approved"),
        ("y", "Conditional approved"),
        ("r", RED_GROUP),
        ("g so", "Status only (no inspector notes on file)"),
        ("", "No inspection"),
        ("g p", "Roaches or rodents cited"),
    )
    return f'<div class="legend">{"".join(_key(c, label) for c, label in keys)}</div>'


def place_href(place: Place, up: str = "") -> str:
    """Link to a place's page from a page `up` folders below the root."""
    return f"{up}{PLACE_DIR}/{esc(place.slug)}.html"


def _row_flags(place: Place) -> str:
    flags = []
    if place.headline_pests:
        flags.append('<span class="flag">Roaches or rodents cited</span>')
    reopened = row_flag(place)
    if reopened:
        flags.append(f'<span class="flag">{esc(reopened)}</span>')
    elif place.closures and level(place.latest.status) != "r":
        start = short_date(place.closures[-1].episode.start)
        flags.append(f'<span class="flag">{esc(RED_GROUP)} {start}</span>')
    return "".join(flags)


def row_html(place: Place, today: date) -> str:
    """One place in a list: name, address, latest status and date, flags, recent statuses (phones) and strip."""
    latest = place.latest
    meta = (
        f'<span class="data">{esc(place.address)}</span>{chip(latest.status)}'
        f"<span>{nice_date(latest.date)}</span>{_row_flags(place)}"
    )
    return (
        f'<li><a class="row" href="{place_href(place)}"><div class="info"><div class="nm">{esc(place.name)}</div>'
        f'<div class="meta">{meta}</div><div class="recent">{esc(recent_text(place.inspections))}</div></div>'
        f"{strip_html(place, today)}</a></li>"
    )


def plain_row_html(place: Place) -> str:
    """One place in the no-JavaScript list: name, address, latest status and date."""
    latest = place.latest
    return (
        f'<li><a class="row" href="{place_href(place)}"><div class="info"><div class="nm">{esc(place.name)}</div>'
        f'<div class="meta"><span class="data">{esc(place.address)}</span>{chip(latest.status)}'
        f"<span>{nice_date(latest.date)}</span></div></div></a></li>"
    )


def rows_html(rows: list[str]) -> str:
    """A list of place rows."""
    return f'<ul class="rows">{"".join(rows)}</ul>'


def notice_html(place: Place, inspection: Inspection, *, pest: bool) -> str:
    """A This-week card: date, name, address, status, and either the inspector's pest words or the count."""
    quote = notice_quote(place, inspection) if pest else None
    why = f"<q>{esc(quote)}</q>" if quote else f'<span class="quiet">{esc(notice_count_text(inspection))}</span>'
    kind = " pest" if pest else ""
    return (
        f'<a class="notice{kind}" href="{place_href(place)}"><span class="eyebrow">{nice_date(inspection.date)}</span>'
        f'<span class="nm">{esc(place.name)}</span><span class="data muted">{esc(place.address)}</span>'
        f'<span>{chip(inspection.status)}</span>{why}<span class="today">Status today: {esc(status_today(place))}</span></a>'
    )
