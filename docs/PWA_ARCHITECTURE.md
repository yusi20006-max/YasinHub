# YasinHub PWA Architecture

Issues **#56** (foundation) and **#57** (live observability).

## Architecture

```text
YasinHub PWA (dashboard/)
    ↓ existing HTTP API contracts (polling)
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
| `dashboard/app.js` | Entry: route wiring, fetch orchestration, polling |
| `dashboard/js/router.js` | Hash router (`#/…`) |
| `dashboard/js/api.js` | HTTP client for Observer endpoints |
| `dashboard/js/models.js` | Typed normalize helpers (execution/fleet/event) |
| `dashboard/js/views.js` | Loading / empty / error / content renderers |
| `dashboard/sw.js` | Service worker (app-shell cache) |
| `dashboard/manifest.json` | Installable PWA manifest |

## Routing

| Hash route | View |
|------------|------|
| `#/` | Overview / system status (`GET /api/dashboard`) |
| `#/executions` | Execution list (`GET /api/executions`) |
| `#/executions/:id` | Execution detail + events |
| `#/fleets` | Fleet list (`GET /api/fleets`) |
| `#/fleets/:id` | Fleet detail (workers, progress, partial failures) |
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

UI states: **loading**, **empty**, **error**, **offline**, plus a **stale** indicator.

## Safety

- No shell / filesystem / computer-use controls in the UI.
- No secrets, tokens, or credentials rendered.
- No second execution state machine in the frontend.
- Backend remains authoritative for lifecycle and 404/409 semantics.

## Out of scope

- **#56/#57**: control buttons (pause/resume/cancel) → **#58**
- Authentication / real Agent transport → **#59**
- WebSocket streaming (polling is the initial transport)
- Telegram/Discord
