/**
 * View renderers: loading, empty, error, content.
 * Observability-focused projections (#57). No lifecycle authority.
 * @module views
 */
import { statusClass } from "./models.js";
import { navigate } from "./router.js";

export function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function formatTs(ts) {
  if (ts == null || typeof ts !== "number") return "—";
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch (_) {
    return String(ts);
  }
}

export function renderLoading(el, message) {
  el.innerHTML = `<div class="state state-loading" role="status">${escapeHtml(message || "Loading…")}</div>`;
}

export function renderEmpty(el, message) {
  el.innerHTML = `<div class="state state-empty">${escapeHtml(message || "No data")}</div>`;
}

export function renderError(el, message, offline) {
  const cls = offline ? "state state-error state-offline" : "state state-error";
  el.innerHTML = `<div class="${cls}" role="alert">${escapeHtml(message || "Error")}</div>`;
}

function workerStatusCounts(workers) {
  const counts = {};
  for (const w of workers || []) {
    const s = String(w.status || "unknown").toLowerCase();
    counts[s] = (counts[s] || 0) + 1;
  }
  return counts;
}

export function renderOverview(el, data) {
  const d = (data && data.dashboard) || data || {};
  el.innerHTML = `
    <section class="cards overview-cards" aria-label="System metrics">
      <article class="card"><h3>Projects</h3><p class="metric">${escapeHtml(d.total_projects ?? 0)}</p></article>
      <article class="card"><h3>Running</h3><p class="metric">${escapeHtml(d.running ?? 0)}</p></article>
      <article class="card"><h3>Success</h3><p class="metric">${escapeHtml(d.success ?? 0)}</p></article>
      <article class="card"><h3>Failed</h3><p class="metric">${escapeHtml(d.failed ?? 0)}</p></article>
      <article class="card"><h3>Unknown</h3><p class="metric">${escapeHtml(d.unknown ?? 0)}</p></article>
    </section>
    <p class="hint">Live observer surface. Backend remains authoritative for lifecycle.</p>`;
}

