# Copyright (c) 2026 nm_health contributors
"""The site's pages as HTML bodies: This week (and Last month, All time), Places, Map, About, one place's record."""

from collections.abc import Callable
from dataclasses import dataclass

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
    reopened_html,
    row_html,
    rows_axis_html,
    rows_html,
    source_links,
    strip_axis_html,
    strip_html,
)
from nm_health.viewmodel import (
    MAYBE_SAME,
    MIDDOT,
    MONTH_SPAN_DAYS,
    RED_GROUP,
    TAG_LABEL,
    WEEK_SPAN_DAYS,
    ClosureRun,
    Period,
    PestCitation,
    Place,
    Reopening,
    amended_text,
    closed_text,
    closure_end,
    closure_start,
    coverage_line,
    kind_line,
    latest_report,
    latest_result_text,
    level,
    nice_date,
    other_pest_kinds,
    permit_line_text,
    permit_lines,
    pest_reading,
    plural,
    reopenings,
    report_text,
    select_period,
    short_date,
    source_label,
    thousands,
    unique_places,
    violation_lead,
    violation_title,
    when_text,
)

PAGE_SIZE = 60  # rows shown before "Show more" (places.js pages the same way)
PLACES_AXIS_ID = "axis"  # places.js shows this strip axis above the rows it draws
FILTERS = (
    ("all", "All"),
    ("red", RED_GROUP),
    ("reopened", "Open again after a red result"),
    ("pests", "Roaches or rodents"),
    ("employee", "Employee items"),
    ("maybe", "May be the same business"),
)
NO_JS_MAP = "The map needs JavaScript."
MAP_NOTE = (
    "Each dot is a place in the weekly reports on file, coloured by its latest status as issued by the city. "
    "Pinch, drag or use + and \u2212 to zoom. Use the Places tab to browse by name."
)
MAP_LEGEND = (
    ("--ok-cell", False, "Approved"),
    ("--warn-cell", False, "Conditional approved"),
    ("--bad-cell", False, RED_GROUP),
    ("--surface", True, "Roaches or rodents cited in notes on file"),
)
NOT_A_CERTIFICATE = "An inspection reports what one inspector found on one day. No citation is not a certification."
NO_LATER_APPROVAL = "No later approved inspection in the weekly reports on file."
UP = "../"  # place pages sit one folder below the site root
ISO_DATE_LEN = len("2026-01-01")
YEAR_LEN = len("2026")
SHA_SHOWN = 12  # hex digits of a report's SHA-256 shown on the About page


# ---------- This week, Last month, All time ----------


def _more_note(total: int) -> str:
    """Under a list cut at PAGE_SIZE: where the rest are."""
    if total <= PAGE_SIZE:
        return ""
    return f'<p class="note">Newest {PAGE_SIZE} shown. Every place is on the <a href="places.html">Places</a> tab.</p>'


def _cards(cards: list[str], empty: str) -> str:
    if not cards:
        return f'<p class="muted">{esc(empty)}</p>'
    return f'<div class="lead">{"".join(cards[:PAGE_SIZE])}</div>' + _more_note(len(cards))


def _pest_section(period: Period, no_pests: str) -> str:
    cards = [notice_html(p, i, pest=True) for p, i in period.pest_visits]
    if period.own_pests:
        return heading("Roaches or rodents cited", len(cards)) + _cards(cards, no_pests)
    report = period.pest_report
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


LONG_BANNER = (
    "The city's weekly report for the newest dates isn't on file yet. Statuses for those dates come from the "
    "city's inspection-status feed; their inspector notes and pest citations appear once the report is saved."
)
NO_PESTS_IN_REPORT = "None cited in that report."
NO_PESTS_IN_RANGE = "None cited in the inspector notes on file for these dates."
RANGE_TAB = "week"  # the tab every time-range page sits under


DISCLAIMER = (
    "This site is not endorsed by, affiliated with, or approved by the City of Albuquerque Environmental Health "
    "Department. Please double-check inspection results with the city's own records before relying on them."
)


CITY_RESULTS_URL = "https://www.cabq.gov/environmentalhealth/food-safety/restaurant-inspection-results"
CITY_MOST_RECENT_URL = "https://www.cabq.gov/environmentalhealth/documents/chpd_main_inspection_report.pdf"
# noreferrer: the city's site is not told where the reader came from.
NEW_WINDOW = 'target="_blank" rel="noopener noreferrer"'


def external_link(url: str, label: str) -> str:
    """A link out to the city's site: new window, no referrer."""
    return f'<a href="{esc(url)}" {NEW_WINDOW}>{esc(label)}</a>'


