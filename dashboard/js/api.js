/**
 * HTTP API client for YasinHub Observer endpoints.
 * Transport-agnostic boundary: callers depend on this module, not fetch details.
 * @module api
 */

import {
  normalizeExecution,
  normalizeEvent,
  normalizeFleet,
} from "./models.js";

const API_BASE = "";

export async function getJSON(path) {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return { ok: false, offline: true, error: false, status: null, data: null, message: "offline" };
  }
  try {
    const res = await fetch(API_BASE + path, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    let data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) {
      return { ok: false, offline: false, error: true, status: res.status, data, message: (data && data.error) || res.statusText || "request failed" };
    }
    return { ok: true, offline: false, error: false, status: res.status, data, message: null };
  } catch (e) {
    return { ok: false, offline: false, error: true, status: null, data: null, message: e && e.message ? String(e.message) : "network error" };
  }
}

export async function listExecutions(filters) {
  const qs = new URLSearchParams();
  if (filters) {
    if (filters.task_id) qs.set("task_id", filters.task_id);
    if (filters.session_id) qs.set("session_id", filters.session_id);
    if (filters.status) qs.set("status", filters.status);
  }
  const q = qs.toString();
  const result = await getJSON("/api/executions" + (q ? "?" + q : ""));
  if (!result.ok || !result.data) return result;
  const items = Array.isArray(result.data.executions) ? result.data.executions.map(normalizeExecution) : [];
  return { ...result, executions: items, count: result.data.count };
}

export async function getExecution(executionId) {
  const result = await getJSON("/api/executions/" + encodeURIComponent(executionId));
  if (!result.ok || !result.data) return result;
  return { ...result, execution: result.data.execution ? normalizeExecution(result.data.execution) : null };
}

export async function listExecutionEvents(executionId) {
  const result = await getJSON("/api/executions/" + encodeURIComponent(executionId) + "/events");
  if (!result.ok || !result.data) return result;
  const events = Array.isArray(result.data.events) ? result.data.events.map(normalizeEvent) : [];
  events.sort((a, b) => (a.sequence - b.sequence) || (a.timestamp - b.timestamp));
  return { ...result, events, count: result.data.count };
}

export async function listEvents(filters) {
  const qs = new URLSearchParams();
  if (filters) ["execution_id", "task_id", "session_id", "worker_id", "event_type", "limit"].forEach((k) => { if (filters[k] != null && filters[k] !== "") qs.set(k, String(filters[k])); });
  const q = qs.toString();
  const result = await getJSON("/api/execution-events" + (q ? "?" + q : ""));
  if (!result.ok || !result.data) return result;
  const events = Array.isArray(result.data.events) ? result.data.events.map(normalizeEvent) : [];
  events.sort((a, b) => (a.sequence - b.sequence) || (a.timestamp - b.timestamp));
  return { ...result, events, count: result.data.count };
}

export async function listFleets() {
  const result = await getJSON("/api/fleets");
  if (!result.ok || !result.data) return result;
  const fleets = Array.isArray(result.data.fleets) ? result.data.fleets.map(normalizeFleet) : [];
  return { ...result, fleets, count: result.data.count };
}

export async function getFleet(taskId) {
  const result = await getJSON("/api/fleets/" + encodeURIComponent(taskId));
  if (!result.ok || !result.data) return result;
  return { ...result, fleet: result.data.fleet ? normalizeFleet(result.data.fleet) : null };
}

export async function getSystemDashboard() { return getJSON("/api/dashboard"); }
export async function getSystemStatus() { return getJSON("/api/status"); }
export async function getHealth() { return getJSON("/api/health"); }

