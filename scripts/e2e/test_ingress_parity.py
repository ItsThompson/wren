from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLOUDFLARE_CONFIG = ROOT / "deployments/cloudflare/config.yml"
E2E_NGINX_CONFIG = ROOT / "e2e/ingress/nginx.conf"


class IngressParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cloudflare = CLOUDFLARE_CONFIG.read_text()
        cls.nginx = E2E_NGINX_CONFIG.read_text()

    def test_shared_service_targets_match(self) -> None:
        expected_targets = {
            "CF_APP_HOSTNAME": ("http://frontend:80", "frontend:80"),
            "CF_API_HOSTNAME": ("http://backend:8000", "backend:8000"),
            "CF_MCP_HOSTNAME": ("http://mcp:9000", "mcp:9000"),
        }
        for hostname_variable, (production_target, nginx_target) in expected_targets.items():
            with self.subTest(hostname_variable=hostname_variable):
                production_blocks = self._cloudflare_blocks(hostname_variable)
                self.assertTrue(production_blocks)
                self.assertIn(production_target, "\n".join(production_blocks))
                self.assertIn(f"server {nginx_target};", self.nginx)

    def test_api_observability_paths_are_blocked_in_both_edges(self) -> None:
        production = "\n".join(self._cloudflare_blocks("CF_API_HOSTNAME"))
        self.assertIn("^/(metrics|healthz|readyz)/?$", production)

        api_server = self._nginx_server("api.wren.test")
        for path in ("/metrics", "/healthz", "/readyz"):
            with self.subTest(path=path):
                self.assertIn(f"location = {path} {{ return 404; }}", api_server)
        self.assertIn("proxy_pass http://backend;", api_server)

    def test_mcp_public_allowlist_matches_production(self) -> None:
        production = "\n".join(self._cloudflare_blocks("CF_MCP_HOSTNAME"))
        self.assertIn(
            r"^/(mcp(/.*)?|\.well-known/oauth-protected-resource)$",
            production,
        )

        mcp_server = self._nginx_server("mcp.wren.test")
        self.assertIn("location = /.well-known/oauth-protected-resource {", mcp_server)
        self.assertIn("location = /mcp {", mcp_server)
        self.assertIn("location ^~ /mcp/ {", mcp_server)
        self.assertIn("location / { return 404; }", mcp_server)
        self.assertNotIn("/.well-known/oauth-protected-resource/mcp", mcp_server)

    def test_test_only_recorder_routes_are_scoped_to_the_app_host(self) -> None:
        app_server = self._nginx_server("app.wren.test")
        for path in (
            "/_e2e/sentry/api/1/envelope/",
            "/_e2e/recorder/ready",
            "/_e2e/recorder/envelopes",
            "/_e2e/recorder/artifacts",
        ):
            with self.subTest(path=path):
                self.assertIn(f"location = {path} {{", app_server)
                self.assertIn("proxy_pass http://recorder;", app_server)

        for server_name in ("api.wren.test", "mcp.wren.test"):
            with self.subTest(server_name=server_name):
                self.assertNotIn("/_e2e/", self._nginx_server(server_name))

    def test_public_proxies_forward_https(self) -> None:
        for server_name in ("app.wren.test", "api.wren.test", "mcp.wren.test"):
            server = self._nginx_server(server_name)
            proxy_count = server.count("proxy_pass ")
            self.assertGreater(proxy_count, 0, server_name)
            self.assertEqual(
                proxy_count,
                server.count("proxy_set_header X-Forwarded-Proto https;"),
                server_name,
            )

    def _cloudflare_blocks(self, hostname_variable: str) -> list[str]:
        blocks = re.split(r"(?=  - hostname: )", self.cloudflare)
        return [block for block in blocks if f"${{{hostname_variable}}}" in block]

    def _nginx_server(self, server_name: str) -> str:
        candidates = re.finditer(
            r"\n    server \{\n(?P<body>.*?\n    \}\n)",
            self.nginx,
            re.DOTALL,
        )
        for candidate in candidates:
            body = candidate.group("body")
            if f"server_name {server_name};" in body:
                return body
        self.fail(f"missing nginx server block for {server_name}")


if __name__ == "__main__":
    unittest.main()
