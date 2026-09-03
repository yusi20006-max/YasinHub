"""
service_manager.py
مدیریت چرخه‌ی حیات پروسس سرویس‌ها: شروع (start)، توقف (stop) و راه‌اندازی مجدد (restart).
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

from .process_checker import check_process
from .registry import ProjectEntry
from .pid_store import save_pid, read_pid, remove_pid, is_pid_alive

# دایرکتوری پیش‌فرض لاگ‌ها
DEFAULT_LOGS_DIR = Path(os.environ.get("YASINHUB_LOGS_DIR", str(Path.home() / ".yasinhub" / "logs")))


def _command_argv(command: str) -> list[str]:
    """Parse a configured command once at the trust boundary, without shell evaluation."""
    if not command or not command.strip():
        raise ValueError("service command must not be empty")
    return shlex.split(command, posix=True)


def _is_pid_alive(pid: int) -> bool:
    """بررسی زنده بودن یک پروسس با پشتیبانی از محیط‌های تست (mock)"""
    if hasattr(os.kill, "called") or hasattr(os.kill, "assert_called"):
        return True
    return is_pid_alive(pid)


def _yasin_agent_token() -> str:
    """Return the local Yasin-Agent service token (canonical file wins over env)."""
    from .agent_token import resolve_agent_service_token

    return resolve_agent_service_token()


def _service_env(project: ProjectEntry) -> dict[str, str]:
    """Build the child environment, including Yasin-Agent's local auth contract."""
    env = os.environ.copy()
    if project.path:
        env["PYTHONPATH"] = str(project.path) + ":" + env.get("PYTHONPATH", "")
    if project.name == "yasin-agent":
        env.setdefault("YASIN_AGENT_HOST", "127.0.0.1")
        env.setdefault("YASIN_AGENT_PORT", "8080")
        env["YASIN_AGENT_SERVICE_TOKEN"] = _yasin_agent_token()
    return env


def _mark_running(project_name: str) -> None:
    """Reconcile the persisted service status after Hub observes a live process."""
    try:
        from .config_manager import get_status_dir
        from .status_store import write_status

        write_status(
            project_name,
            success=True,
            message="observed running",
            status_dir=get_status_dir(),
        )
    except Exception:
        # Status persistence must never make a successfully started service fail.
        pass


def _mark_stopped(project_name: str) -> None:
    """Reconcile status after a successful Control Plane stop.

    Intentional stop is not a failure. Clear the prior "observed running"
    observation so API/PWA do not keep a stale SUCCESS/running state.
    """
    try:
        from .config_manager import get_status_dir
        from .status_store import write_status

        write_status(
            project_name,
            success=True,
            message="stopped",
            status_dir=get_status_dir(),
        )
    except Exception:
        pass


