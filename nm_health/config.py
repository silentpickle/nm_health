import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
DB_PATH = DATA_DIR / "nm_health.db"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# Albuquerque Environmental Health Department inspection report URL
CABQ_INSPECTION_PDF_URL = os.getenv(
    "CABQ_INSPECTION_PDF_URL",
    "https://www.cabq.gov/environmentalhealth/documents/chpd_main_inspection_report.pdf",
)

# Polling Interval (in seconds) - Default: once every 24 hours (86400 seconds)
DEFAULT_POLL_INTERVAL = int(os.getenv("NM_HEALTH_POLL_INTERVAL", "86400"))

# User-Agent for downloading city reports
HTTP_USER_AGENT = os.getenv(
    "NM_HEALTH_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 NMHealthSafetyBot/1.0",
)

# Firebase configuration
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "abq-food-inspections")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
