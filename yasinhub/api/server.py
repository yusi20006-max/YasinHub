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

    def handle_control(self, clean_path: str) -> bool:
        if clean_path.startswith("/api/control/"):
            parts = clean_path.split("/")
            if len(parts) < 5:
                return False

            service = parts[3]
            action = parts[4]

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
                return True

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
                return True

            self.send_json({
                "service": service,
                "action": action,
                "success": result
            })
            return True
        return False

    def do_POST(self):
        parsed_url = urlparse(self.path)
        clean_path = parsed_url.path

        from .interface_routes import handle_interface_routes
        if handle_interface_routes(
            clean_path,
            "POST",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        from .control_routes import handle_control_api_routes
        if handle_control_api_routes(
            clean_path,
            "POST",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        if self.handle_control(clean_path):
            return

        from .integration_routes import handle_integration_routes
        if handle_integration_routes(
            clean_path,
            "POST",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        from .observer_routes import handle_execution_observer
        if handle_execution_observer(
            clean_path,
            "POST",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        from .slack_routes import handle_slack_routes
        if handle_slack_routes(
            clean_path,
            "POST",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        if clean_path in ("/api/events/cleanup", "/api/events/clear"):
            from ..events_engine import cleanup_events
            success = cleanup_events()
            self.send_json({
                "success": success,
                "message": "Event storage cleaned up successfully" if success else "Failed to clean up event storage"
            })
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)
        clean_path = parsed_url.path

        from .interface_routes import handle_interface_routes
        if handle_interface_routes(
            clean_path,
            "GET",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        from .control_routes import handle_control_api_routes
        if handle_control_api_routes(
            clean_path,
            "GET",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        if self.handle_control(clean_path):
            return

        from .integration_routes import handle_integration_routes
        if handle_integration_routes(
            clean_path,
            "GET",
            self.path,
            getattr(self, "headers", {}),
            getattr(self, "rfile", None),
            self.send_json,
        ):
            return

        from .observer_routes import handle_execution_observer
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

            self.send_json({
                "ecosystem": "Yasin",
                "dashboard": summary
            })
            return

        if clean_path == "/api/status":
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

        if clean_path == "/api/services":
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

        if clean_path.startswith("/api/logs/"):
            service = clean_path.split("/")[-1]

            query_params = parse_qs(parsed_url.query)
            try:
                max_lines = int(query_params.get("lines", ["100"])[0])
            except ValueError:
                max_lines = 100

            max_lines = max(10, min(max_lines, 1000))

            filter_term = query_params.get("filter", [None])[0]

            from ..config_manager import get_logs_dir
            log_dir = get_logs_dir()
            log_file = log_dir / f"{service}.log"

            if log_file.exists():
                all_lines = log_file.read_text(
                    encoding="utf-8",
                    errors="ignore"
                ).splitlines()

                if filter_term:
                    all_lines = [line for line in all_lines if filter_term.lower() in line.lower()]

                lines = all_lines[-max_lines:]
            else:
                lines = []

            self.send_json({
                "service": service,
                "count": len(lines),
                "lines": lines
            })
            return

        if clean_path.startswith("/api/metrics/"):
            service = clean_path.split("/")[-1]

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

            saved_pid = read_pid(service)
            if saved_pid and is_pid_alive(saved_pid):
                data["pid"] = saved_pid

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

        if clean_path in ("/api/events/cleanup", "/api/events/clear"):
            from ..events_engine import cleanup_events
            success = cleanup_events()
            self.send_json({
                "success": success,
                "message": "Event storage cleaned up successfully" if success else "Failed to clean up event storage"
            })
            return

        if clean_path == "/api/events":
            query_params = parse_qs(parsed_url.query)
            service = query_params.get("service", [None])[0]
            event_type = query_params.get("type", [None])[0] or query_params.get("event_type", [None])[0]
            severity = query_params.get("severity", [None])[0]
            level = query_params.get("level", [None])[0]
            limit_str = query_params.get("limit", [None])[0]

            try:
                limit = int(limit_str) if limit_str is not None else 50
            except ValueError:
                limit = 50

            from ..events_engine import parse_events_from_logs, filter_events
            all_events = parse_events_from_logs()
            filtered = filter_events(
                all_events,
                service=service,
                event_type=event_type,
                severity=severity,
                level=level,
                limit=limit
            )

            self.send_json({
                "count": len(filtered),
                "events": filtered
            })
            return

        if clean_path == "/dashboard":
            query = parsed_url.query
            redirect_target = "/dashboard/"
            if query:
                redirect_target += f"?{query}"
            self.send_response(301)
            self.send_header("Location", redirect_target)
            self.end_headers()
            return

        if clean_path.startswith("/dashboard/"):
            dashboard_root = Path(__file__).resolve().parents[2] / "dashboard"

            relative_path_str = clean_path[len("/dashboard/"):]
            if not relative_path_str or relative_path_str == "/":
                relative_path_str = "index.html"

            file_path = (dashboard_root / unquote(relative_path_str)).resolve()

            if file_path.is_relative_to(dashboard_root) and file_path.exists() and file_path.is_file():
                content = file_path.read_bytes()

                if file_path.suffix == ".html":
                    content_type = "text/html; charset=utf-8"
                elif file_path.suffix == ".css":
                    content_type = "text/css; charset=utf-8"
                elif file_path.suffix == ".js":
                    content_type = "application/javascript"
                elif file_path.suffix == ".json":
                    content_type = "application/json"
                elif file_path.suffix == ".png":
                    content_type = "image/png"
                elif file_path.suffix == ".svg":
                    content_type = "image/svg+xml"
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
