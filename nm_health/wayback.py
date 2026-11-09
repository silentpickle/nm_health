# Copyright (c) 2026 nm_health contributors
"""Backfill the archive from the Internet Archive's copies of the weekly report."""

import json
import logging
import time
import urllib.error
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime

from nm_health.archive import Archived, archive_bytes, download, is_pdf
from nm_health.settings import Settings

LOG = logging.getLogger(__name__)
TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"
PAUSE_SECONDS = 2.0  # be polite to web.archive.org between snapshot downloads


@dataclass(frozen=True)
class Snapshot:
    """One distinct capture of the report URL."""

    timestamp: str

    @property
    def seen_at(self) -> datetime:
        """When the Wayback Machine captured it."""
        return datetime.strptime(self.timestamp, TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def cdx_query_url(settings: Settings) -> str:
    """CDX API query: one row per distinct content digest, successful captures only."""
    query = urllib.parse.urlencode(
        {
            "url": settings.report_url.removeprefix("https://www."),
            "output": "json",
            "fl": "timestamp",
            "collapse": "digest",
            "filter": "statuscode:200",
        },
    )
    return f"{settings.cdx_url}?{query}"


def parse_cdx(body: bytes) -> list[Snapshot]:
    """Rows of a CDX JSON answer; the first row is the header."""
    rows: list[list[str]] = json.loads(body or b"[]")
    return [Snapshot(row[0]) for row in rows[1:]]


def list_snapshots(settings: Settings) -> list[Snapshot]:
    """Every distinct capture of the report URL."""
    return parse_cdx(download(cdx_query_url(settings), settings.user_agent, settings.timeout_seconds))


def _fetch_snapshot(snapshot: Snapshot, settings: Settings) -> bytes | None:
    """Raw bytes of one capture, or None (logged) when the archive can't serve it."""
    url = settings.raw_url_template.format(timestamp=snapshot.timestamp, url=settings.report_url)
    try:
        return download(url, settings.user_agent, settings.timeout_seconds)
    except urllib.error.HTTPError as error:
        LOG.warning("wayback %s: HTTP %s, skipped", snapshot.timestamp, error.code)
        return None


def backfill(settings: Settings) -> list[Archived]:
    """Archive every capture that is a PDF; log and skip the rest."""
    results: list[Archived] = []
    for snapshot in list_snapshots(settings):
        body = _fetch_snapshot(snapshot, settings)
        time.sleep(PAUSE_SECONDS)
        if body is None:
            continue
        if not is_pdf(body):
            LOG.warning("wayback %s: not a PDF (%d bytes), skipped", snapshot.timestamp, len(body))
            continue
        results.append(archive_bytes(body, f"wayback:{snapshot.timestamp}", snapshot.seen_at, settings))
    return results
