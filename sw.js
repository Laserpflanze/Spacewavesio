/* Offline Arcade — service worker.
   The shell is precached at install; the big game files (~160 MB total) are
   cached at runtime, as each game itself downloads them — so nothing is ever
   downloaded twice and the tab never janks from a giant parallel pre-cache.
   Cache-first afterwards: every game boots from cache even offline. */
var CACHE = 'space-waves-v13';
var SHELL = [
  './',
  './index.html',
  './manifest.webmanifest',
  './games/space-waves/index.html',
  './games/traffic-rider/index.html',
  /* Traffic Rider StreamingAssets: precached at install so every scene
     transition, audio bank and bike model is available even on the very
     first offline run. Missing menusceneasset = stuck on a black loading
     screen after the first mission (the game reloads its menu scene from
     that bundle); missing <bike> bundle = hang when riding that bike. */
  './games/traffic-rider/StreamingAssets/Master.bank',
  './games/traffic-rider/StreamingAssets/Master.strings.bank',
  './games/traffic-rider/StreamingAssets/MBK_Nitro2.bank',
  './games/traffic-rider/StreamingAssets/AssetBundles/mbk_nitro',
  './games/traffic-rider/StreamingAssets/AssetBundles/menusceneasset',
  './games/traffic-rider/StreamingAssets/AssetBundles/aprilia_rsv4',
  './games/traffic-rider/StreamingAssets/AssetBundles/bmw_k1200s',
  './games/traffic-rider/StreamingAssets/AssetBundles/bmw_s1000rr',
  './games/traffic-rider/StreamingAssets/AssetBundles/dodge_tomahawk',
  './games/traffic-rider/StreamingAssets/AssetBundles/ducati_1098r',
  './games/traffic-rider/StreamingAssets/AssetBundles/ducati_multistrada',
  './games/traffic-rider/StreamingAssets/AssetBundles/ducati_streetfighter_v4_sp2',
  './games/traffic-rider/StreamingAssets/AssetBundles/harley_davidson_fxstc',
  './games/traffic-rider/StreamingAssets/AssetBundles/harley_davidson_vrod',
  './games/traffic-rider/StreamingAssets/AssetBundles/honda_cb750f',
  './games/traffic-rider/StreamingAssets/AssetBundles/honda_cbr_250r',
  './games/traffic-rider/StreamingAssets/AssetBundles/indian_chieftain',
  './games/traffic-rider/StreamingAssets/AssetBundles/kawasaki_h2r',
  './games/traffic-rider/StreamingAssets/AssetBundles/kawasaki_klx250',
  './games/traffic-rider/StreamingAssets/AssetBundles/kawasaki_kx450f',
  './games/traffic-rider/StreamingAssets/AssetBundles/kawasaki_ninja_zx10r',
  './games/traffic-rider/StreamingAssets/AssetBundles/kawasaki_z750',
  './games/traffic-rider/StreamingAssets/AssetBundles/kawasaki_zzr1400',
  './games/traffic-rider/StreamingAssets/AssetBundles/lazareth_lm410',
  './games/traffic-rider/StreamingAssets/AssetBundles/mv_agusta_f4',
  './games/traffic-rider/StreamingAssets/AssetBundles/pulsar_rs200',
  './games/traffic-rider/StreamingAssets/AssetBundles/suzuki_hayabusa',
  './games/traffic-rider/StreamingAssets/AssetBundles/vespa_946',
  './games/traffic-rider/StreamingAssets/AssetBundles/vyrus_alyen',
  './games/traffic-rider/StreamingAssets/AssetBundles/yamaha_midnight',
  './games/traffic-rider/StreamingAssets/AssetBundles/yamaha_vmax',
  /* Per-bike FMOD sound banks: loaded at RIDE START for bikes that define
     one — a missing bank = infinite loading screen when riding that bike. */
  './games/traffic-rider/StreamingAssets/Aprilia_RSV4.bank',
  './games/traffic-rider/StreamingAssets/Bmw_S1000RR.bank',
  './games/traffic-rider/StreamingAssets/Ducati_1098R.bank',
  './games/traffic-rider/StreamingAssets/Harley_Davidson.bank',
  './games/traffic-rider/StreamingAssets/Honda_CB750F.bank',
  './games/traffic-rider/StreamingAssets/Honda_CBR250R.bank',
  './games/traffic-rider/StreamingAssets/Honda_Shadow.bank',
  './games/traffic-rider/StreamingAssets/Kawasaki_1400_GTR.bank',
  './games/traffic-rider/StreamingAssets/Kawasaki_KLX250.bank',
  './games/traffic-rider/StreamingAssets/Kawasaki_KX450F.bank',
  './games/traffic-rider/StreamingAssets/Kawasaki_Z750.bank',
  './games/traffic-rider/StreamingAssets/Suzuki_Hayabusa_GSX1300R.bank',
  './games/traffic-rider/StreamingAssets/Vespa_946.bank'
];

/* A few bank names in the game's data (Ninja3, ZX10R, 250X) have NO file on
   the original CDN under any casing. Serving any valid FMOD bank beats the
   infinite loading screen: the game proceeds and just falls back to a
   default engine sound for those bikes. */
var BANK_FALLBACK = './games/traffic-rider/StreamingAssets/Vespa_946.bank';

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

  // Shell (loader pages, game wrapper pages, manifest): network-first so
  // updates always propagate, falling back to cache when offline.
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

  // Game assets: cache-first; on first play download once and store.
  // /StreamingAssets/ = FMOD audio banks (Traffic Rider needs them offline too).
  if (url.pathname.indexOf('/Build/') !== -1 ||
      url.pathname.indexOf('/StreamingAssets/') !== -1) {
    e.respondWith(
      caches.match(e.request, { ignoreSearch: true }).then(function (hit) {
        if (hit) return hit;
        return fetch(e.request).then(function (resp) {
          if (resp && resp.ok) {
            var copy = resp.clone();
            caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
          }
          // missing per-bike bank -> serve a valid one instead of hanging
          if ((!resp || !resp.ok) && /\.bank$/.test(url.pathname)) {
            return caches.match(BANK_FALLBACK).then(function (fb) {
              if (fb) return fb;
              return resp;
            });
          }
          return resp;
        }).catch(function () {
          // offline and not cached: same bank fallback
          if (/\.bank$/.test(url.pathname)) {
            return caches.match(BANK_FALLBACK);
          }
          throw 0;
        });
      })
    );
  }
  // anything else: let the browser handle it
});
