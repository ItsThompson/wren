"""Render and validate generated ingress adapter output."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from ingress_contract import (
        CLOUDFLARE_PATH,
        NGINX_PATH,
        _path_regex,
        load_contract,
        render_cloudflare,
        validate_contract,
    )
except ModuleNotFoundError:
    from .ingress_contract import (
        CLOUDFLARE_PATH,
        NGINX_PATH,
        _path_regex,
        load_contract,
        render_cloudflare,
        validate_contract,
    )


def _proxy_lines(upstream: str, headers: list[str] | None = None) -> list[str]:
    lines = [
        f"            proxy_pass http://{upstream};",
        "            proxy_set_header Host $host;",
        "            proxy_set_header X-Forwarded-Host $host;",
        "            proxy_set_header X-Forwarded-For $remote_addr;",
        "            proxy_set_header X-Forwarded-Proto https;",
    ]
    lines.extend(f"            proxy_set_header {header};" for header in headers or [])
    return lines


def _nginx_location(match: dict[str, Any], action: dict[str, Any], upstream: str) -> list[str]:
    if match["kind"] == "all":
        locations = ["location / {"]
    elif match["kind"] == "paths":
        locations = [f"location ~ {_path_regex(match)} {{"]
    elif match["kind"] == "allowlist":
        locations = [f"location = {path} {{" for path in match["exact"]]
        for prefix in match["prefix"]:
            locations.extend([f"location = {prefix} {{", f"location ^~ {prefix}/ {{"])
    else:
        raise ValueError(f"unknown match kind: {match['kind']}")

    lines: list[str] = []
    for location in locations:
        lines.append(f"        {location}")
        if action["kind"] == "status":
            lines.append(f"            return {action['status']};")
        else:
            lines.extend(_proxy_lines(upstream))
        lines.append("        }")
        lines.append("")
    return lines


def render_nginx(contract: dict[str, Any]) -> str:
    validate_contract(contract)
    adapter = contract["e2e_adapter"]
    app_host = next((host for host in contract["hosts"] if host["id"] == "app"), None)
    if app_host is None or not app_host["e2e_hostname"]:
        raise ValueError("E2E rendering requires the app hostname")
    e2e_hosts = [host for host in contract["hosts"] if host["e2e_hostname"]]
    if app_host not in e2e_hosts:
        raise ValueError("E2E rendering could not select the app host")
    recorder_upstream = urlsplit(adapter["recorder_service"]).hostname or ""
    recorder_port = urlsplit(adapter["recorder_service"]).port or 80
    services = {f"{recorder_upstream}:{recorder_port}"}
    for host in e2e_hosts:
        for route in host["routes"]:
            action = route["action"]
            if action["kind"] == "proxy":
                parsed = urlsplit(action["service"])
                services.add(f"{parsed.hostname}:{parsed.port or 80}")

    lines = [
        "# GENERATED FILE: python3 scripts/ingress_contract.py --write",
        "# Source: deployments/ingress/contract.json",
        "events {}",
        "",
        "http {",
        "    client_max_body_size 1m;",
        "",
    ]
    for service in sorted(services):
        name, port = service.split(":", 1)
        lines.append(f"    upstream {name} {{ server {service}; }}")
    lines.extend(
        [
            "",
            "    server {",
            "        listen 443 ssl default_server;",
            "        server_name _;",
            "",
        ]
    )
    lines.extend(
        [
            f"        ssl_certificate {adapter['tls']['certificate']};",
            f"        ssl_certificate_key {adapter['tls']['key']};",
            "        return 444;",
            "    }",
            "",
        ]
    )

    for host in e2e_hosts:
        lines.extend(
            [
                "    server {",
                "        listen 443 ssl;",
                f"        server_name {host['e2e_hostname']};",
                "",
                f"        ssl_certificate {adapter['tls']['certificate']};",
                f"        ssl_certificate_key {adapter['tls']['key']};",
                "",
            ]
        )
        if host["id"] == "app":
            for recorder_route in adapter["recorder_routes"]:
                lines.append(f"        location = {recorder_route['path']} {{")
                lines.extend(_proxy_lines(recorder_upstream, recorder_route["headers"]))
                lines.append("        }")
                lines.append("")
        for route in host["routes"]:
            action = route["action"]
            upstream = ""
            if action["kind"] == "proxy":
                upstream = urlsplit(action["service"]).hostname or ""
            lines.extend(_nginx_location(route["match"], action, upstream))
        lines.append("    }")
        lines.append("")
    lines.extend(["}", ""])
    return "\n".join(lines)


def generated_outputs_are_current(contract: dict[str, Any] | None = None) -> bool:
    contract = contract or load_contract()
    return (
        CLOUDFLARE_PATH.read_text(encoding="utf-8") == render_cloudflare(contract)
        and NGINX_PATH.read_text(encoding="utf-8") == render_nginx(contract)
    )


def output_contents(contract: dict[str, Any]) -> tuple[tuple[Path, str], ...]:
    return (
        (CLOUDFLARE_PATH, render_cloudflare(contract)),
        (NGINX_PATH, render_nginx(contract)),
    )
