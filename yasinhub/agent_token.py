"""Canonical shared service-token contract for Yasin-Agent \u2194 YasinHub.

Source of truth (deterministic, production):
  ~/.yasinhub/yasin-agent.token   (mode 600)

Resolution order for resolve_agent_service_token():
  1. Non-empty token file (always preferred when present)
  2. YASIN_AGENT_SERVICE_TOKEN env (persisted to file if file was missing)
  3. YASINHUB_AGENT_SERVICE_TOKEN env (same)
  4. Generate a new token and write the file

Stale environment variables must NOT override an existing token file.
Never log or return the token in error messages intended for operators.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional


TOKEN_FILENAME = "yasin-agent.token"
TOKEN_DIR_NAME = ".yasinhub"


def token_path(home: Optional[Path] = None) -> Path:
    """Return the canonical path to the shared service token file."""
    base = home if home is not None else Path.home()
    return base / TOKEN_DIR_NAME / TOKEN_FILENAME


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_file(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def resolve_agent_service_token(
    *,
    env: Optional[dict] = None,
    home: Optional[Path] = None,
    persist: bool = True,
) -> str:
    """Resolve the shared Agent service token using the canonical contract.

    When the token file exists and is non-empty it always wins over environment
    variables so Hub, runit, and curl verification share one secret.
    """
    e = env if env is not None else os.environ
    path = token_path(home=home)
    file_token = _read_file(path)
    if file_token:
        return file_token

    for key in ("YASIN_AGENT_SERVICE_TOKEN", "YASINHUB_AGENT_SERVICE_TOKEN"):
        val = (e.get(key) or "").strip()
        if val:
            if persist:
                _write_file(path, val)
            return val

    token = secrets.token_urlsafe(32)
    if persist:
        _write_file(path, token)
    return token


def ensure_token_file(*, home: Optional[Path] = None) -> Path:
    """Ensure the token file exists (mode 600) and return its path."""
    path = token_path(home=home)
    resolve_agent_service_token(home=home, persist=True)
    return path
