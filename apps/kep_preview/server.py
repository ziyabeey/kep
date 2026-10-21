"""Serve the local KEP development preview; never fetch sources or call models.

Run from the repository root: python3 -m apps.kep_preview.server
This deliberately has no production authentication or deployment configuration.
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import planner, service

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 16_384
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
)


class PreviewServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = "KepPreview/0.1"
    sys_version = ""

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        # Escapes also make malformed lone-surrogate input safe in error replies.
        self._send(status, json.dumps(payload, ensure_ascii=True, allow_nan=False).encode(),
                   "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _path(self) -> str | None:
        authority = self.headers.get("Host", "").lower()
        if authority not in self.server.allowed_authorities:
            self._error(403, "Bu sunucu adresine izin verilmedi.")
            return None
        if not self.path.startswith("/") or self.path.startswith("//"):
            self._error(400, "Geçersiz istek yolu.")
            return None
        try:
            return urlsplit(self.path).path
        except ValueError:
            self._error(400, "Geçersiz istek yolu.")
            return None

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = self._path()
        if path is None:
            return
        if path == "/api/health":
            self._json(200, {"status": "ok", "research_only": True,
                             "model_used": False, "traffic_live": False})
        elif path == "/api/bootstrap":
            self._json(200, service.bootstrap())
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif path in ASSETS:
            name, content_type = ASSETS[path]
            try:
                body = (STATIC / name).read_bytes()
            except OSError:
                self._error(503, "Önizleme dosyaları henüz hazır değil.")
                return
            self._send(200, body, content_type)
        else:
            self._error(404, "Bu sayfa bulunamadı.")

    def do_POST(self) -> None:
        path = self._path()
        if path is None:
            return
        handlers = {"/api/discover": service.discover,
                    "/api/chat": service.chat,
                    "/api/plan": planner.plan}
        if path not in handlers:
            self._error(404, "Bu işlem bulunamadı.")
            return
        origin = self.headers.get("Origin")
        if origin is not None:
            try:
                parsed = urlsplit(origin)
                valid = (parsed.scheme in {"http", "https"}
                         and parsed.netloc.lower() == self.headers.get("Host", "").lower()
                         and not parsed.path and not parsed.query and not parsed.fragment)
            except ValueError:
                valid = False
            if not valid:
                self._error(403, "İstek önizlemenin kendi sayfasından gelmelidir.")
                return
        if self.headers.get("Transfer-Encoding"):
            self._error(400, "Parçalı istek gövdesi desteklenmiyor.")
            return
        if self.headers.get_content_type() != "application/json":
            self._error(415, "JSON biçiminde bir istek gönder.")
            return
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isascii() or not raw_length.isdigit():
            self._error(411, "İstek boyutu belirtilmelidir.")
            return
        significant_length = raw_length.lstrip("0") or "0"
        if len(significant_length) > len(str(MAX_BODY)):
            self._error(413, "Bu istek çok uzun.")
            return
        length = int(significant_length)
        if length > MAX_BODY:
            self._error(413, "Bu istek çok uzun.")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"),
                                 parse_constant=lambda _: (_ for _ in ()).throw(
                                     ValueError("Sonlu olmayan sayıya izin verilmiyor.")))
            if not isinstance(payload, dict):
                raise ValueError("İstek bir JSON nesnesi olmalıdır.")
            result = handlers[path](payload)
        except RecursionError:
            self._error(400, "İstek nesnesi çok derin.")
            return
        except (ValueError, TypeError, UnicodeError) as exc:
            self._error(400, str(exc))
            return
        self._json(200, result)


def make_server(host: str = "127.0.0.1", port: int = 4180,
                extra_hosts: tuple[str, ...] = ()) -> PreviewServer:
    server = PreviewServer((host, port), Handler)
    port = server.server_port
    server.allowed_authorities = {
        f"localhost:{port}", f"127.0.0.1:{port}", f"[::1]:{port}",
        *[value.lower() for value in extra_hosts],
    }
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4180)
    parser.add_argument("--allow-host", action="append", default=[],
                        help="Exact additional Host authority for a development proxy.")
    args = parser.parse_args()
    if args.port < 0 or args.port > 65535:
        parser.error("port 0..65535 aralığında olmalıdır")
    server = make_server(args.host, args.port, tuple(args.allow_host))
    print(f"Kep local preview: http://{args.host}:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
