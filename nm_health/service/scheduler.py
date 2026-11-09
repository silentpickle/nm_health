import time
import logging
import sys
from datetime import datetime
from typing import Optional
from pathlib import Path

from nm_health.config import DATA_DIR, DEFAULT_POLL_INTERVAL
from nm_health.db.local_store import LocalStore
from nm_health.ingest.fetcher import ReportFetcher

# Setup logging
log_file = DATA_DIR / "scheduler.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("nm_health.scheduler")

def run_once(store: Optional[LocalStore] = None) -> dict:
    """Execute a single check against CABQ and ingest if updated."""
    store = store or LocalStore()
    fetcher = ReportFetcher(store)
    logger.info("Executing scheduled check of CABQ inspection report...")
    try:
        result = fetcher.check_and_ingest(force=False)
        if result.get("status") == "already_ingested":
            logger.info("CABQ inspection report unchanged (SHA256: %s).", result.get("sha256"))
        elif result.get("status") == "success":
            logger.info(
                "Ingested NEW report %s (Week: %s). Establishments: %d, Inspections: %d, Violations: %d, Closures: %d",
                result.get("report_id"),
                result.get("week_range"),
                result.get("total_establishments"),
                result.get("total_inspections"),
                result.get("total_violations"),
                len(result.get("new_closures", [])),
            )
        return result
    except Exception as e:
        logger.error("Failed during scheduled ingestion check: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}

def run_daemon(interval: int = DEFAULT_POLL_INTERVAL):
    """
    Runs a continuous background loop, sleeping for `interval` seconds between checks.
    Defaults to 86,400s (24 hours).
    """
    logger.info("Starting NM Health Ingestion Daemon (Poll Interval: %d seconds / %.1f hours)...", interval, interval / 3600.0)
    store = LocalStore()

    while True:
        try:
            run_once(store)
        except Exception as e:
            logger.error("Unexpected error in daemon loop: %s", e)
        
        logger.info("Sleeping for %d seconds until next check...", interval)
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("NM Health Ingestion Daemon stopped by user.")
            break