def disclaimer_html() -> str:
    """The red legal notice shown at the top of the landing page, with a pointer to the city's own results page."""
    city = external_link(CITY_RESULTS_URL, "the city's restaurant inspection results page")
    return f'<p class="disclaimer" role="note"><strong>Legal notice:</strong> {esc(DISCLAIMER)} See {city}.</p>'


def data_link_html() -> str:
    """Pointer from the landing page to everything pulled so far."""
    return '<p class="eyebrow"><a href="data.html">See every report PDF we have pulled</a></p>'


def latest_report_html(data: SiteData) -> str:
    """The week of the newest weekly PDF on file, so readers know how current the record is."""
    report = latest_report(data.reports)
    if report is None or report.week_end is None:
        return ""
    stamp = f"Latest weekly report on file: week ending {nice_date(report.week_end)}"
    return f'<p class="eyebrow">{stamp}</p>' + data_link_html()


def date_span(first: str, last: str) -> str:
    """'Oct 24 - Oct 30, 2026' (en dash), naming the first day's year too when it differs from the last day's."""
    shown = short_date(first) if first[:YEAR_LEN] == last[:YEAR_LEN] else nice_date(first)
    return f"{shown} {EN_DASH} {nice_date(last)}"


@dataclass(frozen=True)
class TimeRange:
    """One of the time-range pages: the newest inspection date and span_days before it (None: everything on file)."""

    file: str
    title: str
    span_days: int | None
    banner: str  # shown when no weekly report on file covers the newest date
    no_pests: str  # shown when the range's own inspections cite no roaches or rodents


# Every range: a reopening dated inside it, on a later day than the closure (before the range or inside it).
REOPENED_IN_RANGE = "Reopened after a closure"
NO_REOPENED_IN_RANGE = "No place reopened after a closure during these dates."
WEEK_RANGE = TimeRange(
    "index.html",
    "This week",
    WEEK_SPAN_DAYS,
    BANNER,
    NO_PESTS_IN_REPORT,
)
MONTH_RANGE = TimeRange(
    "month.html",
    "Last month",
    MONTH_SPAN_DAYS,
    LONG_BANNER,
    NO_PESTS_IN_RANGE,
)
ALL_RANGE = TimeRange(
    "all.html",
    "All time",
    None,
    LONG_BANNER,
    NO_PESTS_IN_RANGE,
)
RANGES = (WEEK_RANGE, MONTH_RANGE, ALL_RANGE)


def _range_link(time_range: TimeRange, current: TimeRange) -> str:
    here = ' aria-current="page"' if time_range == current else ""
    return f'<a href="{time_range.file}"{here}>{esc(time_range.title)}</a>'


def range_switch(current: TimeRange) -> str:
    """Links between the time-range pages, the current one marked."""
    links = "".join(_range_link(r, current) for r in RANGES)
    return f'<nav class="range" aria-label="Time range">{links}</nav>'


def _range_head(time_range: TimeRange) -> str:
    return f'{disclaimer_html()}\n<h1 class="view">{esc(time_range.title)}</h1>\n{range_switch(time_range)}'


def _other_rows(data: SiteData, period: Period) -> str:
    places = unique_places(period.other)
    weeks = data.settings.strip_weeks
    rows = rows_html([row_html(p, data.today, data.covered, weeks) for p in places[:PAGE_SIZE]])
    return rows_axis_html(data.today, weeks) + rows + _more_note(len(places))


def range_reopenings(data: SiteData, period: Period) -> list[Reopening]:
    """Places reopened in the range after a closure on an earlier day, the closure before the range or inside it."""
    return reopenings(data.places, period.start, period.end)


def _reopened_section(data: SiteData, period: Period) -> str:
    cards = [reopened_html(data, r) for r in range_reopenings(data, period)]
    return heading(REOPENED_IN_RANGE, len(cards)) + _cards(cards, NO_REOPENED_IN_RANGE)


def _range_body(data: SiteData, time_range: TimeRange, period: Period) -> str:
    red = [notice_html(p, i, pest=False) for p, i in period.red]
    parts = [
        _range_head(time_range),
        latest_report_html(data),
        f'<p class="eyebrow">Inspections {date_span(period.start, period.end)}</p>',
        "" if period.covered else f'<p class="banner">{esc(time_range.banner)}</p>',
        heading(RED_GROUP, len(red)),
        _cards(red, "None in the city's records for these dates."),
        _reopened_section(data, period),
        _pest_section(period, time_range.no_pests),
        heading("Other inspections", len(period.other)),
        _other_rows(data, period),
    ]
    return "\n".join(parts)


