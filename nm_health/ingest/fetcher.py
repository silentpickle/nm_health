import hashlib  # noqa: CPY001, D100, I001
import shutil
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional  # noqa: UP035

from nm_health.config import (
    CABQ_INSPECTION_PDF_URL,
    ARCHIVE_DIR,
    HTTP_USER_AGENT,
)
from nm_health.db.local_store import LocalStore
from nm_health.ingest.parser import InspectionReportParser


class ReportFetcher:
    """
    Checks CABQ for new inspection reports, archives PDFs,
    and coordinates ingestion into the database.
    """  # noqa: D205, D212

    def __init__(self, store: Optional[LocalStore] = None):  # noqa: ANN204, D107, UP045
        self.store = store or LocalStore()

    def calculate_sha256(self, file_path: Path) -> str:  # noqa: D102
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:  # noqa: PTH123
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def download_report(self, url: str = CABQ_INSPECTION_PDF_URL, target_path: Optional[Path] = None) -> Path:  # noqa: UP045
        """Download latest PDF from CABQ."""
        if target_path is None:
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005
            target_path = ARCHIVE_DIR / f"temp_{now_str}.pdf"

        req = urllib.request.Request(  # noqa: S310
            url,
            headers={
                "User-Agent": HTTP_USER_AGENT,
                "Accept": "application/pdf,*/*",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp, open(target_path, "wb") as out_f:  # noqa: PTH123, S310
            shutil.copyfileobj(resp, out_f)

        return target_path

    def ingest_file(
        self,
        file_path: Path,
        source_url: str = CABQ_INSPECTION_PDF_URL,
        force: bool = False,  # noqa: FBT001, FBT002
    ) -> Dict[str, Any]:  # noqa: UP006
        """
        Parses a local PDF report file, archives it, and saves structured records into the DB.
        """  # noqa: D200, D212
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")  # noqa: EM102, TRY003

        sha256 = self.calculate_sha256(file_path)
        file_size = file_path.stat().st_size

        if not force and self.store.report_exists(sha256):
            return {
                "status": "already_ingested",
                "sha256": sha256,
                "message": "Report has already been ingested. Use force=True to reprocess.",
            }

        # Parse PDF
        parser = InspectionReportParser(file_path)
        parsed_data = parser.parse()

        # Archive file permanently
        date_prefix = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
        archive_name = f"{date_prefix}_{sha256[:12]}.pdf"
        archive_dest = ARCHIVE_DIR / archive_name
        if file_path.resolve() != archive_dest.resolve():
            shutil.copy2(file_path, archive_dest)

        meta = parsed_data.get("metadata", {})

        # Insert report record
        report_id = self.store.insert_report(
            {
                "sha256_hash": sha256,
                "filename": archive_name,
                "source_url": source_url,
                "week_start": meta.get("week_start"),
                "week_end": meta.get("week_end"),
                "raw_title": meta.get("raw_title"),
                "amendment_notes": meta.get("amendment_notes"),
                "file_size": file_size,
                "archive_path": str(archive_dest),
                "total_establishments": parsed_data.get("total_establishments", 0),
                "total_inspections": parsed_data.get("total_inspections", 0),
            }
        )

        # Save Establishments, Permits, Inspections, and Violations
        saved_establishments = 0
        saved_inspections = 0
        saved_violations = 0
        new_closures = []

        # Map establishment slug to DB ID
        est_id_map = {}
        for slug, est in parsed_data["establishments"].items():
            est_id = self.store.upsert_establishment(est["name"], est["raw_address"])
            est_id_map[slug] = est_id
            saved_establishments += 1

            # Save permits
            for p_num, p_data in est.get("permits", {}).items():
                self.store.upsert_permit(
                    establishment_id=est_id,
                    permit_number=p_num,
                    permit_type=p_data.get("permit_type", ""),
                    operational_status=p_data.get("operational_status", "Open"),
                )

        # Save inspections and violations
        for insp in parsed_data["inspections"]:
            est_id = est_id_map[insp["establishment_slug"]]

            insp_id = self.store.upsert_inspection(
                {
                    "report_id": report_id,
                    "establishment_id": est_id,
                    "inspection_id_num": insp["inspection_id_num"],
                    "inspection_date": insp["inspection_date"],
                    "inspection_type": insp["inspection_type"],
                    "inspection_status": insp["inspection_status"],
                    "summary_page": insp.get("summary_page"),
                    "detail_page": insp.get("detail_page"),
                    "has_pest_violation": insp.get("has_pest_violation", False),
                    "has_critical_violation": insp.get("has_critical_violation", False),
                    "violation_count": insp.get("violation_count", 0),
                    "raw_summary_line": insp.get("raw_summary_line", ""),
                }
            )
            saved_inspections += 1

            if "closure" in insp["inspection_status"].lower():
                new_closures.append(
                    {
                        "name": insp["establishment_name"],
                        "address": insp["establishment_address"],
                        "status": insp["inspection_status"],
                        "date": insp["inspection_date"],
                    }
                )

            for v in insp.get("violations", []):
                self.store.insert_violation(
                    {
                        "inspection_id": insp_id,
                        "category": v.get("category", ""),
                        "item_title": v.get("item_title", ""),
                        "rule_description": v.get("rule_description", ""),
                        "observation": v.get("observation", ""),
                        "raw_text": v.get("raw_text", ""),
                        "is_pest": v.get("is_pest", False),
                    }
                )
                saved_violations += 1

        return {
            "status": "success",
            "report_id": report_id,
            "sha256": sha256,
            "archive_path": str(archive_dest),
            "week_range": meta.get("week_range_str"),
            "total_establishments": saved_establishments,
            "total_inspections": saved_inspections,
            "total_violations": saved_violations,
            "new_closures": new_closures,
        }

    def check_and_ingest(self, force: bool = False) -> Dict[str, Any]:  # noqa: FBT001, FBT002, UP006
        """
        Polls CABQ website, downloads current PDF, and ingests if new.
        """  # noqa: D200, D212
        temp_file = ARCHIVE_DIR / "latest_incoming.pdf"
        try:
            self.download_report(CABQ_INSPECTION_PDF_URL, temp_file)
            result = self.ingest_file(temp_file, source_url=CABQ_INSPECTION_PDF_URL, force=force)
            return result  # noqa: RET504
        finally:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
