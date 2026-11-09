# Copyright (c) 2026 nm_health contributors
"""CLI commands for the pipeline: `archive`, `backfill-wayback`, `ingest` (rebuild the database), `site`."""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from nm_health import settings as settings_module
from nm_health.archive import Archived, archive_current, archive_file
from nm_health.database import write_database
from nm_health.rebuild import rebuild
from nm_health.site import write_site
from nm_health.wayback import backfill


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")


def _report(result: Archived) -> None:
    state = "NEW" if result.is_new else "already archived"
    _say(f"{state}: {result.path.name}")


def _seen_at(text: str | None) -> datetime:
    if text is None:
        return datetime.now(tz=UTC)
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def cmd_archive(args: argparse.Namespace) -> None:
    """Archive this week's report from the city, or a local PDF with --file."""
    settings = settings_module.load()
    if args.file is None:
        _report(archive_current(settings))
        return
    pdf = Path(args.file)
    source = args.source or f"file:{pdf.name}"
    _report(archive_file(pdf, source, _seen_at(args.seen_at), settings))


def cmd_backfill_wayback(_args: argparse.Namespace) -> None:
    """Archive every distinct Wayback Machine capture of the report."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results = backfill(settings_module.load())
    for result in results:
        _report(result)
    _say(f"{sum(r.is_new for r in results)} new of {len(results)} PDF captures")


def cmd_ingest(_args: argparse.Namespace) -> None:
    """Rebuild the database from every archived PDF."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = settings_module.load()
    rebuilt = rebuild(settings)
    write_database(rebuilt, settings.db, settings.archive_dir)
    for report in rebuilt.reports:
        _say(f"{report.file}: {report.layout}, {report.inspections} inspections")
    places = len({(i.name, i.address) for i in rebuilt.inspections})
    _say(
        f"{len(rebuilt.inspections)} inspections of {places} places from {len(rebuilt.reports)} reports -> {settings.db}"
    )


def cmd_site(_args: argparse.Namespace) -> None:
    """Render the static site from every archived PDF."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = settings_module.load()
    places = write_site(rebuild(settings), settings)
    _say(f"{places} place pages -> {settings.site_dir}")


def add_commands(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Register the archive commands on the main CLI."""
    p_archive = subparsers.add_parser("archive", help="Save this week's report PDF if it is new (no parsing)")
    p_archive.add_argument("--file", help="archive this local PDF instead of downloading")
    p_archive.add_argument("--source", help="where --file came from (manifest note)")
    p_archive.add_argument("--seen-at", help="ISO time --file was first seen (default: now)")
    p_archive.set_defaults(func=cmd_archive)

    p_wayback = subparsers.add_parser("backfill-wayback", help="Archive every Wayback Machine copy of the report")
    p_wayback.set_defaults(func=cmd_backfill_wayback)

    p_ingest = subparsers.add_parser("ingest", help="Rebuild the database from every archived PDF")
    p_ingest.set_defaults(func=cmd_ingest)

    p_site = subparsers.add_parser("site", help="Render the static site (GitHub Pages) from every archived PDF")
    p_site.set_defaults(func=cmd_site)
