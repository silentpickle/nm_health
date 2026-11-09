# Copyright (c) 2026 nm_health contributors
"""Rebuild every inspection from the archived PDFs; nothing derived is ever committed.

Reports are read oldest first. When two reports state the same inspection (an amended re-issue, or a later week
repeating it), the later report wins. Routine inspections reuse the permit number as their ID, so an inspection is
keyed by (ID, date).
"""

import json
import logging
import subprocess
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

from nm_health.feed import FeedRecord, load_records
from nm_health.identity import normalized_address, split_dba
from nm_health.ingest.parser import InspectionReportParser
from nm_health.legacy_parser import is_legacy, parse_legacy
from nm_health.model import Inspection, Violation
from nm_health.settings import Settings
from nm_health.tags import tagged

LOG = logging.getLogger(__name__)
CURRENT_MARKER = "Inspection Result:"
LAYOUT_CURRENT = "current"
LAYOUT_LEGACY = "legacy"
LAYOUT_UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Report:
    """One archived PDF and what came out of it."""

    file: str
    sha256: str
    week_start: str | None
    week_end: str | None
    source: str
    seen_at: str
    layout: str
    inspections: int


@dataclass(frozen=True)
class Rebuilt:
    """Every inspection (deduplicated, tagged) and every report it came from."""

    inspections: tuple[Inspection, ...]
    reports: tuple[Report, ...]


def read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    """Manifest entries by file name; a file listed twice keeps its first entry (first seen)."""
    entries: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry: dict[str, Any] = json.loads(line)
        entries.setdefault(str(entry["file"]), entry)
    return entries


def report_text(pdf: Path) -> str:
    """All pages' text via pdftotext, pages separated by form feeds."""
    result = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, check=True)
    return result.stdout.decode("utf-8", errors="replace")


def _violation(raw: dict[str, Any]) -> Violation:
    return Violation(
        category=str(raw["category"]),
        item=str(raw["item_title"]),
        rule=str(raw["rule_description"]),
        observation=str(raw["observation"]),
    )


def _from_current(raw: dict[str, Any], report_file: str) -> Inspection:
    return Inspection(
        inspection_id=str(raw["inspection_id_num"]),
        date=str(raw["inspection_date"]),
        kind=str(raw["inspection_type"]),
        status=str(raw["inspection_status"]),
        name=str(raw["establishment_name"]),
        address=str(raw["establishment_address"]),
        permit_number=raw["permit_number"],
        permit_type=raw["permit_type"],
        report_file=report_file,
        page=raw["detail_page"] or raw["summary_page"],
        violations=tuple(_violation(v) for v in raw["violations"]),
    )


def parse_report(pdf: Path) -> tuple[str, list[Inspection]]:
    """(layout, inspections) for one archived PDF, choosing the parser by its text."""
    text = report_text(pdf)
    if is_legacy(text):
        return LAYOUT_LEGACY, parse_legacy(text, pdf.name)
    if CURRENT_MARKER not in text:
        LOG.warning("%s: no known report layout, skipped", pdf.name)
        return LAYOUT_UNREADABLE, []
    parsed = InspectionReportParser(pdf).parse()
    return LAYOUT_CURRENT, [_from_current(raw, pdf.name) for raw in parsed["inspections"]]


def _order_key(entry: dict[str, Any]) -> tuple[str, str]:
    return (str(entry.get("week_end") or ""), str(entry.get("seen_at") or ""))


def _report(entry: dict[str, Any], layout: str, count: int) -> Report:
    return Report(
        file=str(entry["file"]),
        sha256=str(entry["sha256"]),
        week_start=entry.get("week_start"),
        week_end=entry.get("week_end"),
        source=str(entry.get("source", "")),
        seen_at=str(entry.get("seen_at", "")),
        layout=layout,
        inspections=count,
    )


def _prepare(inspection: Inspection) -> Inspection:
    """Tag violations and show the place under the name people know (DBA), keeping the legal name."""
    name, legal_name = split_dba(inspection.name)
    return replace(
        inspection,
        name=name,
        legal_name=inspection.legal_name or legal_name,
        violations=tuple(tagged(v) for v in inspection.violations),
    )


def _supersede(previous: Inspection | None, current: Inspection) -> Inspection:
    """A later report's version wins; if it changed the status, remember the first status reported."""
    if previous is None or previous.status == current.status:
        return current
    return replace(current, amended_from=previous.amended_from or previous.status)


def _from_feed(record: FeedRecord) -> Inspection:
    """An inspection known only from the status feed: no violation text."""
    return Inspection(
        inspection_id=record.number,
        date=record.date,
        kind=record.kind,
        status=record.status,
        name=record.name,
        address=record.address,
        permit_number=None,
        permit_type=None,
        report_file="",
        page=None,
        legal_name=record.legal_name,
        has_details=False,
        violation_count=record.violations,
        lat=record.lat,
        lng=record.lng,
    )


def merge_feed(detailed: list[Inspection], records: list[FeedRecord]) -> list[Inspection]:
    """Detailed inspections gain the feed's coordinates and count; feed-only inspections are added without text."""
    by_key = {(r.number, r.date): r for r in records}
    by_address = {normalized_address(r.address): r for r in records if r.lat is not None}
    merged: list[Inspection] = []
    for inspection in detailed:
        match = by_key.pop((inspection.inspection_id, inspection.date), None)
        nearby = match or by_address.get(normalized_address(inspection.address))
        if nearby is not None:
            inspection = replace(inspection, lat=nearby.lat, lng=nearby.lng)  # noqa: PLW2901 - enriching the loop item
        if match is not None:
            inspection = replace(inspection, violation_count=match.violations)  # noqa: PLW2901 - enriching the loop item
        merged.append(inspection)
    return merged + [_from_feed(r) for r in by_key.values()]


def rebuild(settings: Settings, since: date | None = None) -> Rebuilt:
    """Every archived PDF (oldest week first, later reports win) merged with the status feed.

    With `since`, only inspections on or after that date are kept (the site's 12-month window); without it,
    everything archived and the whole feed.
    """
    entries = sorted(read_manifest(settings.manifest).values(), key=_order_key)
    latest: dict[tuple[str, str], Inspection] = {}
    reports: list[Report] = []
    for entry in entries:
        layout, inspections = parse_report(settings.archive_dir / str(entry["file"]))
        reports.append(_report(entry, layout, len(inspections)))
        for inspection in map(_prepare, inspections):
            key = (inspection.inspection_id, inspection.date)
            latest[key] = _supersede(latest.get(key), inspection)
    cutoff = (since or date.min).isoformat()
    detailed = [i for i in latest.values() if i.date >= cutoff]
    merged = merge_feed(detailed, load_records(settings, since or date.min))
    ordered = sorted(merged, key=lambda i: (i.date, i.name, i.inspection_id))
    return Rebuilt(inspections=tuple(ordered), reports=tuple(reports))
