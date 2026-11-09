# Copyright (c) 2026 nm_health contributors
"""Static site for GitHub Pages: an index of every place, one page per place, and the list of archived reports.

Everything is plain HTML so it reads and links without JavaScript; search.js only filters the index.
Claims stay within what the archive shows: "no pest citations in the N archived inspections", never "pest-free".
"""

import html
import json
import shutil
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from nm_health.identity import establishment_slug, normalized_address
from nm_health.model import Inspection
from nm_health.rebuild import Rebuilt, Report
from nm_health.settings import Settings

STATIC_DIR = Path(__file__).resolve().parent / "site_static"
STATIC_FILES = ("style.css", "search.js")
SITE_TITLE = "ABQ Food Inspection History"
PESTS = "pests"
RED = "red"
TAG_LABELS = {
    "pests": "Pests seen",
    "pest_control": "Pest control",
    "employee_items": "Employee items",
    "food_temperature": "Food temperature",
    "handwashing": "Handwashing",
    "sanitizer": "Sanitizer",
    "date_marking": "Date marking",
    "permit": "Permit",
    "training": "Training",
}
FILTERS = (("all", "All"), (RED, "Closed or failed"), (PESTS, "Pests seen"), ("employee_items", "Employee items"))
LEVELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (RED, ("closure", "unsatisfactory")),
    ("yellow", ("conditional",)),
    ("green", ("approved",)),
)
DEFAULT_LEVEL = "gray"
SYNTHETIC_ID_PREFIX = "legacy-"  # made up by legacy_parser; meaningless to readers
EN_DASH = "\u2013"
MIDDOT = "\u00b7"
LEFT_ARROW = "\u2190"


@dataclass(frozen=True)
class Place:
    """Every archived inspection of one establishment, newest first."""

    slug: str
    name: str
    address: str
    inspections: tuple[Inspection, ...]

    @property
    def latest(self) -> Inspection:
        """The most recent inspection."""
        return self.inspections[0]


def esc(text: str) -> str:
    """HTML-escape text for element content and attribute values."""
    return html.escape(text, quote=True)


def nice_date(iso: str) -> str:
    """'2026-10-29' -> 'Oct 29, 2026'."""
    day = date.fromisoformat(iso)
    return f"{day:%b} {day.day}, {day.year}"


def status_level(status: str) -> str:
    """Badge colour for a status: red (closed/failed), yellow (conditional), green (approved), gray (other)."""
    lower = status.lower()
    return next((level for level, words in LEVELS if any(w in lower for w in words)), DEFAULT_LEVEL)


def has_tag(inspection: Inspection, tag: str) -> bool:
    """True when any violation in the inspection carries the tag."""
    return any(tag in v.tags for v in inspection.violations)


def group_places(inspections: tuple[Inspection, ...]) -> list[Place]:
    """Inspections grouped by place; places ordered by most recent inspection first."""
    by_slug: dict[str, list[Inspection]] = defaultdict(list)
    for inspection in inspections:
        by_slug[establishment_slug(inspection.name, inspection.address)].append(inspection)
    places = []
    for slug, found in by_slug.items():
        ordered = tuple(sorted(found, key=lambda i: (i.date, i.inspection_id), reverse=True))
        places.append(Place(slug, ordered[0].name, normalized_address(ordered[0].address), ordered))
    return sorted(places, key=lambda p: (p.latest.date, p.name), reverse=True)


def _times(count: int) -> str:
    return "1 time" if count == 1 else f"{count} times"


def pest_line(place: Place) -> tuple[str, bool]:
    """(sentence, is_alert) about pest citations, limited to what the archive holds."""
    dates = sorted({i.date for i in place.inspections}, reverse=True)
    pest_dates = [i.date for i in place.inspections if has_tag(i, PESTS)]
    if not pest_dates:
        span = f"{nice_date(dates[-1])} {EN_DASH} {nice_date(dates[0])}" if len(dates) > 1 else nice_date(dates[0])
        return f"No pest citations in {len(place.inspections)} archived inspection(s) ({span}).", False
    last = max(pest_dates)
    later = [d for d in dates if d > last]
    if not later:
        return f"Pests cited on {nice_date(last)}, the latest inspection date in the archive.", True
    since = f"inspected {_times(len(later))} since, most recently {nice_date(later[0])}"
    return f"Last pest citation {nice_date(last)} {MIDDOT} {since}.", False


