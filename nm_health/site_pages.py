# Copyright (c) 2026 nm_health contributors
"""The site's pages as HTML bodies: This week, Places, Map, About, and one place's whole record."""

from collections.abc import Callable

from nm_health.model import Inspection, Violation
from nm_health.rebuild import Report
from nm_health.signals import HEADLINE_PESTS, is_pass, is_red
from nm_health.site_html import (
    EN_DASH,
    LEFT_ARROW,
    REPORTS_DIR,
    Page,
    SiteData,
    chip,
    esc,
    heading,
    legend_html,
    months_html,
    notice_html,
    plain_row_html,
    row_html,
    rows_html,
    source_links,
    strip_html,
)
from nm_health.viewmodel import (
    MIDDOT,
    RED_GROUP,
    TAG_LABEL,
    ClosureRun,
    PestCitation,
    Place,
    Week,
    amended_text,
    closed_text,
    closure_end,
    closure_start,
    coverage_line,
    feed_only_text,
    kind_line,
    level,
    nice_date,
    other_pest_kinds,
    pest_reading,
    plural,
    report_text,
    select_week,
    short_date,
    status_today,
    thousands,
    unique_places,
    violation_lead,
    violation_title,
    when_text,
)

PAGE_SIZE = 60  # rows shown before "Show more" (places.js pages the same way)
FILTERS = (
    ("all", "All"),
    ("red", RED_GROUP),
    ("reopened", "Open again after a red result"),
    ("pests", "Roaches or rodents"),
    ("employee", "Employee items"),
)
NO_JS_MAP = "The map needs JavaScript."
MAP_NOTE = (
    "Each dot is a place inspected in the last 12 months, coloured by its latest status as issued by the city. "
    "Pinch, drag or use + and \u2212 to zoom. Use the Places tab to browse by name."
)
MAP_LEGEND = (
    ("--ok-cell", False, "Approved"),
    ("--warn-cell", False, "Conditional approved"),
    ("--bad-cell", False, RED_GROUP),
    ("--surface", True, "Roaches or rodents cited in notes on file"),
)
NOT_A_CERTIFICATE = "An inspection reports what one inspector found on one day. No citation is not a certification."
NO_LATER_APPROVAL = "No later approved inspection on record."
UP = "../"  # place pages sit one folder below the site root
ISO_DATE_LEN = len("2026-01-01")
SHA_SHOWN = 12  # hex digits of a report's SHA-256 shown on the About page


# ---------- This week ----------


def _cards(cards: list[str], empty: str) -> str:
    if not cards:
        return f'<p class="muted">{esc(empty)}</p>'
    return f'<div class="lead">{"".join(cards)}</div>'


def _pest_section(week: Week) -> str:
    cards = [notice_html(p, i, pest=True) for p, i in week.pest_visits]
    if week.covered:
        return heading("Roaches or rodents cited", len(cards)) + _cards(cards, "None cited in that report.")
    report = week.pest_report
    if report is None or report.week_start is None or report.week_end is None:
        empty = "No weekly report on file yet, so pest citations can't be shown."
        return heading("Roaches or rodents cited", 0) + f'<p class="muted">{esc(empty)}</p>'
    title = f"Roaches or rodents cited, week of {short_date(report.week_start)}"
    span = f"{short_date(report.week_start)} {EN_DASH} {nice_date(report.week_end)}"
    note = f'<p class="note">From the latest weekly report on file ({span}).</p>'
    return heading(title, len(cards)) + note + _cards(cards, "None cited in that report.")


BANNER = (
    "The city's weekly report for this week isn't on file yet. Statuses below come from the city's "
    "inspection-status feed; inspector notes and pest citations appear once the report is saved."
)


def _week_body(data: SiteData, week: Week) -> str:
    red = [notice_html(p, i, pest=False) for p, i in week.red]
    other = unique_places(week.other)[:PAGE_SIZE]
    parts = [
        '<h1 class="view">This week</h1>',
        f'<p class="eyebrow">Inspections {short_date(week.start)} {EN_DASH} {nice_date(week.end)}</p>',
        "" if week.covered else f'<p class="banner">{esc(BANNER)}</p>',
        heading(RED_GROUP, len(red)),
        _cards(red, "None in the city's records for these dates."),
        _pest_section(week),
        heading("Other inspections", len(week.other)),
        rows_html([row_html(p, data.today) for p in other]),
    ]
    return "\n".join(parts)


