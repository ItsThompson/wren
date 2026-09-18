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
            declared_length=1_048_576 + 1,
        )
        self.assertEqual(status, 413)
        self.assertEqual(server.ENVELOPES, [])


if __name__ == "__main__":
    unittest.main()
