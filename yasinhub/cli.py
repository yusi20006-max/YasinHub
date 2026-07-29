"""
cli.py
دستور وضعیت و مدیریت سرویس\u200cها:

    python -m yasinhub.cli status
    python -m yasinhub.cli start [service_name | all]
    python -m yasinhub.cli stop [service_name | all]
    python -m yasinhub.cli restart [service_name | all]

این ابزار به عنوان لایه کنترل مرکزی اکوسیستم Yasin عمل می\u200cکند.
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from .report import ProjectReport, build_report


def _format_process(running: Optional[bool]) -> str:
    if running is None:
        return "—"
    return "در حال اجرا" if running else "متوقف"


def _format_last_run(report: ProjectReport) -> str:
    if report.last_run is None:
        return "بدون گزارش"
    result_word = "موفق" if report.last_success else "ناموفق"
    return f"{report.last_run} ({result_word})"


def format_report(reports: List[ProjectReport]) -> str:
    lines = []
    name_width = max((len(r.name) for r in reports), default=10)
    for r in reports:
        lines.append(
            f"{r.name.ljust(name_width)}  پروسس: {_format_process(r.process_running):<10}  "
            f"آخرین اجرا: {_format_last_run(r)}"
        )
        if r.last_message:
            lines.append(f"{" " * name_width}  پیام: {r.last_message}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="yasinhub")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # دستور وضعیت (بدون تغییر)
    subparsers.add_parser("status", help="نمایش وضعیت هم\u200eی پروژه\u200cها")

    # دستورات مدیریت فرآیندها
    start_parser = subparsers.add_parser("start", help="شروع اجرای یک یا همه سرویس\u200cها")
    start_parser.add_argument("service", nargs="?", default="all", help="نام سرویس مورد نظر یا all")

    stop_parser = subparsers.add_parser("stop", help="متوقف کردن یک یا همه سرویس\u200cها")
    stop_parser.add_argument("service", nargs="?", default="all", help="نام سرویس مورد نظر یا all")

    restart_parser = subparsers.add_parser("restart", help="راه\u200cاندازی مجدد یک یا همه سرویس\u200cها")
    restart_parser.add_argument("service", nargs="?", default="all", help="نام سرویس مورد نظر یا all")

    args = parser.parse_args(argv)

    if args.command == "status":
        reports = build_report()
        print(format_report(reports))
        return 0

    elif args.command in ("start", "stop", "restart"):
        from .registry import default_registry
        from .service_manager import start_service, stop_service, restart_service

        projects = default_registry()
        service_name = args.service

        if service_name != "all":
            selected_project = next((p for p in projects if p.name == service_name), None)
            if not selected_project:
                print(f"خطا: سرویس با نام '{service_name}' یافت نشد.")
                return 1
            targets = [selected_project]
        else:
            targets = projects

        success_count = 0
        for project in targets:
            if args.command == "start":
                success = start_service(project)
            elif args.command == "stop":
                success = stop_service(project)
            else:
                success = restart_service(project)

            if success:
                success_count += 1

        print(f"عملیات '{args.command}' بر روی {success_count} از {len(targets)} سرویس با موفقیت انجام شد.")
        # اگر کاربر یک سرویس خاص را درخواست کرده بود و موفق نشد، کد ۱ برگشت داده شود
        if service_name != "all" and success_count == 0:
            return 1
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
