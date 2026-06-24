// 항상 최신 코드를 받도록 네트워크 우선(network-first) 서비스워커.
// (GitHub Pages가 옛 JS를 캐시해 업데이트가 안 보이던 문제 해결)
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  e.respondWith((async () => {
    try {
      const net = await fetch(req, { cache: "no-store" });
      const cache = await caches.open("spotlight-cache");
      cache.put(req, net.clone());
      return net;
    } catch (err) {
      const cached = await caches.match(req);
      if (cached) return cached;
      throw err;
    }
  })());
});
