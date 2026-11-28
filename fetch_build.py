"""Docker build step: fetch the Unity WebGL build files for every game from
the CrazyGames CDN.

The CDN behaves inconsistently depending on which edge server answers the
request: the exact same URL can return the raw uncompressed content OR
brotli/gzip-compressed bytes. Serving compressed bytes as-is breaks the game
(the browser parses them as JS/data and fails).

This script normalizes every download to the plain uncompressed file the
Unity loader expects (verified via magic bytes), patches each framework.js so
no external CrazyGames SDK is ever loaded (fully offline capable), and fails
the Docker build loudly if anything still looks wrong.

Adding a new game: append an entry to GAMES below with its build file URLs
(from the game's crazygames.com page source) and create
games/<slug>/index.html (copy an existing wrapper and adjust).
"""
import gzip
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

BASE_SW = "https://files.crazygames.com/space-waves/114/Build"
BASE_TR = "https://files.crazygames.com/traffic-rider-vvq/92/Build"

# slug -> {relative path: (CDN url, magic bytes)}
GAMES = {
    "space-waves": {
        "Build/loader.js":    (BASE_SW + "/f5621fc8e6401e7302a362d609e496a1.loader.js", b"createUnityInstance"),
        "Build/data.unityweb": (BASE_SW + "/1a568795816f05437ab0d4e6f50dc4ac.data.br", b"UnityWebData1.0\0"),
        "Build/wasm.wasm":    (BASE_SW + "/c1aca0022182358dc43860f4ad8c934f.wasm.br", b"\x00asm"),
        "Build/framework.js": (BASE_SW + "/285f771aa266df412210c567c3f51a97.framework.js.br", b"unityFramework"),
    },
    "traffic-rider": {
        "Build/loader.js":          (BASE_TR + "/cba27609590673cc3e95d6eb17d640a8.loader.js", b"createUnityInstance"),
        "Build/data.unityweb":      (BASE_TR + "/6834d2611f2acc43ab198a14e50d3950.data.br", b"UnityWebData1.0\0"),
        "Build/data-astc.unityweb": (BASE_TR + "/astc_34010f8eca9bb9457eada2bdf4e595ba.data.br", b"UnityWebData1.0\0"),
        "Build/wasm.wasm":          (BASE_TR + "/45549e91792524a5c448dfd4d9a940eb.wasm.br", b"\x00asm"),
        "Build/framework.js":       (BASE_TR + "/426b65e576b84554a7f883ca826cc3a7.framework.js.br", b"unityFramework"),
        # FMOD audio banks (referenced by the game at startup; live OUTSIDE the
        # data archive in StreamingAssets/). Missing them = BankLoadException
        # and the game freezes on its logo.
        "StreamingAssets/Master.bank":        ("https://files.crazygames.com/traffic-rider-vvq/92/StreamingAssets/Master.bank", b"FEV "),
        "StreamingAssets/Master.strings.bank": ("https://files.crazygames.com/traffic-rider-vvq/92/StreamingAssets/Master.strings.bank", b"FEV "),
        # Dedicated FMOD bank for the Nitro bike (loaded when that bike spawns).
        "StreamingAssets/MBK_Nitro2.bank":    ("https://files.crazygames.com/traffic-rider-vvq/92/StreamingAssets/MBK_Nitro2.bank", b"FEV "),
        # Unity AssetBundle loaded at startup (the "Nitro" bike model).
        "StreamingAssets/AssetBundles/mbk_nitro": ("https://files.crazygames.com/traffic-rider-vvq/92/StreamingAssets/AssetBundles/mbk_nitro", b"UnityFS"),
        # Unity SCENE bundle for the menu: after EVERY race the game reloads
        # its menu scene FROM THIS BUNDLE (LoadMenuScene -> "menuScene" ->
        # StreamingAssets/AssetBundles/menusceneasset). Missing it = the
        # loading screen after the first mission never finishes (stuck on a
        # black screen forever). It is the only scene bundle the CDN ships
        # (mainsceneasset etc. are 404 - gameplay scenes live in the data file).
        "StreamingAssets/AssetBundles/menusceneasset": ("https://files.crazygames.com/traffic-rider-vvq/92/StreamingAssets/AssetBundles/menusceneasset", b"UnityFS"),
    },
}

