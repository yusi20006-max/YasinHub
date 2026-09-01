#!/data/data/com.termux/files/usr/bin/bash
# Install Yasin-Agent as a termux-services (runit) supervised service.
# Production ownership: runit supervises agent_platform.server; YasinHub only observes.
set -euo pipefail

if [ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]; then
  echo "WARNING: not running inside Termux; continuing with PREFIX=${PREFIX:-unset}" >&2
fi

PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
HOME_DIR="${HOME}"
AGENT_ROOT="${YASIN_AGENT_ROOT:-${HOME_DIR}/yasineco/Yasin-agent}"
HUB_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SERVICE_SRC="${HUB_ROOT}/scripts/termux/yasin-agent"
SERVICE_NAME="yasin-agent"

# termux-services places services under $PREFIX/var/service
SERVICE_DIR="${PREFIX}/var/service/${SERVICE_NAME}"

echo "Installing ${SERVICE_NAME} service from ${SERVICE_SRC}"
echo "Agent root (canonical): ${AGENT_ROOT}"

if [ ! -d "${AGENT_ROOT}" ]; then
  echo "ERROR: canonical agent path missing: ${AGENT_ROOT}" >&2
  echo "Clone Yasin-agent into ~/yasineco/Yasin-agent first." >&2
  exit 1
fi

# Ensure shared token file exists with mode 600 (do not print value).
TOKEN_DIR="${HOME_DIR}/.yasinhub"
TOKEN_FILE="${TOKEN_DIR}/yasin-agent.token"
mkdir -p "${TOKEN_DIR}"
if [ ! -f "${TOKEN_FILE}" ]; then
  # Generate once; compatible with YasinHub service_manager._yasin_agent_token
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets, pathlib; p=pathlib.Path.home()/".yasinhub"/"yasin-agent.token"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(secrets.token_urlsafe(32)+"\n"); p.chmod(0o600)'
  else
    # Fallback: openssl
    openssl rand -base64 32 | tr -d '\n' > "${TOKEN_FILE}"
    echo >> "${TOKEN_FILE}"
    chmod 600 "${TOKEN_FILE}"
  fi
  echo "Created token file ${TOKEN_FILE} (mode 600)"
else
  chmod 600 "${TOKEN_FILE}" || true
  echo "Using existing token file ${TOKEN_FILE}"
fi

# Install service definition (copy, not symlink, so PREFIX layout is self-contained)
mkdir -p "${SERVICE_DIR}/log"
cp -f "${SERVICE_SRC}/run" "${SERVICE_DIR}/run"
cp -f "${SERVICE_SRC}/log/run" "${SERVICE_DIR}/log/run"
chmod 755 "${SERVICE_DIR}/run" "${SERVICE_DIR}/log/run"

# Optional down file handling: remove so service can start
rm -f "${SERVICE_DIR}/down" 2>/dev/null || true

echo "Service files installed at ${SERVICE_DIR}"
echo
echo "Next steps (Termux):"
echo "  pkg install termux-services"
echo "  sv-enable ${SERVICE_NAME}   # if available"
echo "  sv up ${SERVICE_NAME}"
echo "  sv status ${SERVICE_NAME}"
echo "  tail -f ~/.yasinhub/logs/yasin-agent/current"
echo
echo "Health (replace TOKEN from file, never commit it):"
echo "  TOKEN=\$(tr -d '\\n\\r' < ~/.yasinhub/yasin-agent.token)"
echo "  curl -sS -H \"Authorization: Bearer \$TOKEN\" http://127.0.0.1:8080/v1/health"
echo "  curl -sS -H \"Authorization: Bearer \$TOKEN\" http://127.0.0.1:8080/v1/ready"
