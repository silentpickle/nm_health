import sqlite3
import re
import contextlib
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from nm_health.config import DB_PATH
from nm_health.ingest.normalizer import normalize_address, normalize_establishment_name

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256_hash TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    source_url TEXT NOT NULL,
    week_start TEXT,
    week_end TEXT,
    raw_title TEXT,
    amendment_notes TEXT,
    file_size INTEGER,
    archive_path TEXT,
    total_establishments INTEGER DEFAULT 0,
    total_inspections INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS establishments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    raw_address TEXT NOT NULL,
    normalized_address TEXT NOT NULL,
    street_number TEXT,
    street_name TEXT,
    quadrant TEXT,
    unit TEXT,
    city TEXT DEFAULT 'Albuquerque',
    state TEXT DEFAULT 'NM',
    latest_status TEXT,
    latest_inspection_date TEXT,
    has_pest_history INTEGER DEFAULT 0,
    total_inspections INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_est_slug ON establishments(slug);
CREATE INDEX IF NOT EXISTS idx_est_norm_name ON establishments(normalized_name);
CREATE INDEX IF NOT EXISTS idx_est_norm_addr ON establishments(normalized_address);
CREATE INDEX IF NOT EXISTS idx_est_latest_status ON establishments(latest_status);

CREATE TABLE IF NOT EXISTS permits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    establishment_id INTEGER NOT NULL REFERENCES establishments(id) ON DELETE CASCADE,
    permit_number TEXT NOT NULL,
    permit_type TEXT,
    operational_status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(establishment_id, permit_number)
);

CREATE TABLE IF NOT EXISTS inspections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES reports(id) ON DELETE SET NULL,
    establishment_id INTEGER NOT NULL REFERENCES establishments(id) ON DELETE CASCADE,
    permit_id INTEGER REFERENCES permits(id) ON DELETE SET NULL,
    inspection_id_num TEXT NOT NULL,
    inspection_date TEXT NOT NULL,
    inspection_type TEXT,
    inspection_status TEXT,
    summary_page INTEGER,
    detail_page INTEGER,
    has_pest_violation INTEGER DEFAULT 0,
    has_critical_violation INTEGER DEFAULT 0,
    violation_count INTEGER DEFAULT 0,
    raw_summary_line TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(inspection_id_num, inspection_date)
);

CREATE INDEX IF NOT EXISTS idx_insp_est_id ON inspections(establishment_id);
CREATE INDEX IF NOT EXISTS idx_insp_date ON inspections(inspection_date);
CREATE INDEX IF NOT EXISTS idx_insp_status ON inspections(inspection_status);
CREATE INDEX IF NOT EXISTS idx_insp_report ON inspections(report_id);

CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id INTEGER NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    item_title TEXT,
    rule_description TEXT,
    observation TEXT,
    raw_text TEXT,
    is_pest INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_viol_insp_id ON violations(inspection_id);
CREATE INDEX IF NOT EXISTS idx_viol_category ON violations(category);
CREATE INDEX IF NOT EXISTS idx_viol_is_pest ON violations(is_pest);

