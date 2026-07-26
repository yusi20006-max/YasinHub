"""
cli.py
دستور وضعیت ساده:

    python -m yasinhub.cli status

خروجی یک جدول متنی ساده برای هر پروژه است — بدون داشبورد سنگین، فقط
یک نگاه سریع به این‌که چه‌چیزی زنده است و آخرین اجرا چطور بوده.
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
            lines.append(f"{' ' * name_width}  پیام: {r.last_message}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="yasinhub")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="نمایش وضعیت همه‌ی پروژه‌ها")

    args = parser.parse_args(argv)

    if args.command == "status":
        reports = build_report()
        print(format_report(reports))
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
