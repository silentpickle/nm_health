import argparse  # noqa: CPY001, D100, I001
import sys
import json  # noqa: F401
from datetime import datetime  # noqa: F401

from nm_health.config import DB_PATH, CABQ_INSPECTION_PDF_URL  # noqa: F401
from nm_health.commands import add_commands
from nm_health.db.local_store import LocalStore

# ANSI Colors for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"


def status_badge(status: str) -> str:  # noqa: D103
    s = status or "Unknown"
    lower = s.lower()
    if "closure" in lower or "unsatisfactory" in lower or "downgrade" in lower:
        return f"{RED}{BOLD}● {s}{RESET}"
    elif "conditional" in lower:  # noqa: RET505
        return f"{YELLOW}{BOLD}▲ {s}{RESET}"
    elif "approved" in lower:
        return f"{GREEN}{BOLD}✔ {s}{RESET}"
    return f"{DIM}{s}{RESET}"


def cmd_search(args):  # noqa: ANN001, ANN201
    """Search establishments by name, address, or violation keyword."""
    store = LocalStore()
    results = store.search_establishments(query=args.query, status=args.status or "", limit=args.limit)

    print(f"\n{BOLD}Search Results for:{RESET} '{args.query}' ({len(results)} found)\n")  # noqa: T201
    if not results:
        print(f"{DIM}No matching establishments found.{RESET}")  # noqa: T201
        return

    for est in results:
        badge = status_badge(est.get("latest_status"))
        pest_flag = f" {RED}{BOLD}[PEST HISTORY]{RESET}" if est.get("has_pest_history") else ""
        print(f"{BOLD}[ID: {est['id']}]{RESET} {BOLD}{est['name']}{RESET}{pest_flag}")  # noqa: T201
        print(f"   Address:        {est['normalized_address']} ({est['raw_address']})")  # noqa: T201
        print(f"   Latest Status:  {badge} (Last Inspection: {est.get('latest_inspection_date') or 'N/A'})")  # noqa: T201
        print(f"   Total History:  {est.get('total_inspections', 0)} inspections recorded")  # noqa: T201
        print(f"   Lookup command: nm-health lookup {est['id']}")  # noqa: T201
        print("-" * 70)  # noqa: T201


def cmd_lookup(args):  # noqa: ANN001, ANN201, PLR0912
    """Lookup detailed inspection history for a specific establishment."""
    store = LocalStore()
    est_id = None
    if args.target.isdigit():
        est_id = int(args.target)
    else:
        matches = store.search_establishments(query=args.target, limit=1)
        if matches:
            est_id = matches[0]["id"]

    if not est_id:
        print(f"{RED}Error:{RESET} Could not find establishment matching '{args.target}'")  # noqa: T201
        return

    detail = store.get_establishment_detail(est_id)
    if not detail:
        print(f"{RED}Error:{RESET} Establishment ID {est_id} not found.")  # noqa: T201
        return

    print("=" * 78)  # noqa: T201
    print(f"{BOLD}{detail['name']}{RESET}")  # noqa: T201
    print(f"Address:        {detail['normalized_address']} (Raw: {detail['raw_address']})")  # noqa: T201
    print(f"Latest Status:  {status_badge(detail.get('latest_status'))}")  # noqa: T201
    if detail.get("has_pest_history"):
        print(f"{RED}{BOLD}⚠ Warning: History of pest/rodent/insect violations on record.{RESET}")  # noqa: T201
    print("=" * 78)  # noqa: T201

    # Permits
    if detail.get("permits"):
        print(f"\n{CYAN}{BOLD}Permits:{RESET}")  # noqa: T201
        for p in detail["permits"]:
            print(f"  • Permit #{p['permit_number']}: {p['permit_type']} (Status: {p['operational_status']})")  # noqa: T201

    # Inspections History
    inspections = detail.get("inspections", [])
    print(f"\n{CYAN}{BOLD}Chronological Inspection History ({len(inspections)} records):{RESET}")  # noqa: T201
    for insp in inspections:
        badge = status_badge(insp["inspection_status"])
        print(f"\n  ┌─ {BOLD}{insp['inspection_date']}{RESET} | Status: {badge}")  # noqa: T201
        print(f"  │  ID: {insp['inspection_id_num']} | Type: {insp['inspection_type']}")  # noqa: T201
        if insp.get("report_filename"):
            dl_time = insp.get("report_downloaded_at") or "N/A"
            pg = insp.get("detail_page") or insp.get("summary_page") or 1
            h = (insp.get("report_sha256") or "")[:16]
            print(f"  │  Retained PDF:  {GREEN}{insp['report_filename']}{RESET} (Page #{pg})")  # noqa: T201
            print(f"  │  Downloaded At: {CYAN}{dl_time}{RESET} | SHA256: {DIM}{h}...{RESET}")  # noqa: T201
            print(f"  │  Report Week:   {insp.get('week_start')} to {insp.get('week_end')}")  # noqa: T201

        violations = insp.get("violations", [])
        if not violations:
            print(f"  └─ {GREEN}No violations recorded.{RESET}")  # noqa: T201
        else:
            print(f"  │  Violations ({len(violations)}):")  # noqa: T201
            for v in violations:
                is_pest = v.get("is_pest")
                pest_tag = f"{RED}{BOLD}[PEST WARNING]{RESET} " if is_pest else ""
                print(f"  │   • {pest_tag}{BOLD}{v['category']}{RESET}: {v['item_title']}")  # noqa: T201
                if v.get("observation"):
                    obs = v["observation"].replace("\n", " ")
                    print(f"  │     {DIM}Observation:{RESET} {obs}")  # noqa: T201
            print(f"  └─")  # noqa: F541, T201