# Licensed-bike Unity bundles: the in-game models for the purchasable
# real-world bikes (Honda CBR250R, Ducati Streetfighter, Harley Davidson,
# ...). The garage previews come from the data file, but RIDING one of these
# bikes fetches StreamingAssets/AssetBundles/<name> at runtime — a missing
# file = hang on the bike-selection/loading screen.
# Complete inventory (verified 2026-11-27..28 by exhaustive probing of 1000+
# candidate names over 8 rounds, plus live network capture of the game's own
# boot-time prefetches, which exposed yamaha_midnight).
TR_BIKE_BUNDLES = [
    "aprilia_rsv4", "bmw_k1200s", "bmw_s1000rr", "dodge_tomahawk",
    "ducati_1098r", "ducati_multistrada", "ducati_streetfighter_v4_sp2",
    "harley_davidson_fxstc", "harley_davidson_vrod", "honda_cb750f",
    "honda_cbr_250r", "indian_chieftain", "kawasaki_h2r", "kawasaki_klx250",
    "kawasaki_kx450f", "kawasaki_ninja_zx10r", "kawasaki_z750",
    "kawasaki_zzr1400", "lazareth_lm410", "mv_agusta_f4", "pulsar_rs200",
    "suzuki_hayabusa", "vespa_946", "vyrus_alyen", "yamaha_midnight",
    "yamaha_vmax",
]
BASE_TR_ROOT = "https://files.crazygames.com/traffic-rider-vvq/92"  # StreamingAssets live outside /Build
GAMES["traffic-rider"].update({
    f"StreamingAssets/AssetBundles/{s}": (
        BASE_TR_ROOT + f"/StreamingAssets/AssetBundles/{s}", b"UnityFS")
    for s in TR_BIKE_BUNDLES
})

# Per-bike FMOD sound banks: at RIDE START the game loads
# StreamingAssets/<BankName>.bank for bikes that define one (the bank-name
# table sits in the data file: Aprilia_RSV4, Bmw_S1000RR, ... 16 entries).
# Missing bank = the FMOD load never completes = infinite "loading" screen
# when riding the newly bought bike. These are RIFF/FSB5 files, not FEV.
# Verified complete on 2026-11-28: 3 further table entries (Ninja3, ZX10R,
# 250X) have NO file on the CDN under any casing — sw.js serves a fallback
# bank for those so they no longer hang.
TR_BIKE_BANKS = [
    "Aprilia_RSV4", "Bmw_S1000RR", "Ducati_1098R", "Harley_Davidson",
    "Honda_CB750F", "Honda_CBR250R", "Honda_Shadow", "Kawasaki_1400_GTR",
    "Kawasaki_KLX250", "Kawasaki_KX450F", "Kawasaki_Z750",
    "Suzuki_Hayabusa_GSX1300R", "Vespa_946",
]
GAMES["traffic-rider"].update({
    f"StreamingAssets/{b}.bank": (
        BASE_TR_ROOT + f"/StreamingAssets/{b}.bank", b"RIFF")
    for b in TR_BIKE_BANKS
})

# Marker string the Unity loader itself uses to detect its brotli wrapper
# (see hasUnityMarker in loader.js).
UNITY_BROTLI_MARKER = b"UnityWeb Compressed Content"

# The games' bundled glue normally loads the CrazyGames SDK from their CDN at
# runtime. Offline that script never arrives -> JSLibCallback_Init never fires
# -> the game hangs forever; online on our own domain it runs in "disabled"
# mode (sdkDisabled errors). We patch framework.js right after download so no
# external SDK is ever needed: a complete local stub is installed instead.
SDK_LOADER_OLD = (
    b'var script=document.createElement("script");'
    b'script.src="https://sdk.crazygames.com/crazygames-sdk-v3.js";'
    b'document.head.appendChild(script);'
    b'script.addEventListener("load",function(){')

