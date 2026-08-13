const CACHE_NAME = "yasinhub-dashboard-v1";

const ASSETS = [
    "/dashboard/",
    "/dashboard/index.html",
    "/dashboard/style.css",
    "/dashboard/app.js",
    "/dashboard/manifest.json",
    "/dashboard/icon-192.png",
    "/dashboard/icon-512.png"
];

// On install, cache all application shell assets with robust per-asset tolerance
self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log("[ServiceWorker] Caching App Shell assets...");
            const cachePromises = ASSETS.map(asset => {
                return cache.add(asset).catch(err => {
                    console.warn(`[ServiceWorker] Failed to cache asset: ${asset}`, err);
                });
            });
            return Promise.all(cachePromises);
        }).then(() => {
            return self.skipWaiting();
        })
    );
});

// On activate, clean up old caches and claim clients
self.addEventListener("activate", event => {
    event.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(
                keys.map(key => {
                    if (key.startsWith("yasinhub-dashboard-") && key !== CACHE_NAME) {
                        console.log("[ServiceWorker] Removing obsolete cache:", key);
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => {
            return self.clients.claim();
        })
    );
});

// Cache first strategy for static app shell, with network backup and safe offline response
self.addEventListener("fetch", event => {
    const url = new URL(event.request.url);

    // Bypass Service Worker for any non-GET requests
    if (event.request.method !== "GET") {
        return;
    }

    // Bypass Service Worker for API endpoints (keep them dynamic and never cache secrets or dynamic data)
    if (url.pathname.includes("/api/")) {
        return;
    }

    // Only process requests within the /dashboard/ scope
    if (!url.pathname.startsWith("/dashboard/")) {
        return;
    }

    event.respondWith(
        caches.match(event.request).then(cachedResponse => {
            if (cachedResponse) {
                return cachedResponse;
            }

            // Fallback to fetch
            return fetch(event.request).then(networkResponse => {
                // Only cache verified static shell assets or static file types, not broad dynamic GET outputs
                const isStaticAsset = ASSETS.includes(url.pathname) ||
                                      url.pathname.endsWith(".html") ||
                                      url.pathname.endsWith(".css") ||
                                      url.pathname.endsWith(".js") ||
                                      url.pathname.endsWith(".json") ||
                                      url.pathname.endsWith(".png") ||
                                      url.pathname.endsWith(".svg");

                if (networkResponse && networkResponse.status === 200 && networkResponse.type === "basic" && isStaticAsset) {
                    const responseToCache = networkResponse.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, responseToCache);
                    });
                }
                return networkResponse;
            }).catch(() => {
                // Safe offline fallback when both cache and network fail
                return new Response("Offline resource not available", {
                    status: 503,
                    statusText: "Service Unavailable"
                });
            });
        })
    );
});
