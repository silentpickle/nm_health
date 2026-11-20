# Copyright (c) 2026 nm_health contributors
"""Pages and sections for news summaries: our saved record of each article, and where the site lists them.

A reader checks a Journal-sourced statement against the article, or, behind its paywall or after it moves, against
our saved record (news/<slug>.html) and an Internet Archive copy. The saved record lists exactly what we recorded:
the week and each place as printed, never the article's text (docs/news-links.md).
"""

from datetime import date

from nm_health.news import RED, Entry, NewsLink, usable_entries
from nm_health.news_fold import link_slug, saved_page, source_of
from nm_health.site_html import EN_DASH, LEFT_ARROW, PLACE_DIR, Page, SiteData, esc, news_links_html, used_news
from nm_health.viewmodel import MIDDOT, nice_date, short_date

USED = "Used here"
NOT_USED = "Not used: the city's report for that day is on file"
SAVED_NOTE = (
    "What this site recorded from the article: the week it covers and each place it lists, as printed. The article's "
    "text isn't kept here. Entries dated in a week whose city report is on file aren't used: the city's report wins."
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


def _place_slugs(data: SiteData, link: NewsLink) -> dict[tuple[str, str], str]:
    """(name, address) as the article prints them -> the place page its inspections joined."""
    return {
        (i.name, i.address): place.slug
        for place in data.places
        for i in place.inspections
        if i.news is not None and i.news.url == link.url
    }


def _entry_row(entry: Entry, slug: str | None, on_site: str) -> str:
    name = f'<a href="../{PLACE_DIR}/{esc(slug)}.html">{esc(entry.name)}</a>' if slug else esc(entry.name)
    return (
        f"<tr><td>{esc(entry.color)}</td><td>{name}</td><td>{esc(entry.address)}</td>"
        f"<td>{esc(_as_printed(entry))}</td><td>{esc(on_site)}</td></tr>"
    )


def _weeks(link: NewsLink) -> str:
    return ", ".join(f"{short_date(w.start.isoformat())} {EN_DASH} {nice_date(w.end.isoformat())}" for w in link.weeks)


def news_page(data: SiteData, link: NewsLink) -> Page:
    """news/<slug>.html: our saved record of one article, each entry linked to its place page when used."""
    usable = usable_entries(link, _city_days(data))
    slugs = _place_slugs(data, link)
    rows = "".join(
        _entry_row(entry, slugs.get((entry.name, entry.address)), USED if entry in usable else NOT_USED)
        for entry in link.entries
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


def _news_row(data: SiteData, link: NewsLink) -> str:
    usable = len(usable_entries(link, _city_days(data)))
    source = source_of(link, _outlet(data, link))
    links = f" {MIDDOT} ".join(news_links_html(source))
    return (
        f"<tr><td>{esc(_weeks(link))}</td><td>{links}</td><td>{len(link.entries)}</td>"
        f'<td>{usable}</td><td class="data">{esc(link_slug(link))}</td></tr>'
    )


def news_table(data: SiteData) -> str:
    """The data page's list of news summaries, newest week first; '' when there are none."""
    if not data.news_links:
        return ""
    ordered = sorted(data.news_links, key=lambda link: link.weeks[-1].end, reverse=True)
    rows = "".join(_news_row(data, link) for link in ordered)
    return f"""<h2>Albuquerque Journal summaries</h2>
<p>For weeks whose city report wasn't saved: {len(ordered)} articles, each recorded by hand from the article page
(the week and each place as printed, never the article's text). Each links to the article, our saved record of it,
and an Internet Archive copy when one exists.</p>
<div class="tablewrap"><table class="datatable"><thead><tr><th>Week</th><th>Article</th><th>Entries</th>
<th>Used here</th><th>Record</th></tr></thead><tbody>{rows}</tbody></table></div>"""


def news_about(data: SiteData) -> str:
    """The about page's paragraph on news summaries; '' when there are none."""
    if not data.news_links:
        return ""
    return (
        f"<p>For {used_news(data)} weeks whose city report wasn't saved, the site uses the Albuquerque "
        "Journal's weekly summary of that report: the same places, dates and results, without the inspector's notes. "
        "On the weeks both are on file, every inspection in the city's report is in the Journal's summary with the "
        "same result. A summary never replaces a city report: for days a city report on file covers, only the city's "
        "report is used. Each statement from a summary links to the article, our saved record of it, and an Internet "
        'Archive copy when one exists (<a href="data.html">list of summaries</a>).</p>'
    )
