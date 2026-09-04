#!/data/data/com.termux/files/usr/bin/bash
# Phase 3 device verification checklist for YasinHub Control Plane ↔ YasinRelay.
# Does NOT invent credentials. Redact secrets. Safe to run in operator sessions.
set -euo pipefail

echo "=== Phase 3 Control Plane device verification ==="
echo "date: $(date -Is 2>/dev/null || date)"
echo "uname: $(uname -a)"
echo "PREFIX: ${PREFIX:-unset}"
echo "ANDROID_API_LEVEL: ${ANDROID_API_LEVEL:-$(getprop ro.build.version.sdk 2>/dev/null || echo unset)}"
echo "machine: $(uname -m)"
python --version 2>&1 || true
echo "LD_PRELOAD_set: $([ -n "${LD_PRELOAD:-}" ] && echo yes || echo no)"

if [ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]; then
  echo "RESULT: not Termux PREFIX — skip device-only checks"
  exit 0
fi

PY_VER="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
LIB="$PREFIX/lib/libpython${PY_VER}.so"
if [ -f "$LIB" ]; then
  echo "libpython: OK ($LIB)"
else
  echo "libpython: MISSING ($LIB)"
fi

RELAY_ROOT="${YASIN_ECOSYSTEM_ROOT:-$HOME/yasineco}/YasinRelay"
LAUNCHER="$RELAY_ROOT/.venv/bin/yasinrelay-termux"
if [ -x "$LAUNCHER" ]; then
  echo "launcher: OK ($LAUNCHER)"
  "$LAUNCHER" --help >/dev/null && echo "launcher_help: OK"
  set +e
  SOURCE_CHANNELS="" "$LAUNCHER" run --non-interactive
  code=$?
  set -e
  if [ "$code" -eq 0 ]; then
    echo "empty_source: UNEXPECTED success"
  else
    echo "empty_source_honest_fail: OK (exit $code)"
  fi
else
  echo "launcher: MISSING at $LAUNCHER"
fi

if python -c "import yasinhub" 2>/dev/null; then
  python -c "from yasinhub.services.doctor_service import DoctorService; import json; print(json.dumps(DoctorService().run()['termux'], indent=2))"
else
  echo "yasinhub: not importable in this session"
fi

echo "SOURCE_CHANNELS_set: $([ -n "${SOURCE_CHANNELS:-}" ] && echo yes || echo no)"
echo "NOTE: full publish loop requires operator SOURCE_CHANNELS/credentials — never invent them."
echo "=== end Phase 3 verification ==="
