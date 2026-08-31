# YasinHub Authentication (#109)

Authentication establishes **identity**. Authorization remains with **Policy**.

## Modes

| `YASIN_AUTH_MODE` | Behavior |
|-------------------|----------|
| `production` | Bearer token **required** on `/api/interface` and `/api/control`. Soft `X-Actor` / body `actor` cannot authenticate. |
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
- Unauthenticated production requests cannot reach Control API mutations.
- Policy / audit / `control_event_id` remain authoritative after identity is established.
