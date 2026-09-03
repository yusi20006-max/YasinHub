const CACHE_NAME = "yasinhub-dashboard-v3";

// Keep the shell aligned with index.html. HTML and executable assets use
// network-first below so a deploy can never be masked by an older cache.
const ASSETS = [
  "/dashboard/",
  "/dashboard/index.html",
  "/dashboard/style.css?v=2",
  "/dashboard/ui20.css",
  "/dashboard/app.js",
  "/dashboard/chat.js",
  "/dashboard/ui20.js",
  "/dashboard/service-controls.js?v=3",
  "/dashboard/js/api.js",
  "/dashboard/js/models.js",
  "/dashboard/js/router.js",
  "/dashboard/js/views.js",
  "/dashboard/manifest.json",
  "/dashboard/icon-192.png",
  "/dashboard/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => Promise.all(ASSETS.map((asset) => cache.add(asset).catch(() => undefined))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.map((key) => key.startsWith("yasinhub-dashboard-") && key !== CACHE_NAME
          ? caches.delete(key)
          : undefined)
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // APIs must always reach the live backend. Never serve dashboard data from
  // the application-shell cache.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(req).catch(() => new Response(JSON.stringify({ error: "offline" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }))
    );
    return;
  }

  if (!url.pathname.startsWith("/dashboard")) return;

  const isAppShell = url.pathname === "/dashboard/"
    || url.pathname === "/dashboard/index.html"
    || url.pathname.endsWith(".js")
    || url.pathname.endsWith(".css");

  // Network-first for HTML/JS/CSS is intentional: stale executable code can
  // otherwise leave a newly deployed PWA stuck on an obsolete shell.
  if (isAppShell) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => {});
          }
          return res;
        })
        .catch(() => caches.match(req).then((cached) => cached || new Response("Offline", { status: 503 })))
    );
    return;
  }

  // Immutable-ish assets (icons/manifest) can remain cache-first with a
  // network fallback so the PWA remains usable offline.
  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => {});
      }
      return res;
    }))
  );
});
