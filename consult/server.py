"""Local HTTP server for the independent OWN-PT consultation interface."""

from __future__ import annotations

import json
import os
import socket
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from .store import OwnptStore

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class ConsultHandler(SimpleHTTPRequestHandler):
    store: OwnptStore | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, format: str, *args) -> None:
        print("http:", format % args, flush=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/stats":
                self._json(self.store.stats())
                return
            if parsed.path == "/api/suggest":
                query = parse_qs(parsed.query)
                self._json(
                    self.store.suggest(
                        query.get("q", [""])[0],
                        query.get("lang", ["pt"])[0],
                    )
                )
                return
            if parsed.path == "/api/search":
                query = parse_qs(parsed.query)
                self._json(
                    self.store.search(
                        query.get("q", [""])[0],
                        lang=query.get("lang", ["all"])[0],
                        pos=query.get("pos", [""])[0],
                        mode=query.get("mode", ["prefix"])[0],
                    )
                )
                return
            if parsed.path == "/api/random":
                self._json(self.store.random_synset() or {})
                return
            if parsed.path.startswith("/api/synset/"):
                synset_id = unquote(parsed.path[len("/api/synset/") :]).strip()
                payload = self.store.synset(synset_id)
                if not payload:
                    self._json({"error": "not found"}, status=404)
                    return
                self._json(payload)
                return
            if parsed.path in {"/", "/index.html"}:
                self.path = "/index.html"
            super().do_GET()
        except Exception as exc:
            traceback.print_exc()
            try:
                self._json({"error": str(exc)}, status=500)
            except Exception:
                pass

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ConsultServer(ThreadingHTTPServer):
    allow_reuse_address = False


def consult_url_if_running(host: str, port: int) -> str | None:
    """Return the local URL if this interface is already serving on host:port."""
    import json
    import urllib.error
    import urllib.request

    url = f"http://{host}:{port}/"
    try:
        with urllib.request.urlopen(f"{url}api/stats", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict) and "pt_synsets" in payload:
        return url
    return None


def port_is_free(host: str, port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def serve(store: OwnptStore, host: str = "127.0.0.1", port: int = 8765) -> ConsultServer:
    ConsultHandler.store = store
    return ConsultServer((host, port), ConsultHandler)
