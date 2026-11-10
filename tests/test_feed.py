# Copyright (c) 2026 nm_health contributors
"""The status feed: which rows count, how names and addresses are read, and what gets kept."""

import gzip
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from nm_health import feed as feed_module
from nm_health.feed import (
    FeedError,
    FeedRecord,
    content_hash,
    load_records,
    parse,
    query_url,
    save_raw,
    to_record,
    years_to_fetch,
)
from nm_health.settings import Settings
from tests.test_archive import make_settings

SEEN = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
YEAR = 2025
LOOKBACK_DAYS = 2200


def row(**overrides: object) -> dict[str, Any]:
    """One feed row shaped like the real API's, for Dragon Sushi's Jul 13, 2026 closure."""
    base: dict[str, Any] = {
        ":id": "row-1",
        ":updated_at": "2026-07-29T00:00:00.000Z",
        "ticket_id": "abc",
        "category": "Routine Food Establishment Inspection",
        "street_address": "6902 MENAUL BLVD NE Albuquerque, NM 87110 ",
        "location": {"type": "Point", "coordinates": [-106.55, 35.11]},
        "ticket_detail_entry0": "RT-FOODEST-056969-2026",
        "ticket_detail_entry2": "Long Cao LLC DBA Dragon Sushi",
        "ticket_detail_entry3": "Closure  Re-Inspection Required",
        "ticket_detail_entry4": "3",
        "ticket_detail_entry7": "2026-07-13T11:45:00.000",
        "ticket_detail_entry9": "18",
        "ticket_detail_entry13": "Dragon Sushi",
    }
    return {**base, **overrides}


def body(*rows: dict[str, Any], incomplete: bool = False) -> bytes:
    """A details response holding the rows."""
    data = {"records": list(rows), "count": len(rows), "incomplete": incomplete}
    return json.dumps({"api_data": data, "soql_queries": []}).encode()


def feed_settings(tmp_path: Path) -> Settings:
    """Settings whose feed folder is inside tmp_path."""
    return replace(
        make_settings(tmp_path),
        feed_url="https://example.test/details.json",
        feed_categories="8:4300-4312",
        feed_bounds=(35.4, 34.8, -106.2, -107.0),
        feed_raw_dir=tmp_path / "feed",
    )


def test_dragon_sushi_row() -> None:
    """DBA column wins for the name; legal name kept; city suffix and double spaces dropped; coordinates read."""
    assert to_record(row()) == FeedRecord(
        number="RT-FOODEST-056969-2026",
        date="2026-07-13",
        kind="Routine Food Establishment Inspection",
        status="Closure Re-Inspection Required",
        name="Dragon Sushi",
        legal_name="Long Cao LLC",
        address="6902 MENAUL BLVD NE",
        lat=35.11,
        lng=-106.55,
        violations=18,
        risk="3",
        time="11:45",
    )


def test_date_only_start_has_no_time() -> None:
    """An actual start without a time part leaves the time unknown."""
    record = to_record(row(ticket_detail_entry7="2026-07-13"))
    assert record is not None
    assert (record.date, record.time) == ("2026-07-13", None)


@pytest.mark.parametrize(
    ("overrides", "expected_name", "expected_legal"),
    [
        pytest.param({"ticket_detail_entry13": None}, "Dragon Sushi", "Long Cao LLC", id="dba_in_company"),
        pytest.param({"ticket_detail_entry13": None, "ticket_detail_entry2": "BAMBOO"}, "BAMBOO", None, id="no_dba"),
        pytest.param({"ticket_detail_entry2": "Dragon Sushi"}, "Dragon Sushi", None, id="same_names"),
    ],
)
def test_names(overrides: dict[str, Any], expected_name: str, expected_legal: str | None) -> None:
    """Without a DBA column the company name is split on 'DBA'; identical names keep no legal name."""
    record = to_record(row(**overrides))
    assert record is not None
    assert (record.name, record.legal_name) == (expected_name, expected_legal)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"category": "Routine Swimming Pool Inspection"}, id="pool_dropped"),
        pytest.param({"ticket_detail_entry3": "Requested"}, id="requested_dropped"),
        pytest.param({"ticket_detail_entry7": None}, id="undated_dropped"),
    ],
)
def test_rows_that_are_not_food_inspections(overrides: dict[str, Any]) -> None:
    """Pools, not-yet-done requests and rows with no actual date are not inspections we show."""
    assert to_record(row(**overrides)) is None


