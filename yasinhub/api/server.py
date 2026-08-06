"""
YasinHub lightweight API server
"""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler

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
