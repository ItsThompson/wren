# ruff: noqa: S101

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ingress_contract import (  # noqa: E402
    load_contract,
    render_cloudflare,
    resolve_route,
    validate_contract,
)
from scripts.ingress_models import ProxyAction, StatusAction  # noqa: E402
from scripts.ingress_render import generated_outputs_are_current, render_nginx  # noqa: E402

if TYPE_CHECKING:
    from scripts.ingress_models import IngressContract


class TestIngressContract:
    contract: ClassVar[IngressContract]

    @classmethod
    def setup_class(cls) -> None:
        cls.contract = load_contract()

    def test_contract_validates_and_renders_both_outputs(self) -> None:
        validate_contract(self.contract)
        assert render_cloudflare(self.contract)
        assert render_nginx(self.contract)
        assert generated_outputs_are_current(self.contract)

    def test_generated_outputs_are_stale_when_contract_changes(self) -> None:
        changed = self.contract.model_copy(deep=True)
        action = changed.hosts[0].routes[0].action
        if not isinstance(action, ProxyAction):
            pytest.fail("app route must proxy to the frontend")
        action.service = "http://changed:80"
        assert not generated_outputs_are_current(changed)

    def test_validation_rejects_duplicate_hosts_and_nonterminal_catch_all(self) -> None:
        duplicate_host = self.contract.model_dump(mode="json")
        duplicate_host["hosts"].append(copy.deepcopy(duplicate_host["hosts"][0]))
        with pytest.raises(ValueError, match="host IDs must be unique"):
            validate_contract(duplicate_host)

        nonterminal_catch_all = self.contract.model_dump(mode="json")
        api_routes = nonterminal_catch_all["hosts"][1]["routes"]
        api_routes.reverse()
        with pytest.raises(ValueError, match="catch-all route on api must be last"):
            validate_contract(nonterminal_catch_all)

        noncanonical_path = self.contract.model_dump(mode="json")
        noncanonical_path["hosts"][1]["routes"][0]["match"]["paths"] = ["/metrics/"]
        with pytest.raises(ValueError, match="must not have a trailing slash"):
            validate_contract(noncanonical_path)

        root_prefix = self.contract.model_dump(mode="json")
        root_prefix["hosts"][2]["routes"][0]["match"]["prefix"] = ["/"]
        with pytest.raises(ValueError, match="prefixes must not include root"):
            validate_contract(root_prefix)

        for service in (
            "https://frontend:80/path",
            "http://frontend; return 200;",
            "http://frontend:80\nproxy_pass http://evil",
        ):
            invalid_service = self.contract.model_dump(mode="json")
            invalid_service["hosts"][0]["routes"][0]["action"]["service"] = service
            with pytest.raises(ValueError, match=r"(invalid service URL|control character)"):
                validate_contract(invalid_service)

        missing_app_hostname = self.contract.model_dump(mode="json")
        missing_app_hostname["hosts"][0]["e2e_hostname"] = None
        with pytest.raises(ValueError, match="app host needs an E2E hostname"):
            validate_contract(missing_app_hostname)
        with pytest.raises(ValueError, match="app host needs an E2E hostname"):
            render_nginx(missing_app_hostname)

        invalid_app_hostname = self.contract.model_dump(mode="json")
        invalid_app_hostname["hosts"][0]["e2e_hostname"] = "app.wren.test; return 200;"
        with pytest.raises(ValueError, match="invalid hostname"):
            validate_contract(invalid_app_hostname)

    def test_nonterminal_route_overlaps_are_rejected(self) -> None:
        overlapping_paths = self.contract.model_dump(mode="json")
        overlapping_paths["hosts"][1]["routes"].insert(
            1,
            {
                "id": "api-duplicate-block",
                "match": {"kind": "paths", "paths": ["/metrics"], "trailing_slash": False},
                "action": {"kind": "status", "status": 404},
            },
        )
        with pytest.raises(ValueError, match="routes on api overlap"):
            validate_contract(overlapping_paths)

        overlapping_allowlist = self.contract.model_dump(mode="json")
        overlapping_allowlist["hosts"][2]["routes"].insert(
            0,
            {
                "id": "mcp-duplicate-public",
                "match": {"kind": "allowlist", "exact": ["/mcp"], "prefix": []},
                "action": {"kind": "proxy", "service": "http://mcp:9000"},
            },
        )
        with pytest.raises(ValueError, match="routes on mcp overlap"):
            validate_contract(overlapping_allowlist)

    def test_ordered_nonterminal_routes_before_catch_all_are_valid(self) -> None:
        validate_contract(self.contract)
        assert [route.id for route in self.contract.hosts[1].routes] == [
            "api-observability-block",
            "api",
        ]
        assert [route.id for route in self.contract.hosts[2].routes] == [
            "mcp-public",
            "mcp-catch-all",
        ]
        assert [route.id for route in self.contract.hosts[3].routes] == [
            "docs-health-block",
            "docs",
        ]

    def test_production_hosts_and_targets_are_generated(self) -> None:
        cloudflare = render_cloudflare(self.contract)
        parsed = yaml.safe_load(cloudflare)
        assert [route.get("hostname") for route in parsed["ingress"][:-1]] == [
            "${CF_APP_HOSTNAME}",
            "${CF_API_HOSTNAME}",
            "${CF_API_HOSTNAME}",
            "${CF_MCP_HOSTNAME}",
            "${CF_MCP_HOSTNAME}",
            "${CF_DOCS_HOSTNAME}",
            "${CF_DOCS_HOSTNAME}",
        ]
        assert parsed["ingress"][-1]["service"] == "http_status:404"
        for variable, service in (
            ("CF_APP_HOSTNAME", "http://frontend:80"),
            ("CF_API_HOSTNAME", "http://backend:8000"),
            ("CF_MCP_HOSTNAME", "http://mcp:9000"),
            ("CF_DOCS_HOSTNAME", "http://docs:80"),
        ):
            assert f"hostname: ${{{variable}}}" in cloudflare
            assert f"service: {service}" in cloudflare
        assert "service: http_status:404" in cloudflare

        nginx = render_nginx(self.contract)
        for service in ("frontend:80", "backend:8000", "mcp:9000"):
            assert f"server {service};" in nginx

    def _assert_status(self, action: object, status: int) -> None:
        if not isinstance(action, StatusAction):
            pytest.fail("route must return a status")
        assert action.status == status

    def test_observability_and_docs_paths_are_blocked(self) -> None:
        for host, path in (
            ("api", "/metrics"),
            ("api", "/metrics/"),
            ("api", "/healthz"),
            ("api", "/readyz/"),
            ("docs", "/healthz"),
            ("docs", "/healthz/"),
        ):
            route = resolve_route(self.contract, host, path)
            self._assert_status(route.action, 404)

        assert resolve_route(self.contract, "api", "/users").id == "api"
        assert resolve_route(self.contract, "docs", "/").id == "docs"
        nginx = render_nginx(self.contract)
        assert "location ~ ^/(metrics|healthz|readyz)/?$ {" in nginx

    def test_mcp_allowlist_and_catch_all(self) -> None:
        for path in (
            "/.well-known/oauth-protected-resource",
            "/mcp",
            "/mcp/",
            "/mcp/messages",
        ):
            assert resolve_route(self.contract, "mcp", path).id == "mcp-public"
        for path in ("/healthz", "/metrics", "/.well-known/oauth-protected-resource/mcp"):
            route = resolve_route(self.contract, "mcp", path)
            assert route.id == "mcp-catch-all"
            self._assert_status(route.action, 404)

        assert resolve_route(self.contract, "mcp", "/mcpx").id == "mcp-catch-all"
        cloudflare = render_cloudflare(self.contract)
        assert "mcp(/.*)?" in cloudflare
        assert "mcpx" not in cloudflare

    def test_root_path_and_trailing_slash_resolution_match_generated_regex(self) -> None:
        root_contract = self.contract.model_dump(mode="json")
        root_contract["hosts"][0]["routes"] = [
            {
                "id": "app-root-block",
                "match": {"kind": "paths", "paths": ["/"], "trailing_slash": True},
                "action": {"kind": "status", "status": 404},
            },
            {
                "id": "app",
                "match": {"kind": "all"},
                "action": {"kind": "proxy", "service": "http://frontend:80"},
            },
        ]
        typed = validate_contract(root_contract)
        assert resolve_route(typed, "app", "/").id == "app-root-block"
        assert resolve_route(typed, "app", "//").id == "app"
        assert "location ~ ^/$ {" in render_nginx(typed)
        assert "path: '^/$'" in render_cloudflare(typed)

    def test_e2e_adapter_rejects_nginx_injection_values(self) -> None:
        for header in (
            "X-Recorder-Token $http_x_recorder_token; return 200;",
            "X-Recorder-Token $http_x_recorder_token\nreturn 200;",
            "X Recorder Token $token",
        ):
            invalid = self.contract.model_dump(mode="json")
            invalid["e2e_adapter"]["recorder_routes"][1]["headers"] = [header]
            with pytest.raises(ValueError, match=r"(invalid recorder header|control character)"):
                validate_contract(invalid)

        invalid_path = self.contract.model_dump(mode="json")
        invalid_path["e2e_adapter"]["recorder_routes"][0]["path"] = "/_e2e/ready; return 200;"
        with pytest.raises(ValueError, match="invalid path"):
            validate_contract(invalid_path)

        invalid_tls = self.contract.model_dump(mode="json")
        invalid_tls["e2e_adapter"]["tls"]["certificate"] = "/etc/nginx/certs/wren.pem; return 200;"
        with pytest.raises(ValueError, match="invalid Nginx path"):
            validate_contract(invalid_tls)

    def test_e2e_adapter_keeps_tls_and_recorder_routes_explicit(self) -> None:
        nginx = render_nginx(self.contract)
        assert "listen 443 ssl default_server;" in nginx
        assert "server_name app.wren.test;" in nginx
        for route in self.contract.e2e_adapter.recorder_routes:
            assert f"location = {route.path} {{" in nginx
        assert "docs.wren.test" not in nginx
        assert "/.well-known/oauth-protected-resource/mcp" not in nginx
