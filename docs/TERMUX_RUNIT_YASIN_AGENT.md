# Termux Production: Yasin-Agent under runit / termux-services

Issue **#149** — finalize production integration between YasinHub and Yasin-Agent on Termux.

## Target architecture

```text
termux-services (runit)
    ↓
runsv yasin-agent
    ↓
~/yasineco/Yasin-agent/.venv/bin/python -m agent_platform.server
    ↓
127.0.0.1:8080   (Authorization: Bearer <service token>)

YasinHub
    ↓ authenticated HTTP (YASINHUB_AGENT_BASE_URL + YASINHUB_AGENT_SERVICE_TOKEN)
    ↓
Yasin-Agent
```

**Not** the anti-pattern:

```text
YasinHub CLI → subprocess.Popen → agent_platform.server   (second instance)
```

YasinHub may still call `start yasin-agent` for operator convenience. That path is **idempotent**: if `agent_platform.server` is already running (under runit or otherwise), Hub reports the existing PIDs and does **not** spawn a duplicate.

## Canonical paths

| Component | Path |
|-----------|------|
| Ecosystem root | `~/yasineco` |
| Yasin-Agent | `~/yasineco/Yasin-agent` |
| YasinHub | `~/yasineco/YasinHub` (or wherever Hub is installed) |
| Service token file | `~/.yasinhub/yasin-agent.token` (mode `600`) |
| Agent logs (multilog) | `~/.yasinhub/logs/yasin-agent/` |

Legacy paths (`~/yasin-ecosystem/...`, `Yasin-agent-main`) are resolved at runtime by `ConfigManager._canonical_project_path` and must not be used as the live layout.

## Prerequisites on Termux

```bash
pkg update -y
pkg install -y termux-services python git

mkdir -p ~/yasineco
cd ~/yasineco
git -C Yasin-agent pull || git clone https://github.com/yusi20006-max/Yasin-agent.git Yasin-agent
git -C YasinHub pull || git clone https://github.com/yusi20006-max/YasinHub.git YasinHub

cd ~/yasineco/Yasin-agent
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e '.[server]'
```

## Install the supervised service

```bash
cd ~/yasineco/YasinHub
bash scripts/termux/install_yasin_agent_service.sh
```

This ensures `~/.yasinhub/yasin-agent.token` (mode 600), copies run scripts into `$PREFIX/var/service/yasin-agent/`, and prints activation commands.

## Activate and control

```bash
sv-enable yasin-agent || true
sv up yasin-agent
sv status yasin-agent
tail -f ~/.yasinhub/logs/yasin-agent/current
```

## Health / ready contract (must stay authenticated)

Unauthenticated requests to `/v1/health` and `/v1/ready` must return **401**.

```bash
TOKEN=$(tr -d '\n\r' < ~/.yasinhub/yasin-agent.token)
# expect 401 without Authorization
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/v1/health
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/health
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/ready
```

| Variable | Role |
|----------|------|
| `YASIN_AGENT_SERVICE_TOKEN` | Token expected by Agent server |
| `YASINHUB_AGENT_SERVICE_TOKEN` | Token used by Hub HTTP client |
| `YASINHUB_AGENT_BASE_URL` | e.g. `http://127.0.0.1:8080` |

**Never** put the real token in source, commits, logs, or error messages.

## Single-instance / crash recovery

- runit restarts the process on crash automatically.
- `pgrep -f agent_platform.server` must show exactly one process while healthy.
- `yasinhub.cli start yasin-agent` detects running process via `process_pattern="agent_platform.server"` and does not spawn another.

## YasinHub observation

```bash
python -m yasinhub.cli status
python -m yasinhub.cli agent status yasin-agent
python -m yasinhub.cli agent health yasin-agent
```

## Regression coverage

- Canonical path + migration (`tests/test_config_manager.py`)
- Token / no shell injection (`tests/test_service_manager_security.py`)
- Termux service definition (`tests/test_termux_runit_agent.py`)
