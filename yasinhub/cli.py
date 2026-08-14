"""
cli.py
دستور وضعیت و مدیریت سرویس‌ها:

    python -m yasinhub.cli status
    python -m yasinhub.cli core
    python -m yasinhub.cli dashboard [--live] [--interval SECONDS]
    python -m yasinhub.cli start [service_name | all]
    python -m yasinhub.cli stop [service_name | all]
    python -m yasinhub.cli restart [service_name | all]
    python -m yasinhub.cli agent [register | status | health | start | stop | restart] [args]
    python -m yasinhub.cli press [status | health | rewrites] [args]

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
        status_persian = r.health_state
        if status_persian == "RUNNING":
            status_persian = "در حال اجرا"
        elif status_persian == "SUCCESS":
            status_persian = "موفق"
        elif status_persian == "FAILED":
            status_persian = "خطا"
        elif status_persian == "UNKNOWN":
            status_persian = "نامشخص"
        elif status_persian == "STALE":
            status_persian = "کهنه"
        elif status_persian == "IDLE":
            status_persian = "ایستاده"

        lines.append(
            f"{r.name.ljust(name_width)}  وضعیت: {status_persian:<10}  "
            f"آخرین اجرا: {_format_last_run(r)}"
        )

        if r.last_message:
            lines.append(
                f"{' ' * name_width}  پیام: {r.last_message}"
            )

    return "\n".join(lines)

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="yasinhub")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # دستور وضعیت (بدون تغییر)
    subparsers.add_parser("status", help="نمایش وضعیت همه‌ی پروژه‌ها")

    # دستور وضعیت هسته مرکزی یاسین
    subparsers.add_parser("core", help="نمایش وضعیت و اطلاعات ران‌تایم Yasin-Core")

    # دستور داشبورد مانیتورینگ سلامت اکوسیستم
    dash_parser = subparsers.add_parser("dashboard", help="نمایش داشبورد مانیتورینگ سلامت اکوسیستم یاسین")
    dash_parser.add_argument("--live", action="store_true", help="نمایش پویای داشبورد (بروزرسانی مداوم)")
    dash_parser.add_argument("--interval", type=float, default=2.0, help="فاصله زمانی بروزرسانی داشبورد به ثانیه")

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

    # دستور مدیریت و مانیتورینگ سرویس رله یاسین (Yasin-Relay)
    relay_parser = subparsers.add_parser("relay", help="مدیریت و مانیتورینگ سرویس رله یاسین (Yasin-Relay)")
    relay_subparsers = relay_parser.add_subparsers(dest="action", required=True)

    # relay connect
    relay_subparsers.add_parser("connect", help="اتصال به سرویس رله")

    # relay status
    relay_subparsers.add_parser("status", help="نمایش وضعیت سرویس رله")

    # relay event <event_type> <payload>
    event_p = relay_subparsers.add_parser("event", help="مدیریت رویداد سرویس رله")
    event_p.add_argument("event_type", help="نوع رویداد")
    event_p.add_argument("payload", help="بدنه رویداد (به صورت JSON یا متن)")

    # relay verify-channels [channels]
    verify_p = relay_subparsers.add_parser("verify-channels", help="تأیید به‌روزرسانی کانال‌های سرویس رله")
    verify_p.add_argument("channels", nargs="*", help="لیست کانال‌ها برای تأیید")

    # دستور مدیریت و مانیتورینگ سرویس فیدخوان یاسین (YasinFeed)
    feed_parser = subparsers.add_parser("feed", help="مدیریت و مانیتورینگ سرویس فیدخوان یاسین (YasinFeed)")
    feed_subparsers = feed_parser.add_subparsers(dest="action", required=True)

    # feed status
    feed_subparsers.add_parser("status", help="نمایش وضعیت و سلامت فیدخوان")

    # feed articles [--page PAGE] [--limit LIMIT]
    articles_p = feed_subparsers.add_parser("articles", help="نمایش لیست آخرین مقالات دریافت شده")
    articles_p.add_argument("--page", "-p", type=int, default=1, help="شماره صفحه")
    articles_p.add_argument("--limit", "-l", type=int, default=10, help="تعداد مقالات در هر صفحه")

    # feed article <article_id>
    article_p = feed_subparsers.add_parser("article", help="نمایش جزئیات یک مقاله خاص")
    article_p.add_argument("article_id", help="شناسه مقاله")

    # دستور مدیریت و مانیتورینگ سرویس پرس یاسین (YasinPress)
    press_parser = subparsers.add_parser("press", help="مدیریت و مانیتورینگ سرویس پرس یاسین (YasinPress)")
    press_subparsers = press_parser.add_subparsers(dest="action", required=True)

    # press status
    press_subparsers.add_parser("status", help="نمایش وضعیت سرویس پرس")

    # press health
    press_subparsers.add_parser("health", help="بررسی سلامت سرویس پرس")

    # press rewrites [--limit LIMIT]
    rewrites_p = press_subparsers.add_parser("rewrites", help="نمایش آخرین مقالات بازنویسی شده")
    rewrites_p.add_argument("--limit", "-l", type=int, default=10, help="تعداد مقالات برای نمایش")

    # دستورات مدیریت فرآیندها
    start_parser = subparsers.add_parser("start", help="شروع اجرای یک یا همه سرویس‌ها")
    start_parser.add_argument("service", nargs="?", default="all", help="نام سرویس مورد نظر یا all")

    stop_parser = subparsers.add_parser("stop", help="متوقف کردن یک یا همه سرویس‌ها")
    stop_parser.add_argument("service", nargs="?", default="all", help="نام سرویس مورد نظر یا all")

    restart_parser = subparsers.add_parser("restart", help="راه‌اندازی مجدد یک یا همه سرویس‌ها")
    restart_parser.add_argument("service", nargs="?", default="all", help="نام سرویس مورد نظر یا all")

    # دستور دکتر سیستم (بررسی سلامت و عیب‌یابی)
    subparsers.add_parser("doctor", help="بررسی سلامت سیستم و عیب‌یابی (Doctor)")

    args = parser.parse_args(argv)

    if args.command == "status":
        reports = build_report()
        print(format_report(reports))
        return 0

    elif args.command == "dashboard":
        from .dashboard import display_dashboard
        display_dashboard(live_mode=args.live, update_interval=args.interval)
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

    elif args.command == "relay":
        from .relay_integration import RelayIntegration
        integration = RelayIntegration()

        if args.action == "connect":
            success = integration.connect()
            if success:
                print("ارتباط با سرویس رله با موفقیت برقرار شد.")
                return 0
            else:
                print("خطا: برقراری ارتباط با سرویس رله ناموفق بود. بررسی کنید که yasin_relay نصب و متصل باشد.")
                return 1

        elif args.action == "status":
            status_info = integration.get_status()
            print("==================================================")
            print("وضعیت سرویس رله Yasin-Relay")
            print("==================================================")
            if "error" in status_info and status_info["error"]:
                print(f"خطا: {status_info['error']}")
                return 1
            else:
                print(f"وضعیت فعلی: {status_info.get('status', 'unknown')}")
                for key, val in status_info.items():
                    if key not in ("status", "error"):
                        print(f"{key}: {val}")
            print("==================================================")
            return 0

        elif args.action == "event":
            import json
            try:
                payload_dict = json.loads(args.payload)
            except Exception:
                payload_dict = {"message": args.payload}

            success = integration.handle_event(args.event_type, payload_dict)
            if success:
                print(f"رویداد '{args.event_type}' با موفقیت پردازش شد.")
                return 0
            else:
                print(f"خطا: پردازش رویداد '{args.event_type}' ناموفق بود.")
                return 1

        elif args.action == "verify-channels":
            result = integration.verify_channels(args.channels if args.channels else None)
            if result.get("status") == "success" or result.get("verified") is True:
                print("==================================================")
                print("وضعیت تأیید کانال‌ها:")
                print("==================================================")
                print(f"وضعیت: {result.get('status', 'success')}")
                if "channels" in result and result["channels"]:
                    print(f"کانال‌های تأیید شده: {', '.join(result['channels'])}")
                if "message" in result:
                    print(f"پیام: {result['message']}")
                print("==================================================")
                return 0
            else:
                print(f"خطا: تأیید کانال‌ها ناموفق بود. {result.get('error', 'خطای نامشخص')}")
                return 1

    elif args.command == "feed":
        from .services.feed_service import FeedService
        service = FeedService()

        if args.action == "status":
            health_info = service.health()
            version_str = service.version()

            print("==================================================")
            print("وضعیت سرویس فیدخوان یاسین YasinFeed")
            print("==================================================")

            raw_status = health_info.get("status")
            if raw_status == "healthy" or raw_status == "ok":
                status_str = "سالم (Healthy)"
            else:
                status_str = "ناسالم (Unhealthy)"

            print(f"وضعیت فعلی: {status_str}")
            print(f"نسخه سرویس: {version_str}")

            if "error" in health_info and health_info["error"]:
                print(f"خطا: {health_info['error']}")

            # دریافت آمار و مسیرها در صورت سالم بودن
            if raw_status in ("healthy", "ok"):
                try:
                    stats = service.repository.client.stats()
                    if stats:
                        print("آمار پردازش:")
                        for k, v in stats.items():
                            print(f"  {k}: {v}")
                except Exception:
                    pass

                try:
                    routes = service.repository.client.routes()
                    if routes:
                        print(f"مسیرهای API: {', '.join(routes)}")
                except Exception:
                    pass

            print("==================================================")
            return 0 if raw_status in ("healthy", "ok") else 1

        elif args.action == "articles":
            from rich.console import Console
            from rich.table import Table

            console = Console()
            articles = service.get_articles(page=args.page, limit=args.limit)

            if not articles:
                console.print("[yellow]هیچ مقاله‌ای یافت نشد یا خطا در برقراری ارتباط رخ داده است.[/yellow]")
                return 1

            table = Table(title=f"لیست مقالات فیدخوان (صفحه {args.page})", show_header=True, header_style="bold cyan")
            table.add_column("شناسه (ID)", style="dim")
            table.add_column("عنوان (Title)")
            table.add_column("تاریخ انتشار (Published)")
            table.add_column("وضعیت بازنویسی (Status)")

            for art in articles:
                table.add_row(
                    str(art.id),
                    str(art.title),
                    str(art.published_at),
                    str(art.status)
                )

            console.print(table)
            return 0

        elif args.action == "article":
            from rich.console import Console
            from rich.panel import Panel

            console = Console()
            art = service.get_article(args.article_id)

            if not art:
                console.print(f"[bold red]خطا: مقاله‌ای با شناسه '{args.article_id}' یافت نشد.[/bold red]")
                return 1

            console.print(Panel(
                f"[bold cyan]عنوان:[/bold cyan] {art.title}\n"
                f"[bold cyan]تاریخ:[/bold cyan] {art.published_at}\n"
                f"[bold cyan]وضعیت بازنویسی:[/bold cyan] {art.status}\n\n"
                f"[bold cyan]محتوا:[/bold cyan]\n{art.content}",
                title=f"جزئیات مقاله {art.id}",
                expand=False
            ))
            return 0

    elif args.command == "press":
        from .services.press_service import PressService
        service = PressService()

        if args.action == "status":
            status_info = service.get_status()
            print("==================================================")
            print("وضعیت سرویس پرس YasinPress")
            print("==================================================")
            if "error" in status_info and status_info["error"]:
                print(f"خطا: {status_info['error']}")
                return 1
            else:
                print(f"وضعیت فعلی: {status_info.get('status', 'unknown')}")
                for key, val in status_info.items():
                    if key not in ("status", "error"):
                        print(f"{key}: {val}")
            print("==================================================")
            return 0

        elif args.action == "health":
            health_info = service.health()
            print("==================================================")
            print("بررسی سلامت سرویس پرس YasinPress")
            print("==================================================")
            if "error" in health_info and health_info["error"]:
                print("وضعیت سلامت: ناسالم (Unhealthy)")
                print(f"خطا: {health_info['error']}")
                return 1
            else:
                print(f"وضعیت سلامت: {health_info.get('status', 'healthy')}")
                for key, val in health_info.items():
                    if key not in ("status", "error"):
                        print(f"{key}: {val}")
            print("==================================================")
            return 0

        elif args.action == "rewrites":
            from rich.console import Console
            from rich.table import Table

            console = Console()
            rewrites = service.get_rewrites(limit=args.limit)

            if not rewrites:
                console.print("[yellow]هیچ مقاله بازنویسی شده‌ای یافت نشد یا خطا در برقراری ارتباط رخ داده است.[/yellow]")
                return 1

            table = Table(title=f"لیست مقالات بازنویسی شده YasinPress-Rewrite", show_header=True, header_style="bold cyan")
            table.add_column("شناسه (ID)", style="dim")
            table.add_column("عنوان اصلی (Original Title)")
            table.add_column("عنوان بازنویسی شده (Rewritten Title)")
            table.add_column("وضعیت (Status)")

            for item in rewrites:
                table.add_row(
                    str(item.get("id", "")),
                    str(item.get("original_title", "")),
                    str(item.get("rewritten_title", "")),
                    str(item.get("status", ""))
                )

            console.print(table)
            return 0

    elif args.command == "doctor":
        from .services.doctor_service import DoctorService
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from typing import Any

        doctor = DoctorService()
        result = doctor.run()

        console = Console()
        console.print(Panel("[bold green]🩺 بررسی سلامت و عیب‌یابی سیستم (YasinHub Doctor)[/bold green]", expand=False))

        # 1. Python Environment
        py_info = result.get("python", {})
        py_status = py_info.get("status")
        py_status_str = "[green]✔ سالم (OK)[/green]" if py_status == "ok" else f"[red]❌ خطا ({py_status})[/red]"

        console.print("\n[bold cyan]💻 مشخصات محیط اجرا (Python Runtime):[/bold cyan]")
        console.print(f"  وضعیت: {py_status_str}")
        console.print(f"  نسخه پایتون: [yellow]{py_info.get('version')}[/yellow]")
        console.print(f"  سیستم‌عامل: [yellow]{py_info.get('platform')}[/yellow]")

        # 2. Ecosystem Health
        console.print("\n[bold cyan]🌐 وضعیت سلامت سرویس‌های اکوسیستم (Ecosystem Health):[/bold cyan]")
        eco_info = result.get("ecosystem", {})

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("سرویس (Service)", style="bold")
        table.add_column("وضعیت (Status)", justify="center")
        table.add_column("جزئیات / خطا (Details / Error)")

        def get_status_details(name: str, data: Any):
            if not isinstance(data, dict):
                return "[red]❌ نامشخص[/red]", str(data)

            raw_status = data.get("status")
            if isinstance(raw_status, dict):
                err = raw_status.get("error") or data.get("error")
                raw_status = raw_status.get("status")
            else:
                err = data.get("error")

            if raw_status in ("healthy", "ok", "active", "SUCCESS"):
                status_str = "[green]✔ سالم (OK)[/green]"
            elif raw_status in ("unhealthy", "failed", "FAILED", "unknown"):
                status_str = "[red]❌ ناسالم (Unhealthy)[/red]"
            else:
                status_str = f"[yellow]⚠ {raw_status}[/yellow]"

            details = []
            if data.get("version"):
                details.append(f"نسخه: {data.get('version')}")
            if data.get("projects") is not None:
                details.append(f"تعداد پروژه‌ها: {data.get('projects')}")
            if err:
                details.append(f"[red]{err}[/red]")

            details_str = " | ".join(details) if details else "—"
            return status_str, details_str

        for srv_key, srv_name in [
            ("feed", "YasinFeed (فید خوان یاسین)"),
            ("core", "YasinCore (هسته مرکزی)"),
            ("agent", "YasinAgent (عامل هوشمند)"),
            ("relay", "YasinRelay (رله هوشمند)"),
            ("registry", "Registry (ثبت پروژه‌ها)"),
            ("press", "YasinPress (سیستم پرس یاسین)")
        ]:
            srv_data = eco_info.get(srv_key, {})
            status_str, details_str = get_status_details(srv_name, srv_data)
            table.add_row(srv_name, status_str, details_str)

        console.print(table)
        console.print("\n[bold green]✓ بررسی عیب‌یابی به پایان رسید.[/bold green]")
        return 0

    elif args.command in ("start", "stop", "restart"):
        from .registry import default_registry
        from .service_manager import start_service, stop_service, restart_service
        from rich.console import Console

        console = Console()
        projects = default_registry()
        service_name = args.service

        if service_name != "all":
            selected_project = next((p for p in projects if p.name == service_name), None)
            if not selected_project:
                console.print(f"[bold red]خطا:[/bold red] سرویس با نام '[cyan]{service_name}[/cyan]' یافت نشد.")
                return 1
            targets = [selected_project]
        else:
            targets = projects

        total_services = len(targets)
        console.print(f"\n[bold yellow]🚀 آغاز فرآیند '{args.command}' برای {total_services} سرویس...[/bold yellow]\n")

        success_count = 0
        for i, project in enumerate(targets, 1):
            console.print(f"[bold blue][{i}/{total_services}][/bold blue] عملیات [bold]{args.command}[/bold] روی [cyan]{project.name}[/cyan]...")

            if args.command == "start":
                success = start_service(project)
            elif args.command == "stop":
                success = stop_service(project)
            else:
                success = restart_service(project)

            if success:
                success_count += 1
                console.print(f"[green]✔[/green] سرویس [cyan]{project.name}[/cyan] با موفقیت پردازش شد.\n")
            else:
                console.print(f"[red]❌[/red] خطا در پردازش سرویس [cyan]{project.name}[/cyan].\n")

        console.print(f"[bold green]✓ عملیات '{args.command}' بر روی {success_count} از {total_services} سرویس با موفقیت انجام شد.[/bold green]")
        if service_name != "all" and success_count == 0:
            return 1
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
