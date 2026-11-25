/* Space Waves offline service worker.
   The shell is precached at install; the big game files (~60 MB) are cached
   at runtime, as the game itself downloads them — so nothing is ever
   downloaded twice and the tab never janks from a giant parallel pre-cache.
   Cache-first afterwards: the game boots from cache even offline. */
var CACHE = 'space-waves-v7';
var SHELL = ['./', './index.html', './manifest.webmanifest'];

self.addEventListener('install', function (e) {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      return Promise.all(SHELL.map(function (url) {
        return c.add(new Request(url, { cache: 'reload' })).catch(function (err) {
          console.warn('[SW] failed to cache', url, err);
        });
      }));
    })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      // drop every cache from older versions — old/corrupt entries can never come back
      return Promise.all(keys.filter(function (k) { return k !== CACHE; })
        .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  var url = new URL(e.request.url);

  if (url.origin !== self.location.origin) return;

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

  // Game assets: cache-first; on first visit download once and store.
  if (url.pathname.indexOf('/Build/') !== -1) {
    e.respondWith(
      caches.match(e.request, { ignoreSearch: true }).then(function (hit) {
        if (hit) return hit;
        return fetch(e.request).then(function (resp) {
          if (resp && resp.ok) {
            var copy = resp.clone();
            caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
          }
          return resp;
        });
      })
    );
  }
  // anything else: let the browser handle it
});
