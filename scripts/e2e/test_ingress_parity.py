from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ingress_contract import (  # noqa: E402
    load_contract,
    render_cloudflare,
    resolve_route,
    validate_contract,
)
from ingress_render import generated_outputs_are_current, render_nginx  # noqa: E402


class IngressContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_contract()

    def test_contract_validates_and_renders_both_outputs(self) -> None:
        validate_contract(self.contract)
        self.assertTrue(render_cloudflare(self.contract))
        self.assertTrue(render_nginx(self.contract))
        self.assertTrue(generated_outputs_are_current(self.contract))

    def test_generated_outputs_are_stale_when_contract_changes(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["hosts"][0]["routes"][0]["action"]["service"] = "http://changed:80"
        self.assertFalse(generated_outputs_are_current(changed))

    def test_validation_rejects_duplicate_hosts_and_nonterminal_catch_all(self) -> None:
        duplicate_host = copy.deepcopy(self.contract)
        duplicate_host["hosts"].append(copy.deepcopy(duplicate_host["hosts"][0]))
        with self.assertRaises(ValueError):
            validate_contract(duplicate_host)

        nonterminal_catch_all = copy.deepcopy(self.contract)
        api_routes = nonterminal_catch_all["hosts"][1]["routes"]
        api_routes.reverse()
        with self.assertRaises(ValueError):
            validate_contract(nonterminal_catch_all)

        for service in (
            "https://frontend:80/path",
            "http://frontend; return 200;",
            "http://frontend:80\nproxy_pass http://evil",
        ):
            with self.subTest(service=service):
                invalid_service = copy.deepcopy(self.contract)
                invalid_service["hosts"][0]["routes"][0]["action"]["service"] = service
                with self.assertRaises(ValueError):
                    validate_contract(invalid_service)

        missing_app_hostname = copy.deepcopy(self.contract)
        missing_app_hostname["hosts"][0]["e2e_hostname"] = None
        with self.assertRaises(ValueError):
            validate_contract(missing_app_hostname)
        with self.assertRaises(ValueError):
            render_nginx(missing_app_hostname)

        invalid_app_hostname = copy.deepcopy(self.contract)
        invalid_app_hostname["hosts"][0]["e2e_hostname"] = "app.wren.test; return 200;"
        with self.assertRaises(ValueError):
            validate_contract(invalid_app_hostname)

    def test_production_hosts_and_targets_are_generated(self) -> None:
        cloudflare = render_cloudflare(self.contract)
        for variable, service in (
            ("CF_APP_HOSTNAME", "http://frontend:80"),
            ("CF_API_HOSTNAME", "http://backend:8000"),
            ("CF_MCP_HOSTNAME", "http://mcp:9000"),
            ("CF_DOCS_HOSTNAME", "http://docs:80"),
        ):
            with self.subTest(variable=variable):
                self.assertIn(f"hostname: ${{{variable}}}", cloudflare)
                self.assertIn(f"service: {service}", cloudflare)
        self.assertIn("service: http_status:404", cloudflare)

        nginx = render_nginx(self.contract)
        for service in ("frontend:80", "backend:8000", "mcp:9000"):
            with self.subTest(service=service):
                self.assertIn(f"server {service};", nginx)

    def test_observability_and_docs_paths_are_blocked(self) -> None:
        for host, path in (
            ("api", "/metrics"),
            ("api", "/metrics/"),
            ("api", "/healthz"),
            ("api", "/readyz/"),
            ("docs", "/healthz"),
            ("docs", "/healthz/"),
        ):
            with self.subTest(host=host, path=path):
                route = resolve_route(self.contract, host, path)
                self.assertEqual(route["action"], {"kind": "status", "status": 404})

        self.assertEqual(resolve_route(self.contract, "api", "/users")["id"], "api")
        self.assertEqual(resolve_route(self.contract, "docs", "/")["id"], "docs")
        nginx = render_nginx(self.contract)
        self.assertIn("location ~ ^/(metrics|healthz|readyz)/?$ {", nginx)

    def test_mcp_allowlist_and_catch_all(self) -> None:
        for path in (
            "/.well-known/oauth-protected-resource",
            "/mcp",
            "/mcp/",
            "/mcp/messages",
        ):
            with self.subTest(path=path):
                self.assertEqual(resolve_route(self.contract, "mcp", path)["id"], "mcp-public")
        for path in ("/healthz", "/metrics", "/.well-known/oauth-protected-resource/mcp"):
            with self.subTest(path=path):
                self.assertEqual(resolve_route(self.contract, "mcp", path)["id"], "mcp-catch-all")
                self.assertEqual(resolve_route(self.contract, "mcp", path)["action"]["status"], 404)

    def test_e2e_adapter_rejects_nginx_injection_values(self) -> None:
        for header in (
            "X-Recorder-Token $http_x_recorder_token; return 200;",
            "X-Recorder-Token $http_x_recorder_token\nreturn 200;",
            "X Recorder Token $token",
        ):
            with self.subTest(header=header):
                invalid = copy.deepcopy(self.contract)
                invalid["e2e_adapter"]["recorder_routes"][1]["headers"] = [header]
                with self.assertRaises(ValueError):
                    validate_contract(invalid)

        invalid_path = copy.deepcopy(self.contract)
        invalid_path["e2e_adapter"]["recorder_routes"][0]["path"] = "/_e2e/ready; return 200;"
        with self.assertRaises(ValueError):
            validate_contract(invalid_path)

        invalid_tls = copy.deepcopy(self.contract)
        invalid_tls["e2e_adapter"]["tls"]["certificate"] = "/etc/nginx/certs/wren.pem; return 200;"
        with self.assertRaises(ValueError):
            validate_contract(invalid_tls)

    def test_e2e_adapter_keeps_tls_and_recorder_routes_explicit(self) -> None:
        nginx = render_nginx(self.contract)
        self.assertIn("listen 443 ssl default_server;", nginx)
        self.assertIn("server_name app.wren.test;", nginx)
        for route in self.contract["e2e_adapter"]["recorder_routes"]:
            self.assertIn(f"location = {route['path']} {{", nginx)
        self.assertNotIn("docs.wren.test", nginx)
        self.assertNotIn("/.well-known/oauth-protected-resource/mcp", nginx)


if __name__ == "__main__":
    unittest.main()
