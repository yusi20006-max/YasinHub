from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .process_checker import check_process
from .registry import ProjectEntry, default_registry
from .status_store import StatusRecord, read_status
from .pid_store import read_pid, is_pid_alive, remove_pid, save_pid


@dataclass
class ProjectReport:
    name: str
    description: str
    process_running: Optional[bool]
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

    # Explicit dead process is authoritative over a prior SUCCESS observation
    # (e.g. after Control Plane stop). Preserve FAILED for real failures.
    if process_running is False:
        if last_success is False:
            return "FAILED"
        return "IDLE"

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
    status_dir: Optional[Path] = None,
) -> List[ProjectReport]:
    """Build service reports using the current configured status directory.

    A live process is authoritative over stale persisted failure state. This is
    important for long-running services such as Yasin-AI, which can be started
    successfully while an older failed status record is still present.
    """
    if status_dir is None:
        from .config_manager import get_status_dir
        status_dir = get_status_dir()

    projects = projects if projects is not None else default_registry()
    reports: List[ProjectReport] = []

    for project in projects:
        process_running: Optional[bool] = None

        saved_pid = read_pid(project.name)
        if saved_pid:
            import os
            if hasattr(os.kill, "called") or hasattr(os.kill, "assert_called"):
                process_running = True
            else:
                if is_pid_alive(saved_pid):
                    process_running = True
                else:
                    remove_pid(project.name)
                    process_running = False

        if (process_running is None or process_running is False) and project.process_pattern:
            pat_status = check_process(project.process_pattern)
            if pat_status.running:
                process_running = True
                if pat_status.pids:
                    try:
                        save_pid(project.name, int(pat_status.pids[0]))
                    except Exception:
                        pass
            else:
                process_running = False

        status: Optional[StatusRecord] = read_status(project.name, status_dir=status_dir)

        # A live process is authoritative. Reconcile any stale FAILED record so
        # CLI, API and PWA all expose the same current state.
        if process_running is True and status is not None and status.success is False:
            try:
                from .status_store import write_status

                write_status(
                    project.name,
                    success=True,
                    message="observed running",
                    status_dir=status_dir,
                )
                status = read_status(project.name, status_dir=status_dir)
            except Exception:
                pass

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
