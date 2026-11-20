# Copyright (c) 2026 nm_health contributors
"""Pages and sections for news summaries: our saved record of each article, and where the site lists them.

A reader checks a Journal-sourced statement against the article, or, behind its paywall or after it moves, against
our saved record (news/<slug>.html) and an Internet Archive copy. The saved record lists exactly what we recorded:
the week, each place as printed, and each red-listed place's description, quoted (docs/news-links.md).
"""

from datetime import date

from nm_health.news import RED, Entry, NewsLink, usable_entries
from nm_health.news_fold import link_slug, saved_page, source_of
from nm_health.site_html import (
    EN_DASH,
    LEFT_ARROW,
    PLACE_DIR,
    REPORTS_DIR,
    Page,
    SiteData,
    esc,
    news_links_html,
    used_news,
)
from nm_health.viewmodel import MIDDOT, covering_report, nice_date, plural, short_date

USED = "Used here"
NOT_USED = "Not used:"
CITY_REPORT = "the city's report for that day is on file"
SAVED_NOTE = (
    "What this site recorded from the article: the week it covers, each place it lists with its dates and results, and "
    "each red-listed place's description, quoted as the paper printed it. GREEN, YELLOW and RED are the paper's lists: "
    "passed (the city's Approved), conditional (Conditional Approved), and closed or failing (Closure or "
    "Unsatisfactory). Entries dated in a week whose city report is on file aren't used: the city's report wins."
)


def _outlet(data: SiteData, link: NewsLink) -> str:
    return dict(data.settings.news_outlets).get(link.source, link.source)


def _city_days(data: SiteData) -> frozenset[date]:
    return frozenset(map(date.fromisoformat, data.city_covered))


def _as_printed(entry: Entry) -> str:
    """The entry's dates and results as the article prints them, e.g. "Closure (Nov 9); re-inspection required"."""
    if entry.color == RED:
        return "; ".join(f"{o.result} ({short_date(o.on.isoformat())})" for o in entry.outcomes) or "No result printed"
    dates = ", ".join(short_date(day.isoformat()) for day in entry.dates)
    return f"{dates} ({', '.join(entry.classes)})" if entry.classes else dates


def _place_links(data: SiteData, link: NewsLink) -> dict[tuple[str, str], tuple[str, int]]:
    """(name, address) as the article prints them -> its place page and the oldest inspection there from this article."""
    found: dict[tuple[str, str], tuple[str, int]] = {}
    for place in data.places:
        for index, i in enumerate(place.inspections):
            if i.news is not None and i.news.url == link.url:
                found[i.name, i.address] = (place.slug, index)  # newest first: the last kept is the oldest
    return found


def _on_site(data: SiteData, entry: Entry, used: tuple[str, int] | None) -> str:
    """'Used here' linked to the inspection on its place page, or why not, linked to the city's report."""
    if used is not None:
        slug, index = used
        return f'<a href="../{PLACE_DIR}/{esc(slug)}.html#insp-{index}">{USED}</a>'
    day = entry.dates[0].isoformat() if entry.dates else ""
    report = covering_report(data.all_reports, day) if day else None
    city = f'<a href="../{REPORTS_DIR}/{esc(report.file)}">{esc(CITY_REPORT)}</a>' if report else esc(CITY_REPORT)
    return f"{esc(NOT_USED)} {city}"


def _entry_row(entry: Entry, place: tuple[str, int] | None, on_site: str) -> str:
    slug = place[0] if place else None
    name = f'<a href="../{PLACE_DIR}/{esc(slug)}.html">{esc(entry.name)}</a>' if slug else esc(entry.name)
    row = (
        f"<tr><td>{esc(entry.color)}</td><td>{name}</td><td>{esc(entry.address)}</td>"
        f"<td>{esc(_as_printed(entry))}</td><td>{on_site}</td></tr>"
    )
    if not entry.notes:
        return row
    quote = " ".join(entry.notes)
    return f'{row}<tr class="desc"><td></td><td colspan="4"><blockquote class="obs">{esc(quote)}</blockquote></td></tr>'


