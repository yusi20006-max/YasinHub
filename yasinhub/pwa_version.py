"""Canonical YasinHub PWA/package version and runtime build identity."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Single source of truth for the application/PWA release version.
PWA_VERSION = "1.0.0"


def get_build_identity() -> str:
    """Return a short Git revision, with safe runtime fallbacks."""
    configured = os.environ.get("YASINHUB_BUILD", "").strip()
    if configured:
        return configured[:64]

    repo_root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"

    build = result.stdout.strip()
    return build[:64] if result.returncode == 0 and build else "unknown"


def version_payload() -> dict[str, str]:
    """Return the public, secret-free runtime version payload."""
    return {
        "service": "YasinHub",
        "pwa_version": PWA_VERSION,
        "build": get_build_identity(),
    }
