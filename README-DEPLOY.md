# Offline Arcade — phone-friendly Railway game loader

A private, offline-capable mini arcade: one dark-mode loader page, multiple
games, zero ads, zero CrazyGames SDK network calls. Currently includes:

- **Space Waves** (build 114)
- **Traffic Rider** (build 92)

## How it works

The folder contains only SMALL files (< 25 MB each), so you can upload every
one of them to GitHub directly from your phone's browser. The Unity build
files (~160 MB total) are downloaded automatically by Docker during the
Railway build, normalized (the CDN sometimes serves brotli/gzip bytes),
verified via magic bytes, and patched: the CrazyGames SDK loader inside each
`framework.js` is replaced with a complete local stub, so games boot and save
progress with **zero network access**.

```
index.html                        ← loader (black/white dark mode)
sw.js                             ← service worker (v13): precaches the shell AND
                                     ALL Traffic Rider StreamingAssets at install
                                     (16 FMOD banks incl. 13 per-bike banks + 28
                                     Unity bundles: menu scene + every purchasable
                                     bike model). Missing menusceneasset = black
                                     screen after the first mission; missing a
                                     bike bundle or the bike's .bank = infinite
                                     loading when riding it — so .bank requests
                                     that are missing on the CDN fall back to a
                                     valid bank instead of hanging
manifest.webmanifest
server.py                         ← static server, correct MIME + cache headers
Dockerfile                        ← runs fetch_build.py at Railway build time
fetch_build.py                    ← downloads + verifies + patches all games
games/space-waves/index.html      ← game wrapper (SDK stub, DPR cap, no ads)
games/traffic-rider/index.html    ← game wrapper (ASTC texture auto-select)
```

## Deploy steps from your phone

1. **GitHub:** open your existing repo → Add file → Upload files →
   replace `index.html`, `sw.js`, `server.py`, `fetch_build.py`,
   `manifest.webmanifest` and add the two new `games/*/index.html`
   (create the folders when uploading: name the file
   `games/space-waves/index.html` — GitHub web accepts paths in the
   filename box). Commit → Railway redeploys automatically.
2. **Railway:** build takes a few minutes (downloads the game files).
3. **First run per game:** open the loader, tap the game once ON WIFI —
   the service worker caches its files as it downloads them.
4. **After that:** fully offline. School wifi? Airplane mode? Doesn't matter.

## Notes

- Keep the Railway URL **private** — personal use only, don't share it.
- "Not cached" on the loader = that game hasn't had its first online run yet.
- Traffic Rider auto-picks the ASTC texture set on mobile GPUs (iPads) and
  the desktop set elsewhere — both files are cached separately, and only the
  one your device uses is ever downloaded.
- "Reset cache" (footer of the loader, or the link inside each game) wipes
  all cached files and re-downloads on the next run.
- **Adding another game:** find it on crazygames.com, view the page source
  for its `files.crazygames.com/.../Build/...` URLs, append an entry in
  `fetch_build.py` (GAMES dict), copy any `games/*/index.html` wrapper and
  adjust the build file names, add the new game row + status check to the
  loader, and bump the CACHE version in `sw.js`. Then upload the changed
  files.