def _weeks(link: NewsLink) -> str:
    return ", ".join(f"{short_date(w.start.isoformat())} {EN_DASH} {nice_date(w.end.isoformat())}" for w in link.weeks)


def news_page(data: SiteData, link: NewsLink) -> Page:
    """news/<slug>.html: our saved record of one article, each entry linked to its place page when used."""
    usable = usable_entries(link, _city_days(data))
    places = _place_links(data, link)
    rows = "".join(
        _entry_row(entry, place, _on_site(data, entry, place if entry in usable else None))
        for entry in link.entries
        for place in [places.get((entry.name, entry.address))]
    )
    links = f" {MIDDOT} ".join([f'<a href="{esc(link.url)}">Read the article</a>', *_archived(link)])
    body = f"""<section class="about">
<a href="../data.html">{LEFT_ARROW} Data we have pulled</a>
<h1 class="view">{esc(link.headline)}</h1>
<p>{esc(_outlet(data, link))}, published {esc(nice_date(link.published.isoformat()))}. {links}</p>
<p>Week covered: {esc(_weeks(link))}. {len(usable)} of {len(link.entries)} entries used here.</p>
<p class="note">{esc(SAVED_NOTE)}</p>
<div class="tablewrap"><table class="datatable"><thead><tr><th>List</th><th>Place</th><th>Address</th>
<th>Dates and results, as printed</th><th>On this site</th></tr></thead><tbody>{rows}</tbody></table></div>
</section>"""
    return Page(link.headline, body, "data")


def _archived(link: NewsLink) -> list[str]:
    return [f'<a href="{esc(link.archived_url)}">archived copy</a>'] if link.archived_url else []


def news_pages(data: SiteData) -> dict[str, Page]:
    """Every saved-record page, by its path under the site root."""
    return {saved_page(link): news_page(data, link) for link in data.news_links}


NONE_USED = "none: the city's report for that week is on file"


def _news_row(data: SiteData, link: NewsLink) -> str:
    usable = len(usable_entries(link, _city_days(data)))
    source = source_of(link, _outlet(data, link))
    links = f" {MIDDOT} ".join(news_links_html(source))
    used = str(usable) if usable or not link.entries else NONE_USED
    return (
        f"<tr><td>{esc(_weeks(link))}</td><td>{links}</td><td>{len(link.entries)}</td>"
        f"<td>{esc(used)}</td><td>{esc(link_slug(link))}</td></tr>"
    )


def news_table(data: SiteData) -> str:
    """The data page's list of news summaries, newest week first; '' when there are none."""
    if not data.news_links:
        return ""
    ordered = sorted(data.news_links, key=lambda link: link.weeks[-1].end, reverse=True)
    rows = "".join(_news_row(data, link) for link in ordered)
    return f"""<h2>Albuquerque Journal summaries</h2>
<p>For weeks whose city report wasn't saved: {len(ordered)} articles. Each was saved one at a time from the article
page in a browser (nothing crawls the paper's site), keeping the week, each place as printed, and red places'
descriptions, quoted. Each links to the article, our saved record, and an Internet Archive copy when one exists.
"Used here" counts the entries the site states; an article on a week whose city report is on file isn't used.</p>
<div class="tablewrap"><table class="datatable"><thead><tr><th>Week</th><th>Article</th><th>Entries</th>
<th>Used here</th><th>Record</th></tr></thead><tbody>{rows}</tbody></table></div>"""


def news_about(data: SiteData) -> str:
    """The about page's paragraph on news summaries; '' when there are none."""
    if not data.news_links:
        return ""
    return (
        f"<p>For {plural(used_news(data), 'week', 'weeks')} whose city report wasn't saved, the site uses the Albuquerque "
        "Journal's weekly summary of that report: the same places, dates and results, and for closed or failing places "
        "the paper's description, quoted as its words (not the inspector's notes). "
        "On the weeks both are on file, every inspection in the city's report is in the Journal's summary with the "
        "same result. A summary never replaces a city report: for days a city report on file covers, only the city's "
        "report is used. Each statement from a summary links to the article, our saved record of it, and an Internet "
        'Archive copy when one exists (<a href="data.html">list of summaries</a>).</p>'
    )
