# YasinHub Authentication (#109)

Authentication establishes **identity**. Authorization remains with **Policy**.

## Modes

| `YASIN_AUTH_MODE` | Behavior |
|-------------------|----------|
| `production` | Bearer token **required** on `/api/interface`, `/api/control`, direct service mutations under `/api/control/<service>/<action>`, Observer mutations (`pause`, `resume`, `cancel`, fleet `cancel`), and the operational audit read surface `/api/audit`. Soft `X-Actor` / body `actor` cannot authenticate. |
| `development` | Soft actor allowed (role VIEWER). Bearer token accepted when configured. |
| `test` | Soft actor allowed (role OPERATOR for local control tests). |

If `YASIN_AUTH_TOKENS` is set and mode is unset, mode defaults to **production**.

## Token configuration

```bash
export YASIN_AUTH_MODE=production
export YASIN_AUTH_TOKENS='tok_live_abc:admin:alice,tok_live_def:operator:bob'
```

Format per entry: `token:role[:yasin_user_id]`

Roles: `VIEWER` | `OPERATOR` | `DEVELOPER` | `ADMIN`

## HTTP usage

```http
POST /api/interface
Authorization: Bearer tok_live_abc
Content-Type: application/json

{"text":"status","thread_id":"s1"}
```

Authenticated principal **overrides** client-supplied `actor` / `yasin_user_id`.

## Slack

Unchanged. Slack continues to use HMAC signature verification, replay protection,
and `YASIN_SLACK_IDENTITY_MAP`. HTTP token auth does not apply to Slack routes.

## Security properties

- Tokens are never logged (only short SHA-256 fingerprints on failure).
- Constant-time token compare.
- Unauthenticated production requests cannot reach HTTP control mutations.
- `VIEWER` is read-only for HTTP control and cannot query the operational audit surface; `OPERATOR`, `DEVELOPER`, and `ADMIN` may perform standard control mutations and read audit history.
- Authenticated principal identity overrides body/query/header actor hints; actor spoofing cannot elevate role.
- Direct service controls and Observer mutations are authorized through the existing PolicyEngine and retain audit/idempotency handling.
- Policy / audit / `control_event_id` remain authoritative after identity is established.


## HTTP mutation inventory (#190)

The reviewed HTTP mutation surface is:

- `POST /api/control/<service>/<action>` — Bearer authentication + existing PolicyEngine role enforcement.
- `POST /api/control` and `POST /api/control/command` — Bearer authentication + existing ControlAPI/PolicyEngine boundary.
- Observer `POST /api/executions/<id>/{pause,resume,cancel}` — Bearer authentication + PolicyEngine.
- Observer `POST /api/fleets/<task_id>/cancel` — Bearer authentication + PolicyEngine.
- `POST /api/events/cleanup` and `POST /api/events/clear` — Bearer authentication + PolicyEngine `events_cleanup` role enforcement.
- `GET /api/events/cleanup` and `GET /api/events/clear` are also treated as mutations because they execute cleanup and use the same security boundary.

No read-only endpoint was changed solely for this inventory. Authenticated identity remains authoritative over client actor fields; cleanup idempotency uses the existing control-event/idempotency headers where supplied.
