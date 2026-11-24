"""A small local web server for the Hallucinope interface. Standard library only.

    python -m hallucinope.web             # opens http://127.0.0.1:8000 in your browser
    python -m hallucinope.web --port 8080 --no-browser

It listens on 127.0.0.1 only, so nobody else on your network can reach it.
Population data is loaded once at start-up (from the cache when it's fresh).

API: POST /api/check with {"text": "..."} returns every claim with its
verdict, explanation, receipt and position in the text (see build_payload).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..data.models import DataSourceError
from ..data.population import load
from .payload import MAX_TEXT, VERDICT_KEYS, Checker, build_payload  # noqa: F401 (re-exported)

log = logging.getLogger("hallucinope.web")

STATIC = Path(__file__).with_name("static")
FILES = {  # the only files ever served: no path from the request touches the disk
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/static/samples.js": ("samples.js", "text/javascript; charset=utf-8"),
}
MAX_BODY = 64 * 1024             # bytes per request


def make_handler(checker: Checker) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Hallucinope/1.2"

        def log_message(self, fmt, *args):   # quiet: no line per request
            log.debug("[Web:Server] " + fmt, *args)

        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: HTTPStatus, data: dict) -> None:
            self._send(status, json.dumps(data).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self) -> None:
            entry = FILES.get(self.path.split("?")[0])
            if entry is None:
                self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
                return
            name, content_type = entry
            self._send(HTTPStatus.OK, (STATIC / name).read_bytes(), content_type)

        def do_POST(self) -> None:
            if self.path != "/api/check":
                self._json(HTTPStatus.NOT_FOUND, {"error": "Unknown address."})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                               {"error": f"That's too much text. Check up to "
                                         f"{MAX_TEXT:,} characters at a time."})
                    return
                text = json.loads(self.rfile.read(length) or b"{}").get("text", "")
                if not isinstance(text, str) or not text.strip():
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "Paste some text to check."})
                    return
                if len(text) > MAX_TEXT:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                               {"error": f"That's {len(text):,} characters. Check up to "
                                         f"{MAX_TEXT:,} at a time."})
                    return
                self._json(HTTPStatus.OK, checker.check(text.strip()))
            except (ValueError, AttributeError):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "The request wasn't valid JSON."})
            except Exception:                                 # never leak internals
                log.exception("[Web:Server] check failed")
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                           {"error": "Something went wrong while checking. "
                                     "The details are in the terminal."})

    return Handler


def serve(checker: Checker, port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(checker))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hallucinope.web",
                                     description="Open the Hallucinope web interface.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    print("Loading population data (the first time can take a few minutes)...")
    try:
        checker = Checker(load())
    except DataSourceError as exc:
        print(f"No population data available. {exc}", file=sys.stderr)
        return 1
    for note in checker.population.notes:
        print(f"Note: {note}")
    try:
        httpd = serve(checker, args.port)
    except OSError:
        print(f"Port {args.port} is busy. Try: python -m hallucinope.web --port 8080",
              file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{args.port}"
    print(f"Hallucinope is running at {url}  (press Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0
