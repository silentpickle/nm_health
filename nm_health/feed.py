# Copyright (c) 2026 nm_health contributors
"""The city's Info Connect inspection-status feed: status, violation count and coordinates, no violation text.

The feed is filtered by the date a record was created, which can be years before the inspection, so it is
fetched in creation-year chunks reaching back `feed_lookback_days`. Every response whose content changed is kept,
gzipped, under `feed_raw_dir/<year>/` (the city can rewrite a record's status later; git history keeps both).
"""

import gzip
import hashlib
import json
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from nm_health.archive import download
from nm_health.identity import split_dba, strip_city
from nm_health.settings import Settings

SHA_PREFIX_LEN = 12
FOOD_MARKER = "Food"
NOT_DONE_STATUS = "Requested"
VOLATILE_PREFIX = ":"  # Socrata row metadata (:id, :version, :updated_at...) changes without the data changing
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
ISO_DATE_LEN = len("2026-01-01")
# The feed's numbered columns (from the SoQL query it echoes back).
NUMBER, COMPANY, STATUS, RISK, ACTUAL_START, VIOLATIONS, DBA = (
    "ticket_detail_entry0",
    "ticket_detail_entry2",
    "ticket_detail_entry3",
    "ticket_detail_entry4",
    "ticket_detail_entry7",
    "ticket_detail_entry9",
    "ticket_detail_entry13",
)


class FeedError(Exception):
    """A feed response we must not keep (truncated)."""


@dataclass(frozen=True)
class FeedRecord:
    """One completed food inspection as the feed states it."""

    number: str
    date: str  # ISO yyyy-mm-dd, the actual start
    kind: str
    status: str
    name: str
    legal_name: str | None
    address: str
    lat: float | None
    lng: float | None
    violations: int | None
    risk: str | None


def query_url(settings: Settings, start: date, end: date) -> str:
    """Details query for records created between start and end (inclusive)."""
    lat1, lat2, lng1, lng2 = settings.feed_bounds
    params = {
        "categories": settings.feed_categories,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "lat1": lat1,
        "lat2": lat2,
        "lng1": lng1,
        "lng2": lng2,
        "search_field": "",
        "search_value": "",
        "shape_group_id": "",
        "shape_ids": "",
        "statusFilter": "",
    }
    return f"{settings.feed_url}?{urllib.parse.urlencode(params)}"


def years_to_fetch(today: date, lookback_days: int) -> list[int]:
    """Creation years covering the lookback period, oldest first."""
    first = (today - timedelta(days=lookback_days)).year
    return list(range(first, today.year + 1))


def records_of(body: bytes) -> list[dict[str, Any]]:
    """The record list inside a details response; a truncated response is an error, never a silent gap."""
    data = json.loads(body)["api_data"]
    if data.get("incomplete"):
        msg = f"feed response is incomplete ({len(data['records'])} of {data.get('count')} records)"
        raise FeedError(msg)
    rows: list[dict[str, Any]] = data["records"]
    return rows


def content_hash(body: bytes) -> str:
    """Hash of the records with Socrata's row metadata removed, so only real changes count."""
    stable = [
        {k: v for k, v in row.items() if not k.startswith(VOLATILE_PREFIX)}
        for row in sorted(records_of(body), key=lambda r: str(r.get("ticket_id")))
    ]
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def latest_raw(settings: Settings, year: int) -> Path | None:
    """Most recently saved response for a creation year."""
    return next(iter(sorted((settings.feed_raw_dir / str(year)).glob("*.json.gz"), reverse=True)), None)


def save_raw(settings: Settings, year: int, body: bytes, seen_at: datetime) -> Path | None:
    """Keep the response if its content differs from the last one kept for that year; returns the new file."""
    digest = content_hash(body)
    previous = latest_raw(settings, year)
    if previous is not None and previous.name.endswith(f"_{digest[:SHA_PREFIX_LEN]}.json.gz"):
        return None
    folder = settings.feed_raw_dir / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{seen_at.strftime(TIMESTAMP_FORMAT)}_{digest[:SHA_PREFIX_LEN]}.json.gz"
    path.write_bytes(gzip.compress(body, mtime=0))
    return path


def collect(settings: Settings, now: datetime) -> list[Path]:
    """Fetch each creation year in the lookback period; keep the ones that changed."""
    saved: list[Path] = []
    for year in years_to_fetch(now.date(), settings.feed_lookback_days):
        url = query_url(settings, date(year, 1, 1), date(year, 12, 31))
        path = save_raw(settings, year, download(url, settings.user_agent, settings.timeout_seconds), now)
        if path is not None:
            saved.append(path)
    return saved


def _coordinates(row: dict[str, Any]) -> tuple[float | None, float | None]:
    location = row.get("location") or {}
    coordinates = location.get("coordinates") or []
    if len(coordinates) != len(("lng", "lat")):
        return None, None
    return float(coordinates[1]), float(coordinates[0])


def _names(row: dict[str, Any]) -> tuple[str, str | None]:
    company = str(row.get(COMPANY) or "").strip()
    dba = str(row.get(DBA) or "").strip()
    if not dba:
        return split_dba(company)
    split_name, split_legal = split_dba(company)
    legal = split_legal or split_name
    return dba, (legal if legal and legal.lower() != dba.lower() else None)


def _violations(row: dict[str, Any]) -> int | None:
    raw = str(row.get(VIOLATIONS) or "").strip()
    return int(raw) if raw.isdigit() else None


def to_record(row: dict[str, Any]) -> FeedRecord | None:
    """A completed food inspection, or None for pools, not-yet-done requests and undated rows."""
    kind, status, started = str(row.get("category") or ""), str(row.get(STATUS) or ""), str(row.get(ACTUAL_START) or "")
    if FOOD_MARKER not in kind or status == NOT_DONE_STATUS or not started:
        return None
    name, legal_name = _names(row)
    lat, lng = _coordinates(row)
    return FeedRecord(
        number=str(row.get(NUMBER) or "").strip(),
        date=started[:ISO_DATE_LEN],
        kind=kind,
        status=" ".join(status.split()),
        name=name,
        legal_name=legal_name,
        address=strip_city(str(row.get("street_address") or "")),
        lat=lat,
        lng=lng,
        violations=_violations(row),
        risk=str(row.get(RISK)) if row.get(RISK) else None,
    )


def parse(body: bytes) -> list[FeedRecord]:
    """Completed food inspections in a details response."""
    return [record for row in records_of(body) if (record := to_record(row)) is not None]


def load_records(settings: Settings, since: date) -> list[FeedRecord]:
    """Inspections on or after `since`, from the latest kept response of each year; one per (number, date)."""
    by_key: dict[tuple[str, str], FeedRecord] = {}
    for folder in sorted(settings.feed_raw_dir.glob("*")):
        latest = latest_raw(settings, int(folder.name)) if folder.name.isdigit() else None
        if latest is None:
            continue
        for record in parse(gzip.decompress(latest.read_bytes())):
            if record.date >= since.isoformat():
                by_key[(record.number, record.date)] = record
    return sorted(by_key.values(), key=lambda r: (r.date, r.number))


def today_utc() -> datetime:
    """Now, in UTC (one place to stub in tests)."""
    return datetime.now(tz=UTC)
