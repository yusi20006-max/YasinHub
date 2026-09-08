"""
config_manager.py
لایه مدیریت پیکربندی مرکزی YasinHub.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

DEFAULT_CONFIG_DIR = Path(os.environ.get("YASINHUB_CONFIG_DIR", str(Path.home() / ".yasinhub")))
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"


class ValidationError(ValueError):
    pass


@dataclass
class ProjectConfig:
    name: str
    process_pattern: Optional[str] = None
    description: str = ""
    start_command: Optional[str] = None
    stop_command: Optional[str] = None


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        config_data: Dict[str, Any] = {"projects": []}
        if yaml is not None and self.config_path.exists():
            try:
                loaded = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    config_data.update(loaded)
            except Exception as e:
                print(f"هشدار: خطا در خواندن فایل پیکربندی: {e}", file=sys.stderr)

        if not config_data.get("projects"):
            from .registry import DEFAULT_PROJECTS
            config_data["projects"] = [
                {
                    "name": p.name,
                    "path": p.path,
                    "process_pattern": p.process_pattern,
                    "description": p.description,
                    "start_command": p.start_command,
                    "stop_command": p.stop_command,
                    "enabled": p.enabled,
                    "host": p.host,
                    "port": p.port,
                    "health_endpoint": p.health_endpoint,
                }
                for p in DEFAULT_PROJECTS
            ]
        else:
            # Canonical port metadata is authoritative. A stale local config
            # must not resurrect a retired/synthetic HTTP port assignment.
            from .ports import health_endpoint_for, host_for, port_for
            for proj in config_data["projects"]:
                if not isinstance(proj, dict) or not proj.get("name"):
                    continue
                name = proj["name"]
                canonical_port = port_for(name)
                canonical_host = host_for(name)
                canonical_endpoint = health_endpoint_for(name)
                proj["port"] = canonical_port
                proj["host"] = canonical_host
                proj["health_endpoint"] = canonical_endpoint
                # Migrate the known broken Agent command from Issue #179's
                # first registry revision. Do not manufacture a virtualenv.
                if name == "yasin-agent" and proj.get("start_command") == ".venv/bin/python -m agent_platform.server":
                    proj["start_command"] = "python3 -m agent_platform.server.app"
                if name == "yasinfeed":
                    stored = proj.get("path")
                    if stored and str(stored).endswith("/Yasinfeed-main"):
                        proj["path"] = str(Path(stored).with_name("Yasinfeed"))

        status_dir_env = os.environ.get("YASIN_STATUS_DIR") or os.environ.get("YASINHUB_STATUS_DIR")
        if status_dir_env:
            config_data["status_dir"] = status_dir_env
        logs_dir_env = os.environ.get("YASINHUB_LOGS_DIR")
        if logs_dir_env:
            config_data["logs_dir"] = logs_dir_env
        if "status_dir" not in config_data:
            config_data["status_dir"] = str(Path.home() / ".yasin_status")
        if "logs_dir" not in config_data:
            config_data["logs_dir"] = str(Path.home() / ".yasinhub" / "logs")

        self.validate_config(config_data)
        self._config = config_data
        return self._config

    def validate_config(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise ValidationError("پیکربندی باید یک دیکشنری معتبر باشد.")
        if "status_dir" in data and not isinstance(data["status_dir"], str):
            raise ValidationError("فیلد status_dir باید رشته باشد.")
        if "logs_dir" in data and not isinstance(data["logs_dir"], str):
            raise ValidationError("فیلد logs_dir باید رشته باشد.")
        if "projects" in data:
            if not isinstance(data["projects"], list):
                raise ValidationError("فیلد projects باید لیستی از پروژه‌ها باشد.")
            seen_names = set()
            for idx, proj in enumerate(data["projects"]):
                if not isinstance(proj, dict):
                    raise ValidationError(f"پروژه با ایندکس {idx} باید یک دیکشنری باشد.")
                name = proj.get("name")
                if not name or not isinstance(name, str):
                    raise ValidationError(f"پروژه با ایندکس {idx} فاقد نام معتبر (رشته غیر خالی) است.")
                if name in seen_names:
                    raise ValidationError(f"نام پروژه '{name}' تکراری است.")
                seen_names.add(name)
                for field in ("path", "process_pattern", "description", "start_command", "stop_command", "host", "health_endpoint"):
                    val = proj.get(field)
                    if val is not None and not isinstance(val, str):
                        raise ValidationError(f"فیلد {field} در پروژه '{name}' باید رشته باشد.")
                if "port" in proj and proj["port"] is not None:
                    if not isinstance(proj["port"], int) or isinstance(proj["port"], bool):
                        raise ValidationError(f"فیلد port در پروژه '{name}' باید عدد صحیح باشد.")
                    if not 1 <= proj["port"] <= 65535:
                        raise ValidationError(f"فیلد port در پروژه '{name}' خارج از محدوده معتبر است.")
                if "enabled" in proj and not isinstance(proj["enabled"], bool):
                    raise ValidationError(f"فیلد enabled در پروژه '{name}' باید بولی باشد.")

    def reload_config(self) -> Dict[str, Any]:
        return self.load_config()

    def get_config(self) -> Dict[str, Any]:
        return self._config

    def get_status_dir(self) -> Path:
        return Path(os.path.expanduser(self._config.get("status_dir") or str(Path.home() / ".yasin_status")))

    def get_logs_dir(self) -> Path:
        return Path(os.path.expanduser(self._config.get("logs_dir") or str(Path.home() / ".yasinhub" / "logs")))

    @staticmethod
    def _canonical_project_path(path: Optional[str]) -> Optional[str]:
        if not path:
            return path
        from .registry import YASIN_ECOSYSTEM_ROOT
        expanded = Path(os.path.expanduser(path))
        try:
            is_canonical = expanded == YASIN_ECOSYSTEM_ROOT or YASIN_ECOSYSTEM_ROOT in expanded.parents
        except Exception:
            is_canonical = False
        if is_canonical:
            candidate = expanded
        else:
            parts = expanded.parts
            candidate = None
            for legacy_marker in ("yasin-ecosystem", "yasineco"):
                if legacy_marker in parts:
                    idx = parts.index(legacy_marker)
                    relative_parts = parts[idx + 1 :]
                    candidate = YASIN_ECOSYSTEM_ROOT.joinpath(*relative_parts) if relative_parts else YASIN_ECOSYSTEM_ROOT
                    break
            if candidate is None:
                candidate = expanded
        if candidate.exists():
            return str(candidate)
        if candidate.name.endswith("-main"):
            canonical = candidate.with_name(candidate.name[:-5])
            if canonical.exists():
                return str(canonical)
        if candidate != expanded and expanded.exists():
            return str(expanded)
        return str(candidate)

    def get_projects(self) -> List[ProjectConfig]:
        from .ports import health_endpoint_for, host_for, port_for
        from .registry import ProjectEntry
        projects_list = []
        for item in self._config.get("projects", []):
            name = item["name"]
            projects_list.append(
                ProjectEntry(
                    name=name,
                    path=self._canonical_project_path(item.get("path")),
                    process_pattern=item.get("process_pattern"),
                    description=item.get("description", ""),
                    start_command=item.get("start_command"),
                    stop_command=item.get("stop_command"),
                    enabled=item.get("enabled", True),
                    host=host_for(name),
                    port=port_for(name),
                    health_endpoint=health_endpoint_for(name),
                )
            )
        return projects_list


_manager = ConfigManager()


def get_config() -> Dict[str, Any]:
    return _manager.get_config()


def get_projects() -> List[Any]:
    return _manager.get_projects()


def get_status_dir() -> Path:
    return _manager.get_status_dir()


def get_logs_dir() -> Path:
    return _manager.get_logs_dir()


def reload_config() -> Dict[str, Any]:
    return _manager.reload_config()


def validate_config(data: Dict[str, Any]) -> None:
    _manager.validate_config(data)
