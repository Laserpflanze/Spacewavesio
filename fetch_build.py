"""Docker build step: fetch the Unity WebGL build files from the CrazyGames CDN.

The CDN behaves inconsistently depending on which edge server answers the
request: the exact same URL can return the raw uncompressed content OR
brotli/gzip-compressed bytes. Serving compressed bytes as-is breaks the game
(the browser parses them as JS/data and fails, e.g. "Invalid character
'\\ufffd'" or "still brotli-compressed" errors).

This script normalizes every download to the plain uncompressed file the
Unity loader expects (byte-for-byte identical to the locally verified build),
verifies the magic bytes of each file, and fails the Docker build loudly if
anything still looks wrong.
"""
import gzip
import os
import subprocess
import sys
import urllib.request

BASE = "https://files.crazygames.com/space-waves/114/Build"
FILES = {
    "Build/loader.js": (BASE + "/f5621fc8e6401e7302a362d609e496a1.loader.js",
                        b"createUnityInstance"),
    "Build/data.unityweb": (BASE + "/1a568795816f05437ab0d4e6f50dc4ac.data.br",
                            b"UnityWebData1.0\0"),
    "Build/wasm.wasm": (BASE + "/c1aca0022182358dc43860f4ad8c934f.wasm.br",
                        b"\x00asm"),
    "Build/framework.js": (BASE + "/285f771aa266df412210c567c3f51a97.framework.js.br",
                           b"unityFramework"),
}

# Marker string the Unity loader itself uses to detect its brotli wrapper
# (see hasUnityMarker in loader.js).
UNITY_BROTLI_MARKER = b"UnityWeb Compressed Content"

# The game's bundled glue normally loads the CrazyGames SDK from their CDN at
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
    b'systemInfo:{browser:{name:"browser",version:"1"},os:{name:"os",version:"1"},deviceType:"desktop"},'
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
    if data.count(SDK_LOADER_OLD) != 1:
        sys.exit(f"FAIL {path}: SDK loader pattern not found exactly once "
                 f"({data.count(SDK_LOADER_OLD)}) — build file changed upstream?")
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


def main():
    os.makedirs("Build", exist_ok=True)
    ok = True
    for dest, (url, magic) in FILES.items():
        req = urllib.request.Request(url, headers={
            "Accept-Encoding": "identity",  # ask for no transfer encoding
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) railway-docker-build",
        })
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                raw = r.read()
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

    if not ok:
        sys.exit("Build aborted: one or more game files are corrupt.")

    patch_framework("Build/framework.js")
    print("All game files fetched, verified and patched (no external SDK needed).")


if __name__ == "__main__":
    main()