def range_page(data: SiteData, time_range: TimeRange) -> Page:
    """One time-range page: closures, pest citations and every other inspection in the range."""
    period = select_period(data.places, data.reports, time_range.span_days)
    if period is None:
        body = f'{_range_head(time_range)}<p class="muted">No inspections on file yet.</p>'
        return Page(time_range.title, body, RANGE_TAB)
    return Page(time_range.title, _range_body(data, time_range, period), RANGE_TAB)


def week_page(data: SiteData) -> Page:
    """index.html: the newest seven days of inspections."""
    return range_page(data, WEEK_RANGE)


# ---------- Data ----------

HEADER_SEEN = "City letterhead: Environmental Health Department"
HEADER_ABSENT = "No department letterhead on page 1 (older layout)"


def archive_tree_url(data: SiteData) -> str:
    """The archive folder on GitHub, one step up from a file's page."""
    return data.settings.pdf_base_url.replace("/blob/", "/tree/")


def _data_row(data: SiteData, report: Report) -> str:
    start = short_date(report.week_start) if report.week_start else "?"
    end = nice_date(report.week_end) if report.week_end else "week not stated"
    letterhead = HEADER_SEEN if report.letterhead else HEADER_ABSENT
    amended = f"Amended {esc(report.amended_on)}" if report.amended_on else "Not marked amended"
    saved = nice_date(report.seen_at[:ISO_DATE_LEN])
    return (
        f"<tr><td>{start} {EN_DASH} {end}</td>"
        f'<td><a href="{REPORTS_DIR}/{esc(report.file)}">PDF</a> {MIDDOT} '
        f'<a href="{esc(data.settings.pdf_base_url + report.file)}">GitHub</a></td>'
        f"<td>{esc(letterhead)}</td><td>{amended}</td>"
        f"<td>{report.inspections}</td><td>{saved}</td>"
        f'<td class="data">{esc(report.source)}</td>'
        f'<td class="data">{esc(report.sha256[:SHA_SHOWN])}</td></tr>'
    )


def data_page(data: SiteData) -> Page:
    """data.html: every weekly report PDF in the archive, so each can be checked against the city's own."""
    ordered = sorted(data.all_reports, key=lambda r: (r.week_end or "", r.seen_at), reverse=True)
    rows = "".join(_data_row(data, r) for r in ordered)
    head = (
        "<tr><th>Week</th><th>File</th><th>Header</th><th>Amendment</th><th>Inspections</th>"
        "<th>Saved</th><th>Source</th><th>SHA-256</th></tr>"
    )
    body = f"""<section class="about">
<h1 class="view">Data we have pulled</h1>
<p>Every weekly report PDF saved so far: {len(ordered)} files, byte for byte as the city published them.
Browse the whole folder on <a href="{esc(archive_tree_url(data))}">GitHub (data/archive)</a>.</p>
<div class="tablewrap"><table class="datatable"><thead>{head}</thead><tbody>{rows}</tbody></table></div>
</section>"""
    return Page("Data we have pulled", body, "data")


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
        f"{rows_axis_html(data.today, data.settings.strip_weeks, element_id=PLACES_AXIS_ID)}\n"
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
    amended = f" {MIDDOT} Amended {esc(report.amended_on)} per its header" if report.amended_on else ""
    return (
        f'<li>{start} {EN_DASH} {end} {MIDDOT} {count} {MIDDOT} <a href="{REPORTS_DIR}/{esc(report.file)}">PDF</a>'
        f'<div class="quiet">Saved {saved}{amended} from <span class="data">{esc(report.source)}</span> {MIDDOT} '
        f'SHA-256 <span class="data">{esc(report.sha256[:SHA_SHOWN])}</span> {MIDDOT} '
        f'<a href="{history}">archive history</a></div></li>'
    )


def _reports_list(data: SiteData) -> str:
    ordered = sorted(data.reports, key=lambda r: r.week_end or "", reverse=True)
    return f'<ul class="reports">{"".join(_report_item(data, r) for r in ordered)}</ul>'