-- Virtual FTS5 tables for fast search
CREATE VIRTUAL TABLE IF NOT EXISTS establishments_fts USING fts5(
    name,
    normalized_address,
    raw_address,
    content='establishments',
    content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS violations_fts USING fts5(
    observation,
    category,
    item_title,
    content='violations',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS establishments_ai AFTER INSERT ON establishments BEGIN
  INSERT INTO establishments_fts(rowid, name, normalized_address, raw_address) 
  VALUES (new.id, new.name, new.normalized_address, new.raw_address);
END;

CREATE TRIGGER IF NOT EXISTS establishments_ad AFTER DELETE ON establishments BEGIN
  INSERT INTO establishments_fts(establishments_fts, rowid, name, normalized_address, raw_address) 
  VALUES('delete', old.id, old.name, old.normalized_address, old.raw_address);
END;

CREATE TRIGGER IF NOT EXISTS establishments_au AFTER UPDATE ON establishments BEGIN
  INSERT INTO establishments_fts(establishments_fts, rowid, name, normalized_address, raw_address) 
  VALUES('delete', old.id, old.name, old.normalized_address, old.raw_address);
  INSERT INTO establishments_fts(rowid, name, normalized_address, raw_address) 
  VALUES (new.id, new.name, new.normalized_address, new.raw_address);
END;

CREATE TRIGGER IF NOT EXISTS violations_ai AFTER INSERT ON violations BEGIN
  INSERT INTO violations_fts(rowid, observation, category, item_title) 
  VALUES (new.id, new.observation, new.category, new.item_title);
END;

CREATE TRIGGER IF NOT EXISTS violations_ad AFTER DELETE ON violations BEGIN
  INSERT INTO violations_fts(violations_fts, rowid, observation, category, item_title) 
  VALUES('delete', old.id, old.observation, old.category, old.item_title);
END;
"""


class LocalStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextlib.contextmanager
    def get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    def report_exists(self, sha256_hash: str) -> bool:
        with self.get_connection() as conn:
            cur = conn.execute("SELECT 1 FROM reports WHERE sha256_hash = ?", (sha256_hash,))
            return cur.fetchone() is not None

    def insert_report(self, report_data: Dict[str, Any]) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO reports (
                    sha256_hash, filename, source_url, week_start, week_end,
                    raw_title, amendment_notes, file_size, archive_path,
                    total_establishments, total_inspections
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sha256_hash) DO UPDATE SET
                    week_start=excluded.week_start,
                    week_end=excluded.week_end,
                    total_establishments=excluded.total_establishments,
                    total_inspections=excluded.total_inspections
                RETURNING id;
                """,
                (
                    report_data["sha256_hash"],
                    report_data["filename"],
                    report_data.get("source_url", ""),
                    report_data.get("week_start"),
                    report_data.get("week_end"),
                    report_data.get("raw_title"),
                    report_data.get("amendment_notes"),
                    report_data.get("file_size", 0),
                    report_data.get("archive_path", ""),
                    report_data.get("total_establishments", 0),
                    report_data.get("total_inspections", 0),
                ),
            )
            return cur.fetchone()[0]

    def upsert_establishment(self, name: str, raw_address: str) -> int:
        norm_name = normalize_establishment_name(name)
        addr_info = normalize_address(raw_address)
        # Unique slug based on normalized address and cleaned name
        name_clean = re.sub(r"[^a-z0-9]+", "-", norm_name.lower()).strip("-")
        slug = f"{name_clean}-{addr_info['slug']}"

        with self.get_connection() as conn:
            # Check existing by slug or by normalized address + normalized name
            cur = conn.execute(
                "SELECT id FROM establishments WHERE slug = ? OR (normalized_name = ? AND normalized_address = ?)",
                (slug, norm_name, addr_info["normalized_address"]),
            )
            row = cur.fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE establishments
                    SET updated_at = CURRENT_TIMESTAMP,
                        raw_address = ?
                    WHERE id = ?
                    """,
                    (raw_address, row[0]),
                )
                return row[0]

            cur = conn.execute(
                """
                INSERT INTO establishments (
                    slug, name, normalized_name, raw_address, normalized_address,
                    street_number, street_name, quadrant, unit, city, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id;
                """,
                (
                    slug,
                    name.strip(),
                    norm_name,
                    raw_address.strip(),
                    addr_info["normalized_address"],
                    addr_info["street_number"],
                    addr_info["street_name"],
                    addr_info["quadrant"],
                    addr_info["unit"],
                    addr_info["city"],
                    addr_info["state"],
                ),
            )
            return cur.fetchone()[0]

    def upsert_permit(
        self, establishment_id: int, permit_number: str, permit_type: str, operational_status: str
    ) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO permits (establishment_id, permit_number, permit_type, operational_status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(establishment_id, permit_number) DO UPDATE SET
                    permit_type = excluded.permit_type,
                    operational_status = excluded.operational_status
                RETURNING id;
                """,
                (establishment_id, permit_number.strip(), permit_type.strip(), operational_status.strip()),
            )
            return cur.fetchone()[0]

    def upsert_inspection(self, inspection_data: Dict[str, Any]) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO inspections (
                    report_id, establishment_id, permit_id, inspection_id_num,
                    inspection_date, inspection_type, inspection_status,
                    summary_page, detail_page, has_pest_violation,
                    has_critical_violation, violation_count, raw_summary_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(inspection_id_num, inspection_date) DO UPDATE SET
                    report_id = excluded.report_id,
                    inspection_status = excluded.inspection_status,
                    has_pest_violation = excluded.has_pest_violation,
                    has_critical_violation = excluded.has_critical_violation,
                    violation_count = excluded.violation_count,
                    detail_page = excluded.detail_page
                RETURNING id;
                """,
                (
                    inspection_data.get("report_id"),
                    inspection_data["establishment_id"],
                    inspection_data.get("permit_id"),
                    inspection_data["inspection_id_num"],
                    inspection_data["inspection_date"],
                    inspection_data.get("inspection_type"),
                    inspection_data.get("inspection_status"),
                    inspection_data.get("summary_page"),
                    inspection_data.get("detail_page"),
                    1 if inspection_data.get("has_pest_violation") else 0,
                    1 if inspection_data.get("has_critical_violation") else 0,
                    inspection_data.get("violation_count", 0),
                    inspection_data.get("raw_summary_line", ""),
                ),
            )
            insp_id = cur.fetchone()[0]

            # Update establishment summary stats
            est_id = inspection_data["establishment_id"]
            conn.execute(
                """
                UPDATE establishments
                SET latest_status = (
                        SELECT inspection_status FROM inspections
                        WHERE establishment_id = ?
                        ORDER BY inspection_date DESC, id DESC LIMIT 1
                    ),
                    latest_inspection_date = (
                        SELECT MAX(inspection_date) FROM inspections
                        WHERE establishment_id = ?
                    ),
                    total_inspections = (
                        SELECT COUNT(*) FROM inspections
                        WHERE establishment_id = ?
                    ),
                    has_pest_history = (
                        CASE WHEN EXISTS (
                            SELECT 1 FROM inspections
                            WHERE establishment_id = ? AND has_pest_violation = 1
                        ) THEN 1 ELSE 0 END
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (est_id, est_id, est_id, est_id, est_id),
            )
            return insp_id

    def insert_violation(self, violation_data: Dict[str, Any]) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO violations (
                    inspection_id, category, item_title, rule_description,
                    observation, raw_text, is_pest
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id;
                """,
                (
                    violation_data["inspection_id"],
                    violation_data.get("category", ""),
                    violation_data.get("item_title", ""),
                    violation_data.get("rule_description", ""),
                    violation_data.get("observation", ""),
                    violation_data.get("raw_text", ""),
                    1 if violation_data.get("is_pest") else 0,
                ),
            )
            return cur.fetchone()[0]

    def search_establishments(self, query: str = "", status: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            params = []
            where_clauses = []

            if status:
                where_clauses.append("e.latest_status LIKE ?")
                params.append(f"%{status}%")

            if query:
                clean_q = query.strip()
                # Check if it's an FTS search
                fts_query = " OR ".join(f'"{word}*"' for word in clean_q.split() if word.isalnum())
                if fts_query:
                    # Search either establishment name/address or violation keywords
                    sql = f"""
                    SELECT DISTINCT e.*
                    FROM establishments e
                    WHERE (
                        e.id IN (
                            SELECT rowid FROM establishments_fts WHERE establishments_fts MATCH ?
                        )
                        OR e.id IN (
                            SELECT i.establishment_id 
                            FROM inspections i
                            JOIN violations v ON v.inspection_id = i.id
                            WHERE v.id IN (SELECT rowid FROM violations_fts WHERE violations_fts MATCH ?)
                        )
                        OR e.name LIKE ?
                        OR e.normalized_address LIKE ?
                    )
                    """
                    params.extend([fts_query, fts_query, f"%{clean_q}%", f"%{clean_q}%"])
                    if status:
                        sql += " AND e.latest_status LIKE ?"
                        params.append(f"%{status}%")
                    sql += " ORDER BY e.has_pest_history DESC, e.latest_inspection_date DESC LIMIT ?"
                    params.append(limit)
                    rows = conn.execute(sql, params).fetchall()
                    return [dict(r) for r in rows]

            # Fallback when query is empty but status or default listing
            sql = "SELECT e.* FROM establishments e"
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            sql += " ORDER BY e.latest_inspection_date DESC, e.id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def get_establishment_detail(self, establishment_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            est_row = conn.execute("SELECT * FROM establishments WHERE id = ?", (establishment_id,)).fetchone()
            if not est_row:
                return None

            est = dict(est_row)

            # Permits
            permits = conn.execute(
                "SELECT * FROM permits WHERE establishment_id = ? ORDER BY id ASC", (establishment_id,)
            ).fetchall()
            est["permits"] = [dict(p) for p in permits]

            # Inspections
            inspections = conn.execute(
                """
                SELECT i.*, 
                       r.filename as report_filename, 
                       r.week_start, 
                       r.week_end, 
                       r.archive_path,
                       r.created_at as report_downloaded_at,
                       r.file_size as report_file_size,
                       r.sha256_hash as report_sha256,
                       r.source_url as report_source_url
                FROM inspections i
                LEFT JOIN reports r ON r.id = i.report_id
                WHERE i.establishment_id = ?
                ORDER BY i.inspection_date DESC, i.id DESC
                """,
                (establishment_id,),
            ).fetchall()

            insp_list = []
            for insp_row in inspections:
                insp = dict(insp_row)
                violations = conn.execute(
                    "SELECT * FROM violations WHERE inspection_id = ? ORDER BY is_pest DESC, id ASC", (insp["id"],)
                ).fetchall()
                insp["violations"] = [dict(v) for v in violations]
                insp_list.append(insp)

            est["inspections"] = insp_list
            return est

    def get_reports(self) -> List[Dict[str, Any]]:
        """List all archived PDF reports in reverse chronological order."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, sha256_hash, filename, source_url, week_start, week_end,
                       raw_title, amendment_notes, file_size, archive_path,
                       total_establishments, total_inspections, created_at as downloaded_at
                FROM reports
                ORDER BY downloaded_at DESC, id DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent inspections that resulted in closure, downgrade, or conditional approval."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT i.*, e.name as establishment_name, e.normalized_address, e.raw_address
                FROM inspections i
                JOIN establishments e ON e.id = i.establishment_id
                WHERE i.inspection_status LIKE '%Closure%'
                   OR i.inspection_status LIKE '%Unsatisfactory%'
                   OR i.inspection_status LIKE '%Conditional%'
                   OR i.has_pest_violation = 1
                ORDER BY i.inspection_date DESC, i.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            alerts = []
            for r in rows:
                item = dict(r)
                viols = conn.execute(
                    "SELECT category, item_title, observation, is_pest FROM violations WHERE inspection_id = ?",
                    (item["id"],),
                ).fetchall()
                item["violations"] = [dict(v) for v in viols]
                alerts.append(item)
            return alerts

    def get_stats(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            est_count = conn.execute("SELECT COUNT(*) FROM establishments").fetchone()[0]
            insp_count = conn.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
            viol_count = conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
            pest_count = conn.execute(
                "SELECT COUNT(DISTINCT establishment_id) FROM inspections WHERE has_pest_violation = 1"
            ).fetchone()[0]
            closure_count = conn.execute(
                "SELECT COUNT(*) FROM inspections WHERE inspection_status LIKE '%Closure%'"
            ).fetchone()[0]
            report_count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]

            # Status breakdown
            statuses = conn.execute(
                "SELECT inspection_status, COUNT(*) as cnt FROM inspections GROUP BY inspection_status ORDER BY cnt DESC"
            ).fetchall()

            return {
                "total_establishments": est_count,
                "total_inspections": insp_count,
                "total_violations": viol_count,
                "establishments_with_pest_violations": pest_count,
                "total_closures": closure_count,
                "total_reports": report_count,
                "status_breakdown": {row["inspection_status"]: row["cnt"] for row in statuses},
            }
