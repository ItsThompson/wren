"""Render validated ingress models through the checked-in templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from scripts.ingress_contract import (
    CLOUDFLARE_PATH,
    NGINX_PATH,
    ROOT,
    _path_regex,
    load_contract,
    validate_contract,
)
from scripts.ingress_models import (
    Action,
    AllMatch,
    AllowlistMatch,
    Host,
    IngressContract,
    PathsMatch,
    ProxyAction,
    Route,
)

TEMPLATE_PATH = ROOT / "deployments/ingress/templates"
_ENVIRONMENT = Environment(
    loader=FileSystemLoader(TEMPLATE_PATH),
    undefined=StrictUndefined,
    autoescape=select_autoescape(
        enabled_extensions=("html", "xml"), default_for_string=False, default=False
    ),
    keep_trailing_newline=True,
)


@dataclass(frozen=True)
class NginxLocation:
    directive: str
    action: Action
    upstream: str | None = None
    headers: tuple[str, ...] = ()


@dataclass(frozen=True)
class NginxHost:
    hostname: str
    locations: tuple[NginxLocation, ...]


def _service_host(service: str) -> str:
    hostname = urlsplit(service).hostname
    if hostname is None:
        raise ValueError(f"service URL has no hostname: {service!r}")
    return hostname


def _service_address(service: str) -> str:
    parsed = urlsplit(service)
    return f"{_service_host(service)}:{parsed.port or 80}"


def _route_locations(route: Route) -> list[str]:
    match = route.match
    if isinstance(match, AllMatch):
        return ["location / {"]
    if isinstance(match, PathsMatch):
        return [f"location ~ {_path_regex(match)} {{"]
    if isinstance(match, AllowlistMatch):
        locations = [f"location = {path} {{" for path in match.exact]
        for prefix in match.prefix:
            locations.extend([f"location = {prefix} {{", f"location ^~ {prefix}/ {{"])
        return locations
    raise ValueError(f"unknown route match: {match!r}")


def _nginx_locations(route: Route) -> tuple[NginxLocation, ...]:
    upstream = None
    if isinstance(route.action, ProxyAction):
        upstream = _service_host(route.action.service)
    return tuple(
        NginxLocation(directive=directive, action=route.action, upstream=upstream)
        for directive in _route_locations(route)
    )


def _host_locations(
    host: Host,
    recorder_service: str,
    recorder_headers: dict[str, tuple[str, ...]],
) -> tuple[NginxLocation, ...]:
    locations: list[NginxLocation] = []
    if host.id == "app":
        recorder_upstream = _service_host(recorder_service)
        for path, headers in recorder_headers.items():
            locations.append(
                NginxLocation(
                    directive=f"location = {path} {{",
                    action=ProxyAction(kind="proxy", service=recorder_service),
                    upstream=recorder_upstream,
                    headers=headers,
                )
            )
    for route in host.routes:
        locations.extend(_nginx_locations(route))
    return tuple(locations)


def _nginx_context(contract: IngressContract) -> dict[str, Any]:
    adapter = contract.e2e_adapter
    e2e_hosts = [host for host in contract.hosts if host.e2e_hostname is not None]
    recorder_headers = {route.path: tuple(route.headers) for route in adapter.recorder_routes}
    upstreams = {_service_address(adapter.recorder_service)}
    for host in e2e_hosts:
        for route in host.routes:
            if isinstance(route.action, ProxyAction):
                upstreams.add(_service_address(route.action.service))
    return {
        "upstreams": tuple(
            {"name": address.rsplit(":", 1)[0], "address": address} for address in sorted(upstreams)
        ),
        "certificate": adapter.tls.certificate,
        "key": adapter.tls.key,
        "hosts": tuple(
            NginxHost(
                hostname=host.e2e_hostname or "",
                locations=_host_locations(host, adapter.recorder_service, recorder_headers),
            )
            for host in e2e_hosts
        ),
    }


def render_nginx(contract: object) -> str:
    typed_contract = validate_contract(contract)
    return _ENVIRONMENT.get_template("nginx.conf.j2").render(**_nginx_context(typed_contract))


def render_cloudflare(contract: object) -> str:
    typed_contract = validate_contract(contract)
    routes: list[dict[str, str | None]] = []
    for host in typed_contract.hosts:
        for route in host.routes:
            path = _path_regex(route.match)
            service = (
                route.action.service
                if isinstance(route.action, ProxyAction)
                else f"http_status:{route.action.status}"
            )
            routes.append(
                {
                    "hostname": f"${{{host.cloudflare_variable}}}",
                    "path": path,
                    "service": service,
                }
            )
    catch_all = typed_contract.catch_all
    catch_all_service = (
        catch_all.service
        if isinstance(catch_all, ProxyAction)
        else f"http_status:{catch_all.status}"
    )
    rendered = _ENVIRONMENT.get_template("cloudflare.yml.j2").render(
        tunnel="${CF_TUNNEL_ID}",
        routes=tuple(routes),
        catch_all=catch_all_service,
    )
    parsed = yaml.safe_load(rendered)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("ingress"), list):
        raise ValueError("Cloudflare template did not produce an ingress YAML document")
    return rendered


def generated_outputs_are_current(contract: IngressContract | None = None) -> bool:
    typed_contract = contract or load_contract()
    return all(
        path.exists() and path.read_text(encoding="utf-8") == content
        for path, content in output_contents(typed_contract)
    )


def output_contents(contract: IngressContract) -> tuple[tuple[Path, str], ...]:
    return (
        (CLOUDFLARE_PATH, render_cloudflare(contract)),
        (NGINX_PATH, render_nginx(contract)),
    )
