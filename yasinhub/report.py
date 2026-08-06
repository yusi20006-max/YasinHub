"""
report.py
ترکیب اطلاعات status_store (آخرین اجرای گزارش‌شده) و process_checker
(آیا الان زنده است) در یک خروجی واحد و قابل‌فهم برای هر پروژه.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .process_checker import check_process
from .registry import ProjectEntry, default_registry
from .status_store import DEFAULT_STATUS_DIR, StatusRecord, read_status


@dataclass
class ProjectReport:
    name: str
    description: str
    process_running: Optional[bool]  # None یعنی پروژه پروسس دائمی ندارد
    last_run: Optional[str]
    last_success: Optional[bool]
    last_message: str
    health_state: str



def calculate_health_state(
    process_running: Optional[bool],
    last_run: Optional[str],
    last_success: Optional[bool],
) -> str:
    if process_running is True:
        return "RUNNING"

    if last_success is False:
        return "FAILED"

    if last_success is True:
        return "SUCCESS"

    if last_run is None:
        return "UNKNOWN"

    return "IDLE"

def build_report(
    projects: Optional[List[ProjectEntry]] = None,
    status_dir: Path = DEFAULT_STATUS_DIR,
) -> List[ProjectReport]:
    projects = projects if projects is not None else default_registry()
    reports: List[ProjectReport] = []

    for project in projects:
        process_running: Optional[bool] = None
        if project.process_pattern:
            process_running = check_process(project.process_pattern).running

        status: Optional[StatusRecord] = read_status(project.name, status_dir=status_dir)

        reports.append(
            ProjectReport(
                name=project.name,
                description=project.description,
                process_running=process_running,
                last_run=status.last_run if status else None,
                last_success=status.success if status else None,
                last_message=status.message if status else "",
                health_state=calculate_health_state(
                    process_running,
                    status.last_run if status else None,
                    status.success if status else None,
                ),
            )
        )

    return reports
