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
from .pid_store import save_pid, read_pid, remove_pid

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

        save_pid(project.name, proc.pid)
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
    توقف سرویس با PID ذخیره شده یا process pattern
    """

    saved_pid = read_pid(project.name)

    if saved_pid:
        try:
            if hasattr(os, "killpg"):
                try:
                    os.killpg(
                        os.getpgid(saved_pid),
                        signal.SIGTERM
                    )
                except OSError:
                    os.kill(
                        saved_pid,
                        signal.SIGTERM
                    )
            else:
                os.kill(
                    saved_pid,
                    signal.SIGTERM
                )

            remove_pid(project.name)

            print(
                f"PID {saved_pid} stopped"
            )

            return True

        except ProcessLookupError:
            remove_pid(project.name)


        except Exception as e:
            print(
                f"PID stop error: {e}"
            )


    if project.stop_command:
        try:
            subprocess.run(
                project.stop_command,
                shell=True,
                timeout=10
            )

            return True

        except Exception:
            return False


    if project.process_pattern:

        status = check_process(
            project.process_pattern
        )

        if not status.running:
            return False


        for pid_str in status.pids:

            try:
                os.kill(
                    int(pid_str),
                    signal.SIGTERM
                )

                return True

            except Exception:
                pass


    return False



def restart_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """
    راه‌اندازی مجدد یک سرویس با ترکیب متوقف کردن و شروع مجدد آن.
    """
    print(f"در حال ری‌استارت کردن سرویس {project.name}...")
    # فقط سرویس‌های دائمی را متوقف می‌کنیم.
    # Jobها (مثل yasinrelay) بعد از اجرا پروسس دائمی ندارند.
    if project.stop_command or project.process_pattern:
        stop_service(project)

    # شروع مجدد سرویس یا اجرای Job
    return start_service(project, logs_dir=logs_dir)