SDK_STUB_NEW = (
    b'var script={addEventListener:function(ev,fn){if(ev==="load")setTimeout(fn,0)}};'
    b'(function(){function P(v){return Promise.resolve(v)}var noop=function(){};'
    b'var sdk={environment:"local",init:function(){return P()},'
    b'ad:{hasAdblock:function(){return P(false)},addAdblockPopupListener:noop,'
    b'requestAd:function(type,cb){cb=cb||{};setTimeout(function(){'
    b'try{if(cb.adStarted)cb.adStarted()}catch(e){}'
    b'try{if(cb.adFinished)cb.adFinished()}catch(e){}},0);return P()},'
    b'prefetchAd:function(){return P()}},'
    b'game:{settings:{},quality:"",inviteParams:{},'
    b'inviteLink:function(p){return ""},'
    b'addSettingsChangeListener:noop,addQualityChangeListener:noop,'
    b'addJoinRoomListener:noop,removeJoinRoomListener:noop,'
    b'updateRoom:function(){return P()},setGameContext:noop,clearGameContext:noop,'
    b'gameplayStart:noop,gameplayStop:noop,happytime:noop,'
    b'showInviteButton:function(p){return ""},hideInviteButton:noop,leftRoom:function(){return P()}},'
    b'user:{isUserAccountAvailable:false,'
    b'getUser:function(){return P({username:"Player",userId:"local-player",avatarUrl:""})},'
    b'getUserToken:function(){return P("")},getXsollaUserToken:function(){return P("")},'
    # REAL SDK v3 systemInfo shape (verified against sdk.crazygames.com
    # crazygames-sdk-v3.js demo mode): device type lives at
    # systemInfo.device.type — a nested object. The earlier flat
    # `deviceType:"desktop"` key was IGNORED by the game's C# SDK, so
    # CrazySDK.User.SystemInfo.DeviceType parsed empty and Traffic Rider
    # fell back to its own touch detection -> mobile mode (touch controls,
    # keyboard dead) on iPads. `device:{type:"desktop"}` forces desktop mode.
    b'systemInfo:{browser:{name:"browser",version:"1"},'
    b'countryCode:"US",locale:"en-US",'
    b'os:{name:"os",version:"1"},'
    b'device:{type:"desktop"},'
    b'applicationType:"web"},'
    b'submitScore:function(){return P()},addScore:function(){return P()},'
    b'addAuthListener:noop,showAuthPrompt:function(){return P(false)},'
    b'showAccountLinkPrompt:function(){return P(false)},listFriends:function(){return P([])}},'
    b'data:{getItem:function(k){try{return localStorage.getItem("cg_"+k)}catch(e){return null}},'
    b'setItem:function(k,v){try{localStorage.setItem("cg_"+k,String(v))}catch(e){}},'
    b'removeItem:function(k){try{localStorage.removeItem("cg_"+k)}catch(e){}},'
    b'clear:function(){try{for(var i=localStorage.length-1;i>=0;i--){var key=localStorage.key(i);'
    b'if(key&&key.indexOf("cg_")===0)localStorage.removeItem(key)}}catch(e){}},'
    b'syncUnityGameData:function(){}},'
    b'store:{setSandbox:noop,buyItem:function(){return P()}},'
    b'analytics:{trackOrder:function(){return P()}},'
    b'banner:{requestOverlayBanners:function(){return P([])}}};'
    b'window.CrazyGames=window.CrazyGames||{};window.CrazyGames.SDK=sdk;'
    b'window.Crazygames=window.Crazygames||{};window.Crazygames.sdk=sdk;'
    b'window.Crazygames.SDK=sdk})();'
    b'script.addEventListener("load",function(){')


def patch_framework(path):
    """Replace the CDN SDK loader with the local stub (see comment above)."""
    with open(path, "rb") as f:
        data = f.read()
    if b"sdk.crazygames.com" not in data and b"window.CrazyGames.SDK=sdk" in data:
        print(f"OK   {path}: SDK stub already applied")
        return
    n = data.count(SDK_LOADER_OLD)
    if n == 0:
        print(f"WARN {path}: no CrazyGames SDK loader found — left unpatched "
              "(game may not use the SDK).", file=sys.stderr)
        return
    if n != 1:
        sys.exit(f"FAIL {path}: SDK loader pattern found {n} times — refusing blind replace")
    patched = data.replace(SDK_LOADER_OLD, SDK_STUB_NEW, 1)
    if b"sdk.crazygames.com" in patched or b"unityFramework" not in patched:
        sys.exit(f"FAIL {path}: SDK patch produced unexpected content")
    with open(path, "wb") as f:
        f.write(patched)
    print(f"OK   {path}: SDK loader replaced with local stub "
          f"({len(data):,} -> {len(patched):,} bytes)")


