# Space Waves — phone-friendly Railway deploy kit

This folder contains only SMALL files (< 25 MB each), so you can upload every one
of them to GitHub directly from your phone's browser. The Unity build files
(~60 MB) are downloaded automatically by Docker during the Railway build.

## Files to upload to your GitHub repo

Upload ALL of these (keep the names exactly):

- `Dockerfile`
- `fetch_build.py`
- `server.py`
- `index.html`
- `sw.js`
- `manifest.webmanifest`

That's it. 6 files, none bigger than 8 KB.

## Steps from your phone

1. **Create the repo:** github.com → + (top right) → New repository →
   name it (e.g. `space-waves`), set it to **Private** → Create.
2. **Upload:** "uploading an existing file" link (or Add file → Upload files) →
   select the 5 files → Commit changes. All are tiny, so the 25 MB web limit
   is no problem.
3. **Railway:** railway.com → sign in with GitHub → New Project →
   "Deploy from GitHub repo" → pick your repo → Deploy.
   Railway sees the `Dockerfile`, builds it (downloads the game files itself,
   takes ~1 min), and starts the server on `$PORT`.
4. **Open your game:** in the service settings → Networking → "Generate Domain"
   → open the URL. First load caches everything (service worker); after that
   it boots fast even on bad mobile internet.

## Notes

- Keep the Railway URL **private** — it's the developer's game, don't share it.
- If the build fails with a download error, the CrazyGames CDN URL for build 114
  may have changed — update the 4 URLs inside `fetch_build.py` (they come from
  the game's "game files" page source).
- The CDN sometimes serves brotli/gzip-compressed bytes depending on which of
  its edge servers answers. `fetch_build.py` detects and decompresses that
  automatically and verifies each file, so the game always gets plain,
  verified content.
- `fetch_build.py` also **patches framework.js**: the game normally loads the
  CrazyGames SDK from their CDN at runtime — offline that script never arrives
  and the game hangs forever, and online on a custom domain the SDK refuses to
  run ("sdkDisabled"). The patch replaces the CDN loader with a complete local
  stub SDK, so the game needs **zero network access for the SDK**: it boots and
  plays fully offline, online, anywhere. No ads either way.
- Everything else (fullscreen, no ads, offline cache) behaves exactly like the
  local version.
