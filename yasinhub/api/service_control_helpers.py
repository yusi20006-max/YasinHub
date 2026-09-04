"""Helpers for service control responses (Phase 4)."""

from __future__ import annotations

from typing import Any, Dict

from ..pid_store import is_pid_alive, read_pid
from ..report import build_report


def service_runtime_snapshot(service: str) -> Dict[str, Any]:
    """Authoritative PID + health for a single service after control ops."""
    reports = build_report()
    report = next((r for r in reports if r.name == service), None)
    pid = read_pid(service)
    if pid is not None and not is_pid_alive(pid):
        pid = None
    if report is None:
        return {
            "status": "UNKNOWN",
            "pid": pid,
            "message": "",
            "process_running": None,
            "last_run": None,
            "success": None,
        }
    return {
        "status": report.health_state,
        "pid": pid,
        "message": report.last_message or "",
        "process_running": report.process_running,
        "last_run": report.last_run,
        "success": report.last_success,
    }


def status_project_payload(report) -> Dict[str, Any]:
    pid = read_pid(report.name)
    if pid is not None and not is_pid_alive(pid):
        pid = None
    return {
        "name": report.name,
        "status": report.health_state,
        "last_run": report.last_run,
        "success": report.last_success,
        "message": report.last_message,
        "metrics": report.metrics,
        "db_stats": report.db_stats,
        "health": report.health,
        "pid": pid,
        "process_running": report.process_running,
    }