def about_page(data: SiteData) -> Page:
    """about.html: where the data comes from and what it does not say."""
    counts = (
        f"For this period, {len(data.reports)} weekly reports are on file, listing {thousands(data.total)} inspections "
        f"of {thousands(len(data.places))} places. Weeks whose report wasn't saved aren't shown: the site states only "
        "what a weekly report on file says."
    )
    body = f"""<section class="about">
<h1 class="view">About this data</h1>
<h2>Where it comes from</h2>
<p>The City of Albuquerque publishes one PDF of the week's food inspections and replaces it the next week. This site
keeps every copy it saves and shows the last 12 months. Every statement links to the page of the report it comes from;
the copies here are byte-for-byte what the city published.</p>
<p>The city also runs a public inspection-status feed. It is separate from the weekly reports, and this site treats it
as a separate source: it is used only for the coordinates of the dots on the map, and no statement here rests on it.</p>
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


def _is_recent(data: SiteData, day: str) -> bool:
    """True when the day falls in the week of the newest weekly report on file."""
    report = latest_report(data.reports)
    if report is None or report.week_start is None or report.week_end is None:
        return False
    return report.week_start <= day <= report.week_end


def _most_recent_link(data: SiteData, day: str) -> str:
    """A 'most recent' link to the city's current report, only for a violation dated in the newest report's week."""
    if not _is_recent(data, day):
        return ""
    link = external_link(CITY_MOST_RECENT_URL, "most recent")
    return f'<div class="quiet">City\'s current report: {link}</div>'


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
        f"{_most_recent_link(data, citation.date)}"
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
    closed = "".join(f'<div class="closed">{esc(closed_text(spell, data.covered))}</div>' for spell in run.closed)
    sources = _sources(data, place, _closure_cited(place, run))
    recent = _most_recent_link(data, run.episode.start)
    return _fact(RED_GROUP, f'{esc(closure_start(run))}{closed}<div class="quiet">{after}</div>{sources}{recent}')


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


def _permit_line(data: SiteData, line: Inspection) -> str:
    page = data.permit_pages.get((line.report_file, line.permit_number or ""))
    href = f"{UP}{REPORTS_DIR}/{esc(line.report_file)}" + (f"#page={page}" if page else "")
    where = f"p. {page}" if page else "PDF"
    return f'<li><q>{esc(permit_line_text(line))}</q> <a href="{href}">{where}</a></li>'


def _city_status(data: SiteData, place: Place) -> str:
    """The city's own words from its latest weekly report on file, then the latest result, then any newer record."""
    latest = place.latest
    report = source_label(latest, data.week_starts.get(latest.report_file)).split(" (", 1)[0]
    lines = "".join(_permit_line(data, line) for line in permit_lines(place))
    return (
        f'<div class="today"><span class="lbl">The city\'s latest weekly report on file</span> {esc(report)}'
        f"{f'<ul class="permits">{lines}</ul>' if lines else ''}"
        f"<p>{esc(latest_result_text(place))}</p>{_sources(data, place, [latest])}</div>"
    )


ALSO_PRINTED = "Also printed as:"
MERGED_BY_PERMIT = "Merged by permit; names differ."


def _also_printed(place: Place) -> str:
    """The other names the reports printed for this place, each linked to its newest inspection, and the review note."""
    if not place.also_printed:
        return ""
    names = ", ".join(
        f'<a href="#insp-{place.inspections.index(i)}">{esc(i.name)}</a> ({esc(nice_date(i.date))})'
        for i in place.also_printed
    )
    return f'<p class="also">{esc(ALSO_PRINTED)} {names}. <span class="quiet">{esc(MERGED_BY_PERMIT)}</span></p>'


CANT_TELL_NOTE = "The city's records don't say whether they are one business, so the site keeps them apart."


def _maybe_same(place: Place) -> str:
    """Each place the records can't tell apart from this one, linked."""
    if not place.maybe_same:
        return ""
    links = " and ".join(f'<a href="{esc(slug)}.html">{esc(name)}</a>' for slug, name in place.maybe_same)
    return f'<p class="also">{esc(MAYBE_SAME)} {links}. <span class="quiet">{esc(CANT_TELL_NOTE)}</span></p>'


def _place_head(data: SiteData, place: Place) -> str:
    legal = f" {MIDDOT} {place.legal_name}" if place.legal_name else ""
    return (
        f'<div class="place-head"><a href="../places.html">{LEFT_ARROW} All places</a>'
        f'<h1 class="view">{esc(place.name)}</h1><div class="addr">{esc(place.address + legal)}</div>'
        f"{_also_printed(place)}{_maybe_same(place)}{_city_status(data, place)}</div>"
    )


def place_page(data: SiteData, place: Place) -> Page:
    """place/<slug>.html: the strip, what the records show, and every inspection with its source."""
    timeline = "".join(_timeline_item(data, i, n) for n, i in enumerate(place.inspections))
    weeks = data.settings.strip_weeks
    body = (
        f"{_place_head(data, place)}\n"
        '<section class="record" aria-label="What the city\'s records show">'
        f"{strip_axis_html(data.today, weeks)}{strip_html(place, data.today, weeks, big=True)}{months_html(data.today, weeks)}{legend_html()}"
        f'<p class="coverage">{esc(coverage_line(place))}</p>{_facts(data, place)}'
        f'<p class="quiet">{esc(NOT_A_CERTIFICATE)}</p></section>\n'
        f"{heading('Inspections', len(place.inspections))}\n"
        f'<ol class="timeline">{timeline}</ol>'
    )
    return Page(place.name, body, "places")
