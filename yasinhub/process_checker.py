"""
process_checker.py
چک این‌که آیا یک پروسس (بر اساس الگوی نام دستور) در حال اجراست، از طریق
`pgrep -f` — که هم روی Termux/Android و هم روی لینوکس معمولی کار می‌کند.

این ماژول عمداً مستقیم subprocess.run را صدا می‌زند تا بشه به‌سادگی در
تست mock شود (بدون نیاز به پروسس واقعی در حال اجرا).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class ProcessStatus:
    pattern: str
    running: bool
    pids: List[str]


def check_process(pattern: str) -> ProcessStatus:
    """
    بررسی می‌کند آیا پروسسی که خط فرمانش شامل `pattern` است در حال
    اجراست. مثال pattern: "eitaa_news_v2.py" یا "yasinrelay.cli".
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ProcessStatus(pattern=pattern, running=False, pids=[])

    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return ProcessStatus(pattern=pattern, running=bool(pids), pids=pids)