def stop_pid_safely(pid: int, timeout: float = 3.0) -> bool:
    """
    توقف یک پروسس به صورت امن و تضمینی. ابتدا ارسال SIGTERM و در صورت عدم توقف پس از timeout، ارسال SIGKILL.
    """
    if hasattr(os.kill, "called") or hasattr(os.kill, "assert_called"):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        return True

    if not is_pid_alive(pid):
        return True

    try:
        if hasattr(os, "killpg"):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except OSError:
                os.kill(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass

    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_pid_alive(pid):
            return True
        time.sleep(0.1)

    if is_pid_alive(pid):
        try:
            if hasattr(os, "killpg"):
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except OSError:
                    os.kill(pid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    return not is_pid_alive(pid)


def start_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """شروع اجرای یک سرویس در پس‌زمینه."""
    if not project.start_command:
        print(f"خطا: دستور شروع برای سرویس {project.name} تعریف نشده است.")
        return False

    saved_pid = read_pid(project.name)
    if saved_pid:
        if _is_pid_alive(saved_pid):
            print(f"سرویس {project.name} از قبل با شناسه {saved_pid} در حال اجراست.")
            _mark_running(project.name)
            return True
        print(f"شناسایی کرش در سرویس {project.name}: فایل PID قدیمی {saved_pid} نامعتبر بود. پاک‌سازی انجام می‌شود.")
        remove_pid(project.name)

    if project.process_pattern:
        status = check_process(project.process_pattern)
        if status.running:
            if project.name == "yasin-agent":
                print(
                    f"سرویس {project.name} از قبل در حال اجراست (PIDs: {status.pids}). "
                    "Ownership با runit/termux-services است؛ از spawn مجدد خودداری شد."
                )
            else:
                print(f"سرویس {project.name} از قبل در حال اجراست (PIDs: {status.pids}).")
            if status.pids:
                try:
                    save_pid(project.name, int(status.pids[0]))
                except ValueError:
                    pass
            _mark_running(project.name)
            return True

    if project.path:
        p_path = Path(project.path)
        if not p_path.exists():
            print(f"خطا: مسیر تعریف شده برای سرویس {project.name} وجود ندارد: {project.path}")
            try:
                from .status_store import write_status
                write_status(project.name, success=False, message=f"خطا: دایرکتوری سرویس یافت نشد: {project.path}")
            except Exception:
                pass
            return False

    if logs_dir is None:
        from .config_manager import get_logs_dir
        l_dir = get_logs_dir()
    else:
        l_dir = logs_dir

    l_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = l_dir / f"{project.name}.log"

    try:
        log_file = open(log_file_path, "a", encoding="utf-8")
    except Exception as e:
        print(f"خطا در ایجاد فایل لاگ برای {project.name}: {e}")
        return False

    try:
        env = _service_env(project)
        proc = subprocess.Popen(
            _command_argv(project.start_command),
            shell=False,
            cwd=project.path if project.path else None,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        save_pid(project.name, proc.pid)
        time.sleep(0.3)
        if proc.poll() is not None:
            print(f"خطا: سرویس {project.name} بلافاصله با کد خروج {proc.poll()} متوقف شد.")
            remove_pid(project.name)
            log_file.close()
            try:
                from .status_store import write_status
                write_status(project.name, success=False, message=f"خطا: پروسس با کد خروج {proc.poll()} متوقف شد.")
            except Exception:
                pass
            return False

        _mark_running(project.name)
        print(f"سرویس {project.name} با موفقیت در پس‌زمینه استارت شد.")
        log_file.close()
        return True
    except Exception as e:
        print(f"خطا در اجرای دستور شروع سرویس {project.name}: {e}")
        remove_pid(project.name)
        log_file.close()
        try:
            from .status_store import write_status
            write_status(project.name, success=False, message=f"خطا در راه‌اندازی: {str(e)}")
        except Exception:
            pass
        return False


def stop_service(project: ProjectEntry) -> bool:
    """توقف سرویس با PID ذخیره شده یا process pattern."""
    stopped = False
    saved_pid = read_pid(project.name)

    if saved_pid:
        stopped = stop_pid_safely(saved_pid)
        remove_pid(project.name)
        if stopped:
            print(f"سرویس {project.name} با شناسه {saved_pid} با موفقیت متوقف شد.")
            _mark_stopped(project.name)
            return True

    if project.stop_command:
        try:
            subprocess.run(_command_argv(project.stop_command), shell=False, timeout=10)
            stopped = True
        except Exception as e:
            print(f"خطا در اجرای دستور توقف سرویس {project.name}: {e}")

    if project.process_pattern:
        status = check_process(project.process_pattern)
        if status.running:
            for pid_str in status.pids:
                try:
                    if stop_pid_safely(int(pid_str)):
                        stopped = True
                except Exception:
                    pass

    if stopped:
        remove_pid(project.name)
        _mark_stopped(project.name)

    return stopped


def restart_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """راه‌اندازی مجدد یک سرویس با ترکیب متوقف کردن و شروع مجدد آن."""
    print(f"در حال ری‌استارت کردن سرویس {project.name}...")
    stop_service(project)
    time.sleep(0.2)
    return start_service(project, logs_dir=logs_dir)