def brotli_decompress(raw):
    """Decompress a brotli stream via the brotli CLI (installed with
    `apk add brotli` in the Dockerfile), falling back to the python brotli
    module if present. Returns None if the input is not valid brotli."""
    try:
        p = subprocess.run(["brotli", "-d", "-c"], input=raw,
                           capture_output=True, timeout=600)
        if p.returncode == 0:
            return p.stdout
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"  brotli CLI error: {e}", file=sys.stderr)
    try:
        import brotli  # optional pip package
        return brotli.decompress(raw)
    except Exception:
        return None


def normalize(raw, magic):
    """Return (data, how) where data passes the magic check, or (None, why)."""
    # 1. Already the plain uncompressed content? Done.
    if magic in raw[:600]:
        return raw, "already uncompressed"

    # 2. gzip/gzip-compressed transfer?
    if raw[:2] == b"\x1f\x8b":
        try:
            out = gzip.decompress(raw)
            if magic in out[:600]:
                return out, "gzip -> uncompressed"
        except Exception:
            pass

    # 3. Brotli (with or without the Unity wrapper marker).
    if UNITY_BROTLI_MARKER in raw[:64] or b"UnityWeb Compress" in raw[:64]:
        out = brotli_decompress(raw)
        if out and magic in out[:600]:
            return out, "Unity brotli wrapper -> uncompressed"
        return None, ("Unity brotli wrapper detected but decompression failed "
                      "(is the `brotli` CLI installed in the image?)")
    out = brotli_decompress(raw)
    if out and len(out) > len(raw) and magic in out[:600]:
        return out, "brotli -> uncompressed"

    return None, "unexpected content (neither plain nor gzip/brotli of what we need)"


def download(url, attempts=6):
    """Fetch a URL as plain bytes. The CDN is flaky: the same URL can 404 on
    one request and 200 on the next, so retry with a short backoff."""
    last = None
    for i in range(attempts):
        req = urllib.request.Request(url, headers={
            "Accept-Encoding": "identity",  # ask for no transfer encoding
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) railway-docker-build",
        })
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.read()
        except Exception as e:
            last = e
            if i + 1 < attempts:
                wait = 3 * (i + 1)
                print(f"  retry {i + 1}/{attempts} for {url} ({e}) — sleeping {wait}s",
                      file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"download failed after {attempts} attempts: {last}")