def week_page(data: SiteData) -> Page:
    """index.html: the newest seven days of inspections."""
    week = select_week(data.places, data.reports)
    if week is None:
        body = '<h1 class="view">This week</h1><p class="muted">No inspections on file yet.</p>'
        return Page("This week", body, "week")
    return Page("This week", _week_body(data, week), "week")


# ---------- Places ----------


def _filter_buttons() -> str:
    buttons = "".join(
        f'<button type="button" data-f="{key}" aria-pressed="{"true" if key == "all" else "false"}">{esc(label)}</button>'
        for key, label in FILTERS
    )
    return f'<div class="filters" role="group" aria-label="Filter places">{buttons}</div>'


def places_page(data: SiteData) -> Page:
    """places.html: every place as a plain link list; places.js adds search, filters, strips and paging."""
    count = thousands(len(data.places))
    body = (
        '<h1 class="view">Places</h1>\n'
        '<div class="search" id="tools" hidden><input id="q" type="search" placeholder="Name or street" '
        f'aria-label="Search places by name or street">{_filter_buttons()}</div>\n'
        f'<div id="list"><p class="eyebrow">{count} of {count} places</p>'
        f"{rows_html([plain_row_html(p) for p in data.places])}</div>"
    )
    return Page("Places", body, "places", '<script type="module" src="places.js"></script>')


# ---------- Map ----------


def _map_key(color: str, ring: str, label: str) -> str:
    return f'<span><i style="background:var({color});{ring}"></i>{esc(label)}</span>'


def map_page(_data: SiteData) -> Page:
    """map.html: one dot per place, drawn by map.js with packages/citymap."""
    ring = "box-shadow:0 0 0 2px var(--ink)"
    keys = "".join(_map_key(color, ring if ringed else "", label) for color, ringed, label in MAP_LEGEND)
    toggle = f"Only places with a {RED_GROUP.lower()} result"
    body = (
        '<h1 class="view">Map</h1>\n'
        f'<p class="note">{esc(MAP_NOTE)}</p>\n'
        f'<button class="toggle" id="red-only" type="button" aria-pressed="false" hidden>{esc(toggle)}</button>\n'
        f'<div class="mapbox" id="map"><noscript><p class="note">{NO_JS_MAP} '
        '<a href="places.html">Browse places by name</a>.</p></noscript></div>\n'
        f'<div class="maplegend">{keys}</div>'
    )
    head = (
        '<link rel="stylesheet" href="citymap.css">\n'
        '<script type="importmap">{"imports": {"citymap": "./citymap.js"}}</script>\n'
        '<script type="module" src="map.js"></script>'
    )
    return Page("Map", body, "map", head)


# ---------- About ----------


def _report_item(data: SiteData, report: Report) -> str:
    start = short_date(report.week_start) if report.week_start else "?"
    end = nice_date(report.week_end) if report.week_end else "?"
    count = plural(report.inspections, "inspection", "inspections")
    saved = nice_date(report.seen_at[:ISO_DATE_LEN])
    history = esc(data.settings.pdf_base_url + report.file)
    return (
        f'<li>{start} {EN_DASH} {end} {MIDDOT} {count} {MIDDOT} <a href="{REPORTS_DIR}/{esc(report.file)}">PDF</a>'
        f'<div class="quiet">Saved {saved} from <span class="data">{esc(report.source)}</span> {MIDDOT} '
        f'SHA-256 <span class="data">{esc(report.sha256[:SHA_SHOWN])}</span> {MIDDOT} '
        f'<a href="{history}">archive history</a></div></li>'
    )


def _reports_list(data: SiteData) -> str:
    ordered = sorted(data.reports, key=lambda r: r.week_end or "", reverse=True)
    return f'<ul class="reports">{"".join(_report_item(data, r) for r in ordered)}</ul>'


