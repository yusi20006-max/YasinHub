# YasinHub PWA Architecture

Issue **#56** — PWA foundation and execution control dashboard shell.

## Architecture

```text
YasinHub PWA (dashboard/)
    ↓ existing HTTP API contracts
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
| `dashboard/app.js` | Entry: route wiring, fetch orchestration |
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
| `#/fleets/:id` | Fleet detail |
| `#/events` | Event timeline (`GET /api/execution-events`) |

Navigation is client-side (hash change). No full page reload for in-app routes.

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

UI states: **loading**, **empty**, **error**, **offline**, plus a **stale** indicator when partial fetch fails.

## Safety

- No shell / filesystem / computer-use controls in the UI.
- No secrets, tokens, or credentials rendered.
- No second execution state machine in the frontend.
- Backend remains authoritative for lifecycle and 404/409 semantics.

## Out of scope for #56

WebSocket/realtime streaming, authentication, control buttons (pause/resume/cancel),
Telegram/Discord, new backend execution logic.

Later issues build on this foundation:

- **#57** — live observability / polling
- **#58** — safe controls
- **#59** — authenticated Agent transport
