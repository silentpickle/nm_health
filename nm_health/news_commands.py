# Copyright (c) 2026 nm_health contributors
"""``nm-health news add`` and ``nm-health news list``: news links, kept apart from the county archive.

See docs/news-links.md. Nothing here fetches a page: ``add`` reads files the browser extension saved.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from nm_health import news
from nm_health import settings as settings_module
from nm_health.news_capture import CaptureRead, read_capture


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")


def _read_json(path: Path) -> tuple[object, str | None]:
    """The file's JSON, or why it couldn't be read: a file saved from a browser can hold anything."""
    if not path.is_file():
        return None, "no such file"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return None, f"not a JSON text file ({error})"


def span(link: news.NewsLink) -> str:
    """The week(s) an article reports on, e.g. 2026-11-08..2026-11-14."""
    return ", ".join(f"{week.start.isoformat()}..{week.end.isoformat()}" for week in link.weeks)


def color_counts(entries: tuple[news.Entry, ...]) -> str:
    """How many places each list holds, e.g. "22 green, 2 yellow, 4 red"."""
    counts = Counter(entry.color for entry in entries)
    listed = [f"{counts[color]} {color.lower()}" for color in news.COLORS if counts[color]]
    return ", ".join(listed) or "no places"


def coverage(link: news.NewsLink, county: frozenset[date]) -> str:
    """How much of the article the county archive leaves usable; the county report always wins."""
    days = news.week_days(link)
    covered = sum(day in county for day in days)
    usable = len(news.usable_entries(link, county))
    total = len(link.entries)
    if covered == 0:
        return f"no county PDF for these days: {usable} of {total} entries usable"
    if usable == 0:
        return f"county PDF covers {covered} of {len(days)} days: not used (the county report wins)"
    return f"county PDF covers {covered} of {len(days)} days: {usable} of {total} entries usable (dated outside it)"


def _add_one(
    path: Path, links: list[news.NewsLink], county: frozenset[date], hosts: tuple[str, ...]
) -> tuple[list[news.NewsLink], list[str]]:
    data, error = _read_json(path)
    read = read_capture(data, hosts) if error is None else CaptureRead(None, [error], [])
    if read.link is None:
        return links, [f"SKIPPED {path.name}: {'; '.join(read.problems)}"]
    links, status = news.upsert(links, read.link)
    said = [
        f"{status}: {read.link.source} {span(read.link)} {read.link.headline}",
        f"  {color_counts(read.link.entries)}; {coverage(read.link, county)}",
    ]
    return links, said + [f"  warning: {warning}" for warning in read.warnings]


def add_lines(paths: list[Path], settings: settings_module.Settings) -> list[str]:
    """Record each capture file in the links file; what happened to each, in order."""
    county = news.county_days(settings.manifest)
    links = news.load_links(settings.news_links)
    said: list[str] = []
    for path in paths:
        links, lines = _add_one(path, links, county, settings.news_hosts)
        said.extend(lines)
    news.save_links(settings.news_links, links)
    return said


def list_lines(settings: settings_module.Settings) -> list[str]:
    """Every news link, oldest week first, with how much of it the county archive leaves usable."""
    links = news.load_links(settings.news_links)
    county = news.county_days(settings.manifest)
    said: list[str] = []
    for link in links:
        said.append(f"{span(link)}  {link.source}  {color_counts(link.entries)}  {coverage(link, county)}")
        said.append(f"  {link.url}")
    usable = sum(len(news.usable_entries(link, county)) for link in links)
    total = sum(len(link.entries) for link in links)
    said.append(f"{len(links)} news links; {usable} of {total} entries usable (dated outside every county PDF's week)")
    unknown = news.unknown_week_files(settings.manifest)
    if unknown:
        said.append(f"Archived PDFs with no week on file (their days aren't counted as covered): {', '.join(unknown)}")
    return said


def cmd_news_add(args: argparse.Namespace) -> None:
    """Record captures the browser extension saved (tools/news-capture)."""
    for line in add_lines(list(args.files), settings_module.load()):
        _say(line)


def cmd_news_list(_args: argparse.Namespace) -> None:
    """List news links and how much of each the county archive leaves usable."""
    for line in list_lines(settings_module.load()):
        _say(line)


def add_commands(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Register ``news add`` and ``news list`` on the main CLI."""
    p_news = subparsers.add_parser("news", help="News links for weeks the county archive lacks (docs/news-links.md)")
    news_commands = p_news.add_subparsers(dest="news_command", required=True)
    p_add = news_commands.add_parser("add", help="Record JSON files saved by the browser extension")
    p_add.add_argument("files", nargs="+", type=Path, help="files the extension saved (nm-health-news-*.json)")
    p_add.set_defaults(func=cmd_news_add)
    p_list = news_commands.add_parser("list", help="List news links and which entries the county archive leaves")
    p_list.set_defaults(func=cmd_news_list)