export async function postJSON(path, body) {
  if (typeof navigator !== "undefined" && navigator.onLine === false) return { ok: false, offline: true, error: false, status: null, data: null, message: "offline" };
  try {
    const res = await fetch(API_BASE + path, { method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" }, credentials: "same-origin", body: JSON.stringify(body || {}) });
    let data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) return { ok: false, offline: false, error: true, status: res.status, data, message: (data && (data.detail || data.error)) || res.statusText || "request failed" };
    return { ok: true, offline: false, error: false, status: res.status, data, message: null };
  } catch (e) {
    return { ok: false, offline: false, error: true, status: null, data: null, message: e && e.message ? String(e.message) : "network error" };
  }
}

export function newRequestId() {
  try { if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID(); } catch (_) {}
  return "req-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

export async function controlExecution(executionId, action, opts) {
  const requestId = (opts && opts.requestId) || newRequestId();
  const path = "/api/executions/" + encodeURIComponent(executionId) + "/" + encodeURIComponent(action);
  const body = { request_id: requestId };
  if (opts && opts.actor) body.actor = String(opts.actor);
  const result = await postJSON(path, body);
  if (!result.ok || !result.data) return { ...result, requestId };
  return { ...result, action: result.data.action || action, execution: result.data.execution ? normalizeExecution(result.data.execution) : null, requestId: result.data.request_id || requestId };
}
export async function pauseExecution(executionId, opts) { return controlExecution(executionId, "pause", opts); }
export async function resumeExecution(executionId, opts) { return controlExecution(executionId, "resume", opts); }
export async function cancelExecution(executionId, opts) { return controlExecution(executionId, "cancel", opts); }

export async function cancelFleet(taskId, opts) {
  const requestId = (opts && opts.requestId) || newRequestId();
  const path = "/api/fleets/" + encodeURIComponent(taskId) + "/cancel";
  const body = { request_id: requestId };
  if (opts && opts.actor) body.actor = String(opts.actor);
  const result = await postJSON(path, body);
  if (!result.ok || !result.data) return { ...result, requestId };
  return { ...result, action: result.data.action || "cancel", fleet: result.data.fleet ? normalizeFleet(result.data.fleet) : null, requestId: result.data.request_id || requestId };
}

export async function controlCommand(payload) {
  const body = {
    action: payload.action,
    actor: payload.actor || "pwa-user",
    source: "pwa",
    execution_id: payload.execution_id || undefined,
    correlation_id: payload.correlation_id || undefined,
    control_event_id: payload.control_event_id || payload.requestId || newRequestId(),
    target_action: payload.target_action || undefined,
    metadata: payload.metadata || {},
  };
  const result = await postJSON("/api/control", body);
  if (!result.ok || !result.data) return { ...result, control: result.data || null, policyDenied: result.status === 403, requestId: body.control_event_id };
  const data = result.data;
  return { ...result, control: data, execution: data.execution ? normalizeExecution(data.execution) : null, policyDenied: data.success === false && (data.policy && data.policy.allowed === false), requestId: data.request_id || body.control_event_id };
}
export async function controlStatus(executionId, opts) { return controlCommand({ action: "status", execution_id: executionId, actor: opts && opts.actor, correlation_id: opts && opts.correlation_id }); }
export async function controlApprove(executionId, targetAction, opts) { return controlCommand({ action: "approve", execution_id: executionId, target_action: targetAction || "production_merge", actor: opts && opts.actor, correlation_id: opts && opts.correlation_id }); }
export async function controlReject(executionId, targetAction, opts) { return controlCommand({ action: "reject", execution_id: executionId, target_action: targetAction || "production_merge", actor: opts && opts.actor, correlation_id: opts && opts.correlation_id }); }
export async function controlRetry(executionId, opts) { return controlCommand({ action: "retry", execution_id: executionId, actor: opts && opts.actor, correlation_id: opts && opts.correlation_id }); }
export async function controlRerun(executionId, opts) { return controlCommand({ action: "re-run", execution_id: executionId, actor: opts && opts.actor, correlation_id: opts && opts.correlation_id }); }
export async function controlCancelViaAPI(executionId, opts) { return controlCommand({ action: "cancel", execution_id: executionId, actor: opts && opts.actor, correlation_id: opts && opts.correlation_id }); }
