"""YasinHub Doctor — runtime and Termux/Control Plane diagnostics."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict

from yasinhub.services.ecosystem_service import EcosystemService


class DoctorService:
    def __init__(self) -> None:
        self.ecosystem = EcosystemService()

    def python_check(self) -> Dict[str, Any]:
        return {
            "version": sys.version,
            "version_info": list(sys.version_info[:3]),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "status": "ok",
        }

    def termux_check(self) -> Dict[str, Any]:
        """Report Termux/Android signals without requiring a device."""
        prefix = os.environ.get("PREFIX", "")
        is_termux_prefix = prefix == "/data/data/com.termux/files/usr"
        prefix_exists = bool(prefix) and Path(prefix).is_dir()
        api_level = os.environ.get("ANDROID_API_LEVEL", "")
        if not api_level:
            try:
                import subprocess

                r = subprocess.run(
                    ["getprop", "ro.build.version.sdk"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if r.returncode == 0 and r.stdout.strip().isdigit():
                    api_level = r.stdout.strip()
            except Exception:
                pass

        ld_preload = os.environ.get("LD_PRELOAD", "")
        libpython = ""
        if is_termux_prefix and prefix_exists:
            ver = f"{sys.version_info.major}.{sys.version_info.minor}"
            candidate = Path(prefix) / "lib" / f"libpython{ver}.so"
            libpython = str(candidate) if candidate.is_file() else f"missing:{candidate}"

        return {
            "PREFIX": prefix or None,
            "is_termux_prefix": is_termux_prefix,
            "prefix_exists": prefix_exists,
            "ANDROID_API_LEVEL": api_level or None,
            "LD_PRELOAD_set": bool(ld_preload),
            "LD_PRELOAD_redacted": "set" if ld_preload else None,
            "libpython": libpython or None,
            "on_device": is_termux_prefix and prefix_exists,
        }

    def control_plane_check(self) -> Dict[str, Any]:
        """Registry contract for YasinRelay without starting processes."""
        try:
            from yasinhub.registry import default_registry

            projects = {p.name: p for p in default_registry()}
            relay = projects.get("yasinrelay")
            if relay is None:
                return {"yasinrelay": "missing", "status": "fail"}
            return {
                "yasinrelay": {
                    "start_command": relay.start_command,
                    "process_pattern": relay.process_pattern,
                    "path": relay.path,
                    "canonical": relay.start_command
                    == ".venv/bin/yasinrelay-termux run --schedule --non-interactive",
                },
                "status": "ok",
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def ecosystem_check(self) -> Any:
        return self.ecosystem.health()

    def run(self) -> Dict[str, Any]:
        return {
            "doctor": "YasinHub Doctor",
            "python": self.python_check(),
            "termux": self.termux_check(),
            "control_plane": self.control_plane_check(),
            "ecosystem": self.ecosystem_check(),
        }
