"""Small job-local HTTP recorder for browser Sentry envelopes."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlparse

TOKEN = os.environ.get("RECORDER_CONTROL_TOKEN", "")
ENVELOPES: list[bytes] = []
LOCK = Lock()


def authorized(request: BaseHTTPRequestHandler) -> bool:
    return bool(TOKEN) and request.headers.get("X-Recorder-Token") == TOKEN


class RecorderHandler(BaseHTTPRequestHandler):
    server_version = "wren-e2e-recorder/1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if path == "/healthz":
            self.respond(200, b"ok\n", "text/plain")
            return
        if path == "/_e2e/recorder/ready":
            if not authorized(self):
                self.respond(401, b"unauthorized\n", "text/plain")
                return
            self.respond(200, b'{"ready":true}\n', "application/json")
            return
        if path == "/_e2e/recorder/envelopes":
            if not authorized(self):
                self.respond(401, b"unauthorized\n", "text/plain")
                return
            with LOCK:
                payload = json.dumps({"count": len(ENVELOPES)}).encode() + b"\n"
            self.respond(200, payload, "application/json")
            return
        self.respond(404, b"not found\n", "text/plain")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if not path.startswith("/_e2e/sentry/api/") or not path.endswith("/envelope/"):
            self.respond(404, b"not found\n", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.respond(400, b"invalid content length\n", "text/plain")
            return
        if length < 1 or length > 1_048_576:
            self.respond(413, b"envelope too large\n", "text/plain")
            return
        body = self.rfile.read(length)
        with LOCK:
            ENVELOPES.append(body)
        self.respond(200, b"{}", "application/json")

    def log_message(self, format: str, *args: object) -> None:
        return

    def respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), RecorderHandler).serve_forever()
