"""
dashboard.py
داشبورد مانیتورینگ سلامت اکوسیستم یاسین (Ecosystem Health Dashboard).
این ماژول وضعیت Yasin-Core، Yasin-Agent، Yasin-Relay و وضعیت سرویس‌ها را با یک طراحی زیبا و کاربرپسند در ترمینال نمایش می‌دهد.
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Dict, List, Optional

from rich.align import Align
from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .agent_integration import AgentIntegration
from .core_integration import CoreIntegration
from .relay_integration import RelayIntegration
from .report import build_report, ProjectReport


def make_header() -> Panel:
    """ایجاد پنل سربرگ داشبورد."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = Text("داشبورد مانیتورینگ سلامت اکوسیستم یاسین (Yasin Ecosystem)", style="bold magenta")
    time_text = Text(f"زمان بروزرسانی: {now}", style="cyan")

    # چیدمان زیبا
    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="right", ratio=1)
    grid.add_row(title, time_text)

    return Panel(grid, style="bold blue")


def make_core_panel(core: CoreIntegration) -> Panel:
    """ایجاد پنل وضعیت هسته مرکزی یاسین (Yasin-Core)."""
    health = core.check_health()
    info = core.get_runtime_info()

    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold yellow", width=15)
    table.add_column(style="white")

    if health["connected"]:
        conn_status = Text("✔ متصل (Connected)", style="bold green")
        sdk_version = Text(health.get("version") or "—", style="green")
        sdk_compat = Text("✓ معتبر (Valid)", style="bold green") if health.get("compatibility") else Text("✗ نامعتبر (Invalid)", style="bold red")

        # اطلاعات ران‌تایم
        agents_list = info.get("agents", [])
        agents_str = ", ".join(agents_list) if agents_list else "هیچ عاملی ثبت نشده است"

        tools_list = info.get("tools", [])
        tools_str = ", ".join(tools_list) if tools_list else "هیچ ابزاری ثبت نشده است"

        plugins_list = info.get("plugins", [])
        plugins_str = ", ".join(plugins_list) if plugins_list else "هیچ پلاگینی ثبت نشده است"

        providers_list = info.get("providers", [])
        providers_str = ", ".join(providers_list) if providers_list else "هیچ ارائه‌دهنده‌ای ثبت نشده است"

        table.add_row("وضعیت اتصال:", conn_status)
        table.add_row("نسخه SDK:", sdk_version)
        table.add_row("سازگاری SDK:", sdk_compat)
        table.add_row("عامل‌ها (Agents):", Text(agents_str, style="cyan"))
        table.add_row("ابزارها (Tools):", Text(tools_str, style="cyan"))
        table.add_row("پلاگین‌ها:", Text(plugins_str, style="cyan"))
        table.add_row("ارائه‌دهندگان هوش مصنوعی:", Text(providers_str, style="cyan"))

        panel_style = "green"
    else:
        conn_status = Text("✘ عدم اتصال (Disconnected)", style="bold red")
        err_msg = Text(health.get("error") or "خطای نامشخص", style="red")

        table.add_row("وضعیت اتصال:", conn_status)
        table.add_row("خطا:", err_msg)

        panel_style = "red"

    return Panel(table, title="[bold cyan]وضعیت Yasin-Core[/bold cyan]", border_style=panel_style)


def make_agent_panel(agent: AgentIntegration) -> Panel:
    """ایجاد پنل وضعیت و سلامت عامل یاسین (Yasin-Agent)."""
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold yellow", width=15)
    table.add_column(style="white")

    if agent.connected:
        conn_status = Text("✔ متصل (Connected)", style="bold green")
        table.add_row("وضعیت اتصال:", conn_status)

        # چک کردن سلامت عامل پیش‌فرض یا وضعیت کلی
        # به عنوان مانیتور کلی، وضعیت عامل پیش‌فرض 'yasin-agent' را چک می‌کنیم
        status_info = agent.get_agent_status("yasin-agent")
        health_info = agent.check_agent_health("yasin-agent")

        if "error" in status_info and status_info["error"] and "yasin_agent" not in str(status_info["error"]):
            status_text = Text(status_info.get("status", "error"), style="bold red")
            health_text = Text("Unhealthy (ناسالم)", style="bold red")
        else:
            status_text = Text(status_info.get("status", "unknown"), style="bold green" if status_info.get("status") in ("running", "healthy", "active") else "yellow")
            health_text = Text(health_info.get("status", "healthy"), style="bold green" if health_info.get("status") == "healthy" else "yellow")

        table.add_row("وضعیت عامل:", status_text)
        table.add_row("وضعیت سلامت:", health_text)

        for key, val in status_info.items():
            if key not in ("name", "status", "error"):
                table.add_row(f"{key}:", Text(str(val), style="cyan"))

        panel_style = "green"
    else:
        conn_status = Text("✘ عدم اتصال (Disconnected)", style="bold red")
        err_msg = Text(agent.connection_error or "کتابخانه yasin_agent یافت نشد", style="red")

        table.add_row("وضعیت اتصال:", conn_status)
        table.add_row("توضیحات:", err_msg)
        panel_style = "red"

    return Panel(table, title="[bold cyan]وضعیت Yasin-Agent[/bold cyan]", border_style=panel_style)


