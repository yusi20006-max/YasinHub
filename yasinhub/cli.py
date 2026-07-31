"""
cli.py
دستور وضعیت و مدیریت سرویس‌ها:

    python -m yasinhub.cli status
    python -m yasinhub.cli core
    python -m yasinhub.cli start [service_name | all]
    python -m yasinhub.cli stop [service_name | all]
    python -m yasinhub.cli restart [service_name | all]
    python -m yasinhub.cli agent [register | status | health | start | stop | restart] [args]

این ابزار به عنوان لایه کنترل مرکزی اکوسیستم Yasin عمل می‌کند.
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
    subparsers.add_parser("status", help="نمایش وضعیت همه‌ی پروژه‌ها")

    # دستور وضعیت هسته مرکزی یاسین
    subparsers.add_parser("core", help="نمایش وضعیت و اطلاعات ران‌تایم Yasin-Core")

    # دستور مدیریت و مانیتورینگ عامل‌های یاسین (Yasin-Agent)
    agent_parser = subparsers.add_parser("agent", help="مدیریت و مانیتورینگ عامل‌های یاسین (Yasin-Agent)")
    agent_subparsers = agent_parser.add_subparsers(dest="action", required=True)

    # agent register <name> [--description <desc>]
    reg_parser = agent_subparsers.add_parser("register", help="ثبت یک عامل جدید")
    reg_parser.add_argument("name", help="نام عامل")
    reg_parser.add_argument("--description", "-d", default="", help="توضیح عامل")

    # agent status <name>
    status_parser = agent_subparsers.add_parser("status", help="نمایش وضعیت یک عامل")
    status_parser.add_argument("name", help="نام عامل")

    # agent health <name>
    health_parser = agent_subparsers.add_parser("health", help="بررسی سلامت یک عامل")
    health_parser.add_argument("name", help="نام عامل")

    # agent start/stop/restart <name>
    start_p = agent_subparsers.add_parser("start", help="شروع به کار یک عامل")
    start_p.add_argument("name", help="نام عامل")

    stop_p = agent_subparsers.add_parser("stop", help="متوقف کردن یک عامل")
    stop_p.add_argument("name", help="نام عامل")

    restart_p = agent_subparsers.add_parser("restart", help="راه‌اندازی مجدد یک عامل")
    restart_p.add_argument("name", help="نام عامل")

    # دستورات مدیریت فرآیندها
    start_parser = subparsers.add_parser("start", help="شروع اجرای یک یا همه سرویس‌ها")
    start_parser.add_argument("service", nargs="?", default="all", help="نام سرویس مورد نظر یا all")

    stop_parser = subparsers.add_parser("stop", help="متوقف کردن یک یا همه سرویس‌ها")
    stop_parser.add_argument("service", nargs="?", default="all", help="نام سرویس مورد نظر یا all")

    restart_parser = subparsers.add_parser("restart", help="راه‌اندازی مجدد یک یا همه سرویس‌ها")
    restart_parser.add_argument("service", nargs="?", default="all", help="نام سرویس مورد نظر یا all")

    args = parser.parse_args(argv)

    if args.command == "status":
        reports = build_report()
        print(format_report(reports))
        return 0

    elif args.command == "core":
        from .core_integration import CoreIntegration
        integration = CoreIntegration()
        health = integration.check_health()

        print("==================================================")
        print("وضعیت اتصال به هسته Yasin-Core")
        print("==================================================")
        print(f"وضعیت اتصال: {'متصل' if health['connected'] else 'عدم اتصال'}")
        if health['connected']:
            print(f"نسخه SDK: {health['version']}")
            print(f"سازگاری SDK: {'معتبر' if health['compatibility'] else 'نامعتبر'}")

            info = integration.get_runtime_info()
            print("--------------------------------------------------")
            print("اطلاعات ران‌تایم (Runtime Information):")
            print(f"عامل‌ها (Agents): {', '.join(info['agents']) if info['agents'] else 'هیچ عاملی ثبت نشده است'}")
            print(f"ابزارها (Tools): {', '.join(info['tools']) if info['tools'] else 'هیچ ابزاری ثبت نشده است'}")
            print(f"پلاگین‌ها (Plugins): {', '.join(info['plugins']) if info['plugins'] else 'هیچ پلاگینی ثبت نشده است'}")
            print(f"ارائه‌دهندگان هوش مصنوعی (Providers): {', '.join(info['providers']) if info['providers'] else 'هیچ ارائه‌دهنده‌ای ثبت نشده است'}")
        else:
            print(f"خطا: {health['error']}")
        print("==================================================")
        return 0

    elif args.command == "agent":
        from .agent_integration import AgentIntegration
        integration = AgentIntegration()

        if args.action == "register":
            success = integration.register_agent(args.name, args.description)
            if success:
                print(f"عامل '{args.name}' با موفقیت ثبت شد.")
                return 0
            else:
                print(f"خطا: ثبت عامل '{args.name}' انجام نشد. بررسی کنید که yasin_agent نصب و متصل باشد.")
                return 1

        elif args.action == "status":
            status_info = integration.get_agent_status(args.name)
            print("==================================================")
            print(f"وضعیت عامل: {args.name}")
            print("==================================================")
            if "error" in status_info and status_info["error"]:
                print(f"خطا: {status_info['error']}")
                return 1
            else:
                print(f"وضعیت فعلی: {status_info.get('status', 'unknown')}")
                for key, val in status_info.items():
                    if key not in ("name", "status", "error"):
                        print(f"{key}: {val}")
            print("==================================================")
            return 0

        elif args.action == "health":
            health_info = integration.check_agent_health(args.name)
            print("==================================================")
            print(f"بررسی سلامت عامل: {args.name}")
            print("==================================================")
            if "error" in health_info and health_info["error"]:
                print(f"وضعیت سلامت: ناسالم (Unhealthy)")
                print(f"خطا: {health_info['error']}")
                return 1
            else:
                print(f"وضعیت سلامت: {health_info.get('status', 'healthy')}")
                for key, val in health_info.items():
                    if key not in ("name", "status", "error"):
                        print(f"{key}: {val}")
            print("==================================================")
            return 0

        elif args.action == "start":
            success = integration.start_agent(args.name)
            if success:
                print(f"عامل '{args.name}' با موفقیت شروع به کار کرد.")
                return 0
            else:
                print(f"خطا: شروع به کار عامل '{args.name}' ناموفق بود.")
                return 1

        elif args.action == "stop":
            success = integration.stop_agent(args.name)
            if success:
                print(f"عامل '{args.name}' با موفقیت متوقف شد.")
                return 0
            else:
                print(f"خطا: متوقف کردن عامل '{args.name}' ناموفق بود.")
                return 1

        elif args.action == "restart":
            success = integration.restart_agent(args.name)
            if success:
                print(f"عامل '{args.name}' با موفقیت راه‌اندازی مجدد شد.")
                return 0
            else:
                print(f"خطا: راه‌اندازی مجدد عامل '{args.name}' ناموفق بود.")
                return 1

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
        if service_name != "all" and success_count == 0:
            return 1
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
