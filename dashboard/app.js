/**
 * YasinHub PWA application entry — observability + safe controls (#57/#58).
 * Polling/revalidation + control plane. No lifecycle authority in the UI.
 */
import { parseRoute, onRouteChange, navKey } from "./js/router.js";
import * as api from "./js/api.js";
import {
  renderLoading,
  renderError,
  renderOverview,
  renderExecutionsList,
  renderExecutionDetail,
  renderFleetsList,
  renderFleetDetail,
  renderEventsTimeline,
  formatControlError,
} from "./js/views.js";

const TITLES = {
  overview: "Overview / System Status",
  executions: "Executions",
  "execution-detail": "Execution Detail",
  fleets: "Fleets",
  "fleet-detail": "Fleet Detail",
  events: "Events",
};
const POLL_LIST_MS = 5000;
const POLL_DETAIL_MS = 3000;
const appState = {
  fetchedAt: null,
  routeName: null,
  routeKey: null,
  hasContent: false,
  pollTimer: null,
  fetchGen: 0,
};

function $(id) { return document.getElementById(id); }
function setConnectionStatus() {
  const el = $("connection-status");
  if (!el) return;
  el.textContent = navigator.onLine ? "Online" : "Offline";
  el.className = "connection-status " + (navigator.onLine ? "status-online" : "status-offline");
}
function setStale(isStale) { const el = $("stale-indicator"); if (el) el.hidden = !isStale; }
function setActiveNav(route) {
  const key = navKey(route);
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.getAttribute("data-nav") === key));
}
function setTitle(route) {
  const el = $("page-title");
  if (el) el.textContent = TITLES[route.name] || "YasinHub";
  document.title = (TITLES[route.name] || "YasinHub") + " · YasinHub";
}
function routeKey(route) { return route.name + ":" + (route.params.id || ""); }
function updateMetaRow() {
  let row = $("live-meta");
  if (!row) {
    const heading = document.querySelector(".page-heading");
    if (!heading) return;
    row = document.createElement("div");
    row.id = "live-meta";
    row.className = "meta-row";
    heading.insertAdjacentElement("afterend", row);
  }
  const ts = appState.fetchedAt ? new Date(appState.fetchedAt).toLocaleTimeString() : "—";
  const polling = appState.pollTimer != null && navigator.onLine && !document.hidden;
  row.innerHTML = `${polling ? '<span class="live-dot" title="Live polling"></span><span>Live</span>' : "<span>Idle</span>"}<span>Updated ${ts}</span>`;
}
function stopPolling() {
  if (appState.pollTimer != null) {
    clearInterval(appState.pollTimer);
    appState.pollTimer = null;
  }
}
function startPolling(route) {
  stopPolling();
  if (!navigator.onLine || document.hidden) { updateMetaRow(); return; }
  const isDetail = route.name === "execution-detail" || route.name === "fleet-detail";
  appState.pollTimer = setInterval(() => {
    if (document.hidden || !navigator.onLine) return;
    renderRoute(parseRoute(), { soft: true });
  }, isDetail ? POLL_DETAIL_MS : POLL_LIST_MS);
  updateMetaRow();
}

