/**
 * Lightweight hash router for the YasinHub PWA shell.
 * Routes:
 *   #/                 → overview
 *   #/executions       → executions list
 *   #/executions/:id   → execution detail
 *   #/fleets           → fleets list
 *   #/fleets/:id       → fleet detail
 *   #/events           → events timeline
 *   #/yasin            → Yasin conversational surface
 * @module router
 */

/**
 * @typedef {Object} Route
 * @property {string} name
 * @property {Object.<string, string>} params
 * @property {string} path
 */

/**
 * @param {string} [hash]
 * @returns {Route}
 */
export function parseRoute(hash) {
  let raw = (hash != null ? hash : (typeof location !== "undefined" ? location.hash : "")) || "";
  if (raw.startsWith("#")) raw = raw.slice(1);
  if (raw.startsWith("/")) raw = raw.slice(1);
  const parts = raw.split("/").filter(Boolean);

  if (parts.length === 0) {
    return { name: "overview", params: {}, path: "/" };
  }
  if (parts[0] === "executions") {
    if (parts[1]) {
      return { name: "execution-detail", params: { id: decodeURIComponent(parts[1]) }, path: "/executions/" + parts[1] };
    }
    return { name: "executions", params: {}, path: "/executions" };
  }
  if (parts[0] === "fleets") {
    if (parts[1]) {
      return { name: "fleet-detail", params: { id: decodeURIComponent(parts[1]) }, path: "/fleets/" + parts[1] };
    }
    return { name: "fleets", params: {}, path: "/fleets" };
  }
  if (parts[0] === "events") {
    return { name: "events", params: {}, path: "/events" };
  }
  if (parts[0] === "yasin") {
    return { name: "yasin", params: {}, path: "/yasin" };
  }
  return { name: "overview", params: {}, path: "/" };
}

/**
 * Navigate without full page reload.
 * @param {string} path e.g. "/executions" or "/executions/exec-1"
 */
export function navigate(path) {
  const normalized = path.startsWith("/") ? path : "/" + path;
  if (typeof location !== "undefined") {
    location.hash = "#" + normalized;
  }
}

/**
 * @param {(route: Route) => void} handler
 * @returns {() => void} unsubscribe
 */
export function onRouteChange(handler) {
  const listener = () => handler(parseRoute());
  if (typeof window !== "undefined") {
    window.addEventListener("hashchange", listener);
  }
  return () => {
    if (typeof window !== "undefined") {
      window.removeEventListener("hashchange", listener);
    }
  };
}

/**
 * Active nav key for highlighting.
 * @param {Route} route
 * @returns {string}
 */
export function navKey(route) {
  if (route.name === "execution-detail") return "executions";
  if (route.name === "fleet-detail") return "fleets";
  return route.name;
}
