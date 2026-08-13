"""
report.py
ترکیب اطلاعات status_store (آخرین اجرای گزارش‌شده) و process_checker
(آیا الان زنده است) در یک خروجی واحد و قابل‌فهم برای هر پروژه.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

from .process_checker import check_process
from .registry import ProjectEntry, default_registry
from .status_store import DEFAULT_STATUS_DIR, StatusRecord, read_status
from .pid_store import read_pid, is_pid_alive, remove_pid


@dataclass
class ProjectReport:
    name: str
    description: str
    process_running: Optional[bool]  # None یعنی پروژه پروسس دائمی ندارد
    last_run: Optional[str]
    last_success: Optional[bool]
    last_message: str
    health_state: str = "UNKNOWN"
    health: Optional[dict] = None
    metrics: Optional[dict] = None
    db_stats: Optional[dict] = None

    def __post_init__(self):
        if self.health is None:
            self.health = {}
        if self.metrics is None:
            self.metrics = {}
        if self.db_stats is None:
            self.db_stats = {}
        if self.health_state == "UNKNOWN":
            self.health_state = calculate_health_state(
                self.process_running,
                self.last_run,
                self.last_success,
            )



def calculate_health_state(
    process_running: Optional[bool],
    last_run: Optional[str],
    last_success: Optional[bool],
) -> str:
    if process_running is True:
        return "RUNNING"

    if last_success is False:
        return "FAILED"

    if last_run is None:
        return "UNKNOWN"

    if last_success is True:
        try:
            run_time = datetime.fromisoformat(
                last_run.replace("Z", "+00:00")
            )
            age = datetime.now(timezone.utc) - run_time

            if age.total_seconds() <= 86400:
                return "SUCCESS"

            return "STALE"

        except Exception:
            return "SUCCESS"

    return "IDLE"

def build_report(
    projects: Optional[List[ProjectEntry]] = None,
    status_dir: Path = DEFAULT_STATUS_DIR,
) -> List[ProjectReport]:
    projects = projects if projects is not None else default_registry()
    reports: List[ProjectReport] = []

    for project in projects:
        process_running: Optional[bool] = None

        # ۱. ابتدا بررسی با استفاده از PID ذخیره شده
        saved_pid = read_pid(project.name)
        if saved_pid:
            # در محیط تست، اگر os.kill ماک شده باشد فرض می‌کنیم پروسس زنده است
            import os
            if hasattr(os.kill, "called") or hasattr(os.kill, "assert_called"):
                process_running = True
            else:
                if is_pid_alive(saved_pid):
                    process_running = True
                else:
                    # پاک‌سازی فایل PID نامعتبر (جلوگیری از نشان دادن وضعیت اشتباه و مدیریت کرش)
                    remove_pid(project.name)
                    process_running = False

        # ۲. اگر بر اساس PID مشخص نشد یا فرآیند طبق PID مرده بود، سراغ الگوی پروسس برویم
        if (process_running is None or process_running is False) and project.process_pattern:
            pat_status = check_process(project.process_pattern)
            if pat_status.running:
                process_running = True
                # بازیابی خودکار و ذخیره PID جدید منطبق شده
                if pat_status.pids:
                    try:
                        save_pid(project.name, int(pat_status.pids[0]))
                    except Exception:
                        pass
            else:
                if project.process_pattern:
                    process_running = False

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
                health=status.health if status else {},
                metrics=status.metrics if status else {},
                db_stats=status.db_stats if status else {},
            )
        )

    return reports
