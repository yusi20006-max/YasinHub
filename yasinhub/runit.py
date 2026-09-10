"""
yasinhub/runit.py — Runit / termux-services lifecycle adapter (Issue #182).

YasinHub remains the single Control Plane and lifecycle authority. For
services already supervised by Runit, the lifecycle path is:

    PWA -> YasinHub -> Runit (sv) -> Service

This module is the ONLY place that shells out to ``sv``. Every helper is
non-interactive, Termux/Android ARM64 compatible, and never raises: failures
are returned as data so callers can fail closed. No secrets are ever logged.

Runit-managed detection is derived from the existing service directory
layout (``$PREFIX/var/service/<name>/run``), never from hard-coded
per-service lists.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def runit_service_root() -> Path:
    """Root of runit service directories (Termux-aware)."""
    prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    return Path(prefix) / "var" / "service"


def service_dir(service_name: str) -> Path:
    """Filesystem directory of a runit service, e.g. .../var/service/<name>."""
    return runit_service_root() / service_name


def is_runit_managed(service_name: str) -> bool:
    """True only when a runit service directory with an executable run file exists."""
    try:
        run_file = service_dir(service_name) / "run"
        return service_dir(service_name).is_dir() and run_file.is_file()
    except Exception:
        return False


def sv_binary() -> Optional[str]:
    """Path to ``sv`` when available, else None. Never raises."""
    try:
        return shutil.which("sv")
    except Exception:
        return None


def is_sv_available() -> bool:
    """True when the ``sv`` control tool is installed."""
    return sv_binary() is not None


@dataclass
class SvResult:
    """Outcome of one ``sv`` invocation. Diagnostics only; never secrets."""

    ok: bool = False
    action: str = ""
    service: str = ""
    detail: str = ""
    returncode: Optional[int] = None


def _run_sv(action: str, service: str, timeout: float = 10.0) -> SvResult:
    """Run ``sv <action> <service>`` non-interactively. Never raises, never prompts."""
    result = SvResult(ok=False, action=action, service=service)
    binary = sv_binary()
    if not binary:
        result.detail = "sv not available on this platform"
        return result
    if not service or not service.strip():
        result.detail = "invalid service name"
        return result
    try:
        proc = subprocess.run(
            [binary, action, service],
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout)),
        )
    except FileNotFoundError:
        result.detail = "sv binary missing"
        return result
    except subprocess.TimeoutExpired:
        result.detail = f"sv {action} timed out"
        return result
    except OSError as exc:
        result.detail = f"sv {action} failed: {type(exc).__name__}"
        return result
    except Exception:
        result.detail = f"sv {action} failed safely"
        return result
    result.returncode = proc.returncode
    output = ((proc.stdout or "") + " " + (proc.stderr or "")).strip()
    # Keep diagnostics short and secret-free (port/PID/service names only).
    result.detail = " ".join(output.split())[:300] or f"sv {action} rc={proc.returncode}"
    result.ok = proc.returncode == 0
    return result


def sv_up(service: str, timeout: float = 10.0) -> SvResult:
    """Bring a runit service up (``sv up``). Never raises."""
    return _run_sv("up", service, timeout=timeout)


def sv_down(service: str, timeout: float = 10.0) -> SvResult:
    """Bring a runit service down (``sv down``). Never raises."""
    return _run_sv("down", service, timeout=timeout)


def sv_status(service: str, timeout: float = 10.0) -> SvResult:
    """Query runit status (``sv status``). ``run:`` means running, ``down:`` stopped."""
    return _run_sv("status", service, timeout=timeout)


def parse_sv_running(detail: str) -> Optional[bool]:
    """Interpret ``sv status`` output: True=run:, False=down:, None=unknown."""
    text = (detail or "").strip()
    if text.startswith("run:"):
        return True
    if text.startswith("down:"):
        return False
    # Some implementations prefix with "run" / "down" without colon.
    lowered = text.lower()
    if "run:" in lowered and "down:" not in lowered:
        return True
    if "down:" in lowered:
        return False
    return None
