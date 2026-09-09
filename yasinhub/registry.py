"""
registry.py
فهرست پروژه‌هایی که YasinHub وضعیت‌شان را نشان می‌دهد.

The registry is the lifecycle source of truth. HTTP port metadata is supplied
by yasinhub.ports; worker/CLI services remain portless until an actual HTTP
runtime is verified.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    import yaml
except ImportError:
    yaml = None

from .ports import health_endpoint_for, host_for, port_for

YASIN_ECOSYSTEM_ROOT = Path(
    os.environ.get("YASIN_ECOSYSTEM_ROOT", str(Path.home() / "YasinEco"))
).expanduser()
DEFAULT_CONFIG_DIR = Path(
    os.environ.get("YASINHUB_CONFIG_DIR", str(Path.home() / ".yasinhub"))
)
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"


@dataclass
class ProjectEntry:
    name: str
    path: Optional[str] = None
    process_pattern: Optional[str] = None
    description: str = ""
    start_command: Optional[str] = None
    stop_command: Optional[str] = None
    enabled: bool = True
    host: Optional[str] = None
    port: Optional[int] = None
    health_endpoint: Optional[str] = None


DEFAULT_PROJECTS: List[ProjectEntry] = [
    ProjectEntry(
        name="yasinfeed",
        path=str(YASIN_ECOSYSTEM_ROOT / "Yasinfeed"),
        process_pattern="yasinfeed.main",
        description="سرویس فید خوان یاسین (YasinFeed)",
        start_command=f"env YASINFEED_PORT={port_for('yasinfeed')} python3 -m yasinfeed.main",
        host=host_for("yasinfeed"),
        port=port_for("yasinfeed"),
        health_endpoint=health_endpoint_for("yasinfeed"),
    ),
    ProjectEntry(
        name="eitaa_news_v2",
        process_pattern="eitaa_news_v2.py",
        description="بات خبری RSS -> @yusinews",
        start_command="python3 eitaa_news_v2.py",
        enabled=False,
    ),
    ProjectEntry(
        name="yasinrelay",
        path=str(YASIN_ECOSYSTEM_ROOT / "YasinRelay"),
        process_pattern="yasinrelay.cli",
        description="تلگرام -> AI -> ایتا",
        start_command=".venv/bin/yasinrelay-termux run --schedule --non-interactive",
        host=None,
        port=None,
        health_endpoint=None,
    ),
    ProjectEntry(
        name="yasin-agent",
        path=str(YASIN_ECOSYSTEM_ROOT / "Yasin-agent"),
        process_pattern="agent_platform.server",
        description="Yasin-Agent HTTP runtime (production: supervised by runit/termux-services)",
        # Canonical interpreter: derived from YASIN_ECOSYSTEM_ROOT. Never
        # hard-code a legacy ecosystem tree path here.
        start_command=str(YASIN_ECOSYSTEM_ROOT / "Yasin-agent" / ".venv" / "bin" / "python") + " -m agent_platform.server",
        host=host_for("yasin-agent"),
        port=port_for("yasin-agent"),
        health_endpoint=health_endpoint_for("yasin-agent"),
    ),
    ProjectEntry(
        name="yasin-ai",
        path=str(YASIN_ECOSYSTEM_ROOT / "Yasin-AI"),
        # Yasin-AI's production supervisor loop is the long-running `serve` command.
        process_pattern="yasin serve",
        description="موتور اصلی هوش مصنوعی یاسین (worker/supervisor)",
        start_command="yasin serve",
        host=None,
        port=None,
        health_endpoint=None,
    ),
    ProjectEntry(
        name="yasin-coder",
        process_pattern="yasin_coder.cli",
        description="دستیار کدنویسی یاسین",
        start_command="python3 -m yasin_coder.cli",
        enabled=False,
        host=None,
        port=None,
        health_endpoint=None,
    ),
    ProjectEntry(
        name="yasinpress",
        path=str(YASIN_ECOSYSTEM_ROOT / "YasinPress-Rewrite-"),
        process_pattern="yasinpress.cli",
        description="سیستم مدیریت و انتشار محتوای یاسین (worker)",
        start_command="python3 -m yasinpress.cli.main run",
        # YasinPress CLI runs the publishing worker; no verified HTTP listener.
        host=None,
        port=None,
        health_endpoint=None,
    ),
    ProjectEntry(
        name="backup_manager",
        process_pattern="backup_manager.py",
        description="مدیریت پشتیبان‌گیری خودکار اکوسیستم",
        start_command="python3 backup_manager.py",
        enabled=False,
    ),
]


def default_registry() -> List[ProjectEntry]:
    from .config_manager import get_projects
    return get_projects()


def load_config(config_path: Optional[Path] = None) -> List[ProjectEntry]:
    path = config_path or DEFAULT_CONFIG_PATH
    if yaml is None:
        return list(DEFAULT_PROJECTS)
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            default_yaml_content = {
                "projects": [
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
            }
            path.write_text(
                yaml.dump(default_yaml_content, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except Exception:
            return list(DEFAULT_PROJECTS)
    from .config_manager import ConfigManager
    return ConfigManager(config_path=path).get_projects()
