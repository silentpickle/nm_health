import http.server  # noqa: CPY001, D100, I001, INP001
import socketserver
import json
import urllib.parse
from pathlib import Path
from typing import Optional  # noqa: F401

from nm_health.db.local_store import LocalStore
from nm_health.config import ARCHIVE_DIR

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"


class HealthAppHandler(http.server.SimpleHTTPRequestHandler):  # noqa: D101
    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN204, D107
        self.store = LocalStore()
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):  # noqa: ANN201, D102, PLR0911
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # API Routes
        if path == "/api/search":
            q = params.get("q", [""])[0]
            status = params.get("status", [""])[0]
            limit = int(params.get("limit", [50])[0])
            results = self.store.search_establishments(query=q, status=status, limit=limit)
            self._send_json(results)
            return

        elif path.startswith("/api/establishments/"):  # noqa: RET505
            est_id_str = path[len("/api/establishments/") :]
            if est_id_str.isdigit():
                detail = self.store.get_establishment_detail(int(est_id_str))
                if detail:
                    self._send_json(detail)
                    return
            self._send_json({"error": "Establishment not found"}, status=404)
            return

        elif path == "/api/alerts":
            limit = int(params.get("limit", [20])[0])
            alerts = self.store.get_recent_alerts(limit=limit)
            self._send_json(alerts)
            return

        elif path == "/api/stats":
            stats = self.store.get_stats()
            self._send_json(stats)
            return

        elif path == "/api/reports":
            reports = self.store.get_reports()
            self._send_json(reports)
            return

        elif path.startswith("/api/pdf/"):
            filename = urllib.parse.unquote(path[len("/api/pdf/") :])
            pdf_path = (ARCHIVE_DIR / filename).resolve()
            # Ensure within ARCHIVE_DIR
            if pdf_path.exists() and ARCHIVE_DIR.resolve() in pdf_path.parents:
                is_download = params.get("download", ["0"])[0].lower() in ["1", "true", "yes"]
                disp_type = "attachment" if is_download else "inline"
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'{disp_type}; filename="{filename}"')
                self.send_header("Content-Length", str(pdf_path.stat().st_size))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(pdf_path, "rb") as f:  # noqa: PTH123
                    self.wfile.write(f.read())
                return
            self._send_json({"error": "PDF file not found"}, status=404)
            return

        # Serve SPA static files (fallback to index.html if not found)
        super().do_GET()

    def _send_json(self, data, status=200):  # noqa: ANN001, ANN202
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8000):  # noqa: ANN201, D103
    server_address = (host, port)
    # Enable address reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(server_address, HealthAppHandler) as httpd:
        print(f"\n=======================================================")  # noqa: F541, T201
        print(f"  NM Health Inspection Tracker & Search Dashboard")  # noqa: F541, T201
        print(f"  Running locally at: http://{host}:{port}")  # noqa: T201
        print(f"  Press Ctrl+C to stop.")  # noqa: F541, T201
        print(f"=======================================================\n")  # noqa: F541, T201
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")  # noqa: T201
