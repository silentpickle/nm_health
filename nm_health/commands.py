# Copyright (c) 2026 nm_health contributors
"""CLI commands for the pipeline: `archive`, `feed`, `backfill-wayback`, `ingest` (rebuild the database), `site`."""

import argparse
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from nm_health import audit, feed, judge, spotcheck
from nm_health import settings as settings_module
from nm_health.archive import Archived, archive_current, archive_file
from nm_health.database import write_database
from nm_health.rebuild import rebuild
from nm_health.site import write_site
from nm_health.viewmodel import group_places
from nm_health.wayback import backfill

ERROR_CHARS = 160  # of a failed judgement's error, printed


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


def window_start(settings: settings_module.Settings) -> date:
    """First day of the window the site and database cover (window_days back from today)."""
    return feed.today_utc().date() - timedelta(days=settings.window_days)


def cmd_ingest(_args: argparse.Namespace) -> None:
    """Rebuild the database from every archived PDF."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = settings_module.load()
    rebuilt = rebuild(settings, window_start(settings))
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
    places = write_site(rebuild(settings, window_start(settings)), settings)
    _say(f"{places} place pages -> {settings.site_dir}")


def cmd_audit(_args: argparse.Namespace) -> None:
    """Check the site's assumptions against the PDFs and the feed; print where they disagree (never fails)."""
    results = audit.run_checks(audit.load(settings_module.load()))
    for line in audit.report_lines(results, feed.today_utc().date()):
        _say(line)


def cmd_spotcheck(args: argparse.Namespace) -> None:
    """Print a packet to paste into any LLM: what the site says about a few places, and the city's records."""
    settings = settings_module.load()
    seed = args.seed if args.seed is not None else feed.today_utc().date().toordinal()
    count = args.places or settings.spotcheck_places
    _say(spotcheck.build(settings, window_start(settings), count, seed))


def cmd_judge(args: argparse.Namespace) -> None:
    """Ask agy (local login) about each long closure: restaurant-only? operating now? Saves after each answer."""
    settings = settings_module.load()
    today = feed.today_utc().date()
    places = group_places(rebuild(settings, window_start(settings)).inspections)
    cases = judge.long_closures(places, today, settings.long_closure_days)
    cache = judge.load_cache(settings.judge_cache)
    todo = [c for c in cases if args.refresh or judge.stale(cache, c)]
    _say(f"{len(cases)} long closures; {len(todo)} to judge")
    failed = [case.place.name for case in todo if not _judge_one(case, cache, settings, today)]
    if failed:
        _say(f"No answer for {len(failed)}, judged next run: {', '.join(failed)}")


def _judge_one(
    case: judge.LongClosure, cache: dict[str, judge.Judgement], settings: settings_module.Settings, today: date
) -> bool:
    """Judge one place and save at once; a model that doesn't answer is reported and left for the next run."""
    try:
        answer = judge.judge(case, settings.judge_command, settings.judge_timeout_seconds, today)
    except judge.JudgeError as error:
        _say(f"{case.place.name}: no answer ({error.__class__.__name__}: {str(error)[:ERROR_CHARS]})")
        return False
    cache[case.place.slug] = answer
    judge.save_cache(settings.judge_cache, cache)
    _say(f"{case.place.name}: restaurant-only {answer.restaurant_only}; operating now: {answer.operating_now}")
    return True


def cmd_feed(_args: argparse.Namespace) -> None:
    """Fetch the city's inspection-status feed; keep each year's response if it changed."""
    settings = settings_module.load()
    saved = feed.collect(settings, feed.today_utc())
    for path in saved:
        _say(f"NEW: {path.relative_to(settings.feed_raw_dir)}")
    _say(f"{len(saved)} changed year(s)")


def add_commands(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Register the archive commands on the main CLI."""
    p_archive = subparsers.add_parser("archive", help="Save this week's report PDF if it is new (no parsing)")
    p_archive.add_argument("--file", help="archive this local PDF instead of downloading")
    p_archive.add_argument("--source", help="where --file came from (manifest note)")
    p_archive.add_argument("--seen-at", help="ISO time --file was first seen (default: now)")
    p_archive.set_defaults(func=cmd_archive)

    p_wayback = subparsers.add_parser("backfill-wayback", help="Archive every Wayback Machine copy of the report")
    p_wayback.set_defaults(func=cmd_backfill_wayback)

    p_feed = subparsers.add_parser("feed", help="Save the city's inspection-status feed if it changed")
    p_feed.set_defaults(func=cmd_feed)

    p_ingest = subparsers.add_parser("ingest", help="Rebuild the database from every archived PDF")
    p_ingest.set_defaults(func=cmd_ingest)

    p_site = subparsers.add_parser("site", help="Render the static site (GitHub Pages) from every archived PDF")
    p_site.set_defaults(func=cmd_site)

    p_audit = subparsers.add_parser("audit", help="Check the site's assumptions against the PDFs and the feed")
    p_audit.set_defaults(func=cmd_audit)

    p_judge = subparsers.add_parser("judge", help="Second opinion on long closures via agy (local login needed)")
    p_judge.add_argument("--refresh", action="store_true", help="judge every long closure again")
    p_judge.set_defaults(func=cmd_judge)

    p_spot = subparsers.add_parser("spotcheck", help="Print an LLM spot-check packet: site statements + city records")
    p_spot.add_argument("--places", type=int, help="how many places to sample (default: [spotcheck] places)")
    p_spot.add_argument("--seed", type=int, help="sample seed, to repeat a packet (default: changes daily)")
    p_spot.set_defaults(func=cmd_spotcheck)
