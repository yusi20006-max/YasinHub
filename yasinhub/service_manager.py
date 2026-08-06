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

# دایرکتوری پیش‌فرض لاگ‌ها
DEFAULT_LOGS_DIR = Path(os.environ.get("YASINHUB_LOGS_DIR", str(Path.home() / ".yasinhub" / "logs")))


def start_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """
    شروع اجرای یک سرویس در پس‌زمینه.
    لاگ‌های استاندارد خروجی و خطا در فایل ~/.yasinhub/logs/<name>.log ذخیره می‌شوند.
    """
    if not project.start_command:
        print(f"خطا: دستور شروع برای سرویس {project.name} تعریف نشده است.")
        return False

    # بررسی فعال بودن پروسس از قبل
    if project.process_pattern:
        status = check_process(project.process_pattern)
        if status.running:
            print(f"سرویس {project.name} از قبل در حال اجراست (PIDs: {status.pids}).")
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
        # اجرای دستور در پس‌زمینه
        # استفاده از shell=True برای ساده‌سازی دستورات خط فرمان با پارامترها و پایپ‌ها
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
        # زمان دادن کوتاه برای استارت اولیه پروسس
        time.sleep(0.3)
        if proc.poll() is not None:
            # پروسس بلافاصله متوقف شده است (خطا در استارت)
            print(f"خطا: سرویس {project.name} بلافاصله با کد خروج {proc.poll()} متوقف شد.")
            log_file.close()
            return False

        print(f"سرویس {project.name} با موفقیت در پس‌زمینه استارت شد.")
        log_file.close()
        return True
    except Exception as e:
        print(f"خطا در اجرای دستور شروع سرویس {project.name}: {e}")
        log_file.close()
        return False


def stop_service(project: ProjectEntry) -> bool:
    """
    متوقف کردن یک سرویس فعال.
    اگر دستور توقف سفارشی تعریف شده باشد آن را اجرا می‌کند،
    در غیر این صورت پروسس‌های منطبق بر process_pattern را با سیگنال خاتمه (SIGTERM) می‌کشد.
    """
    action_taken = False

    if project.stop_command:
        try:
            subprocess.run(project.stop_command, shell=True, timeout=10)
            print(f"دستور توقف سفارشی برای سرویس {project.name} با موفقیت اجرا شد.")
            action_taken = True
        except Exception as e:
            print(f"خطا در اجرای دستور توقف سرویس {project.name}: {e}")
            return False
    elif project.process_pattern:
        status = check_process(project.process_pattern)
        if not status.running:
            print(f"سرویس {project.name} در حال اجرا نیست.")
            return False

        for pid_str in status.pids:
            try:
                pid = int(pid_str)
                # ارسال سیگنال SIGTERM به پروسس و گروه پروسس‌های آن
                if hasattr(os, "killpg"):
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                    except OSError:
                        os.kill(pid, signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
                print(f"سیگنال پایان (SIGTERM) به پروسس {pid} ارسال شد.")
                action_taken = True
            except Exception as e:
                print(f"خطا در فرستادن سیگنال پایان به پروسس {pid_str}: {e}")

        # یک فرصت کوتاه برای پایان یافتن کامل پروسس‌ها
        if action_taken:
            time.sleep(0.3)
    else:
        print(f"خطا: هیچ دستور توقف یا الگوی پروسسی برای سرویس {project.name} تعریف نشده است.")
        return False

    return action_taken


def restart_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """
    راه‌اندازی مجدد یک سرویس با ترکیب متوقف کردن و شروع مجدد آن.
    """
    print(f"در حال ری‌استارت کردن سرویس {project.name}...")
    # توقف در صورتی که در حال اجرا باشد؛ اگر در حال اجرا نباشد هم تلاش برای استارت را متوقف نمی‌کنیم
    stop_service(project)
    # شروع مجدد سرویس
    return start_service(project, logs_dir=logs_dir)
