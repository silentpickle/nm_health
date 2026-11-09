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
PAUSE_SECONDS = 6.0  # be polite to web.archive.org between snapshot downloads
TOO_MANY_REQUESTS = 429
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 30.0  # wait after a 429, times the attempt number, unless Retry-After says otherwise


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


def _retry_wait(error: urllib.error.HTTPError, attempt: int) -> float:
    """Seconds to wait before retrying a rate-limited request."""
    retry_after = error.headers.get("Retry-After", "")
    return float(retry_after) if retry_after.isdigit() else BACKOFF_SECONDS * attempt


def _download_once(url: str, settings: Settings) -> bytes | urllib.error.HTTPError:
    """One attempt; an HTTP error comes back as a value so the caller can decide to retry."""
    try:
        return download(url, settings.user_agent, settings.timeout_seconds)
    except urllib.error.HTTPError as error:
        return error


def _fetch_snapshot(snapshot: Snapshot, settings: Settings) -> bytes | None:
    """Raw bytes of one capture, or None (logged) when the archive can't serve it."""
    url = settings.raw_url_template.format(timestamp=snapshot.timestamp, url=settings.report_url)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = _download_once(url, settings)
        if isinstance(result, bytes):
            return result
        if result.code != TOO_MANY_REQUESTS:
            LOG.warning("wayback %s: HTTP %s, skipped", snapshot.timestamp, result.code)
            return None
        wait = _retry_wait(result, attempt)
        LOG.info("wayback %s: rate limited, retrying in %.0fs", snapshot.timestamp, wait)
        time.sleep(wait)
    LOG.warning("wayback %s: still rate limited after %d attempts, skipped", snapshot.timestamp, MAX_ATTEMPTS)
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
