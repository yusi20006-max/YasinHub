const CACHE = "yasinhub-v2";

self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE).then(cache =>
            cache.addAll([
                "./",
                "./index.html",
                "./style.css",
                "./app.js"
            ])
        )
    );
});


self.addEventListener("fetch", event => {
    event.respondWith(
        caches.match(event.request)
        .then(response => response || fetch(event.request))
    );
});
