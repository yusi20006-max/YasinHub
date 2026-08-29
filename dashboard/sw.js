const CACHE_NAME = "yasinhub-dashboard-v2";

const ASSETS = [
  "/dashboard/",
  "/dashboard/index.html",
  "/dashboard/style.css",
  "/dashboard/app.js",
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
    caches.open(CACHE_NAME).then((cache) => {
      const cachePromises = ASSETS.map((asset) =>
        cache.add(asset).catch(() => undefined)
      );
      return Promise.all(cachePromises);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key.startsWith("yasinhub-dashboard-") && key !== CACHE_NAME) {
            return caches.delete(key);
          }
          return undefined;
        })
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(req).catch(() =>
        new Response(JSON.stringify({ error: "offline" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        })
      )
    );
    return;
  }

  if (!url.pathname.startsWith("/dashboard")) return;

  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
