from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_termux.sh"


def test_termux_bootstrap_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert 'export ANDROID_API_LEVEL="${ANDROID_API_LEVEL:-30}"' in text
    assert 'export CFLAGS=' in text
    assert "pkg install -y python git clang build-essential" in text
    assert 'PYTHON_BIN="${PREFIX}/bin/python"' in text
    assert '"${PYTHON_BIN}" -m venv .venv' in text
    assert "python -m pip install -e ." in text
    assert "import hashlib" in text
    assert "import hmac" in text
    assert "import ssl" in text
    assert "python -m pytest tests/ -q" in text
    assert "python -m yasinhub.cli --help" in text
    assert "python -m yasinhub.cli status" in text
