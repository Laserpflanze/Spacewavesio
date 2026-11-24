/* Space Waves offline service worker.
   Precaches every game file on first visit; cache-first afterwards,
   so the game boots from cache even when the network is down. */
var CACHE = 'space-waves-v3';
var ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './Build/loader.js',
  './Build/framework.js',
  './Build/data.unityweb',
  './Build/wasm.wasm'
];

self.addEventListener('install', function (e) {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      return Promise.all(
        ASSETS.map(function (url) {
          // cache individually so one failed request doesn't drop the whole install
          return c.add(new Request(url, { cache: 'reload' })).catch(function (err) {
            console.warn('[SW] failed to cache', url, err);
          });
        })
      );
    })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  var url = new URL(e.request.url);
  var isShell = e.request.mode === 'navigate' ||
                url.pathname.endsWith('/index.html') ||
                url.pathname.endsWith('/sw.js') ||
                url.pathname.endsWith('/manifest.webmanifest');

  // Shell (index/sw/manifest): network-first so updates always propagate,
  // falling back to cache when offline.
  if (isShell) {
    e.respondWith(
      fetch(e.request).then(function (resp) {
        if (resp && resp.ok) {
          var copy = resp.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return resp;
      }).catch(function () {
        return caches.match(e.request, { ignoreSearch: true })
          .then(function (hit) { return hit || caches.match('./index.html'); });
      })
    );
    return;
  }

  // Build assets: cache-first (immutable in practice, 60 MB).
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(function (hit) {
      if (hit) return hit;
      return fetch(e.request).then(function (resp) {
        if (resp && resp.ok && url.origin === self.location.origin) {
          var copy = resp.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return resp;
      });
    })
  );
});