def about_page(data: SiteData) -> Page:
    """about.html: where the data comes from and what it does not say."""
    counts = (
        f"For this period, {len(data.reports)} weekly reports are on file, so inspector notes exist for "
        f"{thousands(data.with_notes)} of {thousands(data.total)} inspections. "
        "The rest show the status and violation count from the feed only."
    )
    body = f"""<section class="about">
<h1 class="view">About this data</h1>
<h2>Where it comes from</h2>
<p>The City of Albuquerque publishes one PDF of the week's food inspections and replaces it the next week, and runs a
public inspection-status feed. This site keeps both and shows the last 12 months.</p>
<p>{esc(counts)}</p>
<h2>What it does not say</h2>
<p>An inspection reports what one inspector found on one day. No citation is not a certification: inspectors never
declare a place pest-free, and neither does this site.</p>
<p>Statuses are shown in the city's own words. Labels such as \u201cRoaches, live\u201d are this site's reading of the
inspector's notes, which are always quoted beside them. Email addresses and phone numbers in the notes are removed.</p>
<h2>Weekly reports on file</h2>
{_reports_list(data)}
<h2>Report an error</h2>
<p>If something here doesn't match the city's report, open an issue on the project's GitHub page with the place and
the date.</p>
<p><a href="{esc(data.settings.report_error_url)}">Report an error</a></p>
</section>"""
    return Page("About this data", body, "about")


# ---------- Place ----------


def _fact(term: str, detail: str) -> str:
    return f'<dl class="fact"><dt>{esc(term)}</dt><dd>{detail}</dd></dl>'


def _sources(data: SiteData, place: Place, cited: list[Inspection]) -> str:
    """'Source: Oct 9, 2026, 11:30 am inspection: City status feed record' for each inspection a statement rests on."""
    parts = [
        f'<a class="jump" href="#insp-{place.inspections.index(i)}">{esc(when_text(i.date, i.time))}</a>: '
        f"{source_links(data, i, UP)}"
        for i in dict.fromkeys(cited)
    ]
    return f'<div class="src">Source: {"; ".join(parts)}</div>' if parts else ""


def _found(place: Place, day: str | None, wanted: Callable[[Inspection], bool]) -> list[Inspection]:
    """The place's first inspection on `day` that `wanted` accepts, as a list (empty when none)."""
    return next(([i] for i in reversed(place.inspections) if i.date == day and wanted(i)), [])


def _pest_fact(data: SiteData, place: Place, citation: PestCitation) -> str:
    cleared = (
        f"Next approved inspection: {nice_date(citation.cleared)}. "
        if citation.cleared
        else f'<span class="open">{NO_LATER_APPROVAL} </span>'
    )
    reading = esc(pest_reading(citation))
    detail = (
        f'<span class="reading" title="This site\'s reading of the inspector\'s words">{reading}</span>'
        f"<q>{esc(citation.quote)}</q>"
        f'<div class="quiet">Status that day, as issued by the city: {esc(citation.status)}. {cleared}'
        "</div>"
        f"{_sources(data, place, [place.inspections[citation.index]])}"
    )
    return _fact(nice_date(citation.date), detail)


def _closure_cited(place: Place, run: ClosureRun) -> list[Inspection]:
    """The inspections a closure entry rests on: the one that started it, each reopening, the one that ended it."""
    first = _found(place, run.episode.start, lambda i: is_red(i.status))
    reopenings = [
        i
        for spell in run.closed
        for i in place.inspections
        if (i.date, i.time, i.status) == (spell.end, spell.end_time, spell.end_status)
    ]
    last = _found(place, run.episode.end, lambda i: is_pass(i.status) and i.status == run.episode.end_status)
    return first + reopenings + last


def _closure_fact(data: SiteData, place: Place, run: ClosureRun) -> str:
    end = closure_end(run)
    after = esc(end) if end else f'<span class="open">{NO_LATER_APPROVAL}</span>'
    closed = "".join(f'<div class="closed">{esc(closed_text(spell))}</div>' for spell in run.closed)
    sources = _sources(data, place, _closure_cited(place, run))
    return _fact(RED_GROUP, f'{esc(closure_start(run))}{closed}<div class="quiet">{after}</div>{sources}')


