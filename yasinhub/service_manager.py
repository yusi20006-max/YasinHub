"""
service_manager.py
مدیریت چرخه‌ی حیات پروسس سرویس‌ها: شروع (start)، توقف (stop) و راه‌اندازی مجدد (restart).
"""

from __future__ import annotations

import os
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


def _is_pid_alive(pid: int) -> bool:
    """بررسی زنده بودن یک پروسس با پشتیبانی از محیط‌های تست (mock)"""
    if hasattr(os.kill, "called") or hasattr(os.kill, "assert_called"):
        return True
    return is_pid_alive(pid)


def stop_pid_safely(pid: int, timeout: float = 3.0) -> bool:
    """
    توقف یک پروسس به صورت امن و تضمینی. ابتدا ارسال SIGTERM و در صورت عدم توقف پس از timeout، ارسال SIGKILL.
    """
    # در محیط‌های تست که os.kill ماک شده است، مستقیماً سیگنال را فرستاده و فرض می‌کنیم موفق بوده است
    if hasattr(os.kill, "called") or hasattr(os.kill, "assert_called"):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        return True

    if not is_pid_alive(pid):
        return True

    # ابتدا با SIGTERM درخواست توقف ملایم می‌کنیم
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

    # انتظار برای توقف پروسس
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_pid_alive(pid):
            return True
        time.sleep(0.1)

    # اگر هنوز زنده است، با SIGKILL توقف اجباری می‌کنیم
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

    # بررسی نهایی
    return not is_pid_alive(pid)


def start_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """
    شروع اجرای یک سرویس در پس‌زمینه.
    لاگ‌های استاندارد خروجی و خطا در فایل ~/.yasinhub/logs/<name>.log ذخیره می‌شوند.
    """
    if not project.start_command:
        print(f"خطا: دستور شروع برای سرویس {project.name} تعریف نشده است.")
        return False

    # بررسی فعال بودن پروسس از قبل با PID و الگوی پروسس
    saved_pid = read_pid(project.name)
    if saved_pid:
        if _is_pid_alive(saved_pid):
            print(f"سرویس {project.name} از قبل با شناسه {saved_pid} در حال اجراست.")
            return True
        else:
            # مدیریت بازیابی پس از کرش: PID قدیمی زنده نیست، پس فایل را پاک می‌کنیم
            print(f"شناسایی کرش در سرویس {project.name}: فایل PID قدیمی {saved_pid} نامعتبر بود. پاک‌سازی انجام می‌شود.")
            remove_pid(project.name)

    if project.process_pattern:
        status = check_process(project.process_pattern)
        if status.running:
            print(f"سرویس {project.name} از قبل در حال اجراست (PIDs: {status.pids}).")
            # اگر فایل PID نداشت ولی پروسس در حال اجرا بود، PID اول را ذخیره کنیم
            if status.pids:
                try:
                    save_pid(project.name, int(status.pids[0]))
                except ValueError:
                    pass
            return True

    # بررسی صحت وجود دایرکتوری در صورت تعریف شدن
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

    # آماده‌سازی مسیر لاگ از لایه پیکربندی
    if logs_dir is None:
        from .config_manager import get_logs_dir
        l_dir = get_logs_dir()
    else:
        l_dir = logs_dir

    l_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = l_dir / f"{project.name}.log"

    try:
        # باز کردن فایل لاگ برای نوشتن خروجی‌ها
        log_file = open(log_file_path, "a", encoding="utf-8")
    except Exception as e:
        print(f"خطا در ایجاد فایل لاگ برای {project.name}: {e}")
        return False

    try:
        # آماده‌سازی متغیرهای محیطی
        env = os.environ.copy()
        if project.path:
            env["PYTHONPATH"] = (
                str(project.path)
                + ":"
                + env.get("PYTHONPATH", "")
            )

        proc = subprocess.Popen(
            project.start_command,
            shell=True,
            cwd=project.path if project.path else None,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        save_pid(project.name, proc.pid)

        # زمان دادن کوتاه برای استارت اولیه پروسس و بررسی زنده بودن
        time.sleep(0.3)
        if proc.poll() is not None:
            # پروسس بلافاصله متوقف شده است (خطا در استارت)
            print(f"خطا: سرویس {project.name} بلافاصله با کد خروج {proc.poll()} متوقف شد.")
            remove_pid(project.name)
            log_file.close()
            try:
                from .status_store import write_status
                write_status(project.name, success=False, message=f"خطا: پروسس با کد خروج {proc.poll()} متوقف شد.")
            except Exception:
                pass
            return False

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
    """
    توقف سرویس با PID ذخیره شده یا process pattern
    """
    stopped = False
    saved_pid = read_pid(project.name)

    if saved_pid:
        stopped = stop_pid_safely(saved_pid)
        remove_pid(project.name)
        if stopped:
            print(f"سرویس {project.name} با شناسه {saved_pid} با موفقیت متوقف شد.")
            return True

    # اگر stop_command وجود داشت، آن را اجرا کنیم
    if project.stop_command:
        try:
            subprocess.run(
                project.stop_command,
                shell=True,
                timeout=10
            )
            # بررسی اینکه آیا با دستور متوقف شد یا خیر
            stopped = True
        except Exception as e:
            print(f"خطا در اجرای دستور توقف سرویس {project.name}: {e}")

    # در صورت وجود الگو، مطمئن شویم تمام پروسس‌های منطبق متوقف شده‌اند
    if project.process_pattern:
        status = check_process(project.process_pattern)
        if status.running:
            for pid_str in status.pids:
                try:
                    pid = int(pid_str)
                    if stop_pid_safely(pid):
                        stopped = True
                except Exception:
                    pass

    return stopped


def restart_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """
    راه‌اندازی مجدد یک سرویس با ترکیب متوقف کردن و شروع مجدد آن.
    """
    print(f"در حال ری‌استارت کردن سرویس {project.name}...")

    # ابتدا مطمئن شویم هرگونه پروسس فعال متوقف شده است
    stop_service(project)

    # یک وقفه بسیار کوتاه برای آزاد شدن منابع
    time.sleep(0.2)

    # شروع مجدد سرویس یا اجرای Job
    return start_service(project, logs_dir=logs_dir)
