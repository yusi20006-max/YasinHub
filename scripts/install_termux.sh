#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# YasinHub Termux bootstrap. Termux/Android is a first-class target.
if [ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]; then
  echo "ERROR: this installer must run inside Termux." >&2
  exit 1
fi

pkg update -y
pkg upgrade -y
pkg install -y python git

PYTHON_BIN="${PREFIX}/bin/python"
"${PYTHON_BIN}" --version

rm -rf .venv
"${PYTHON_BIN}" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
python -m pip install "pytest>=8.0.0"

python - <<'PY'
import importlib.metadata as metadata
import sys
import yasinhub
print(f"Python: {sys.version}")
print(f"YasinHub: {metadata.version('yasin-hub')}")
print(f"YasinHub import: OK ({yasinhub.__file__})")
PY

python -m pytest tests/ -q
python -m yasinhub.cli --help
python -m yasinhub.cli status

printf '%s\n' \
  'YasinHub Termux installation completed successfully.' \
  'Activate: source .venv/bin/activate' \
  'CLI: python -m yasinhub.cli --help' \
  'Status: python -m yasinhub.cli status'