# The S3 bucket has NO directory listing (verified 2026-11-27), so "download
# everything" can only be done by probing every name the game could request.
# FILES above is the verified complete inventory (2026-11-27, 4 probing
# rounds / 900+ candidate names): the CDN's StreamingAssets contains exactly
# the 16 FMOD banks (3 general + 13 per-bike) + 28 Unity bundles (menu scene
# + Nitro + one per licensed bike)
# listed there — every other candidate probed (per-bike banks, other scene
# bundles, etc/dxt texture variants) returned 404 on the CDN itself.
# This list is re-probed at every build: if the developer ever ships a new
# file (e.g. a bank for a new bike), the build grabs it automatically instead
# of the game hanging on a missing request at runtime.
EXTRA_PROBE = (
    ["MBK_%s.bank" % n for n in (
        "Nitro", "Nitro2", "Nitro3",
        "kawasaki_1400_GTR", "KLX250", "KX450F", "KLX450F", "X450F",
        "Ninja", "Ninja3", "ZX10R", "Z750", "Z800",
        "suzuki_Hayabusa_GSX1300R", "Hayabusa", "GSX1300R",
        "vespa_946", "Vespa946",
        "FZH", "FZHTurbo", "Turbo", "V900", "V900CX", "KF450T", "CX750F",
        "VX95", "VX95Night", "KBX250", "Shadow", "ShadowR",
    )]
    + ["AssetBundles/mbk_%s" % n.lower() for n in (
        "Nitro", "Nitro2", "Nitro3",
        "kawasaki_1400_GTR", "KLX250", "KX450F", "KLX450F", "X450F",
        "Ninja", "Ninja3", "ZX10R", "Z750", "Z800",
        "suzuki_Hayabusa_GSX1300R", "Hayabusa", "GSX1300R",
        "vespa_946", "Vespa946",
        "FZH", "FZHTurbo", "Turbo", "V900", "V900CX", "KF450T", "CX750F",
        "VX95", "VX95Night", "KBX250", "Shadow", "ShadowR",
    )]
    + [
        # other Unity scene bundles (menuScene -> menusceneasset is the only
        # one that exists today; gameplay scenes live inside data.unityweb)
        "AssetBundles/mainsceneasset", "AssetBundles/gamesceneasset",
        "AssetBundles/loadingsceneasset", "AssetBundles/citysceneasset",
        "AssetBundles/crazysdkloadingsceneasset",
        # generic asset bundles (traffic models etc. — all in data today)
        "AssetBundles/carsasset", "AssetBundles/trafficasset",
        "AssetBundles/trucksasset", "AssetBundles/playerasset",
        "AssetBundles/environmentasset", "AssetBundles/wheelasset",
        "AssetBundles/helmetasset", "AssetBundles/roadasset",
    ]
)

BASE_TRAFFIC_RIDER = "https://files.crazygames.com/traffic-rider-vvq/92"


def probe_extras(slug):
    """Re-probe the CDN for any file not in the verified inventory and
    download it if it appeared. Never fails the build (extra files are a
    bonus; required files above already succeeded)."""
    known = set(GAMES[slug].keys())
    found = 0
    for rel in EXTRA_PROBE:
        if f"StreamingAssets/{rel}" in known:
            continue
        url = f"{BASE_TRAFFIC_RIDER}/StreamingAssets/{rel}"
        try:
            raw = download(url, attempts=1)
        except Exception:
            continue  # 404 — expected for all names that don't exist
        # S3 error pages are XML — never save those.
        head = raw[:100].lstrip()
        if raw.startswith(b"<?xml") or head.startswith(b"<Error"):
            continue
        dest = f"games/{slug}/StreamingAssets/{rel}"
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(raw)
        found += 1
        print(f"EXTRA {dest}: {len(raw):,} bytes (new on CDN — grabbed)")
        # normalize known types if possible (banks/bundles are uncompressed)
        if raw[:4] not in (b"FEV ", b"Unit") and len(raw) > 4096:
            print(f"WARN  {dest}: unexpected magic {raw[:8]!r} — saved as-is",
                  file=sys.stderr)
    if found == 0:
        print("CDN inventory check: no additional StreamingAssets files "
              "found (inventory confirmed complete).")
    else:
        print(f"CDN inventory check: {found} new file(s) downloaded — "
              "add them to sw.js SHELL to precache them.")


def main():
    ok = True
    for slug, files in GAMES.items():
        os.makedirs(f"games/{slug}", exist_ok=True)
        for rel, (url, magic) in files.items():
            dest = f"games/{slug}/{rel}"
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                raw = download(url)
            except Exception as e:
                print(f"FAIL {dest}: download error: {e}", file=sys.stderr)
                ok = False
                continue

            data, how = normalize(raw, magic)
            if data is None:
                print(f"FAIL {dest}: {how}, first bytes: {raw[:24]!r}", file=sys.stderr)
                ok = False
                continue

            with open(dest, "wb") as f:
                f.write(data)
            print(f"OK   {dest}: {len(data):,} bytes ({how})")

        patch_framework(f"games/{slug}/Build/framework.js")
        if slug == "traffic-rider":
            probe_extras(slug)

    if not ok:
        sys.exit("Build aborted: one or more game files are corrupt.")

    print("All game files fetched, verified and patched (no external SDK needed).")


if __name__ == "__main__":
    main()
