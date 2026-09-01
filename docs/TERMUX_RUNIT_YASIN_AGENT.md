# Termux Production: Yasin-Agent under runit / termux-services

Issue **#149** / **#151** hardening — production integration on Termux.

## Target architecture

```text
termux-services (runit)
    ↓
runsv yasin-agent
    ↓
~/yasineco/Yasin-agent/.venv/bin/python -m agent_platform.server
    ↓
127.0.0.1:8080   (Authorization: Bearer <canonical token>)

YasinHub ── authenticated HTTP ──► Yasin-Agent
```

**Anti-pattern:** Hub or manual start creating a second `agent_platform.server`.

## Ownership model

| Actor | Role |
|-------|------|
| **runit** | Sole supervisor of `agent_platform.server` |
| **YasinHub** | Observer via HTTP + process detection |
| **`yasinhub.cli start yasin-agent`** | Idempotent — does not spawn if already running |

Install script stops orphan `agent_platform.server` processes so runit owns the only instance.
The `run` script refuses bind when port 8080 is already in use.

## Token contract

**Canonical source:** `~/.yasinhub/yasin-agent.token` (mode **600**).

1. Non-empty token file **always wins** over env
2. Else env (`YASIN_AGENT_SERVICE_TOKEN` / `YASINHUB_AGENT_SERVICE_TOKEN`) → persisted to file
3. Else generate + write file

Never print the token in logs or commits.

## Install

```bash
cd ~/yasineco/YasinHub
bash scripts/termux/install_yasin_agent_service.sh
sv-enable yasin-agent || true
sv up yasin-agent
sleep 2
sv status yasin-agent
```

If you briefly see `warning: yasin-agent/log: unable to open supervise/ok`, re-check after a second. Logger falls back: multilog → svlogd → append-to-file.

## Health / ready

```bash
TOKEN=$(tr -d '\n\r' < ~/.yasinhub/yasin-agent.token)
# Unauthenticated → 401
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/v1/health
# Authenticated → healthy / ready
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/health
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/ready
```

## Single-instance

```bash
pgrep -f agent_platform.server | wc -l   # must be 1
python -m yasinhub.cli start yasin-agent
pgrep -f agent_platform.server | wc -l   # still 1
```

Crash recovery: `kill -9` the PID; runit restarts; count stays 1.

## Troubleshooting duplicates

1. `sv down yasin-agent`
2. `pkill -f agent_platform.server` or re-run install script
3. `sv up yasin-agent`
4. Verify count == 1 and authenticated health