def red_line(place: Place) -> str | None:
    """When the place last failed or was closed, if ever in the archive."""
    reds = [i for i in place.inspections if status_level(i.status) == RED]
    if not reds:
        return None
    return f"Last closed or failed: {nice_date(reds[0].date)} ({reds[0].status})."


def page(title: str, body: str, depth: int, *, script: bool = False) -> str:
    """A full HTML document; depth is how many folders below the site root the page sits."""
    up = "../" * depth
    script_tag = f'<script src="{up}search.js" defer></script>' if script else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="{up}style.css">
{script_tag}
</head>
<body>
<main>
{body}
<footer>Built from the City of Albuquerque's weekly Consumer Health Protection inspection reports, which the city
replaces every week. This archive keeps every copy it has seen. Not affiliated with the City of Albuquerque.</footer>
</main>
</body>
</html>
"""


def _flags(place: Place) -> str:
    flags = {tag for i in place.inspections for v in i.violations for tag in v.tags}
    if any(status_level(i.status) == RED for i in place.inspections):
        flags.add(RED)
    return " ".join(sorted(flags))


def _badge(status: str) -> str:
    return f'<span class="badge {status_level(status)}">{esc(status)}</span>'


def _index_item(place: Place) -> str:
    text, alert = pest_line(place)
    search = esc(f"{place.name} {place.address}".lower())
    alert_class = " alert" if alert else ""
    return f"""<li data-search="{search}" data-flags="{_flags(place)}">
<div class="row"><a class="place-name" href="place/{place.slug}.html">{esc(place.name)}</a>
{_badge(place.latest.status)} <span class="muted">{nice_date(place.latest.date)}</span></div>
<div class="address">{esc(place.address)}</div>
<p class="headline{alert_class}">{esc(text)}</p>
</li>"""


def _coverage(reports: tuple[Report, ...]) -> str:
    weeks = sorted(r.week_end or "" for r in reports if r.inspections)
    if not weeks:
        return '<p class="coverage">No reports archived yet.</p>'
    return (
        f'<p class="coverage">Built from <a href="reports.html">{len(weeks)} archived weekly reports</a> between '
        f"{nice_date(weeks[0])} and {nice_date(weeks[-1])}. A place's history only includes weeks in the archive: "
        "the city publishes only the latest week, so a week nobody saved is gone.</p>"
    )


def render_index(places: list[Place], rebuilt: Rebuilt) -> str:
    """The searchable list of every place."""
    buttons = "".join(
        f'<button type="button" data-filter="{key}" aria-pressed="{str(key == "all").lower()}">{esc(label)}</button>'
        for key, label in FILTERS
    )
    items = "\n".join(_index_item(p) for p in places)
    body = f"""<h1>{SITE_TITLE}</h1>
<p class="lede">Every Albuquerque restaurant inspection the city has published, kept after the city takes it down.</p>
{_coverage(rebuilt.reports)}
<div class="search">
<input id="q" type="search" placeholder="Search a name or street (e.g. pho, Montgomery)" aria-label="Search places">
<div id="filters" class="filters" hidden>{buttons}</div>
</div>
<p id="count" class="count">{len(places)} places</p>
<ul id="places" class="places">
{items}
</ul>"""
    return page(SITE_TITLE, body, 0, script=True)


def _violation_item(v_category: str, v_item: str, observation: str, tags: tuple[str, ...]) -> str:
    title = v_item or v_category
    chips = "".join(f'<span class="tag {esc(t)}">{esc(TAG_LABELS.get(t, t))}</span>' for t in tags)
    category = f' <span class="muted">({esc(v_category)})</span>' if v_item and v_category != v_item else ""
    obs = f'<p class="v-observation">{esc(observation)}</p>' if observation else ""
    return f'<li><span class="v-title">{esc(title)}</span>{category}{chips}{obs}</li>'


def _source(inspection: Inspection, reports: dict[str, Report], pdf_base_url: str) -> str:
    report = reports.get(inspection.report_file)
    week = f"week of {nice_date(report.week_start)}" if report and report.week_start else "weekly"
    page_note = f", page {inspection.page}" if inspection.page else ""
    link = f'<a href="{esc(pdf_base_url + inspection.report_file)}">{week} report (PDF{page_note})</a>'
    parts = [esc(inspection.kind)]
    if not inspection.inspection_id.startswith(SYNTHETIC_ID_PREFIX):
        parts.append(f"#{esc(inspection.inspection_id)}")
    return f" {MIDDOT} ".join([*parts, link])


def _timeline_item(inspection: Inspection, reports: dict[str, Report], pdf_base_url: str) -> str:
    level = status_level(inspection.status)
    violations = "".join(_violation_item(v.category, v.item, v.observation, v.tags) for v in inspection.violations)
    listed = f'<ul class="violations">{violations}</ul>' if violations else '<p class="muted">No violations listed.</p>'
    return f"""<li class="{level}">