def _other_pests_fact(place: Place) -> str:
    other = [c for c in place.pests if not c.headline]
    if not other:
        return ""
    lines = "".join(
        f'<div class="quiet">{short_date(c.date)} {MIDDOT} {esc(other_pest_kinds(c))}: <q>{esc(c.quote)}</q></div>'
        for c in other
    )
    return _fact("Other pests", lines)


def _facts(data: SiteData, place: Place) -> str:
    pests = [_pest_fact(data, place, c) for c in place.pests if c.headline]
    closures = [_closure_fact(data, place, run) for run in reversed(place.closures)]
    return "".join([*pests, *closures, _other_pests_fact(place)])


def _tags(v: Violation) -> str:
    return "".join(
        f'<span class="tag{" hot" if t in HEADLINE_PESTS else ""}">{esc(TAG_LABEL.get(t, t))}</span>' for t in v.tags
    )


def _details(v: Violation) -> str:
    if not v.details:
        return ""
    pairs = "".join(f"<dt>{esc(label)}</dt><dd>{esc(value)}</dd>" for label, value in v.details)
    return f'<dl class="kv">{pairs}</dl>'


def _violation(v: Violation) -> str:
    title = violation_title(v)
    category = f'<span class="vc"> {MIDDOT} {esc(v.category)}</span>' if title != v.category else ""
    lead = violation_lead(v)
    quote = f'<blockquote class="obs">{esc(lead)}</blockquote>' if lead else ""
    return f'<li><span class="vt">{esc(title)}</span>{category}{_tags(v)}{quote}{_details(v)}</li>'


def _inspection_body(inspection: Inspection) -> str:
    if not inspection.has_details:
        return f'<p class="quiet">{esc(feed_only_text(inspection))}</p>'
    if not inspection.violations:
        return '<p class="quiet">The report lists no violations for this inspection.</p>'
    items = "".join(_violation(v) for v in inspection.violations)
    everything = (
        '<details class="all"><summary>Show everything the report says</summary>'
        f"<pre>{esc(report_text(inspection))}</pre></details>"
    )
    return f'<ul class="vio">{items}</ul>{everything}'


def _source(data: SiteData, inspection: Inspection) -> str:
    return source_links(data, inspection, UP)


def _timeline_item(data: SiteData, inspection: Inspection, index: int) -> str:
    amended = amended_text(inspection)
    amend = f'<div class="amend">{esc(amended)}</div>' if amended else ""
    return (
        f'<li class="{level(inspection.status)}" id="insp-{index}">'
        f'<div class="when"><span class="d">{when_text(inspection.date, inspection.time)}</span>'
        f"{chip(inspection.status)}</div>"
        f'<div class="src">{esc(kind_line(inspection))}{_source(data, inspection)}</div>'
        f"{amend}{_inspection_body(inspection)}</li>"
    )


def _place_head(data: SiteData, place: Place) -> str:
    legal = f" {MIDDOT} {place.legal_name}" if place.legal_name else ""
    cited = list(reversed(place.standing)) or [place.latest]
    return (
        f'<div class="place-head"><a href="../places.html">{LEFT_ARROW} All places</a>'
        f'<h1 class="view">{esc(place.name)}</h1><div class="addr">{esc(place.address + legal)}</div>'
        f'<p class="today"><span class="lbl">Status today</span> {esc(status_today(place))}</p>'
        f"{_sources(data, place, cited)}</div>"
    )


def place_page(data: SiteData, place: Place) -> Page:
    """place/<slug>.html: the strip, what the records show, and every inspection with its source."""
    timeline = "".join(_timeline_item(data, i, n) for n, i in enumerate(place.inspections))
    body = (
        f"{_place_head(data, place)}\n"
        '<section class="record" aria-label="What the city\'s records show">'
        f"{strip_html(place, data.today, big=True)}{months_html(data.today)}{legend_html()}"
        f'<p class="coverage">{esc(coverage_line(place))}</p>{_facts(data, place)}'
        f'<p class="quiet">{esc(NOT_A_CERTIFICATE)}</p></section>\n'
        f"{heading('Inspections', len(place.inspections))}\n"
        f'<ol class="timeline">{timeline}</ol>'
    )
    return Page(place.name, body, "places")
