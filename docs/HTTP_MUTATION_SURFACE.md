# HTTP Mutation Surface — YasinHub (#190)

This inventory covers the HTTP API mutation paths reviewed for the P0/P1 control boundary.

## Control-plane mutations

| Surface | Method | Authentication / authorization |
|---|---|---|
| `/api/control/<service>/<action>` | POST | Bearer + existing PolicyEngine/RBAC |
| `/api/control` and `/api/control/command` | POST | Bearer + existing ControlAPI/PolicyEngine |
| `/api/executions/<id>/(pause|resume|cancel)` | POST | Bearer + existing PolicyEngine/RBAC |
| `/api/fleets/<task>/cancel` | POST | Bearer + existing PolicyEngine/RBAC |
| `/api/events/cleanup` | POST/GET | Bearer + existing PolicyEngine/RBAC |
| `/api/events/clear` | POST/GET | Bearer + existing PolicyEngine/RBAC |

## External ingress

- Slack HTTP ingress is protected by Slack's existing HMAC/replay verification.
- Monday/GitHub webhook routes retain their integration-specific verification contracts.
- The PWA/interface mutation path retains HTTP Bearer authentication.

## Read-only routes

Health, status, dashboard, services, logs, metrics, execution reads, fleet reads, and event reads were reviewed as read surfaces and were not changed by #190.

## Security contract

- Production HTTP mutations require authenticated identity.
- `VIEWER` cannot perform control mutations.
- Authenticated principal identity is authoritative; actor hints cannot elevate privileges.
- Event cleanup/clear now enters the same PolicyEngine authorization and audit/idempotency path as other control mutations.
- No new authorization framework is introduced.