async function renderRoute(route, { soft = false } = {}) {
  const content = $("content");
  if (!content) return;
  const key = routeKey(route);
  const routeChanged = key !== appState.routeKey;
  appState.routeName = route.name;
  appState.routeKey = key;
  if (routeChanged) {
    setTitle(route);
    setActiveNav(route);
    appState.hasContent = false;
  }
  setConnectionStatus();

  // Soft refreshes keep the current rendered view visible to avoid a loading flash.
  if (!soft || !appState.hasContent) {
    renderLoading(content, soft ? "Refreshing…" : "Loading…");
  }

  const gen = ++appState.fetchGen;
  try {
    if (route.name === "overview") {
      const [result, statusResult] = await Promise.all([api.getSystemDashboard(), api.getSystemStatus()]);
      if (gen !== appState.fetchGen) return;
      if (result.offline) { renderError(content, "Offline — cannot load system status.", true); setStale(true); appState.hasContent = false; return; }
      if (!result.ok) { renderError(content, result.message || "Failed to load system status."); setStale(true); appState.hasContent = false; return; }
      const projects = statusResult && statusResult.ok && statusResult.data && Array.isArray(statusResult.data.projects) ? statusResult.data.projects : [];
      renderOverview(content, result.data, projects);
      appState.fetchedAt = Date.now(); appState.hasContent = true; setStale(false); updateMetaRow(); return;
    }
    if (route.name === "executions") {
      const result = await api.listExecutions();
      if (gen !== appState.fetchGen) return;
      if (result.offline) { renderError(content, "Offline — cannot load executions.", true); setStale(true); appState.hasContent = false; return; }
      if (!result.ok) { renderError(content, result.message || "Failed to load executions."); setStale(true); appState.hasContent = false; return; }
      renderExecutionsList(content, result.executions || []); appState.fetchedAt = Date.now(); appState.hasContent = true; setStale(false); updateMetaRow(); return;
    }
    if (route.name === "execution-detail") {
      const id = route.params.id;
      const [execRes, eventsRes] = await Promise.all([api.getExecution(id), api.listExecutionEvents(id)]);
      if (gen !== appState.fetchGen) return;
      if (execRes.offline) { renderError(content, "Offline — cannot load execution.", true); setStale(true); appState.hasContent = false; return; }
      if (!execRes.ok || !execRes.execution) { renderError(content, execRes.status === 404 ? "Execution not found (404)." : execRes.message || "Failed to load execution."); setStale(true); appState.hasContent = false; return; }
      renderExecutionDetail(content, execRes.execution, eventsRes.ok ? eventsRes.events || [] : []); appState.fetchedAt = Date.now(); appState.hasContent = true; setStale(!eventsRes.ok); updateMetaRow(); wireControls(content); return;
    }
    if (route.name === "fleets") {
      const result = await api.listFleets();
      if (gen !== appState.fetchGen) return;
      if (result.offline) { renderError(content, "Offline — cannot load fleets.", true); setStale(true); appState.hasContent = false; return; }
      if (!result.ok) { renderError(content, result.message || "Failed to load fleets."); setStale(true); appState.hasContent = false; return; }
      renderFleetsList(content, result.fleets || []); appState.fetchedAt = Date.now(); appState.hasContent = true; setStale(false); updateMetaRow(); return;
    }
    if (route.name === "fleet-detail") {
      const result = await api.getFleet(route.params.id);
      if (gen !== appState.fetchGen) return;
      if (result.offline) { renderError(content, "Offline — cannot load fleet.", true); setStale(true); appState.hasContent = false; return; }
      if (!result.ok || !result.fleet) { renderError(content, result.status === 404 ? "Fleet not found (404)." : result.message || "Failed to load fleet."); setStale(true); appState.hasContent = false; return; }
      renderFleetDetail(content, result.fleet); appState.fetchedAt = Date.now(); appState.hasContent = true; setStale(false); updateMetaRow(); wireControls(content); return;
    }
    if (route.name === "events") {
      const result = await api.listEvents({ limit: 100 });
      if (gen !== appState.fetchGen) return;
      if (result.offline) { renderError(content, "Offline — cannot load events.", true); setStale(true); appState.hasContent = false; return; }
      if (!result.ok) { renderError(content, result.message || "Failed to load events."); setStale(true); appState.hasContent = false; return; }
      renderEventsTimeline(content, result.events || []); appState.fetchedAt = Date.now(); appState.hasContent = true; setStale(false); updateMetaRow(); return;
    }
  } catch (e) {
    if (gen !== appState.fetchGen) return;
    renderError(content, e && e.message ? String(e.message) : "Unexpected error");
    setStale(true);
    appState.hasContent = false;
  }
}

