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

# CrazyGames HTML5 SDK: the game loads it from their CDN, but it refuses to
# work outside crazygames.com (environment "disabled" -> sdkDisabled errors).
# We download it, force its environment check to "local", and the service
# worker serves our patched copy in place of the CDN one.
SDK_URL = "https://sdk.crazygames.com/crazygames-sdk-v3.js"
SDK_OUT = "crazygames-sdk-v3.js"
SDK_CHECK = '["localhost","127.0.0.1","preview.construct.net"].includes(window.location.hostname)'


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

    fetch_sdk()
    print("All game files fetched and verified.")


def fetch_sdk():
    """Download the CrazyGames SDK and force its environment to 'local'."""
    req = urllib.request.Request(SDK_URL, headers={
        "Accept-Encoding": "identity",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) railway-docker-build",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            code = r.read().decode("utf-8", "strict")
    except Exception as e:
        print(f"FAIL {SDK_OUT}: download error: {e}", file=sys.stderr)
        sys.exit("Build aborted: could not download the CrazyGames SDK.")

    if SDK_CHECK in code:
        code = code.replace(SDK_CHECK, "true", 1)
        print(f"OK   {SDK_OUT}: {len(code):,} bytes (environment forced to 'local')")
    else:
        # fall back to a looser match in case the minified array changes
        import re
        patched = re.sub(
            r"\[\s*[\"']localhost[\"']\s*,[^\]]*\]\s*\.\s*includes\s*\(\s*window\.location\.hostname\s*\)",
            "true", code, count=1)
        if patched != code:
            code = patched
            print(f"OK   {SDK_OUT}: {len(code):,} bytes (environment forced to 'local', loose match)")
        else:
            print(f"WARN {SDK_OUT}: environment check not found — served UNPATCHED; "
                  "the SDK may refuse to work on custom domains.", file=sys.stderr)
    with open(SDK_OUT, "w", encoding="utf-8") as f:
        f.write(code)


if __name__ == "__main__":
    main()