def cmd_alerts(args):  # noqa: ANN001, ANN201
    """Show recent closures and downgrades."""
    store = LocalStore()
    alerts = store.get_recent_alerts(limit=args.limit)

    print(f"\n{RED}{BOLD}Recent Health Department Action Alerts ({len(alerts)} items):{RESET}\n")  # noqa: T201
    if not alerts:
        print(f"{GREEN}No recent closures or conditional actions found.{RESET}")  # noqa: T201
        return

    for item in alerts:
        badge = status_badge(item["inspection_status"])
        print(f"• {BOLD}{item['establishment_name']}{RESET} - {item['normalized_address']}")  # noqa: T201
        print(f"  Date: {item['inspection_date']} | Status: {badge} | Type: {item['inspection_type']}")  # noqa: T201
        for v in item.get("violations", []):
            if v.get("is_pest") or "closure" in item["inspection_status"].lower():
                print(f"  - {BOLD}{v['category']}:{RESET} {v.get('observation', '')[:140]}...")  # noqa: T201
        print("-" * 70)  # noqa: T201


def cmd_stats(args):  # noqa: ANN001, ANN201, ARG001
    """Display overall tracking database statistics."""
    store = LocalStore()
    stats = store.get_stats()

    print(f"\n{BOLD}NM Health Safety Tracking Statistics:{RESET}")  # noqa: T201
    print(f"  Total Ingested Reports:             {stats['total_reports']}")  # noqa: T201
    print(f"  Total Establishments Tracked:       {stats['total_establishments']}")  # noqa: T201
    print(f"  Total Inspections Recorded:         {stats['total_inspections']}")  # noqa: T201
    print(f"  Total Violations Logged:            {stats['total_violations']}")  # noqa: T201
    print(f"  Establishments with Pest History:   {RED}{stats['establishments_with_pest_violations']}{RESET}")  # noqa: T201
    print(f"  Total Closures / Stop-Orders:       {RED}{stats['total_closures']}{RESET}")  # noqa: T201
    print("\nStatus Breakdown:")  # noqa: T201
    for status, count in stats.get("status_breakdown", {}).items():
        print(f"  - {status:35s}: {count}")  # noqa: T201


def cmd_reports(args):  # noqa: ANN001, ANN201, ARG001
    """List all retained weekly PDF reports with download timestamps and integrity hashes."""
    store = LocalStore()
    reports = store.get_reports()

    print(f"\n{BOLD}Retained Weekly PDF Inspection Reports ({len(reports)} archived):{RESET}\n")  # noqa: T201
    if not reports:
        print(f"{DIM}No reports archived yet.{RESET}")  # noqa: T201
        return

    for rep in reports:
        print(f"• {BOLD}{rep['filename']}{RESET}")  # noqa: T201
        print(f"  Week Covered:    {rep['week_start']} to {rep['week_end']}")  # noqa: T201
        print(f"  Downloaded At:   {CYAN}{rep['downloaded_at']}{RESET}")  # noqa: T201
        print(f"  Establishments:  {rep['total_establishments']} | Inspections: {rep['total_inspections']}")  # noqa: T201
        print(f"  File Size:       {rep['file_size']:,} bytes")  # noqa: T201
        print(f"  SHA-256 Hash:    {DIM}{rep['sha256_hash']}{RESET}")  # noqa: T201
        print(f"  Local Archive:   {rep['archive_path']}")  # noqa: T201
        print("-" * 75)  # noqa: T201


def cmd_serve(args):  # noqa: ANN001, ANN201
    """Start local web dashboard."""
    from nm_health.web.server import run_server  # noqa: PLC0415

    run_server(host=args.host, port=args.port)


def main():  # noqa: ANN201, D103
    parser = argparse.ArgumentParser(
        prog="nm-health",
        description="Albuquerque & New Mexico Food Inspection Tracking & Lookup Service",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Search
    p_search = subparsers.add_parser("search", help="Search restaurants by name, address, or violation term")
    p_search.add_argument("query", type=str, help="Search query (e.g. 'California Del Norte', 'Central Ave', 'roach')")
    p_search.add_argument("--status", type=str, help="Filter by status (e.g. 'Closure', 'Conditional')")
    p_search.add_argument("--limit", type=int, default=20, help="Maximum results to return")
    p_search.set_defaults(func=cmd_search)

    # Lookup
    p_lookup = subparsers.add_parser("lookup", help="Lookup full inspection history for an establishment")
    p_lookup.add_argument("target", type=str, help="Establishment ID or name")
    p_lookup.set_defaults(func=cmd_lookup)

    # Alerts
    p_alerts = subparsers.add_parser("alerts", help="View recent closures and conditional approvals")
    p_alerts.add_argument("--limit", type=int, default=20, help="Number of alerts to show")
    p_alerts.set_defaults(func=cmd_alerts)

    # Reports
    p_reports = subparsers.add_parser("reports", help="List all retained weekly PDF reports with download dates")
    p_reports.set_defaults(func=cmd_reports)

    # Stats
    p_stats = subparsers.add_parser("stats", help="Display tracking database statistics")
    p_stats.set_defaults(func=cmd_stats)

    # Serve
    p_serve = subparsers.add_parser("serve", help="Start human-readable web dashboard")
    p_serve.add_argument("--host", type=str, default="127.0.0.1", help="Host interface")
    p_serve.add_argument("--port", type=int, default=8000, help="Port number")
    p_serve.set_defaults(func=cmd_serve)

    add_commands(subparsers)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
