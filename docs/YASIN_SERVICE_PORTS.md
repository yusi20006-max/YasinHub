# Yasin Dedicated HTTP Service Port Contract (Issue #179)

Single source of truth in code: `yasinhub/ports.py`
(`YASIN_RESERVED_SERVICE_PORT_RANGE`, `YASIN_SERVICE_PORT_ALLOCATION`).
The service registry (`yasinhub/registry.py` + `yasinhub/config_manager.py`)
is the authoritative source for lifecycle port configuration. No other
repository may hardcode a conflicting canonical Yasin service port.

## 1. Reserved port range

```
7000–7099  (YASIN_RESERVED_SERVICE_PORT_RANGE)
```

Rule: `7000 <= Yasin service port <= 7099`. Ports outside this range are
forbidden for canonical Yasin HTTP services unless an explicit, documented
exception exists. (Legacy `8000`/`8080`/`8101` bindings predate this contract
and are superseded by the allocation below; `YASINHUB_PORT` /
`YASIN_AGENT_PORT` env overrides remain for transitional compatibility.)

## 2. Service allocation

```
7000  YasinHub      host 0.0.0.0 (exception, see §9)   health /api/health
7001  Yasin-AI      host 127.0.0.1                     health /health
7002  Yasin-Agent   host 127.0.0.1                     health /v1/health (Bearer token)
7003  YasinPress    host 127.0.0.1                     health /api/health
7004  YasinFeed     host 127.0.0.1                     health /api/health
7005  Yasin-Coder   host 127.0.0.1                     health /health
```

New services take the next free port from this registry only.

### Services without HTTP ports (portless workers)

```
YasinRelay    -> NO HTTP PORT (worker: .venv/bin/yasinrelay-termux run --schedule --non-interactive, pattern yasinrelay.cli)
eitaa_news_v2 -> NO HTTP PORT (retired worker)
backup_manager -> NO HTTP PORT (retired worker)
```

YasinRelay architecture is unchanged by this contract.

### HTTP evidence levels (actual-code inventory)

- YasinHub: verified (`yasinhub/api/server.py`, `/api/health`).
- Yasin-Agent: verified (`agent_platform.server`, `/v1/health` + `/v1/ready`, token auth).
- YasinFeed: evidenced (`yasinfeed.api` serves `/health` + `/api/health`; port via `YASINFEED_PORT`).
- Yasin-AI: routed (`api_service` handles `GET /health`; Hub runs the `yasin serve`
  supervisor loop — HTTP adoption on 7001 is contract, enforced by Hub lifecycle).
- YasinPress / Yasin-Coder: contract reservations with conventional health paths.

## 3. Registry record (per HTTP service)

```
service_name, canonical_path, start_command, process_pattern,
host, port, health_endpoint
```

Stored configs predating `host`/`port`/`health_endpoint` are backfilled at
runtime from the central allocation; stale files keep loading (legacy path
compatibility from `b7b13bb` is preserved: canonical root stays `~/YasinEco`,
lowercase `~/yasineco` still resolves).

## 4. Process Identity + Port Ownership

A process existing on a port proves nothing. Every lifecycle operation verifies
both: `/proc/<pid>/cmdline` identity (`verify_process_identity`) plus
LISTEN-socket ownership (`verify_port_ownership`).

Ownership proof ladder:

1. Strict: `/proc/net/tcp*` inode -> PID mapping (normal Linux).
2. Correlated (platforms without owner discovery, e.g. hardened Termux
   kernels denying `/proc/net/tcp`): free-before-spawn pre-flight plus an
   occupied port plus the succeeding contract health endpoint anchor the
   verdict. Without a health anchor and without owner proof: fail closed.

## 5. Collision / unknown-owner behavior (FAIL CLOSED)

```
UNKNOWN PORT OWNER -> FAIL CLOSED
```

If the expected Yasin port is occupied by an unrelated process: do NOT kill
it, do NOT terminate it, do NOT reuse its PID, do NOT report RUNNING. The
operation fails and diagnostics record only port/PID numbers (never secrets).

## 6. Start contract

RUNNING only when ALL hold: process alive AND identity matches AND expected
port owned by that process/service AND health endpoint succeeds. Otherwise
`START FAILED`. On post-spawn verification failure only the Hub's own freshly
spawned child is stopped; unknown PIDs are never touched.

## 7. Safe restart sequence

1. Identify current service PID. 2. Verify Process Identity (foreign PIDs are
never killed). 3. Gracefully stop. 4. Verify old PID dead. 5. Verify expected
port released. 6. Start. 7. Obtain new PID. 8. Verify new identity. 9. Verify
new port ownership. 10. Verify HTTP health. 11. Only then report RUNNING.
Guards against PID reuse and stale lifecycle state.

## 8. Wrong-port behavior

A live, identity-matching process listening on a different port than expected
(`expected: 7001, actual: 7002`) is NOT RUNNING. Fail closed.

## 9. Host binding

Local Yasin HTTP services bind `127.0.0.1`. Exception: YasinHub binds
`0.0.0.0` so the PWA dashboard stays reachable; lifecycle checks target
`127.0.0.1` regardless.

## 10. Authority

YasinHub is the sole Control Plane, lifecycle authority, and PID authority
(`PWA -> YasinHub`, `CLI -> YasinHub`). The PWA never manages processes or
ports. No second control plane / PID manager / authorization system exists.

## 11. Cross-repository documentation

The full port-range contract should additionally be recorded in `YASIN-DOCS`.
This file is the minimal repository-local contract; sibling repositories
must not define conflicting ports.

## 12. Security

No secrets in code/tests/logs/docs. No `.env` exposure. No token logging
(health probes never log headers). No unknown-process kills. No broad port
scanning (only expected-port probes). No weakening of identity verification.
No bypass of YasinHub lifecycle authority.
