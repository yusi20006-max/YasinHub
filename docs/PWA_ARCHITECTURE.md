# YasinHub PWA Architecture

Issues **#56** (foundation), **#57** (live observability), **#58** (safe controls).

## Architecture

```text
YasinHub PWA (dashboard/)
    ↓ existing HTTP API contracts (polling + control POST)
YasinHub Observer + Control
    ↓ integration adapter
Yasin-Agent runtime
    ↓
Yasin-MCP governance
```

The PWA is a static shell served by the Hub HTTP server under `/dashboard/`.
It consumes Observer APIs only; it does **not** implement execution lifecycle,
authorization, or tool governance.

## Application structure

| Path | Role |
|------|------|
| `dashboard/index.html` | App shell, navigation landmarks |
| `dashboard/style.css` | Responsive layout (mobile + desktop) |
| `dashboard/app.js` | Entry: route wiring, fetch, polling, controls |
| `dashboard/js/router.js` | Hash router (`#/…`) |
| `dashboard/js/api.js` | HTTP client for Observer + Control endpoints |
| `dashboard/js/models.js` | Typed normalize helpers + control availability |
| `dashboard/js/views.js` | Loading / empty / error / content / control bars |
| `dashboard/sw.js` | Service worker (app-shell cache) |
| `dashboard/manifest.json` | Installable PWA manifest |

## Routing

| Hash route | View |
|------------|------|
| `#/` | Overview / system status (`GET /api/dashboard`) |
| `#/executions` | Execution list (`GET /api/executions`) |
| `#/executions/:id` | Execution detail + events + controls |
| `#/fleets` | Fleet list (`GET /api/fleets`) |
| `#/fleets/:id` | Fleet detail + cancel |
| `#/events` | Event timeline (`GET /api/execution-events`) |

Navigation is client-side (hash change). No full page reload for in-app routes.

## Live observability (#57)

- **Polling / revalidation**: list routes every 5s; detail routes every 3s.
- Polling pauses when the document is hidden or the browser is offline.
- Soft refresh avoids a full loading flash when content is already rendered.
- Generation counter drops stale responses after route changes.
- Live indicator + last-updated timestamp in the page meta row.
- Stale indicator when a partial fetch fails.
- Event lists are sorted by `(sequence, timestamp)` in the API client.
- Fleet views show per-status worker breakdown and progress/error columns.

## Safe controls (#58)

Control plane is exposed through the existing Hub POST endpoints:

- `POST /api/executions/{id}/pause`
- `POST /api/executions/{id}/resume`
- `POST /api/executions/{id}/cancel`
- `POST /api/fleets/{task_id}/cancel`

Behaviour:

- Buttons are enabled only when the current status can accept the action
  (`running`→pause, `paused`→resume, non-terminal→cancel).
- Cancel (execution and fleet) requires an explicit browser confirm.
- Request body carries a generated `request_id` for correlation only;
  the frontend never supplies authenticated actor identity as authority.
- After every control response (success or 404/409), the UI re-fetches
  server state — no permanent optimistic mutation.
- 404 (unknown resource) and 409 (invalid transition) are rendered clearly
  in the control feedback region.

## API boundary

Consumed (unchanged contracts):

- `GET /api/executions`
- `GET /api/executions/{id}`
- `GET /api/executions/{id}/events`
- `GET /api/execution-events`
- `GET /api/fleets`
- `GET /api/fleets/{task_id}`
- `GET /api/dashboard` (overview)
- `GET /api/health`
- `POST /api/executions/{id}/{pause|resume|cancel}`
- `POST /api/fleets/{task_id}/cancel`

UI states: **loading**, **empty**, **error**, **offline**, plus a **stale** indicator.

## Safety

- No shell / filesystem / computer-use controls in the UI.
- No secrets, tokens, or credentials rendered.
- No second execution state machine in the frontend.
- Backend remains authoritative for lifecycle and 404/409 semantics.

## Out of scope

- Authentication / real Agent transport → **#59**
- WebSocket streaming (polling is the initial transport)
- Telegram/Discord
- New authorization or Agent lifecycle logic in the frontend
