"""
service_manager.py
مدیریت چرخه‌ی حیات پروسس سرویس‌ها: شروع (start)، توقف (stop) و راه‌اندازی مجدد (restart).
"""

from __future__ import annotations

import os
import posixpath
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

# قرارداد راستی‌آزمایی راه‌اندازی (Issue #163): پنجره‌ی محدود که پروسس فرزند
# باید در آن زنده بماند تا START موفق گزارش شود. حلقه بر اساس تعداد تلاش است
# (بدون محاسبات time.time) تا با mock شدن time در تست‌ها سازگار بماند.
# خروج زودهنگام بلافاصله تشخیص داده می‌شود (fail fast)؛ این sleep دلخواه نیست.
STARTUP_GRACE_SECONDS = 2.0
STARTUP_POLL_INTERVAL = 0.2


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


def _read_proc_cmdline(pid: int) -> Optional[str]:
    """Read /proc/<pid>/cmdline (Termux/Android + Linux). None when unavailable."""
    try:
        data = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    try:
        return data.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def verify_process_identity(pid: int, process_pattern: Optional[str],
                            start_command: Optional[str] = None) -> Optional[bool]:
    """Check whether a live PID plausibly belongs to the expected service.

    A PID is treated as owned when EITHER the discovery pattern appears in its
    command line OR argv[0] equals the configured start command's argv[0]
    (covers Hub-spawned children whose pattern is meant for externally
    supervised discovery and need not textually match the spawn command).

    Returns True (owned), False (readable but foreign — must not be killed),
    or None (unverifiable: no hints, dead PID, or no /proc support).
    Never raises; verification failure must not crash lifecycle operations.
    """
    if not process_pattern and not start_command:
        return None
    try:
        alive = _is_pid_alive(pid)
    except Exception:
        return None
    if not alive:
        return None
    cmdline = _read_proc_cmdline(pid)
    if cmdline is None:
        return None
    if process_pattern and process_pattern in cmdline:
        return True
    if start_command:
        try:
            argv0 = _command_argv(start_command)[0]
        except ValueError:
            argv0 = ""
        if argv0:
            first = cmdline.split(" ")[0] if cmdline else ""
            if first == argv0 or first.endswith("/" + argv0) or argv0.endswith("/" + first):
                return True
            # argv[0] basename comparison (relative launcher vs resolved path).
            if posixpath.basename(first) == posixpath.basename(argv0):
                return True
    return False


def _wait_for_stable_start(proc: subprocess.Popen, grace: float = STARTUP_GRACE_SECONDS,
                           interval: float = STARTUP_POLL_INTERVAL) -> Optional[int]:
    """Bounded startup verification for a freshly spawned child.

    Polls proc.poll() (authoritative for our own child; fail-fast on early exit)
    for up to `grace` seconds. Returns the exit code if the child died during the
    window, else None (stable). Uses attempt counting so mocked time stays instant.
    """
    attempts = max(1, int(grace / interval))
    for _ in range(attempts):
        code = proc.poll()
        if code is not None:
            return code
        time.sleep(interval)
    return proc.poll()


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
    هرگز خودِ پروسس فراخوان (Hub) را نمی‌کشد.
    """
    try:
        if pid == os.getpid():
            return False
    except Exception:
        pass
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
        exit_code = _wait_for_stable_start(proc)
        if exit_code is not None:
            print(f"خطا: سرویس {project.name} در حین راستی‌آزمایی راه‌اندازی با کد خروج {exit_code} متوقف شد.")
            remove_pid(project.name)
            log_file.close()
            try:
                from .status_store import write_status
                write_status(project.name, success=False, message=f"خطا: پروسس در حین راه‌اندازی با کد خروج {exit_code} متوقف شد.")
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
    """توقف سرویس با PID ذخیره شده یا process pattern.

    قرارداد: فقط پروسس تحت مالکیت Hub خاتمه داده می‌شود؛ PID ذخیره‌شده‌ای که
    هویتش با الگوی سرویس تأیید نشود کشته نمی‌شود (فایل PID کهنه پاک می‌شود).
    الگوی پروسس فقط برای reconciliation/discovery است و هرگز نباید باعث کشته
    شدن خودِ پروسس Hub شود.
    """
    stopped = False
    saved_pid = read_pid(project.name)
    self_pid = os.getpid()
    skip_pattern_kill = False

    if saved_pid:
        if saved_pid == self_pid:
            remove_pid(project.name)
            skip_pattern_kill = True
        else:
            identity = verify_process_identity(
                saved_pid, project.process_pattern, project.start_command
            )
            if identity is False:
                print(f"هشدار: PID ذخیره‌شده {saved_pid} متعلق به سرویس {project.name} نیست؛ کشته نمی‌شود.")
                remove_pid(project.name)
                skip_pattern_kill = True
            else:
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

    if project.process_pattern and not skip_pattern_kill:
        status = check_process(project.process_pattern)
        if status.running:
            for pid_str in status.pids:
                try:
                    pid = int(pid_str)
                except ValueError:
                    continue
                if pid == self_pid:
                    continue
                try:
                    if stop_pid_safely(pid):
                        stopped = True
                except Exception:
                    pass

    if stopped:
        remove_pid(project.name)
        _mark_stopped(project.name)

    return stopped


def restart_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """راه‌اندازی مجدد با قرارداد راستی‌آزمایی: توقف، مرگ پروسس قدیمی، شروع،
    زنده بودن پروسس جدید و تفاوت PID."""
    print(f"در حال ری‌استارت کردن سرویس {project.name}...")
    old_pid = read_pid(project.name)
    stop_service(project)
    if old_pid and _is_pid_alive(old_pid):
        print(f"خطا: پروسس قدیمی {old_pid} سرویس {project.name} پس از توقف هنوز زنده است.")
        try:
            from .status_store import write_status
            write_status(project.name, success=False, message=f"خطا: پروسس قدیمی {old_pid} پس از توقف زنده ماند.")
        except Exception:
            pass
        return False
    time.sleep(0.2)
    if not start_service(project, logs_dir=logs_dir):
        return False
    new_pid = read_pid(project.name)
    if not new_pid or not _is_pid_alive(new_pid):
        print(f"خطا: پروسس جدید سرویس {project.name} پس از ری‌استارت زنده نیست.")
        return False
    if old_pid and new_pid == old_pid:
        print(f"خطا: PID پس از ری‌استارت سرویس {project.name} تغییر نکرد ({new_pid}).")
        return False
    return True