<div class="row"><span class="when">{nice_date(inspection.date)}</span> {_badge(inspection.status)}</div>
<div class="meta">{_source(inspection, reports, pdf_base_url)}</div>
{listed}
</li>"""


def render_place(place: Place, rebuilt: Rebuilt, settings: Settings) -> str:
    """One place's whole archived history."""
    reports = {r.file: r for r in rebuilt.reports}
    pest_text, alert = pest_line(place)
    red = red_line(place)
    red_html = f"<p>{esc(red)}</p>" if red else ""
    permits = sorted({i.permit_number for i in place.inspections if i.permit_number})
    permit_html = f'<p class="muted">Permit {esc(", ".join(permits))}</p>' if permits else ""
    timeline = "\n".join(_timeline_item(i, reports, settings.pdf_base_url) for i in place.inspections)
    alert_class = ' class="headline alert"' if alert else ""
    body = f"""<nav class="crumbs"><a href="../index.html">{LEFT_ARROW} All places</a></nav>
<h1>{esc(place.name)}</h1>
<div class="address">{esc(place.address)}</div>
{permit_html}
<div class="summary"><p{alert_class}>{esc(pest_text)}</p>{red_html}</div>
<h2>Inspections, newest first</h2>
<ul class="timeline">
{timeline}
</ul>"""
    return page(f"{place.name} {EN_DASH} {SITE_TITLE}", body, 1)


def render_reports(rebuilt: Rebuilt, settings: Settings) -> str:
    """Which weekly reports the archive holds."""
    rows = "\n".join(
        f"<tr><td>{nice_date(r.week_start) if r.week_start else '?'} {EN_DASH} {nice_date(r.week_end) if r.week_end else '?'}"
        f'</td><td>{r.inspections}</td><td><a href="{esc(settings.pdf_base_url + r.file)}">PDF</a></td></tr>'
        for r in sorted(rebuilt.reports, key=lambda r: r.week_end or "", reverse=True)
    )
    body = f"""<nav class="crumbs"><a href="index.html">{LEFT_ARROW} All places</a></nav>
<h1>Archived weekly reports</h1>
<p class="lede">Each row is one weekly PDF the city published. Weeks missing here are missing from every history.</p>
<table class="reports"><thead><tr><th>Week</th><th>Inspections</th><th>Source</th></tr></thead>
<tbody>
{rows}
</tbody></table>"""
    return page(f"Archived reports {EN_DASH} {SITE_TITLE}", body, 0)


def _data(places: list[Place], rebuilt: Rebuilt) -> dict[str, object]:
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "reports": [asdict(r) for r in rebuilt.reports],
        "places": [
            {"id": p.slug, "name": p.name, "address": p.address, "inspections": [asdict(i) for i in p.inspections]}
            for p in places
        ],
    }


def write_site(rebuilt: Rebuilt, settings: Settings) -> int:
    """Replace the site folder with freshly rendered pages; returns how many place pages were written."""
    out = settings.site_dir
    shutil.rmtree(out, ignore_errors=True)
    (out / "place").mkdir(parents=True)
    places = group_places(rebuilt.inspections)
    (out / "index.html").write_text(render_index(places, rebuilt), encoding="utf-8")
    (out / "reports.html").write_text(render_reports(rebuilt, settings), encoding="utf-8")
    for place in places:
        (out / "place" / f"{place.slug}.html").write_text(render_place(place, rebuilt, settings), encoding="utf-8")
    for name in STATIC_FILES:
        shutil.copy(STATIC_DIR / name, out / name)
    (out / "data.json").write_text(json.dumps(_data(places, rebuilt), ensure_ascii=False), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return len(places)
