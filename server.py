"""Minimal static file server for Space Waves — works locally and on Railway.

Listens on 0.0.0.0:$PORT (Railway injects PORT; falls back to 8080 locally).
"""
import http.server
import os
import socketserver

PORT = int(os.environ.get("PORT", "8080"))


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".json": "application/json",
        ".webmanifest": "application/manifest+json",
        ".unityweb": "application/octet-stream",
        ".svg": "image/svg+xml",
    }

    def end_headers(self):
        # The service worker is cache-first for /Build/, so HTTP caching here
        # only matters when the SW cache was wiped. Never mark Build files
        # immutable: after a redeploy the SW must re-download updated files.
        path = self.path.lower()
        if "/build/" in path:
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        elif path.endswith("/sw.js") or path.endswith("/index.html") or path == "/":
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()


class ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)
    with ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"Space Waves serving on http://0.0.0.0:{PORT}")
        httpd.serve_forever()