def make_relay_panel(relay: RelayIntegration) -> Panel:
    """ایجاد پنل وضعیت و سلامت سرویس رله (Yasin-Relay)."""
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold yellow", width=15)
    table.add_column(style="white")

    if relay.connected:
        conn_status = Text("✔ متصل (Connected)", style="bold green")
        table.add_row("وضعیت اتصال:", conn_status)

        status_info = relay.get_status()
        status_text = Text(status_info.get("status", "unknown"), style="bold green" if status_info.get("status") == "active" else "yellow")
        table.add_row("وضعیت رله:", status_text)

        for key, val in status_info.items():
            if key not in ("status", "error"):
                table.add_row(f"{key}:", Text(str(val), style="cyan"))

        panel_style = "green"
    else:
        conn_status = Text("✘ عدم اتصال (Disconnected)", style="bold red")
        err_msg = Text(relay.connection_error or "کتابخانه yasin_relay یافت نشد", style="red")

        table.add_row("وضعیت اتصال:", conn_status)
        table.add_row("توضیحات:", err_msg)
        panel_style = "red"

    return Panel(table, title="[bold cyan]وضعیت Yasin-Relay[/bold cyan]", border_style=panel_style)


def make_services_table(reports: List[ProjectReport]) -> Table:
    """ایجاد جدول وضعیت و سلامت سرویس‌های تحت نظارت."""
    table = Table(title="[bold cyan]وضعیت و سلامت سرویس‌های اکوسیستم یاسین[/bold cyan]", expand=True)
    table.add_column("نام سرویس", style="bold magenta", width=15)
    table.add_column("توضیحات", style="dim white")
    table.add_column("وضعیت فرآیند", justify="center", width=15)
    table.add_column("آخرین اجرا", justify="center", width=30)
    table.add_column("آخرین پیام گزارش‌شده", style="cyan")

    for r in reports:
        # قالب‌بندی وضعیت پروسس
        if r.process_running is None:
            proc_status = Text("—", style="dim")
        elif r.process_running:
            proc_status = Text("در حال اجرا", style="bold green")
        else:
            proc_status = Text("متوقف شده", style="bold red")

        # قالب‌بندی آخرین زمان اجرا
        if r.last_run is None:
            last_run_str = Text("بدون گزارش", style="dim")
        else:
            result_word = "موفق" if r.last_success else "ناموفق"
            result_color = "green" if r.last_success else "red"
            last_run_str = Text(f"{r.last_run} ({result_word})", style=result_color)

        table.add_row(
            r.name,
            r.description,
            proc_status,
            last_run_str,
            r.last_message or "—"
        )

    return table


def build_dashboard_layout(
    core: CoreIntegration,
    agent: AgentIntegration,
    relay: RelayIntegration,
    reports: List[ProjectReport]
) -> Layout:
    """ساخت چیدمان کلی داشبورد مانیتورینگ."""
    layout = Layout()

    # تقسیم به بخش سربرگ و بدنه اصلی
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1)
    )

    # تقسیم بدنه اصلی به ستون‌های چپ و راست
    layout["body"].split_row(
        Layout(name="left", ratio=3),
        Layout(name="right", ratio=5)
    )

    # تقسیم ستون چپ به پنل هسته و پنل عامل/رله
    layout["left"].split(
        Layout(name="core", ratio=4),
        Layout(name="agent_relay", ratio=5)
    )

    # تقسیم بخش پایین ستون چپ به عامل و رله
    layout["agent_relay"].split_row(
        Layout(name="agent", ratio=1),
        Layout(name="relay", ratio=1)
    )

    # قرار دادن پنل‌ها در چیدمان
    layout["header"].update(make_header())
    layout["core"].update(make_core_panel(core))
    layout["agent"].update(make_agent_panel(agent))
    layout["relay"].update(make_relay_panel(relay))
    layout["right"].update(Panel(make_services_table(reports), border_style="blue"))

    return layout


def display_dashboard(live_mode: bool = False, update_interval: float = 2.0) -> None:
    """نمایش داشبورد وضعیت و سلامت اکوسیستم به صورت زنده یا ایستا."""
    console = Console()

    # مقداردهی اولیه به اینتگریشن‌ها
    core = CoreIntegration()
    agent = AgentIntegration()
    relay = RelayIntegration()

    if not live_mode:
        reports = build_report()
        layout = build_dashboard_layout(core, agent, relay, reports)
        console.print(layout)
        return

    # حالت نمایش زنده و پویا
    console.clear()
    reports = build_report()
    layout = build_dashboard_layout(core, agent, relay, reports)

    with Live(layout, refresh_per_second=2, screen=True) as live:
        try:
            while True:
                # بروزرسانی مجدد کلاینت‌ها و داده‌ها
                core = CoreIntegration()
                agent = AgentIntegration()
                relay = RelayIntegration()
                reports = build_report()

                # بروزرسانی چیدمان
                layout["header"].update(make_header())
                layout["core"].update(make_core_panel(core))
                layout["agent"].update(make_agent_panel(agent))
                layout["relay"].update(make_relay_panel(relay))
                layout["right"].update(Panel(make_services_table(reports), border_style="blue"))

                live.update(layout)
                time.sleep(update_interval)
        except KeyboardInterrupt:
            # خروج بی سر و صدا در صورت فشردن Ctrl+C
            pass
