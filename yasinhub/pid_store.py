"""
yasinhub/pid_store.py
مدیریت و ذخیره‌سازی شناسه پروسس‌ها (PID) برای مانیتورینگ و توقف سرویس‌ها.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

def get_pid_dir() -> Path:
    """دریافت مسیر دایرکتوری ذخیره‌سازی PIDها"""
    pid_dir = Path.home() / ".yasinhub" / "pids"
    pid_dir.mkdir(parents=True, exist_ok=True)
    return pid_dir

def save_pid(project_name: str, pid: int) -> None:
    """ذخیره PID یک پروژه"""
    pid_file = get_pid_dir() / f"{project_name}.pid"
    pid_file.write_text(str(pid), encoding="utf-8")

def read_pid(project_name: str) -> Optional[int]:
    """خواندن PID ذخیره شده برای یک پروژه"""
    pid_file = get_pid_dir() / f"{project_name}.pid"
    if pid_file.exists():
        try:
            return int(pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            return None
    return None

def remove_pid(project_name: str) -> None:
    """حذف فایل PID مربوط به یک پروژه"""
    pid_file = get_pid_dir() / f"{project_name}.pid"
    if pid_file.exists():
        try:
            pid_file.unlink()
        except OSError:
            pass

def is_pid_alive(pid: int) -> bool:
    """بررسی زنده بودن یک پروسس بر اساس PID"""
    if pid <= 0:
        return False

    # ابتدا اگر فرزند پروسس جاری باشد، وضعیت آن را می‌خوانیم تا از زامبی ماندن آن جلوگیری شود.
    try:
        pid_reaped, _ = os.waitpid(pid, os.WNOHANG)
        if pid_reaped == pid:
            return False
    except ChildProcessError:
        # پروسس جاری والد این PID نیست، پس روال عادی را ادامه می‌دهیم.
        pass
    except OSError:
        pass

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as e:
        import errno
        if e.errno == errno.ESRCH:
            return False
        elif e.errno == errno.EPERM:
            return True
        return False
    return True
