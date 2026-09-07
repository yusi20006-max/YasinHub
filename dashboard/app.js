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
} from "./js/views.js";

const TITLES = {
  overview: "Overview / System Status",
};
const POLL_LIST_MS = 5000;
const appState = {
  fetchedAt: null,
  routeName: null,
  routeKey: null,
  hasContent: false,
  pollTimer: null,
  fetchGen: 0,
};

function $(id) { return document.getElementById(id); }
/**
 * Retirement filter (canonical signal only — never display-text matching).
 * A service is hidden from the dashboard iff the registry advertises it as
 * retired (`enabled === false` in /api/services). Unknown names and fetch
 * failures fail open to the legacy behavior (show everything).
 */
function buildServiceStates(servicesResult) {
  const states = {};
  const list = servicesResult && servicesResult.ok && servicesResult.data && Array.isArray(servicesResult.data.services)
    ? servicesResult.data.services
    : null;
  if (!list) return null;
  list.forEach((svc) => {
    if (svc && svc.name != null) states[String(svc.name)] = { enabled: svc.enabled !== false };
  });
  return states;
}
function isRetiredServiceName(serviceStates, name) {
  if (!serviceStates) return false;
  const entry = serviceStates[String(name)];
  return Boolean(entry && entry.enabled === false);
}
function visibleProjects(projects, serviceStates) {
  if (!Array.isArray(projects)) return [];
  if (!serviceStates) return projects;
  return projects.filter((p) => !isRetiredServiceName(serviceStates, p && p.name));
}
/**
 * Summary mirror of the backend /api/dashboard buckets
 * (server.py: RUNNING / SUCCESS / FAILED / else unknown), computed over the
 * VISIBLE (non-retired) set so cards and counters stay consistent.
 * Post aggregates use the same db_stats summation; retired entries carry
 * none, so visible-only totals equal backend totals for actives.
 */
function summarizeProjects(projects) {
  const summary = { total_projects: 0, running: 0, success: 0, failed: 0, unknown: 0, total_posts: 0, published_posts: 0, pending_posts: 0 };
  if (!Array.isArray(projects)) return summary;
  summary.total_projects = projects.length;
  projects.forEach((p) => {
    const raw = p && (p.status != null ? p.status : p.health_state);
    const st = String(raw != null ? raw : "UNKNOWN");
    if (st === "RUNNING") summary.running += 1;
    else if (st === "SUCCESS") summary.success += 1;
    else if (st === "FAILED") summary.failed += 1;
    else summary.unknown += 1;
    const db = p && p.db_stats;
    if (db) {
      summary.total_posts += Number(db.total_posts) || 0;
      summary.published_posts += Number(db.published_posts) || 0;
      summary.pending_posts += Number(db.pending_posts) || 0;
    }
  });
  return summary;
}
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
  appState.pollTimer = setInterval(() => {
    if (document.hidden || !navigator.onLine) return;
    renderRoute(parseRoute(), { soft: true });
  }, POLL_LIST_MS);
  updateMetaRow();
}

async function renderRoute(route, { soft = false } = {}) {
  const content = $("content");
  if (!content) return;
  // Observer pages (executions/fleets/events) were removed from the PWA UI;
  // any stale deep link or bookmark falls back to the overview page so no
  // dead route can render a blank view.
  if (!route || route.name !== "overview") {
    route = { name: "overview", params: {}, path: "/" };
  }
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
      const [result, statusResult, servicesResult] = await Promise.all([api.getSystemDashboard(), api.getSystemStatus(), api.getServices()]);
      if (gen !== appState.fetchGen) return;
      if (result.offline) { renderError(content, "Offline — cannot load system status.", true); setStale(true); appState.hasContent = false; return; }
      if (!result.ok) { renderError(content, result.message || "Failed to load system status."); setStale(true); appState.hasContent = false; return; }
      const projects = statusResult && statusResult.ok && statusResult.data && Array.isArray(statusResult.data.projects) ? statusResult.data.projects : [];
      const serviceStates = buildServiceStates(servicesResult);
      try { window.__yasinhubServiceStates = serviceStates; } catch (_) {}
      const visible = visibleProjects(projects, serviceStates);
      const backendSummary = result.data && result.data.dashboard ? result.data.dashboard : null;
      const data = result.data ? { ...result.data, dashboard: serviceStates ? summarizeProjects(visible) : backendSummary } : result.data;
      renderOverview(content, data, visible);
      appState.fetchedAt = Date.now(); appState.hasContent = true; setStale(false); updateMetaRow(); return;
    }
  } catch (e) {
    if (gen !== appState.fetchGen) return;
    renderError(content, e && e.message ? String(e.message) : "Unexpected error");
    setStale(true);
    appState.hasContent = false;
  }
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
