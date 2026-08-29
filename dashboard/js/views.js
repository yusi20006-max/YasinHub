/** View renderers: loading, empty, error, content. @module views */
import { statusClass } from "./models.js";
import { navigate } from "./router.js";

export function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&").replace(/</g, "<").replace(/>/g, ">")
    .replace(/"/g, """).replace(/'/g, "&#039;");
}

export function formatTs(ts) {
  if (ts == null || typeof ts !== "number") return "—";
  try { return new Date(ts * 1000).toLocaleString(); } catch (_) { return String(ts); }
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

export function renderOverview(el, data) {
  const d = (data && data.dashboard) || {};
  el.innerHTML = `
    <section class="cards overview-cards">
      <article class="card"><h3>Projects</h3><p class="metric">${escapeHtml(d.total_projects ?? 0)}</p></article>
      <article class="card"><h3>Running</h3><p class="metric">${escapeHtml(d.running ?? 0)}</p></article>
      <article class="card"><h3>Success</h3><p class="metric">${escapeHtml(d.success ?? 0)}</p></article>
      <article class="card"><h3>Failed</h3><p class="metric">${escapeHtml(d.failed ?? 0)}</p></article>
      <article class="card"><h3>Unknown</h3><p class="metric">${escapeHtml(d.unknown ?? 0)}</p></article>
    </section>
    <p class="hint">Observer APIs: Executions · Fleets · Events. Backend remains authoritative.</p>`;
}

export function renderExecutionsList(el, executions) {
  if (!executions.length) { renderEmpty(el, "No executions yet."); return; }
  const rows = executions.map((e) => `
    <tr data-id="${escapeHtml(e.execution_id)}" class="clickable-row">
      <td><code>${escapeHtml(e.execution_id)}</code></td>
      <td>${escapeHtml(e.task_id)}</td>
      <td><span class="badge ${statusClass(e.status)}">${escapeHtml(e.status)}</span></td>
      <td>${escapeHtml(e.agent_id || "—")}</td>
      <td>${escapeHtml(formatTs(e.created_at))}</td>
    </tr>`).join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table" aria-label="Executions">
    <thead><tr><th>Execution</th><th>Task</th><th>Status</th><th>Agent</th><th>Created</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
  el.querySelectorAll("tr.clickable-row").forEach((row) => {
    row.addEventListener("click", () => {
      const id = row.getAttribute("data-id");
      if (id) navigate("/executions/" + encodeURIComponent(id));
    });
  });
}

export function renderExecutionDetail(el, exec, events) {
  const caps = (exec.capabilities || []).map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join(" ");
  const ws = exec.workspace
    ? `<dt>Workspace</dt><dd><code>${escapeHtml(exec.workspace.workspace_id)}</code> (${escapeHtml(exec.workspace.scope || "default")})</dd>`
    : "";
  const evRows = (events || []).map((ev) => `
    <li class="event-item">
      <span class="event-seq">#${escapeHtml(ev.sequence)}</span>
      <span class="event-type">${escapeHtml(ev.event_type)}</span>
      <span class="badge ${statusClass(ev.status)}">${escapeHtml(ev.status)}</span>
      <span class="event-ts">${escapeHtml(formatTs(ev.timestamp))}</span>
    </li>`).join("");
  el.innerHTML = `
    <div class="detail-header">
      <button type="button" class="btn-link" data-back="executions">← Executions</button>
      <h2><code>${escapeHtml(exec.execution_id)}</code></h2>
      <span class="badge ${statusClass(exec.status)}">${escapeHtml(exec.status)}</span>
    </div>
    <dl class="detail-grid">
      <dt>Task</dt><dd>${escapeHtml(exec.task_id)}</dd>
      <dt>Session</dt><dd><code>${escapeHtml(exec.session_id)}</code></dd>
      <dt>Agent</dt><dd>${escapeHtml(exec.agent_id || "—")}</dd>
      ${ws}
      <dt>Capabilities</dt><dd class="chips">${caps || "—"}</dd>
      <dt>Created</dt><dd>${escapeHtml(formatTs(exec.created_at))}</dd>
      <dt>Started</dt><dd>${escapeHtml(formatTs(exec.started_at))}</dd>
      <dt>Finished</dt><dd>${escapeHtml(formatTs(exec.finished_at))}</dd>
      <dt>History</dt><dd>${escapeHtml((exec.history || []).join(" → ") || "—")}</dd>
      ${exec.error ? `<dt>Error</dt><dd class="error-text">${escapeHtml(exec.error)}</dd>` : ""}
    </dl>
    <h3>Events</h3>
    <ul class="event-list">${evRows || '<li class="state-empty">No events</li>'}</ul>`;
  const back = el.querySelector("[data-back]");
  if (back) back.addEventListener("click", () => navigate("/executions"));
}

export function renderFleetsList(el, fleets) {
  if (!fleets.length) { renderEmpty(el, "No fleets yet."); return; }
  const rows = fleets.map((f) => `
    <tr data-id="${escapeHtml(f.task_id)}" class="clickable-row">
      <td><code>${escapeHtml(f.task_id)}</code></td>
      <td><span class="badge ${statusClass(f.status)}">${escapeHtml(f.status)}</span></td>
      <td>${escapeHtml(f.workers.length)}</td>
    </tr>`).join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table" aria-label="Fleets">
    <thead><tr><th>Task</th><th>Status</th><th>Workers</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
  el.querySelectorAll("tr.clickable-row").forEach((row) => {
    row.addEventListener("click", () => {
      const id = row.getAttribute("data-id");
      if (id) navigate("/fleets/" + encodeURIComponent(id));
    });
  });
}

export function renderFleetDetail(el, fleet) {
  const workers = (fleet.workers || []).map((w) => `
    <tr>
      <td><code>${escapeHtml(w.worker_id)}</code></td>
      <td>${escapeHtml(w.role || "—")}</td>
      <td><span class="badge ${statusClass(w.status)}">${escapeHtml(w.status)}</span></td>
      <td><code>${escapeHtml(w.execution_id || "—")}</code></td>
      <td><code>${escapeHtml(w.session_id || "—")}</code></td>
      <td>${escapeHtml(w.error || "—")}</td>
    </tr>`).join("");
  el.innerHTML = `
    <div class="detail-header">
      <button type="button" class="btn-link" data-back="fleets">← Fleets</button>
      <h2><code>${escapeHtml(fleet.task_id)}</code></h2>
      <span class="badge ${statusClass(fleet.status)}">${escapeHtml(fleet.status)}</span>
    </div>
    <div class="table-wrap"><table class="data-table" aria-label="Workers">
      <thead><tr><th>Worker</th><th>Role</th><th>Status</th><th>Execution</th><th>Session</th><th>Error</th></tr></thead>
      <tbody>${workers || '<tr><td colspan="6">No workers</td></tr>'}</tbody>
    </table></div>`;
  const back = el.querySelector("[data-back]");
  if (back) back.addEventListener("click", () => navigate("/fleets"));
}

export function renderEventsTimeline(el, events) {
  if (!events.length) { renderEmpty(el, "No execution events."); return; }
  const items = events.map((ev) => `
    <li class="event-item">
      <span class="event-seq">#${escapeHtml(ev.sequence)}</span>
      <span class="event-type">${escapeHtml(ev.event_type)}</span>
      <span class="badge ${statusClass(ev.status)}">${escapeHtml(ev.status)}</span>
      <span class="event-meta">
        exec=<code>${escapeHtml(ev.execution_id || "—")}</code>
        ${ev.worker_id ? `worker=<code>${escapeHtml(ev.worker_id)}</code>` : ""}
        task=<code>${escapeHtml(ev.task_id || "—")}</code>
      </span>
      <span class="event-ts">${escapeHtml(formatTs(ev.timestamp))}</span>
    </li>`).join("");
  el.innerHTML = `<ul class="event-list timeline">${items}</ul>`;
}
