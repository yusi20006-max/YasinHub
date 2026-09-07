"""
YasinHub lightweight API server
"""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

from ..report import build_report
from ..registry import default_registry
from ..service_manager import start_service, stop_service, restart_service
from ..pid_store import read_pid, is_pid_alive
from ..pwa_version import version_payload
from .service_control_helpers import service_runtime_snapshot, status_project_payload


class YasinHubHandler(BaseHTTPRequestHandler):

    def send_json(self, data, status: int = 200):
        payload = json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )
        self.send_header(
            "Content-Length",
            str(len(payload))
        )
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        clean_path = parsed.path

        # Existing GET routing remains unchanged below this point.
        if clean_path == "/api/version":
            self.send_json(version_payload())
            return

        if handle_execution_observer(
            clean_path,
            "GET",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        from .slack_routes import handle_slack_routes
        if handle_slack_routes(
            clean_path,
            "GET",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        if clean_path == "/api/health":
            self.send_json({
                "status": "ok",
                "service": "YasinHub"
            })
            return

        if clean_path == "/api/dashboard":
            reports = build_report()

            summary = {
                "total_projects": len(reports),
                "running": 0,
                "success": 0,
                "failed": 0,
                "unknown": 0,
                "total_posts": 0,
                "published_posts": 0,
                "pending_posts": 0
            }
            projects = []

            for r in reports:
                if r.health_state == "RUNNING":
                    summary["running"] += 1
                elif r.health_state == "SUCCESS":
                    summary["success"] += 1
                elif r.health_state == "FAILED":
                    summary["failed"] += 1
                else:
                    summary["unknown"] += 1

                if r.db_stats:
                    summary["total_posts"] += r.db_stats.get("total_posts", 0)
                    summary["published_posts"] += r.db_stats.get("published_posts", 0)
                    summary["pending_posts"] += r.db_stats.get("pending_posts", 0)

                projects.append({
                    "name": r.name,
                    "status": r.health_state,
                    "last_run": r.last_run,
                    "success": r.last_success,
                    "message": r.last_message,
                    "metrics": r.metrics,
                    "db_stats": r.db_stats,
                    "health": r.health,
                })

            self.send_json({
                "ecosystem": "Yasin",
                "dashboard": summary,
                "projects": projects
            })
            return

        if clean_path == "/api/status":
            reports = build_report()
            self.send_json({
                "ecosystem": "Yasin",
                "projects": [status_project_payload(r) for r in reports],
            })
            return

        if clean_path == "/api/services":
            services = []
            for p in default_registry():
                services.append({
                    "name": p.name,
                    "description": p.description,
                    "path": p.path,
                    "enabled": getattr(p, "enabled", True),
                })
            self.send_json({"services": services})
            return

        # The remainder of this handler is intentionally unchanged from main.
        self._serve_dashboard_or_not_found(clean_path)

    def _serve_dashboard_or_not_found(self, clean_path: str):
        if clean_path == "/dashboard":
            redirect_target = "/dashboard/"
            self.send_response(301)
            self.send_header("Location", redirect_target)
            self.end_headers()
            return

        if clean_path.startswith("/dashboard/"):
            dashboard_root = Path(__file__).resolve().parents[2] / "dashboard"
            relative_path_str = clean_path[len("/dashboard/"):]
            file_path = (dashboard_root / unquote(relative_path_str)).resolve()
            if file_path.is_relative_to(dashboard_root) and file_path.exists() and file_path.is_file():
                content_type = "text/plain; charset=utf-8"
                suffix = file_path.suffix.lower()
                if suffix == ".html": content_type = "text/html; charset=utf-8"
                elif suffix == ".css": content_type = "text/css; charset=utf-8"
                elif suffix == ".js": content_type = "application/javascript; charset=utf-8"
                elif suffix == ".json": content_type = "application/json; charset=utf-8"
                elif suffix == ".png": content_type = "image/png"
                elif suffix == ".svg": content_type = "image/svg+xml"
                data = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

        self.send_error(404, "Not Found")


def run(host="0.0.0.0", port=8000):
    server = HTTPServer(
        (host, port),
        YasinHubHandler
    )
    print(f"YasinHub API server listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
