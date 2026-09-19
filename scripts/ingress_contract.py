#!/usr/bin/env python3
"""Validate and render the Wren ingress contract."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "deployments/ingress/contract.json"
CLOUDFLARE_PATH = ROOT / "deployments/cloudflare/config.yml"
NGINX_PATH = ROOT / "e2e/ingress/nginx.conf"

HOSTNAME_RE = re.compile(
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
)
SERVICE_HOST_RE = re.compile(
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*"
)
SERVICE_URL_RE = re.compile(
    rf"http://{SERVICE_HOST_RE.pattern}(?::[0-9]{{1,5}})?"
)
PATH_RE = re.compile(r"/[A-Za-z0-9._~!()*+,=@:%/-]+")
NGINX_PATH_RE = re.compile(r"/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+")
RECORDER_HEADER_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9-]* (?:\$[a-z][a-z0-9_]*|[A-Za-z0-9._-]+)"
)


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as contract_file:
        contract = json.load(contract_file)
    validate_contract(contract)
    return contract


def validate_contract(contract: object) -> None:
    if not isinstance(contract, dict) or contract.get("version") != 1:
        raise ValueError("ingress contract version must be 1")
    hosts = contract.get("hosts")
    if not isinstance(hosts, list) or not hosts:
        raise ValueError("ingress contract must define hosts")

    host_ids: set[str] = set()
    cloudflare_variables: set[str] = set()
    e2e_hostnames: set[str] = set()
    for host in hosts:
        if not isinstance(host, dict):
            raise ValueError("each ingress host must be an object")
        host_id = host.get("id")
        variable = host.get("cloudflare_variable")
        if not isinstance(host_id, str) or not host_id or host_id in host_ids:
            raise ValueError(f"invalid or duplicate host id: {host_id!r}")
        if (
            not isinstance(variable, str)
            or not re.fullmatch(r"CF_[A-Z0-9_]+", variable)
            or variable in cloudflare_variables
        ):
            raise ValueError(f"invalid or duplicate Cloudflare variable: {variable!r}")
        e2e_hostname = host.get("e2e_hostname")
        if e2e_hostname is not None and (
            not isinstance(e2e_hostname, str)
            or not HOSTNAME_RE.fullmatch(e2e_hostname)
            or e2e_hostname in e2e_hostnames
        ):
            raise ValueError(f"invalid or duplicate E2E hostname for {host_id}")
        routes = host.get("routes")
        if not isinstance(routes, list) or not routes:
            raise ValueError(f"host {host_id} must define routes")
        route_ids: set[str] = set()
        all_route_indexes: list[int] = []
        for index, route in enumerate(routes):
            if not isinstance(route, dict):
                raise ValueError(f"route on {host_id} must be an object")
            route_id = route.get("id")
            if not isinstance(route_id, str) or not route_id or route_id in route_ids:
                raise ValueError(f"invalid or duplicate route id on {host_id}")
            route_ids.add(route_id)
            _validate_match(route.get("match"), host_id, route_id)
            _validate_action(route.get("action"), host_id, route_id)
            if route["match"].get("kind") == "all":
                all_route_indexes.append(index)
        if all_route_indexes and all_route_indexes != [len(routes) - 1]:
            raise ValueError(f"catch-all route on {host_id} must be last")
        host_ids.add(host_id)
        cloudflare_variables.add(variable)
        if e2e_hostname is not None:
            e2e_hostnames.add(e2e_hostname)
    app_host = next((host for host in hosts if host["id"] == "app"), None)
    if app_host is None:
        raise ValueError("ingress contract must define the app host")
    if app_host.get("e2e_hostname") is None:
        raise ValueError("ingress contract app host needs an E2E hostname")

    catch_all = contract.get("catch_all")
    _validate_action(catch_all, "global", "catch-all")
    adapter = contract.get("e2e_adapter")
    if not isinstance(adapter, dict):
        raise ValueError("e2e_adapter must be an object")
    tls = adapter.get("tls")
    if (
        not isinstance(tls, dict)
        or not _is_safe_nginx_path(tls.get("certificate"))
        or not _is_safe_nginx_path(tls.get("key"))
    ):
        raise ValueError("e2e_adapter must define safe TLS certificate and key paths")
    recorder_service = adapter.get("recorder_service")
    if not _is_http_service(recorder_service):
        raise ValueError("e2e_adapter recorder_service must be an HTTP service")
    recorder_routes = adapter.get("recorder_routes")
    if not isinstance(recorder_routes, list):
        raise ValueError("e2e_adapter recorder_routes must be a list")
    recorder_paths: set[str] = set()
    for route in recorder_routes:
        if not isinstance(route, dict) or not isinstance(route.get("path"), str):
            raise ValueError("each recorder route must define a path")
        headers = route.get("headers", [])
        if not isinstance(headers, list) or any(
            not isinstance(header, str) or not RECORDER_HEADER_RE.fullmatch(header)
            for header in headers
        ):
            raise ValueError("recorder route headers must use safe name/value tokens")
        path = route["path"]
        if (
            not PATH_RE.fullmatch(path)
            or not path.startswith("/_e2e/")
            or path in recorder_paths
        ):
            raise ValueError(f"invalid or duplicate recorder route: {path}")
        recorder_paths.add(path)


def _validate_match(match: object, host_id: str, route_id: str) -> None:
    if not isinstance(match, dict):
        raise ValueError(f"missing match for {host_id}/{route_id}")
    kind = match.get("kind")
    if kind == "all":
        return
    if kind == "paths":
        paths = match.get("paths")
        if not isinstance(paths, list) or not paths or any(
            not isinstance(path, str) or not PATH_RE.fullmatch(path) for path in paths
        ):
            raise ValueError(f"paths match for {host_id}/{route_id} is invalid")
        if not isinstance(match.get("trailing_slash"), bool):
            raise ValueError(f"paths match for {host_id}/{route_id} needs trailing_slash")
        return
    if kind == "allowlist":
        for field in ("exact", "prefix"):
            values = match.get(field)
            if not isinstance(values, list) or any(
                not isinstance(path, str) or not PATH_RE.fullmatch(path) for path in values
            ):
                raise ValueError(f"allowlist {field} for {host_id}/{route_id} is invalid")
        if not match["exact"] and not match["prefix"]:
            raise ValueError(f"allowlist for {host_id}/{route_id} is empty")
        return
    raise ValueError(f"unknown match kind for {host_id}/{route_id}: {kind!r}")


def _is_safe_nginx_path(path: object) -> bool:
    if not isinstance(path, str) or NGINX_PATH_RE.fullmatch(path) is None:
        return False
    return all(part not in {".", ".."} for part in path.split("/")[1:])


def _is_http_service(service: object) -> bool:
    if not isinstance(service, str) or SERVICE_URL_RE.fullmatch(service) is None:
        return False
    try:
        parsed = urlsplit(service)
        return parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        return False


def _validate_action(action: object, host_id: str, route_id: str) -> None:
    if not isinstance(action, dict):
        raise ValueError(f"missing action for {host_id}/{route_id}")
    kind = action.get("kind")
    if kind == "proxy":
        if not _is_http_service(action.get("service")):
            raise ValueError(f"proxy action for {host_id}/{route_id} needs an HTTP service")
        return
    if (
        kind == "status"
        and isinstance(action.get("status"), int)
        and 100 <= action["status"] <= 599
    ):
        return
    raise ValueError(f"invalid action for {host_id}/{route_id}")


def _match_path(match: dict[str, Any], path: str) -> bool:
    kind = match["kind"]
    if kind == "all":
        return True
    if kind == "paths":
        candidates = {path}
        if match["trailing_slash"] and path.endswith("/") and not path.endswith("//"):
            candidates.add(path[:-1])
        return any(candidate in match["paths"] for candidate in candidates)
    if kind == "allowlist":
        if path in match["exact"]:
            return True
        return any(path == prefix or path.startswith(f"{prefix}/") for prefix in match["prefix"])
    raise ValueError(f"unknown match kind: {kind}")


def resolve_route(contract: dict[str, Any], host_id: str, path: str) -> dict[str, Any]:
    """Return the first route action selected for a host and path."""
    validate_contract(contract)
    for host in contract["hosts"]:
        if host["id"] == host_id:
            for route in host["routes"]:
                if _match_path(route["match"], path):
                    return copy.deepcopy(route)
            break
    return {
        "id": "catch-all",
        "match": {"kind": "all"},
        "action": copy.deepcopy(contract["catch_all"]),
    }


def _escaped_path(path: str) -> str:
    return re.escape(path.lstrip("/")).replace("\\-", "-")


def _path_regex(match: dict[str, Any]) -> str | None:
    if match["kind"] == "all":
        return None
    if match["kind"] == "paths":
        paths = [_escaped_path(path) for path in match["paths"]]
        path_expression = paths[0] if len(paths) == 1 else f"({'|'.join(paths)})"
        suffix = "/?" if match["trailing_slash"] else ""
        return rf"^/{path_expression}{suffix}$"
    alternatives = [
        rf"{_escaped_path(path)}(/.*)?" for path in match["prefix"]
    ]
    alternatives.extend(_escaped_path(path) for path in match["exact"])
    return rf"^/({'|'.join(alternatives)})$"


def _cloudflare_service(action: dict[str, Any]) -> str:
    if action["kind"] == "proxy":
        return action["service"]
    return f"http_status:{action['status']}"


def render_cloudflare(contract: dict[str, Any]) -> str:
    validate_contract(contract)
    lines = [
        "# GENERATED FILE: python3 scripts/ingress_contract.py --write",
        "# Source: deployments/ingress/contract.json",
        "tunnel: ${CF_TUNNEL_ID}",
        "credentials-file: /etc/cloudflared/credentials.json",
        "",
        "ingress:",
    ]
    for host in contract["hosts"]:
        for route in host["routes"]:
            lines.append(f"  - hostname: ${{{host['cloudflare_variable']}}}")
            path_regex = _path_regex(route["match"])
            if path_regex is not None:
                lines.append(f"    path: '{path_regex}'")
            lines.append(f"    service: {_cloudflare_service(route['action'])}")
    catch_all = contract["catch_all"]
    lines.append(f"  - service: {_cloudflare_service(catch_all)}")
    return "\n".join(lines) + "\n"


def _write_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write generated configs")
    parser.add_argument(
        "--check", action="store_true", help="fail when generated configs are stale"
    )
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    contract = load_contract()
    try:
        from ingress_render import output_contents
    except ModuleNotFoundError:
        from .ingress_render import output_contents

    outputs = output_contents(contract)
    if args.check:
        stale = [
            str(path.relative_to(ROOT))
            for path, content in outputs
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            print("stale generated ingress output: " + ", ".join(stale))
            return 1
        return 0
    for path, content in outputs:
        _write_atomic(path, content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