def test_missing_coordinates_and_count() -> None:
    """A row without a point or a numeric count still parses."""
    record = to_record(row(location=None, ticket_detail_entry9=""))
    assert record is not None
    assert (record.lat, record.lng, record.violations) == (None, None, None)


def test_incomplete_response_is_an_error() -> None:
    """A truncated response must fail loudly, never become a silent gap."""
    with pytest.raises(FeedError, match="incomplete"):
        parse(body(row(), incomplete=True))


def test_query_and_years(tmp_path: Path) -> None:
    """One query per creation year, reaching back the lookback period."""
    url = query_url(feed_settings(tmp_path), date(YEAR, 1, 1), date(YEAR, 12, 31))
    params = parse_qs(urlsplit(url).query)
    assert (params["start_date"], params["end_date"], params["categories"]) == (
        ["2025-01-01"],
        ["2025-12-31"],
        ["8:4300-4312"],
    )
    assert years_to_fetch(date(2026, 11, 9), LOOKBACK_DAYS) == [2020, 2021, 2022, 2023, 2024, 2025, 2026]


def test_only_real_changes_are_kept(tmp_path: Path) -> None:
    """Row metadata churn is ignored; a status change is a new file, and the newest file is what loads."""
    settings = feed_settings(tmp_path)
    first = save_raw(settings, YEAR, body(row()), SEEN)
    churn = save_raw(settings, YEAR, body(row(**{":updated_at": "2026-11-10"})), LATER)
    changed = save_raw(settings, YEAR, body(row(ticket_detail_entry3="Approved")), LATER)

    assert first is not None
    assert churn is None
    assert changed is not None
    assert content_hash(body(row())) == content_hash(body(row(**{":id": "row-2"})))
    assert gzip.decompress(changed.read_bytes()) == body(row(ticket_detail_entry3="Approved"))
    (loaded,) = load_records(settings, date(2026, 1, 1))
    assert loaded.status == "Approved"


def test_load_records_window_and_dedupe(tmp_path: Path) -> None:
    """Only inspections on or after `since`; one record per (number, date) across years."""
    settings = feed_settings(tmp_path)
    old = row(ticket_id="old", ticket_detail_entry7="2025-06-01T09:00:00.000", ticket_detail_entry0="OLD-1")
    save_raw(settings, YEAR, body(row(), old), SEEN)
    save_raw(settings, YEAR + 1, body(row(ticket_detail_entry3="Approved")), SEEN)
    (ignored := settings.feed_raw_dir / "notes").mkdir()
    assert ignored.is_dir()

    loaded = load_records(settings, date(2025, 11, 9))

    assert [(r.number, r.status) for r in loaded] == [("RT-FOODEST-056969-2026", "Approved")]


def test_collect_fetches_each_year_and_keeps_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One request per creation year; a second identical run keeps nothing new."""
    settings = replace(feed_settings(tmp_path), feed_lookback_days=365)
    requested: list[str] = []

    def fake_download(url: str, _agent: str, _timeout: int) -> bytes:
        requested.append(parse_qs(urlsplit(url).query)["start_date"][0])
        return body(row())

    monkeypatch.setattr(feed_module, "download", fake_download)
    first = feed_module.collect(settings, SEEN)
    second = feed_module.collect(settings, LATER)

    assert requested == ["2025-01-01", "2026-01-01", "2025-01-01", "2026-01-01"]
    assert [p.parent.name for p in first] == ["2025", "2026"]
    assert second == []
    assert feed_module.today_utc().tzinfo is UTC
