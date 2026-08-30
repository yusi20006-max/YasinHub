/**
 * Typed frontend models aligned with YasinHub Observer API contracts (#50-#52).
 * No second lifecycle/state machine — display projection only.
 * @module models
 */

/** @type {ReadonlyArray<string>} */
export const EXECUTION_STATUSES = Object.freeze([
  "queued",
  "running",
  "paused",
  "succeeded",
  "failed",
  "cancelled",
]);

export function normalizeExecution(raw) {
  if (!raw || typeof raw !== "object") {
    return {
      execution_id: "",
      task_id: "",
      session_id: "",
      status: "unknown",
      capabilities: [],
      metadata: {},
      history: [],
      cancel_requested: false,
    };
  }
  const caps = Array.isArray(raw.capabilities)
    ? raw.capabilities.map(String).sort()
    : [];
  return {
    execution_id: String(raw.execution_id || ""),
    task_id: String(raw.task_id || ""),
    session_id: String(raw.session_id || ""),
    status: String(raw.status || "unknown"),
    agent_id: raw.agent_id != null ? String(raw.agent_id) : null,
    workspace: raw.workspace && typeof raw.workspace === "object" ? {
      workspace_id: String(raw.workspace.workspace_id || ""),
      path: raw.workspace.path != null ? String(raw.workspace.path) : null,
      scope: String(raw.workspace.scope || "default"),
      metadata: raw.workspace.metadata && typeof raw.workspace.metadata === "object"
        ? { ...raw.workspace.metadata }
        : {},
    } : null,
    capabilities: caps,
    created_at: typeof raw.created_at === "number" ? raw.created_at : null,
    started_at: typeof raw.started_at === "number" ? raw.started_at : null,
    finished_at: typeof raw.finished_at === "number" ? raw.finished_at : null,
    error: raw.error != null ? String(raw.error) : null,
    result: raw.result,
    metadata: raw.metadata && typeof raw.metadata === "object" ? { ...raw.metadata } : {},
    history: Array.isArray(raw.history) ? raw.history.map(String) : [],
    cancel_requested: Boolean(raw.cancel_requested),
  };
}

export function normalizeEvent(raw) {
  if (!raw || typeof raw !== "object") {
    return {
      event_id: "",
      event_type: "unknown",
      timestamp: 0,
      execution_id: "",
      task_id: "",
      session_id: "",
      status: "",
      metadata: {},
      sequence: 0,
    };
  }
  return {
    event_id: String(raw.event_id || ""),
    event_type: String(raw.event_type || "unknown"),
    timestamp: typeof raw.timestamp === "number" ? raw.timestamp : 0,
    execution_id: String(raw.execution_id || ""),
    task_id: String(raw.task_id || ""),
    session_id: String(raw.session_id || ""),
    status: String(raw.status || ""),
    metadata: raw.metadata && typeof raw.metadata === "object" ? { ...raw.metadata } : {},
    agent_id: raw.agent_id != null ? String(raw.agent_id) : null,
    workspace_id: raw.workspace_id != null ? String(raw.workspace_id) : null,
    sequence: typeof raw.sequence === "number" ? raw.sequence : 0,
    worker_id: raw.worker_id != null ? String(raw.worker_id) : null,
    parent_task_id: raw.parent_task_id != null ? String(raw.parent_task_id) : null,
  };
}

export function normalizeWorker(raw) {
  if (!raw || typeof raw !== "object") {
    return { worker_id: "", status: "unknown" };
  }
  return {
    worker_id: String(raw.worker_id || ""),
    role: String(raw.role || ""),
    objective: String(raw.objective || ""),
    status: String(raw.status || "unknown"),
    execution_id: String(raw.execution_id || ""),
    session_id: String(raw.session_id || ""),
    progress: raw.progress,
    result: raw.result,
    error: raw.error != null ? String(raw.error) : null,
    cancellation_state: raw.cancellation_state != null ? String(raw.cancellation_state) : null,
    agent_id: raw.agent_id != null ? String(raw.agent_id) : null,
  };
}

export function normalizeFleet(raw) {
  if (!raw || typeof raw !== "object") {
    return { task_id: "", status: "unknown", workers: [] };
  }
  const workers = Array.isArray(raw.workers)
    ? raw.workers.map(normalizeWorker).sort((a, b) => a.worker_id.localeCompare(b.worker_id))
    : [];
  return {
    task_id: String(raw.task_id || ""),
    status: String(raw.status || "unknown"),
    workers,
  };
}

export function statusClass(status) {
  const s = String(status || "").toLowerCase();
  if (["queued", "running", "paused", "succeeded", "failed", "cancelled",
       "cancelling", "completed_with_failures"].includes(s)) {
    return "status-" + s.replace(/_/g, "-");
  }
  return "status-unknown";
}

/** Statuses that accept pause. */
export function canPause(status) {
  return String(status || "").toLowerCase() === "running";
}

/** Statuses that accept resume. */
export function canResume(status) {
  return String(status || "").toLowerCase() === "paused";
}

/** Statuses that accept cancel (non-terminal). */
export function canCancel(status) {
  const s = String(status || "").toLowerCase();
  return ["queued", "running", "paused"].includes(s);
}

/** Fleet-level cancel when not already fully terminal. */
export function canCancelFleet(status) {
  const s = String(status || "").toLowerCase();
  return !["succeeded", "failed", "cancelled"].includes(s);
}

/** Retry/re-run from terminal failure or cancel. */
export function canRetry(status) {
  const s = String(status || "").toLowerCase();
  return ["failed", "cancelled"].includes(s);
}

/** Start from queued. */
export function canStart(status) {
  return String(status || "").toLowerCase() === "queued";
}

/** Approve/reject available when not fully terminal success/cancel. */
export function canApprove(status) {
  const s = String(status || "").toLowerCase();
  return !["succeeded", "cancelled"].includes(s);
}
