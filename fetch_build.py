"""Docker build step: downloads the Unity WebGL build files from the
CrazyGames CDN, forcing identity (uncompressed) transfer, then verifies each
file's magic bytes so a compressed/corrupt download can never silently ship.
"""
import os
import sys
import urllib.request

BASE = "https://files.crazygames.com/space-waves/114/Build"
FILES = {
    "Build/loader.js": (BASE + "/f5621fc8e6401e7302a362d609e496a1.loader.js", b"createUnityInstance"),
    "Build/data.unityweb": (BASE + "/1a568795816f05437ab0d4e6f50dc4ac.data.br", b"UnityWebData1.0"),
    "Build/wasm.wasm": (BASE + "/c1aca0022182358dc43860f4ad8c934f.wasm.br", b"\x00asm"),
    "Build/framework.js": (BASE + "/285f771aa266df412210c567c3f51a97.framework.js.br", b"unityFramework"),
}


def main():
    os.makedirs("Build", exist_ok=True)
    ok = True
    for dest, (url, magic) in FILES.items():
        req = urllib.request.Request(url, headers={
            "Accept-Encoding": "identity",   # never accept gzip/brotli transfer encoding
            "User-Agent": "railway-docker-build",
        })
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
        except Exception as e:
            print(f"FAIL {dest}: download error: {e}", file=sys.stderr)
            ok = False
            continue
        if magic not in data[:600]:
            print(f"FAIL {dest}: unexpected content, first bytes: {data[:20]!r} "
                  f"(transfer encoding still applied?)", file=sys.stderr)
            ok = False
            continue
        with open(dest, "wb") as f:
            f.write(data)
        print(f"OK   {dest}: {len(data):,} bytes")
    if not ok:
        sys.exit("Build aborted: one or more game files are corrupt.")


if __name__ == "__main__":
    main()
