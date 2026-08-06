"""
YasinHub lightweight API server
"""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

from ..report import build_report


class YasinHubHandler(BaseHTTPRequestHandler):

    def send_json(self, data):
        payload = json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ).encode("utf-8")

        self.send_response(200)
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


    def do_POST(self):

        if self.path.startswith("/api/control/"):

            parts = self.path.split("/")

            if len(parts) < 5:
                self.send_json({
                    "success": False,
                    "error": "invalid control path"
                })
                return

            service = parts[3]
            action = parts[4]

            from ..registry import default_registry
            from ..service_manager import (
                start_service,
                stop_service,
                restart_service,
            )

            projects = default_registry()

            project = next(
                (p for p in projects if p.name == service),
                None
            )

            if project is None:
                self.send_json({
                    "success": False,
                    "error": "service not found"
                })
                return

            if action == "start":
                result = start_service(project)

            elif action == "stop":
                result = stop_service(project)

            elif action == "restart":
                result = restart_service(project)

            else:
                self.send_json({
                    "success": False,
                    "error": "unknown action"
                })
                return


            self.send_json({
                "service": service,
                "action": action,
                "success": result
            })

            return


        self.send_response(404)
        self.end_headers()


    def do_GET(self):

        if self.path == "/api/health":
            self.send_json({
                "status": "ok",
                "service": "YasinHub"
            })
            return


        if self.path == "/api/dashboard":

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
                    summary["total_posts"] += r.db_stats.get(
                        "total_posts", 0
                    )
                    summary["published_posts"] += r.db_stats.get(
                        "published_posts", 0
                    )
                    summary["pending_posts"] += r.db_stats.get(
                        "pending_posts", 0
                    )

            self.send_json({
                "ecosystem": "Yasin",
                "dashboard": summary
            })
            return



        if self.path == "/api/status":

            reports = build_report()

            self.send_json({
                "ecosystem": "Yasin",
                "projects": [
                    {
                        "name": r.name,
                        "status": r.health_state,
                        "last_run": r.last_run,
                        "success": r.last_success,
                        "message": r.last_message,
                        "metrics": r.metrics,
                        "db_stats": r.db_stats,
                        "health": r.health,
                    }
                    for r in reports
                ]
            })
            return


        if self.path == "/api/services":

            from ..registry import default_registry

            services = []

            for p in default_registry():
                services.append({
                    "name": p.name,
                    "description": p.description,
                    "path": p.path,
                    "controls": [
                        "start",
                        "stop",
                        "restart"
                    ]
                })

            self.send_json({
                "ecosystem": "Yasin",
                "services": services
            })
            return



        if self.path.startswith("/api/logs/"):

            from urllib.parse import urlparse, parse_qs

            parsed = urlparse(self.path)
            service = parsed.path.split("/")[-1]

            try:
                max_lines = int(parse_qs(parsed.query).get("lines", ["100"])[0])
            except ValueError:
                max_lines = 100

            max_lines = max(10, min(max_lines, 1000))

            log_file = (
                Path.home()
                / ".yasinhub"
                / "logs"
                / f"{service}.log"
            )

            if log_file.exists():
                lines = log_file.read_text(
                    encoding="utf-8",
                    errors="ignore"
                ).splitlines()[-max_lines:]
            else:
                lines = []

            self.send_json({
                "service": service,
                "count": len(lines),
                "lines": lines
            })
            return




        if self.path.startswith("/api/metrics/"):

            service = self.path.split("/")[-1]

            from ..registry import default_registry

            projects = default_registry()

            project = next(
                (p for p in projects if p.name == service),
                None
            )

            if project is None:
                self.send_json({
                    "success": False,
                    "error": "service not found"
                })
                return

            data = {
                "service": service,
                "status": "UNKNOWN",
                "pid": None,
                "cpu": 0,
                "memory_mb": 0,
                "uptime": None,
                "metrics": {},
                "db_stats": {}
            }

            try:
                report = build_report()

                item = next(
                    (r for r in report if r.name == service),
                    None
                )

                if item:
                    data["status"] = item.health_state
                    data["metrics"] = item.metrics or {}
                    data["db_stats"] = item.db_stats or {}

            except Exception as e:
                data["error"] = str(e)

            self.send_json(data)
            return



        if self.path == "/api/events":

            events = []

            log_dir = Path.home() / ".yasinhub" / "logs"

            for log_file in log_dir.glob("*.log"):
                service = log_file.stem

                try:
                    lines = log_file.read_text(
                        encoding="utf-8",
                        errors="ignore"
                    ).splitlines()[-50:]

                    for line in reversed(lines):
                        for name in [
                            "ContentReceived",
                            "AIProcessingCompleted",
                            "PublishingCompleted",
                            "DuplicateDetected",
                            "ProcessingStarted",
                            "ERROR"
                        ]:
                            if name in line:
                                events.append({
                                    "service": service,
                                    "type": name,
                                    "message": line
                                })
                                break

                except Exception:
                    pass

            self.send_json({
                "count": len(events),
                "events": events[:50]
            })

            return


        if self.path == "/api/dashboard":

            dashboard = {
                "total_projects": 6,
                "running": 1,
                "published_posts": 0,
                "failed": 0
            }

            try:
                status_file = (
                    Path.home()
                    / ".yasin_status"
                    / "yasinrelay.json"
                )

                if status_file.exists():
                    import json

                    data = json.loads(
                        status_file.read_text(
                            encoding="utf-8"
                        )
                    )

                    dashboard["published_posts"] = (
                        data.get("published", 0)
                    )

            except Exception:
                pass


            self.send_json({
                "dashboard": dashboard
            })

            return


        # Static PWA Dashboard
        if self.path.startswith("/dashboard"):
            from urllib.parse import urlparse

            dashboard_root = Path(__file__).resolve().parents[2] / "dashboard"

            clean_path = urlparse(self.path).path

            request_path = clean_path.replace("/dashboard", "", 1)

            if request_path in ("", "/"):
                request_path = "/index.html"

            file_path = dashboard_root / unquote(request_path.lstrip("/"))

            if file_path.exists() and file_path.is_file():
                content = file_path.read_bytes()

                if file_path.suffix == ".html":
                    content_type = "text/html; charset=utf-8"
                elif file_path.suffix == ".css":
                    content_type = "text/css; charset=utf-8"
                elif file_path.suffix == ".js":
                    content_type = "application/javascript"
                elif file_path.suffix == ".json":
                    content_type = "application/json"
                else:
                    content_type = "application/octet-stream"

                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()

                self.wfile.write(content)
                return


        self.send_response(404)
        self.end_headers()



def run(host="0.0.0.0", port=8000):

    server = HTTPServer(
        (host, port),
        YasinHubHandler
    )

    print(
        f"YasinHub API running on {host}:{port}"
    )

    server.serve_forever()



if __name__ == "__main__":
    run()
