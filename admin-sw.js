const ADMIN_CACHE_NAME = "ofa-admin-shell-v1";
const ADMIN_SHELL_URLS = ["/admin", "/admin-icon.svg", "/admin-manifest.webmanifest"];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(ADMIN_CACHE_NAME)
      .then(cache => cache.addAll(ADMIN_SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key.startsWith("ofa-admin-shell-") && key !== ADMIN_CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || request.method !== "GET") return;
  if (url.pathname.startsWith("/api/")) return;
  if (url.pathname !== "/admin" && url.pathname !== "/admin-icon.svg" && url.pathname !== "/admin-manifest.webmanifest") return;

  event.respondWith(
    fetch(request)
      .then(response => {
        const copy = response.clone();
        caches.open(ADMIN_CACHE_NAME).then(cache => cache.put(request, copy));
        return response;
      })
      .catch(() => caches.match(request))
  );
});
