/**
 * YasinHub PWA application entry — foundation shell (#56).
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
} from "./js/views.js";

const TITLES = {
  overview: "Overview / System Status",
  executions: "Executions",
  "execution-detail": "Execution Detail",
  fleets: "Fleets",
  "fleet-detail": "Fleet Detail",
  events: "Events",
};

const appState = { fetchedAt: null, routeName: null };

function $(id) {
  return document.getElementById(id);
}

function setConnectionStatus() {
  const el = $("connection-status");
  if (!el) return;
  if (navigator.onLine) {
    el.textContent = "Online";
    el.className = "connection-status status-online";
  } else {
    el.textContent = "Offline";
    el.className = "connection-status status-offline";
  }
}

function setStale(isStale) {
  const el = $("stale-indicator");
  if (!el) return;
  el.hidden = !isStale;
}

function setActiveNav(route) {
  const key = navKey(route);
  document.querySelectorAll("[data-nav]").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("data-nav") === key);
  });
}

function setTitle(route) {
  const el = $("page-title");
  if (el) el.textContent = TITLES[route.name] || "YasinHub";
  document.title = (TITLES[route.name] || "YasinHub") + " · YasinHub";
}

async function renderRoute(route) {
  const content = $("content");
  if (!content) return;
  appState.routeName = route.name;
  setTitle(route);
  setActiveNav(route);
  setConnectionStatus();
  renderLoading(content, "Loading…");

  try {
    if (route.name === "overview") {
      const result = await api.getSystemDashboard();
      if (route.name !== appState.routeName) return;
      if (result.offline) {
        renderError(content, "Offline — cannot load system status.", true);
        setStale(true);
        return;
      }
      if (!result.ok) {
        renderError(content, result.message || "Failed to load system status.");
        setStale(true);
        return;
      }
      renderOverview(content, result.data);
      appState.fetchedAt = Date.now();
      setStale(false);
      return;
    }

    if (route.name === "executions") {
      const result = await api.listExecutions();
      if (route.name !== appState.routeName) return;
      if (result.offline) {
        renderError(content, "Offline — cannot load executions.", true);
        setStale(true);
        return;
      }
      if (!result.ok) {
        renderError(content, result.message || "Failed to load executions.");
        setStale(true);
        return;
      }
      renderExecutionsList(content, result.executions || []);
      appState.fetchedAt = Date.now();
      setStale(false);
      return;
    }

    if (route.name === "execution-detail") {
      const id = route.params.id;
      const [execRes, eventsRes] = await Promise.all([
        api.getExecution(id),
        api.listExecutionEvents(id),
      ]);
      if (route.name !== appState.routeName) return;
      if (execRes.offline) {
        renderError(content, "Offline — cannot load execution.", true);
        setStale(true);
        return;
      }
      if (!execRes.ok || !execRes.execution) {
        const msg =
          execRes.status === 404
            ? "Execution not found (404)."
            : execRes.message || "Failed to load execution.";
        renderError(content, msg);
        setStale(true);
        return;
      }
      const events = eventsRes.ok ? eventsRes.events || [] : [];
      renderExecutionDetail(content, execRes.execution, events);
      appState.fetchedAt = Date.now();
      setStale(!eventsRes.ok);
      return;
    }

    if (route.name === "fleets") {
      const result = await api.listFleets();
      if (route.name !== appState.routeName) return;
      if (result.offline) {
        renderError(content, "Offline — cannot load fleets.", true);
        setStale(true);
        return;
      }
      if (!result.ok) {
        renderError(content, result.message || "Failed to load fleets.");
        setStale(true);
        return;
      }
      renderFleetsList(content, result.fleets || []);
      appState.fetchedAt = Date.now();
      setStale(false);
      return;
    }

    if (route.name === "fleet-detail") {
      const result = await api.getFleet(route.params.id);
      if (route.name !== appState.routeName) return;
      if (result.offline) {
        renderError(content, "Offline — cannot load fleet.", true);
        setStale(true);
        return;
      }
      if (!result.ok || !result.fleet) {
        const msg =
          result.status === 404
            ? "Fleet not found (404)."
            : result.message || "Failed to load fleet.";
        renderError(content, msg);
        setStale(true);
        return;
      }
      renderFleetDetail(content, result.fleet);
      appState.fetchedAt = Date.now();
      setStale(false);
      return;
    }

    if (route.name === "events") {
      const result = await api.listEvents({ limit: 100 });
      if (route.name !== appState.routeName) return;
      if (result.offline) {
        renderError(content, "Offline — cannot load events.", true);
        setStale(true);
        return;
      }
      if (!result.ok) {
        renderError(content, result.message || "Failed to load events.");
        setStale(true);
        return;
      }
      renderEventsTimeline(content, result.events || []);
      appState.fetchedAt = Date.now();
      setStale(false);
      return;
    }
  } catch (e) {
    renderError(content, e && e.message ? String(e.message) : "Unexpected error");
    setStale(true);
  }
}

function wireChrome() {
  const themeBtn = $("theme-toggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      document.body.classList.toggle("dark");
    });
  }
  const navToggle = $("nav-toggle");
  const sidebar = $("sidebar");
  if (navToggle && sidebar) {
    navToggle.addEventListener("click", () => {
      const open = sidebar.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
  const refreshBtn = $("refresh-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      renderRoute(parseRoute());
    });
  }
  window.addEventListener("online", () => {
    setConnectionStatus();
    renderRoute(parseRoute());
  });
  window.addEventListener("offline", () => {
    setConnectionStatus();
    setStale(true);
  });
}

function registerSW() {
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/dashboard/sw.js", { scope: "/dashboard/" })
      .catch(() => {});
  });
}

function boot() {
  wireChrome();
  registerSW();
  setConnectionStatus();
  onRouteChange((route) => {
    const sidebar = $("sidebar");
    if (sidebar) sidebar.classList.remove("open");
    renderRoute(route);
  });
  renderRoute(parseRoute());
}

boot();
