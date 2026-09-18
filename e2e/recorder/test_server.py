from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection

import server


class RecorderServerTest(unittest.TestCase):
    def setUp(self) -> None:
        server.TOKEN = "test-control-token"
        server.ENVELOPES.clear()
        server.STORED_BYTES = 0
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.RecorderHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=2)
        self.httpd.server_close()

    def request(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        token: str | None = None,
        declared_length: int | None = None,
    ):
        connection = HTTPConnection("127.0.0.1", self.httpd.server_port)
        headers = {"Content-Length": str(declared_length if declared_length is not None else len(body))}
        if token is not None:
            headers["X-Recorder-Token"] = token
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        content = response.read()
        connection.close()
        return response.status, content

    def test_requires_control_token_for_queries(self) -> None:
        status, _ = self.request("GET", "/_e2e/recorder/ready")
        self.assertEqual(status, 401)

        status, body = self.request("GET", "/_e2e/recorder/ready", token="test-control-token")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ready": True})

    def test_accepts_bounded_envelopes(self) -> None:
        status, _ = self.request(
            "POST", "/_e2e/sentry/api/1/envelope/", body=b"event", token="unexpected"
        )
        self.assertEqual(status, 200)
        self.assertEqual(server.ENVELOPES, [b"event"])

        status, body = self.request(
            "GET", "/_e2e/recorder/envelopes", token="test-control-token"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"count": 1})

    def test_rejects_oversized_envelopes(self) -> None:
        status, _ = self.request(
            "POST",
            "/_e2e/sentry/api/1/envelope/",
            declared_length=server.MAX_ENVELOPE_BYTES + 1,
        )
        self.assertEqual(status, 413)
        self.assertEqual(server.ENVELOPES, [])

    def test_evicts_old_envelopes_at_storage_bounds(self) -> None:
        original_count = server.MAX_STORED_ENVELOPES
        original_bytes = server.MAX_STORED_BYTES
        server.MAX_STORED_ENVELOPES = 2
        server.MAX_STORED_BYTES = 8
        try:
            for envelope in (b"one", b"two", b"three"):
                status, _ = self.request(
                    "POST", "/_e2e/sentry/api/1/envelope/", body=envelope
                )
                self.assertEqual(status, 200)
            self.assertEqual(server.ENVELOPES, [b"two", b"three"])
            self.assertEqual(server.STORED_BYTES, len(b"two") + len(b"three"))
        finally:
            server.MAX_STORED_ENVELOPES = original_count
            server.MAX_STORED_BYTES = original_bytes


if __name__ == "__main__":
    unittest.main()
