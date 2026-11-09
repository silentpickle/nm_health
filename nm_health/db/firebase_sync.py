import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from nm_health.db.local_store import LocalStore
from nm_health.config import FIREBASE_PROJECT_ID, FIREBASE_CREDENTIALS_PATH

logger = logging.getLogger("nm_health.firebase")


class FirebaseSyncer:
    """
    Synchronizes Albuquerque food inspection data to Cloud Firestore.
    """

    def __init__(self, project_id: str = FIREBASE_PROJECT_ID, creds_path: Optional[str] = None):
        self.project_id = project_id
        self.creds_path = creds_path or FIREBASE_CREDENTIALS_PATH
        self._db = None

    def initialize_client(self):
        """Initializes firebase_admin or google-cloud-firestore if available."""
        if self._db is not None:
            return self._db

        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            if not firebase_admin._apps:
                if self.creds_path and os.path.exists(self.creds_path):
                    cred = credentials.Certificate(self.creds_path)
                    firebase_admin.initialize_app(cred, {"projectId": self.project_id})
                else:
                    firebase_admin.initialize_app(options={"projectId": self.project_id})

            self._db = firestore.client()
            return self._db
        except ImportError:
            logger.warning(
                "firebase-admin package is not installed. To sync to Firestore directly from Python, "
                "run: pip install firebase-admin"
            )
            return None
        except Exception as e:
            logger.error("Failed to initialize Firebase Admin client: %s", e)
            return None

    def export_firestore_json(self, store: LocalStore, output_file: Path) -> Path:
        """
        Exports all current establishments, inspections, and reports into a
        structured JSON file ready for batch import or Firestore seed.
        """
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        stats = store.get_stats()
        establishments = store.search_establishments(limit=10000)

        data = {
            "project_id": self.project_id,
            "stats": stats,
            "establishments": [],
        }

        for est in establishments:
            detail = store.get_establishment_detail(est["id"])
            if detail:
                data["establishments"].append(detail)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info("Exported %d establishments to %s", len(data["establishments"]), output_file)
        return output_file

    def sync_store(self, store: LocalStore) -> Dict[str, Any]:
        """
        Syncs local database records to Firestore.
        Falls back to JSON export if client is not configured.
        """
        client = self.initialize_client()
        if not client:
            json_path = store.db_path.parent / "firestore_export.json"
            exported = self.export_firestore_json(store, json_path)
            return {
                "status": "exported_json",
                "message": "Firebase Admin SDK client not initialized. Exported dataset to JSON.",
                "file": str(exported),
            }

        # Sync establishments
        establishments = store.search_establishments(limit=10000)
        synced_count = 0

        for est in establishments:
            detail = store.get_establishment_detail(est["id"])
            if not detail:
                continue

            est_ref = client.collection("establishments").document(detail["slug"])
            est_ref.set(
                {
                    "name": detail["name"],
                    "normalized_name": detail["normalized_name"],
                    "raw_address": detail["raw_address"],
                    "normalized_address": detail["normalized_address"],
                    "street_number": detail["street_number"],
                    "street_name": detail["street_name"],
                    "quadrant": detail["quadrant"],
                    "unit": detail["unit"],
                    "city": detail["city"],
                    "state": detail["state"],
                    "latest_status": detail["latest_status"],
                    "latest_inspection_date": detail["latest_inspection_date"],
                    "has_pest_history": bool(detail["has_pest_history"]),
                    "total_inspections": detail["total_inspections"],
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )

            # Sync inspections subcollection
            for insp in detail.get("inspections", []):
                insp_doc_id = f"{insp['inspection_id_num']}_{insp['inspection_date']}"
                insp_ref = est_ref.collection("inspections").document(insp_doc_id)
                insp_ref.set(
                    {
                        "inspection_id_num": insp["inspection_id_num"],
                        "inspection_date": insp["inspection_date"],
                        "inspection_type": insp["inspection_type"],
                        "inspection_status": insp["inspection_status"],
                        "has_pest_violation": bool(insp.get("has_pest_violation")),
                        "has_critical_violation": bool(insp.get("has_critical_violation")),
                        "violation_count": insp.get("violation_count", 0),
                        "violations": insp.get("violations", []),
                        "report_filename": insp.get("report_filename"),
                    },
                    merge=True,
                )

            synced_count += 1

        return {
            "status": "success",
            "synced_establishments": synced_count,
            "project_id": self.project_id,
        }