function setControlFeedback(message, isError, isPending = false) {
  const el = $("control-feedback");
  if (!el) return;
  el.textContent = message || "";
  el.className = "control-feedback" + (isPending ? " control-pending" : isError ? " control-error" : " control-ok");
}
function setControlsBusy(busy) {
  document.querySelectorAll(".ctrl-btn").forEach((btn) => {
    if (busy) { btn.dataset.prevDisabled = btn.disabled ? "1" : "0"; btn.disabled = true; }
    else if (btn.dataset.prevDisabled === "0") btn.disabled = false;
  });
}
async function handleControlClick(btn) {
  const action = btn.getAttribute("data-ctrl"), id = btn.getAttribute("data-id");
  if (!action || !id) return;
  const confirmMsg = btn.getAttribute("data-confirm");
  if (confirmMsg && !window.confirm(confirmMsg)) return;
  setControlsBusy(true);
  setControlFeedback("Sending " + action + "…", false, true);
  let result;
  try {
    if (action === "pause") result = await api.pauseExecution(id);
    else if (action === "resume") result = await api.resumeExecution(id);
    else if (action === "cancel") { result = await api.controlCancelViaAPI(id); if (!result.ok && result.status !== 403) result = await api.cancelExecution(id); }
    else if (action === "fleet-cancel") result = await api.cancelFleet(id);
    else if (action === "retry") result = await api.controlRetry(id);
    else if (action === "re-run") result = await api.controlRerun(id);
    else if (action === "approve") result = await api.controlApprove(id, "production_merge");
    else if (action === "reject") result = await api.controlReject(id, "production_merge");
    else { setControlFeedback("Unknown action.", true); setControlsBusy(false); return; }
  } catch (e) { setControlFeedback(e && e.message ? String(e.message) : "Control failed", true); setControlsBusy(false); return; }
  if (!result.ok) {
    const msg = result.policyDenied || result.status === 403 ? "Policy denied: " + (result.message || (result.control && result.control.error) || "not allowed") : formatControlError(result);
    setControlFeedback(msg, true);
    setControlsBusy(false);
    await renderRoute(parseRoute(), { soft: true });
    return;
  }
  setControlFeedback("OK: " + (result.action || (result.control && result.control.action) || action) + (result.requestId ? " req=" + result.requestId : ""), false);
  await renderRoute(parseRoute(), { soft: true });
}
function wireControls(root) {
  (root || document).querySelectorAll(".ctrl-btn").forEach((btn) => {
    if (btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", (ev) => { ev.preventDefault(); handleControlClick(btn); });
  });
}
function wireChrome() {
  const themeBtn = $("theme-toggle");
  if (themeBtn) themeBtn.addEventListener("click", () => { const dark = document.body.classList.toggle("dark"); themeBtn.setAttribute("aria-pressed", dark ? "true" : "false"); });
  const navToggle = $("nav-toggle"), sidebar = $("sidebar");
  let backdrop = document.querySelector(".nav-backdrop");
  if (!backdrop) { backdrop = document.createElement("div"); backdrop.className = "nav-backdrop"; backdrop.setAttribute("aria-hidden", "true"); document.body.appendChild(backdrop); }
  const setNavOpen = (open) => { if (!sidebar || !navToggle) return; sidebar.classList.toggle("open", open); navToggle.setAttribute("aria-expanded", open ? "true" : "false"); backdrop.classList.toggle("visible", open); };
  if (navToggle && sidebar) { navToggle.addEventListener("click", () => setNavOpen(!sidebar.classList.contains("open"))); backdrop.addEventListener("click", () => setNavOpen(false)); }
  const refreshBtn = $("refresh-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", () => renderRoute(parseRoute(), { soft: false }));
  window.addEventListener("online", () => { setConnectionStatus(); renderRoute(parseRoute(), { soft: true }); startPolling(parseRoute()); });
  window.addEventListener("offline", () => { setConnectionStatus(); setStale(true); stopPolling(); updateMetaRow(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) { stopPolling(); updateMetaRow(); } else { renderRoute(parseRoute(), { soft: true }); startPolling(parseRoute()); } });
}
function registerSW() {
  if (!(typeof navigator !== "undefined" && "serviceWorker" in navigator)) return;
  window.addEventListener("load", () => navigator.serviceWorker.register("/dashboard/sw.js", { scope: "/dashboard/" }).catch(() => {}));
}
function boot() {
  wireChrome();
  registerSW();
  setConnectionStatus();
  onRouteChange((route) => { const sidebar = $("sidebar"); if (sidebar) sidebar.classList.remove("open"); stopPolling(); renderRoute(route, { soft: false }).then(() => startPolling(route)); });
  const initial = parseRoute();
  renderRoute(initial, { soft: false }).then(() => startPolling(initial));
}
boot();