export function renderExecutionsList(el, executions) {
  if (!executions.length) {
    renderEmpty(el, "No executions yet.");
    return;
  }
  const rows = executions
    .map(
      (e) => `
    <tr data-id="${escapeHtml(e.execution_id)}" class="clickable-row">
      <td><code>${escapeHtml(e.execution_id)}</code></td>
      <td>${escapeHtml(e.task_id || "—")}</td>
      <td><span class="badge ${statusClass(e.status)}">${escapeHtml(e.status)}</span></td>
      <td>${escapeHtml(e.agent_id || "—")}</td>
      <td>${escapeHtml(formatTs(e.created_at))}</td>
      <td>${escapeHtml(e.error || "—")}</td>
    </tr>`
    )
    .join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table" aria-label="Executions">
    <thead><tr>
      <th>Execution</th><th>Task</th><th>Status</th><th>Agent</th><th>Created</th><th>Error</th>
    </tr></thead>
    <tbody>${rows}</tbody></table></div>`;
  el.querySelectorAll("tr.clickable-row").forEach((row) => {
    row.addEventListener("click", () => {
      const id = row.getAttribute("data-id");
      if (id) navigate("/executions/" + encodeURIComponent(id));
    });
  });
}

export function renderExecutionDetail(el, exec, events) {
  const caps = (exec.capabilities || [])
    .map((c) => `<span class="cap-chip">${escapeHtml(c)}</span>`)
    .join("");
  const ws = exec.workspace;
  const history = (exec.history || [])
    .map((h) => `<span class="badge ${statusClass(h)}">${escapeHtml(h)}</span>`)
    .join(" → ");

  const eventItems =
    events && events.length
      ? events
          .map(
            (ev) => `
      <li class="event-item">
        <span class="event-seq">#${escapeHtml(ev.sequence)}</span>
        <span class="event-type">${escapeHtml(ev.event_type)}</span>
        <span class="badge ${statusClass(ev.status)}">${escapeHtml(ev.status)}</span>
        <span class="event-meta">
          ${ev.worker_id ? `worker=<code>${escapeHtml(ev.worker_id)}</code> ` : ""}
          task=<code>${escapeHtml(ev.task_id || "—")}</code>
        </span>
        <span class="event-ts">${escapeHtml(formatTs(ev.timestamp))}</span>
      </li>`
          )
          .join("")
      : "";

  el.innerHTML = `
    <div class="detail-header">
      <button type="button" class="btn-link" data-back="executions">← Executions</button>
      <h2><code>${escapeHtml(exec.execution_id)}</code></h2>
      <span class="badge ${statusClass(exec.status)}">${escapeHtml(exec.status)}</span>
      ${exec.cancel_requested ? '<span class="badge status-cancelling">cancel requested</span>' : ""}
    </div>
    <div class="detail-grid">
      <div class="detail-item"><span class="label">Task</span><code>${escapeHtml(exec.task_id || "—")}</code></div>
      <div class="detail-item"><span class="label">Session</span><code>${escapeHtml(exec.session_id || "—")}</code></div>
      <div class="detail-item"><span class="label">Agent</span>${escapeHtml(exec.agent_id || "—")}</div>
      <div class="detail-item"><span class="label">Created</span>${escapeHtml(formatTs(exec.created_at))}</div>
      <div class="detail-item"><span class="label">Started</span>${escapeHtml(formatTs(exec.started_at))}</div>
      <div class="detail-item"><span class="label">Finished</span>${escapeHtml(formatTs(exec.finished_at))}</div>
      ${
        ws
          ? `<div class="detail-item"><span class="label">Workspace</span>
            <code>${escapeHtml(ws.workspace_id || "—")}</code>
            <div class="hint">${escapeHtml(ws.scope || "")} ${ws.path ? "· " + escapeHtml(ws.path) : ""}</div>
          </div>`
          : ""
      }
      ${
        exec.error
          ? `<div class="detail-item"><span class="label">Error</span><span style="color:var(--danger)">${escapeHtml(exec.error)}</span></div>`
          : ""
      }
    </div>
    ${caps ? `<div class="caps-list" aria-label="Capabilities">${caps}</div>` : ""}
    ${history ? `<p class="hint">History: ${history}</p>` : ""}
    <h3 style="margin:16px 0 8px;font-size:0.95rem">Events</h3>
    ${
      eventItems
        ? `<ul class="event-list timeline">${eventItems}</ul>`
        : `<div class="state state-empty">No events for this execution.</div>`
    }`;

  const back = el.querySelector("[data-back]");
  if (back) back.addEventListener("click", () => navigate("/executions"));
}

export function renderFleetsList(el, fleets) {
  if (!fleets.length) {
    renderEmpty(el, "No fleets yet.");
    return;
  }
  const rows = fleets
    .map((f) => {
      const counts = workerStatusCounts(f.workers);
      const summary = Object.entries(counts)
        .map(([s, n]) => `${n} ${s}`)
        .join(", ");
      return `
    <tr data-id="${escapeHtml(f.task_id)}" class="clickable-row">
      <td><code>${escapeHtml(f.task_id)}</code></td>
      <td><span class="badge ${statusClass(f.status)}">${escapeHtml(f.status)}</span></td>
      <td>${escapeHtml((f.workers || []).length)}</td>
      <td class="hint">${escapeHtml(summary || "—")}</td>
    </tr>`;
    })
    .join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table" aria-label="Fleets">
    <thead><tr><th>Task</th><th>Status</th><th>Workers</th><th>Breakdown</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
  el.querySelectorAll("tr.clickable-row").forEach((row) => {
    row.addEventListener("click", () => {
      const id = row.getAttribute("data-id");
      if (id) navigate("/fleets/" + encodeURIComponent(id));
    });
  });
}

export function renderFleetDetail(el, fleet) {
  const counts = workerStatusCounts(fleet.workers);
  const stats = Object.entries(counts)
    .map(
      ([s, n]) =>
        `<span class="stat"><span class="badge ${statusClass(s)}">${escapeHtml(s)}</span> ${n}</span>`
    )
    .join("");

  const workers = (fleet.workers || [])
    .map(
      (w) => `
    <tr>
      <td><code>${escapeHtml(w.worker_id)}</code></td>
      <td>${escapeHtml(w.role || "—")}</td>
      <td><span class="badge ${statusClass(w.status)}">${escapeHtml(w.status)}</span></td>
      <td><code>${escapeHtml(w.execution_id || "—")}</code></td>
      <td><code>${escapeHtml(w.session_id || "—")}</code></td>
      <td>${w.progress != null ? escapeHtml(String(w.progress)) : "—"}</td>
      <td>${escapeHtml(w.error || "—")}</td>
    </tr>`
    )
    .join("");

  el.innerHTML = `
    <div class="detail-header">
      <button type="button" class="btn-link" data-back="fleets">← Fleets</button>
      <h2><code>${escapeHtml(fleet.task_id)}</code></h2>
      <span class="badge ${statusClass(fleet.status)}">${escapeHtml(fleet.status)}</span>
    </div>
    <div class="fleet-summary">${stats || '<span class="hint">No workers</span>'}</div>
    <div class="table-wrap"><table class="data-table" aria-label="Workers">
      <thead><tr>
        <th>Worker</th><th>Role</th><th>Status</th><th>Execution</th><th>Session</th><th>Progress</th><th>Error</th>
      </tr></thead>
      <tbody>${workers || '<tr><td colspan="7">No workers</td></tr>'}</tbody>
    </table></div>`;
  const back = el.querySelector("[data-back]");
  if (back) back.addEventListener("click", () => navigate("/fleets"));
}

export function renderEventsTimeline(el, events) {
  if (!events.length) {
    renderEmpty(el, "No execution events.");
    return;
  }
  const items = events
    .map(
      (ev) => `
    <li class="event-item">
      <span class="event-seq">#${escapeHtml(ev.sequence)}</span>
      <span class="event-type">${escapeHtml(ev.event_type)}</span>
      <span class="badge ${statusClass(ev.status)}">${escapeHtml(ev.status)}</span>
      <span class="event-meta">
        exec=<code>${escapeHtml(ev.execution_id || "—")}</code>
        ${ev.worker_id ? ` worker=<code>${escapeHtml(ev.worker_id)}</code>` : ""}
        task=<code>${escapeHtml(ev.task_id || "—")}</code>
      </span>
      <span class="event-ts">${escapeHtml(formatTs(ev.timestamp))}</span>
    </li>`
    )
    .join("");
  el.innerHTML = `<ul class="event-list timeline" aria-label="Event timeline">${items}</ul>`;
}
