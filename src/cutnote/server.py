"""Loopback-only editor server with a small, explicit HTTP surface."""

import json
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlsplit

from .fonts import bundled_fonts
from .renderer import RenderOptions, render_note

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/logo.svg": ("logo.svg", "image/svg+xml"),
}
MAX_BODY = 65_536


class EditorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int):
        super().__init__(("127.0.0.1", port), EditorHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.render_slots = threading.BoundedSemaphore(2)
        self.assets = {
            route: (files("cutnote").joinpath("assets", "web", name).read_bytes(), mime)
            for route, (name, mime) in ASSETS.items()
        }


class EditorHandler(BaseHTTPRequestHandler):
    server: EditorServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format: str, *args: object) -> None:
        # Typing in the editor should not fill the terminal with access logs.
        pass

    def _reply(self, status: int, body: bytes, mime: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'none'"
            ),
        )
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status: int, data: dict) -> None:
        self._reply(
            status,
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _local_request(self) -> bool:
        origin = self.headers.get("Origin")
        valid = (
            self.headers.get("Host") == urlsplit(self.server.origin).netloc
            and (origin is None or origin == self.server.origin)
            and self.headers.get("Sec-Fetch-Site") != "cross-site"
        )
        if not valid:
            self._json(403, {"error": "Only requests from this local editor are accepted."})
        return valid

    def do_GET(self) -> None:
        if not self._local_request():
            return
        asset = self.server.assets.get(urlsplit(self.path).path)
        if asset is None:
            self._json(404, {"error": "Not found."})
            return
        body, mime = asset
        self._reply(200, body, mime)

    def do_POST(self) -> None:
        if not self._local_request():
            return
        if self.path != "/api/render":
            self._json(404, {"error": "Not found."})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self._json(415, {"error": "Send application/json."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Invalid content length."})
            return
        if not 0 < length <= MAX_BODY:
            self._json(413, {"error": "Request body must be between 1 and 65,536 bytes."})
            return
        if not self.server.render_slots.acquire(blocking=False):
            self._json(503, {"error": "Editor is busy. Try again in a moment."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict) or set(payload) != {"text", "options"}:
                raise ValueError("Provide text and options in the render request.")
            if not isinstance(payload["options"], dict):
                raise ValueError("Options must be an object.")
            try:
                options = RenderOptions(**payload["options"])
            except TypeError as exc:
                raise ValueError("Unknown render option.") from exc
            result = render_note(payload["text"], options)
            self._json(200, asdict(result))
        except (ValueError, UnicodeError) as exc:
            self._json(400, {"error": str(exc)})
        except TimeoutError:
            self._json(408, {"error": "Request timed out."})
        finally:
            self.server.render_slots.release()


def make_server(port: int = 0) -> EditorServer:
    bundled_fonts()  # Warm font caches before accepting concurrent requests.
    return EditorServer(port)


def serve_gui(port: int = 0, open_browser: bool = True) -> None:
    import typer

    with make_server(port) as server:
        typer.echo(f"Cutnote editor: {server.origin}\nPress Ctrl+C to stop.", err=True)
        if open_browser:
            webbrowser.open(server.origin)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            typer.echo("\nEditor stopped.", err=True)
