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

/**
 * @typedef {Object} ApiResult
 * @property {boolean} ok
 * @property {boolean} offline
 * @property {boolean} error
 * @property {number|null} status
 * @property {*} [data]
 * @property {string|null} [message]
 */

/**
 * Low-level JSON GET.
 * @param {string} path
 * @returns {Promise<ApiResult>}
 */
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
    try {
      data = await res.json();
    } catch (_) {
      data = null;
    }
    if (!res.ok) {
      return {
        ok: false,
        offline: false,
        error: true,
        status: res.status,
        data,
        message: (data && data.error) || res.statusText || "request failed",
      };
    }
    return { ok: true, offline: false, error: false, status: res.status, data, message: null };
  } catch (e) {
    return {
      ok: false,
      offline: false,
      error: true,
      status: null,
      data: null,
      message: e && e.message ? String(e.message) : "network error",
    };
  }
}

/**
 * @param {Object} [filters]
 * @returns {Promise<ApiResult & {executions?: import('./models.js').ExecutionModel[]}>
 */
export async function listExecutions(filters) {
  const qs = new URLSearchParams();
  if (filters) {
    if (filters.task_id) qs.set("task_id", filters.task_id);
    if (filters.session_id) qs.set("session_id", filters.session_id);
    if (filters.status) qs.set("status", filters.status);
  }
  const q = qs.toString();
  const path = "/api/executions" + (q ? "?" + q : "");
  const result = await getJSON(path);
  if (!result.ok || !result.data) return result;
  const items = Array.isArray(result.data.executions)
    ? result.data.executions.map(normalizeExecution)
    : [];
  return { ...result, executions: items, count: result.data.count };
}

/**
 * @param {string} executionId
 */
export async function getExecution(executionId) {
  const result = await getJSON("/api/executions/" + encodeURIComponent(executionId));
  if (!result.ok || !result.data) return result;
  const exec = result.data.execution
    ? normalizeExecution(result.data.execution)
    : null;
  return { ...result, execution: exec };
}

/**
 * @param {string} executionId
 */
export async function listExecutionEvents(executionId) {
  const result = await getJSON(
    "/api/executions/" + encodeURIComponent(executionId) + "/events"
  );
  if (!result.ok || !result.data) return result;
  const events = Array.isArray(result.data.events)
    ? result.data.events.map(normalizeEvent)
    : [];
  events.sort((a, b) => (a.sequence - b.sequence) || (a.timestamp - b.timestamp));
  return { ...result, events, count: result.data.count };
}

/**
 * @param {Object} [filters]
 */
export async function listEvents(filters) {
  const qs = new URLSearchParams();
  if (filters) {
    ["execution_id", "task_id", "session_id", "worker_id", "event_type", "limit"].forEach((k) => {
      if (filters[k] != null && filters[k] !== "") qs.set(k, String(filters[k]));
    });
  }
  const q = qs.toString();
  const result = await getJSON("/api/execution-events" + (q ? "?" + q : ""));
  if (!result.ok || !result.data) return result;
  const events = Array.isArray(result.data.events)
    ? result.data.events.map(normalizeEvent)
    : [];
  events.sort((a, b) => (a.sequence - b.sequence) || (a.timestamp - b.timestamp));
  return { ...result, events, count: result.data.count };
}

/**
 * @returns {Promise<ApiResult & {fleets?: import('./models.js').FleetModel[]}>
 */
export async function listFleets() {
  const result = await getJSON("/api/fleets");
  if (!result.ok || !result.data) return result;
  const fleets = Array.isArray(result.data.fleets)
    ? result.data.fleets.map(normalizeFleet)
    : [];
  return { ...result, fleets, count: result.data.count };
}

/**
 * @param {string} taskId
 */
export async function getFleet(taskId) {
  const result = await getJSON("/api/fleets/" + encodeURIComponent(taskId));
  if (!result.ok || !result.data) return result;
  const fleet = result.data.fleet ? normalizeFleet(result.data.fleet) : null;
  return { ...result, fleet };
}

/**
 * System overview (existing dashboard API).
 */
export async function getSystemDashboard() {
  return getJSON("/api/dashboard");
}

/**
 * Health probe.
 */
export async function getHealth() {
  return getJSON("/api/health");
}

/**
 * Low-level JSON POST for control plane.
 * @param {string} path
 * @param {Object} [body]
 * @returns {Promise<ApiResult>}
 */
