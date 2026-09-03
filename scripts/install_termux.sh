#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# YasinHub Termux bootstrap. Termux/Android ARM64 is a first-class target.
if [ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]; then
  echo "ERROR: this installer must run inside Termux." >&2
  exit 1
fi

# Export Android API & Native ABI compilation flags before building/installing native dependencies
export ANDROID_API_LEVEL="${ANDROID_API_LEVEL:-30}"
export CFLAGS="${CFLAGS:-} -D__ANDROID_API__=${ANDROID_API_LEVEL}"
export LDFLAGS="${LDFLAGS:-}"

pkg update -y
pkg upgrade -y
pkg install -y python git clang build-essential

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
import hashlib
import hmac
import ssl
import yasinhub

print(f"Python: {sys.version}")
print(f"YasinHub: {metadata.version('yasin-hub')}")
print(f"YasinHub import: OK ({yasinhub.__file__})")

# Crypto check
h = hmac.new(b"key", b"test", hashlib.sha256).hexdigest()
assert len(h) == 64
assert ssl.OPENSSL_VERSION
print(f"Crypto/SSL verification: OK ({ssl.OPENSSL_VERSION})")
PY

python -m pytest tests/ -q
python -m yasinhub.cli --help
python -m yasinhub.cli status

printf '%s\n' \
  'YasinHub Termux installation completed successfully.' \
  'Activate: source .venv/bin/activate' \
  'CLI: python -m yasinhub.cli --help' \
  'Status: python -m yasinhub.cli status'
