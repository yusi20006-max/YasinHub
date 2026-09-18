"""Tests for the resource-bounded Termux full-suite runner (#193)."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "test_termux_full.sh"


def test_termux_runner_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_termux_runner_preserves_full_suite_and_reports_termination():
    source = RUNNER.read_text(encoding="utf-8")
    assert 'find tests -maxdepth 1 -type f -name \'test_*.py\'' in source
    assert 'python -m pytest -q --tb=short -ra' in source
    assert "ENVIRONMENT TERMINATION" in source
    assert "TEST FAILURE" in source
    assert 'exit 1' in source
    assert "--ignore" not in source
    assert "--deselect" not in source