export async function postJSON(path, body) {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return { ok: false, offline: true, error: false, status: null, data: null, message: "offline" };
  }
  try {
    const res = await fetch(API_BASE + path, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      credentials: "same-origin",
      body: JSON.stringify(body || {}),
    });
    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      data = null;
    }
    if (!res.ok) {
      return {
        ok: false,
        offline: false,
        error: true,
        status: res.status,
        data,
        message:
          (data && (data.detail || data.error)) ||
          res.statusText ||
          "request failed",
      };
    }
    return { ok: true, offline: false, error: false, status: res.status, data, message: null };
  } catch (e) {
    return {
      ok: false,
      offline: false,
      error: true,
      status: null,
      data: null,
      message: e && e.message ? String(e.message) : "network error",
    };
  }
}

/**
 * Generate a correlation id for control requests (not an auth identity).
 */
export function newRequestId() {
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
  } catch (_) {}
  return "req-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

/**
 * @param {string} executionId
 * @param {"pause"|"resume"|"cancel"} action
 * @param {Object} [opts]
 */
export async function controlExecution(executionId, action, opts) {
  const requestId = (opts && opts.requestId) || newRequestId();
  const path =
    "/api/executions/" +
    encodeURIComponent(executionId) +
    "/" +
    encodeURIComponent(action);
  // Actor is optional display hint only; backend resolves authenticated identity.
  const body = { request_id: requestId };
  if (opts && opts.actor) body.actor = String(opts.actor);
  const result = await postJSON(path, body);
  if (!result.ok || !result.data) return { ...result, requestId };
  const exec = result.data.execution
    ? normalizeExecution(result.data.execution)
    : null;
  return {
    ...result,
    action: result.data.action || action,
    execution: exec,
    requestId: result.data.request_id || requestId,
  };
}

export async function pauseExecution(executionId, opts) {
  return controlExecution(executionId, "pause", opts);
}

export async function resumeExecution(executionId, opts) {
  return controlExecution(executionId, "resume", opts);
}

export async function cancelExecution(executionId, opts) {
  return controlExecution(executionId, "cancel", opts);
}

/**
 * @param {string} taskId
 * @param {Object} [opts]
 */
export async function cancelFleet(taskId, opts) {
  const requestId = (opts && opts.requestId) || newRequestId();
  const path = "/api/fleets/" + encodeURIComponent(taskId) + "/cancel";
  const body = { request_id: requestId };
  if (opts && opts.actor) body.actor = String(opts.actor);
  const result = await postJSON(path, body);
  if (!result.ok || !result.data) return { ...result, requestId };
  const fleet = result.data.fleet ? normalizeFleet(result.data.fleet) : null;
  return {
    ...result,
    action: result.data.action || "cancel",
    fleet,
    requestId: result.data.request_id || requestId,
  };
}

/**
 * Unified Control API (#81/#82) — channel-neutral control surface.
 * All privileged operations go through /api/control.
 * @param {Object} payload
 * @returns {Promise<ApiResult & {control?: Object}>}
 */
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
  if (!result.ok || !result.data) {
    return {
      ...result,
      control: result.data || null,
      policyDenied: result.status === 403,
      requestId: body.control_event_id,
    };
  }
  const data = result.data;
  const exec = data.execution ? normalizeExecution(data.execution) : null;
  return {
    ...result,
    control: data,
    execution: exec,
    policyDenied: data.success === false && (data.policy && data.policy.allowed === false),
    requestId: data.request_id || body.control_event_id,
  };
}

export async function controlStatus(executionId, opts) {
  return controlCommand({
    action: "status",
    execution_id: executionId,
    actor: opts && opts.actor,
    correlation_id: opts && opts.correlation_id,
  });
}

export async function controlApprove(executionId, targetAction, opts) {
  return controlCommand({
    action: "approve",
    execution_id: executionId,
    target_action: targetAction || "production_merge",
    actor: opts && opts.actor,
    correlation_id: opts && opts.correlation_id,
  });
}

export async function controlReject(executionId, targetAction, opts) {
  return controlCommand({
    action: "reject",
    execution_id: executionId,
    target_action: targetAction || "production_merge",
    actor: opts && opts.actor,
    correlation_id: opts && opts.correlation_id,
  });
}

export async function controlRetry(executionId, opts) {
  return controlCommand({
    action: "retry",
    execution_id: executionId,
    actor: opts && opts.actor,
    correlation_id: opts && opts.correlation_id,
  });
}

export async function controlRerun(executionId, opts) {
  return controlCommand({
    action: "re-run",
    execution_id: executionId,
    actor: opts && opts.actor,
    correlation_id: opts && opts.correlation_id,
  });
}

export async function controlCancelViaAPI(executionId, opts) {
  return controlCommand({
    action: "cancel",
    execution_id: executionId,
    actor: opts && opts.actor,
    correlation_id: opts && opts.correlation_id,
  });
}
