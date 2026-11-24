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
        # let the browser cache the big immutable build assets,
        # but always revalidate the shell
        path = self.path.lower()
        if path.startswith("/build/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        elif path.startswith("/sw.js") or path.startswith("/index.html") or path == "/":
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
