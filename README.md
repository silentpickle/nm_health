# NM Food Safety Watch (Albuquerque Restaurant Inspection Tracker)

An automated ingestion, archival, and lookup service for the City of Albuquerque Environmental Health Department's weekly food inspection reports.

---

## The Problem

The City of Albuquerque publishes restaurant inspection grades as a single weekly PDF (`chpd_main_inspection_report.pdf`). When each new report is published, the previous week's PDF is overwritten.

Because of this:
- **No historical memory**: There is no official multi-week history available to the public.
- **Hidden violations**: If a restaurant is shut down or cited for critical health hazards (such as cockroach/rodent infestations, improper food temperatures, or sewage backups), the incident vanishes from the public report once the next week's report is published or the facility passes a re-inspection.

**NM Food Safety Watch** solves this by:
1. **Automated Daily Monitoring**: Automatically polling the CABQ inspection URL once a day.
2. **Permanent Archival**: Calculating SHA-256 checksums and archiving every distinct weekly report PDF into `data/archive/` for posterity.
3. **Structured Ingestion**: Parsing summary tables and detailed inspector observations (including specific pest types, temperatures, and location notes).
4. **Address-Normalized Database**: Standardizing Albuquerque street names, quadrants (`NE`, `NW`, `SE`, `SW`), and unit numbers to link historical inspections to the same physical location over time.
5. **Human-Readable Lookups**:
   - **CLI**: Instant terminal search, inspection timeline lookup, statistics, and alert feeds.
   - **Web Dashboard**: Modern, responsive dashboard with live search, status badges, and expandable violation observations.
   - **Firebase Integration**: Built-in support for Cloud Firestore and Firebase Hosting in the `abq-food-inspections` project.

---

## Quick Start

### 1. Install & Setup
```bash
# Clone and enter directory
cd nm_health

# Install locally in editable mode (creates 'nm-health' CLI tool)
pip3 install -e .
```

Prerequisites:
- `pdftotext` (part of `poppler`, already installed on macOS via `brew install poppler`).

---

## Command Line Interface (CLI)

```bash
# Ingest current live report from CABQ or a local test PDF
nm-health ingest --file sample_inspection_report.pdf

# Search by restaurant name, address, or violation keyword (e.g., pests, foods)
nm-health search "cockroach"
nm-health search "California Del Norte"
nm-health search "Central Ave"

# Detailed chronological inspection history lookup (by ID or name)
nm-health lookup 39
nm-health lookup "California Del Norte"

# View recent enforcement alerts (closures, conditional approvals, downgrades)
nm-health alerts

# Display tracking statistics
nm-health stats

# Launch the local web dashboard
nm-health serve --port 8000

# Run continuous background daily polling daemon (default: 86400s / 24h)
nm-health daemon --interval 86400
```

---

## Web Dashboard

Start the web dashboard:
```bash
nm-health serve --port 8000
```
Then visit `http://127.0.0.1:8000` in your browser.

Features:
- **Instant Search**: Type any restaurant name, street address, or violation term (e.g. `mice`, `cockroach`, `ranch`, `tacos`, `Central Ave`).
- **Status Badges**:
  - 🟢 **Approved**: Passing inspection.
  - 🟡 **Conditional Approved**: Violations found; corrective action required.
  - 🔴 **Closure / Unsatisfactory**: Facility closed or re-inspection ordered.
- **Pest Warning Flags**: Highlights any facility with past rodent, vermin, or insect citations.
- **Detailed History Modal**: Full chronological inspection timeline with exact inspector observation notes and direct links to original archived PDFs.
- **Recent Action Alerts**: Slide-out feed of the latest closures and urgent actions.

---

## Automated Daily Ingestion Service

You can run the ingestion checker in several ways:

### Option A: Built-in Daemon
```bash
nm-health daemon --interval 86400
```
Runs continuously in the background, waking once every 24 hours to check for new reports.

### Option B: System Cron
Add this entry to your crontab (`crontab -e`) to check every morning at 6:00 AM:
```cron
0 6 * * * /usr/local/bin/python3 -m nm_health ingest >> /path/to/nm_health/data/cron.log 2>&1
```

---

## Firebase Integration (Cloud Firestore & Hosting)

A dedicated Firebase project has been created:
- **Project ID**: `abq-food-inspections`
- **Console**: [https://console.firebase.google.com/project/abq-food-inspections/overview](https://console.firebase.google.com/project/abq-food-inspections/overview)

### Setup Steps:
1. Open the [Firebase Console Firestore tab](https://console.firebase.google.com/project/abq-food-inspections/firestore) and click **Create Database** (e.g. location `nam5` or `us-central1`).
2. Deploy Firestore Security Rules & Hosting:
   ```bash
   npx -y firebase-tools@latest deploy --project=abq-food-inspections
   ```
3. Sync local data to Firestore:
   ```bash
   pip3 install firebase-admin
   python3 -c "from nm_health.db.local_store import LocalStore; from nm_health.db.firebase_sync import FirebaseSyncer; syncer = FirebaseSyncer(project_id='abq-food-inspections'); syncer.sync_store(LocalStore())"
   ```

---

## Database Architecture

- `reports`: Tracks each downloaded weekly PDF (SHA-256 hash, week range, file size, archive path).
- `establishments`: Normalized restaurant entities (Name, normalized street address, quadrant, unit, latest status, pest history flag).
- `permits`: Food establishment permits linked to locations.
- `inspections`: Individual inspection events with status, date, type, report page numbers, and critical violation flags.
- `violations`: Individual inspector findings (category, code item, legal requirement, and raw inspector observations).
- `establishments_fts` & `violations_fts`: SQLite FTS5 full-text indices for sub-millisecond keyword queries across all historical notes.
