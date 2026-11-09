# Copyright (c) 2026 nm_health contributors
"""Write a rebuilt archive into the SQLite file the CLI and local dashboard read. Recreated from scratch each run."""

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

from nm_health.db.local_store import SCHEMA_SQL
from nm_health.identity import establishment_slug, normalized_address
from nm_health.ingest.normalizer import normalize_address, normalize_establishment_name
from nm_health.model import Inspection
from nm_health.rebuild import Rebuilt, Report

HEADLINE_PESTS = ("roaches", "rodents")  # what "pest history" means on the site and in the CLI
RED_STATUS_WORDS = ("closure", "unsatisfactory")
SQLITE_SIDE_FILES = ("-wal", "-shm")

REFRESH_ESTABLISHMENTS = """
UPDATE establishments SET
    latest_status = (SELECT inspection_status FROM inspections i WHERE i.establishment_id = establishments.id
                     ORDER BY inspection_date DESC, id DESC LIMIT 1),
    latest_inspection_date = (SELECT MAX(inspection_date) FROM inspections i WHERE i.establishment_id = establishments.id),
    total_inspections = (SELECT COUNT(*) FROM inspections i WHERE i.establishment_id = establishments.id),
    has_pest_history = EXISTS (SELECT 1 FROM inspections i WHERE i.establishment_id = establishments.id
                               AND has_pest_violation = 1)
"""


def _remove(db_path: Path) -> None:
    for suffix in ("", *SQLITE_SIDE_FILES):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)


def _insert_report(conn: sqlite3.Connection, report: Report, archive_dir: Path) -> int:
    pdf = archive_dir / report.file
    row = conn.execute(
        """INSERT INTO reports (sha256_hash, filename, source_url, week_start, week_end, file_size, archive_path,
                                total_inspections, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (
            report.sha256,
            report.file,
            report.source,
            report.week_start,
            report.week_end,
            pdf.stat().st_size,
            str(pdf),
            report.inspections,
            report.seen_at,
        ),
    ).fetchone()
    return int(row[0])


def _establishment_id(conn: sqlite3.Connection, inspection: Inspection) -> int:
    slug = establishment_slug(inspection.name, inspection.address)
    found = conn.execute("SELECT id FROM establishments WHERE slug = ?", (slug,)).fetchone()
    if found is not None:
        return int(found[0])
    address = normalize_address(inspection.address)
    row = conn.execute(
        """INSERT INTO establishments (slug, name, normalized_name, raw_address, normalized_address,
                                       street_number, street_name, quadrant, unit)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (
            slug,
            inspection.name,
            normalize_establishment_name(inspection.name),
            inspection.address,
            normalized_address(inspection.address),
            address["street_number"],
            address["street_name"],
            address["quadrant"],
            address["unit"],
        ),
    ).fetchone()
    return int(row[0])


def _permit_id(conn: sqlite3.Connection, establishment_id: int, inspection: Inspection) -> int | None:
    if inspection.permit_number is None:
        return None
    row = conn.execute(
        """INSERT INTO permits (establishment_id, permit_number, permit_type, operational_status)
           VALUES (?, ?, ?, 'Open')
           ON CONFLICT(establishment_id, permit_number) DO UPDATE SET permit_type = excluded.permit_type
           RETURNING id""",
        (establishment_id, inspection.permit_number, inspection.permit_type or ""),
    ).fetchone()
    return int(row[0])


def _headline_pests(tags: tuple[str, ...]) -> bool:
    return any(tag in tags for tag in HEADLINE_PESTS)


def _violation_count(inspection: Inspection) -> int:
    """Listed violations when the text is on file, else the status feed's count."""
    if inspection.has_details:
        return len(inspection.violations)
    return inspection.violation_count or 0


def _insert_inspection(conn: sqlite3.Connection, inspection: Inspection, report_id: int | None) -> None:
    establishment_id = _establishment_id(conn, inspection)
    has_pests = any(_headline_pests(v.tags) for v in inspection.violations)
    is_red = any(word in inspection.status.lower() for word in RED_STATUS_WORDS)
    row = conn.execute(
        """INSERT INTO inspections (report_id, establishment_id, permit_id, inspection_id_num, inspection_date,
                                    inspection_type, inspection_status, detail_page, has_pest_violation,
                                    has_critical_violation, violation_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (
            report_id,
            establishment_id,
            _permit_id(conn, establishment_id, inspection),
            inspection.inspection_id,
            inspection.date,
            inspection.kind,
            inspection.status,
            inspection.page,
            has_pests,
            is_red or has_pests,
            _violation_count(inspection),
        ),
    ).fetchone()
    conn.executemany(
        """INSERT INTO violations (inspection_id, category, item_title, rule_description, observation, is_pest)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [(row[0], v.category, v.item, v.rule, v.observation, _headline_pests(v.tags)) for v in inspection.violations],
    )


def _insert_all(conn: sqlite3.Connection, inspections: Iterable[Inspection], report_ids: dict[str, int]) -> None:
    for inspection in inspections:
        _insert_inspection(conn, inspection, report_ids.get(inspection.report_file))  # None: feed-only


def write_database(rebuilt: Rebuilt, db_path: Path, archive_dir: Path) -> None:
    """Replace db_path with a fresh database holding every rebuilt inspection."""
    _remove(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.executescript(SCHEMA_SQL)
        report_ids = {r.file: _insert_report(conn, r, archive_dir) for r in rebuilt.reports}
        _insert_all(conn, rebuilt.inspections, report_ids)
        conn.execute(REFRESH_ESTABLISHMENTS)
