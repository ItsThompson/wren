"""Typed models and boundary constraints for the ingress contract."""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    model_validator,
)


def _is_ascii_alnum(character: str) -> bool:
    return character in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _is_dns_alnum(character: str) -> bool:
    return character in "abcdefghijklmnopqrstuvwxyz0123456789"


def _is_dns_label(label: str) -> bool:
    return (
        bool(label)
        and _is_dns_alnum(label[0])
        and _is_dns_alnum(label[-1])
        and all(_is_dns_alnum(character) or character == "-" for character in label)
    )


def _is_dns_name(value: str, *, require_dot: bool) -> bool:
    labels = value.split(".")
    return (not require_dot or len(labels) >= 2) and all(_is_dns_label(label) for label in labels)


def _validated_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if any(character in value for character in "\r\n\x00"):
        raise ValueError(f"{label} contains a control character")
    return value


def _validate_hostname(value: object) -> str:
    value = _validated_string(value, "hostname")
    if not _is_dns_name(value, require_dot=True):
        raise ValueError(f"invalid hostname: {value!r}")
    return value


def _validate_cloudflare_variable(value: object) -> str:
    value = _validated_string(value, "Cloudflare variable")
    if (
        not value.startswith("CF_")
        or not value[3:]
        or not all(character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in value[3:])
    ):
        raise ValueError(f"invalid Cloudflare variable: {value!r}")
    return value


def _validate_path(value: object) -> str:
    value = _validated_string(value, "path")
    if not value.startswith("/") or not all(
        _is_ascii_alnum(character) or character in "/._~!()*+,=@:%-" for character in value
    ):
        raise ValueError(f"invalid path: {value!r}")
    return value


def _validate_nginx_path(value: object) -> str:
    value = _validated_string(value, "Nginx path")
    if not value.startswith("/"):
        raise ValueError(f"invalid Nginx path: {value!r}")
    parts = value.split("/")[1:]
    if not parts or any(not part or part in {".", ".."} for part in parts):
        raise ValueError(f"invalid Nginx path: {value!r}")
    if any(
        not all(_is_ascii_alnum(character) or character in "._-" for character in part)
        for part in parts
    ):
        raise ValueError(f"invalid Nginx path: {value!r}")
    return value


def _is_header_value(value: str) -> bool:
    return bool(value) and all(
        _is_ascii_alnum(character) or character in ".-" for character in value
    )


def _is_header_variable(value: str) -> bool:
    return (
        bool(value)
        and value[0] in "abcdefghijklmnopqrstuvwxyz"
        and all(character in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in value)
    )


def _is_header_name(value: str) -> bool:
    return (
        bool(value)
        and _is_ascii_alnum(value[0])
        and all(_is_ascii_alnum(character) or character == "-" for character in value)
    )


def _validate_recorder_header(value: object) -> str:
    value = _validated_string(value, "recorder header")
    parts = value.split(" ")
    if len(parts) != 2 or not _is_header_name(parts[0]):
        raise ValueError(f"invalid recorder header: {value!r}")
    header_value = parts[1]
    if header_value.startswith("$"):
        if not _is_header_variable(header_value[1:]):
            raise ValueError(f"invalid recorder header: {value!r}")
    elif not _is_header_value(header_value):
        raise ValueError(f"invalid recorder header: {value!r}")
    return value


def _validate_service_url(value: object) -> str:
    value = _validated_string(value, "service URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"invalid service URL: {value!r}") from error
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.hostname is None
        or parsed.path != ""
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
        or not _is_dns_name(parsed.hostname, require_dot=False)
    ):
        raise ValueError(f"invalid service URL: {value!r}")
    return value


Hostname = Annotated[str, BeforeValidator(_validate_hostname)]
CloudflareVariable = Annotated[str, BeforeValidator(_validate_cloudflare_variable)]
IngressPath = Annotated[str, BeforeValidator(_validate_path)]
NginxPath = Annotated[str, BeforeValidator(_validate_nginx_path)]
ServiceUrl = Annotated[str, BeforeValidator(_validate_service_url)]
RecorderHeader = Annotated[str, BeforeValidator(_validate_recorder_header)]
Identifier = Annotated[str, StringConstraints(min_length=1)]


class IngressModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class ProxyAction(IngressModel):
    kind: Literal["proxy"]
    service: ServiceUrl


class StatusAction(IngressModel):
    kind: Literal["status"]
    status: Annotated[StrictInt, Field(ge=100, le=599)]


Action = Annotated[ProxyAction | StatusAction, Field(discriminator="kind")]


class AllMatch(IngressModel):
    kind: Literal["all"]


class PathsMatch(IngressModel):
    kind: Literal["paths"]
    paths: list[IngressPath] = Field(min_length=1)
    trailing_slash: bool

    @model_validator(mode="after")
    def require_unique_paths(self) -> PathsMatch:
        if len(set(self.paths)) != len(self.paths):
            raise ValueError("paths match entries must be unique")
        return self


class AllowlistMatch(IngressModel):
    kind: Literal["allowlist"]
    exact: list[IngressPath]
    prefix: list[IngressPath]

    @model_validator(mode="after")
    def require_paths(self) -> AllowlistMatch:
        if not self.exact and not self.prefix:
            raise ValueError("allowlist must define an exact or prefix path")
        if len(set(self.exact)) != len(self.exact) or len(set(self.prefix)) != len(self.prefix):
            raise ValueError("allowlist entries must be unique")
        return self


Match = Annotated[AllMatch | PathsMatch | AllowlistMatch, Field(discriminator="kind")]


class Route(IngressModel):
    id: Identifier
    match: Match
    action: Action


class Host(IngressModel):
    id: Identifier
    cloudflare_variable: CloudflareVariable
    e2e_hostname: Hostname | None = None
    routes: list[Route] = Field(min_length=1)

    @model_validator(mode="after")
    def require_terminal_catch_all(self) -> Host:
        all_route_indexes = [
            index for index, route in enumerate(self.routes) if route.match.kind == "all"
        ]
        if all_route_indexes and all_route_indexes != [len(self.routes) - 1]:
            raise ValueError(f"catch-all route on {self.id} must be last")
        route_ids = [route.id for route in self.routes]
        if len(set(route_ids)) != len(route_ids):
            raise ValueError(f"route IDs on {self.id} must be unique")
        return self


class TlsPaths(IngressModel):
    certificate: NginxPath
    key: NginxPath


class RecorderRoute(IngressModel):
    path: IngressPath
    headers: list[RecorderHeader] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_e2e_path(self) -> RecorderRoute:
        if not self.path.startswith("/_e2e/"):
            raise ValueError(f"recorder route must be under /_e2e/: {self.path}")
        return self


class E2eAdapter(IngressModel):
    tls: TlsPaths
    recorder_routes: list[RecorderRoute]
    recorder_service: ServiceUrl

    @model_validator(mode="after")
    def require_unique_recorder_paths(self) -> E2eAdapter:
        paths = [route.path for route in self.recorder_routes]
        if len(set(paths)) != len(paths):
            raise ValueError("recorder route paths must be unique")
        return self


class IngressContract(IngressModel):
    version: Literal[1]
    hosts: list[Host] = Field(min_length=1)
    catch_all: Action
    e2e_adapter: E2eAdapter

    @model_validator(mode="after")
    def require_unique_hosts_and_app(self) -> IngressContract:
        host_ids = [host.id for host in self.hosts]
        variables = [host.cloudflare_variable for host in self.hosts]
        e2e_hostnames = [host.e2e_hostname for host in self.hosts if host.e2e_hostname is not None]
        if len(set(host_ids)) != len(host_ids):
            raise ValueError("host IDs must be unique")
        if len(set(variables)) != len(variables):
            raise ValueError("Cloudflare variables must be unique")
        if len(set(e2e_hostnames)) != len(e2e_hostnames):
            raise ValueError("E2E hostnames must be unique")
        app_host = next((host for host in self.hosts if host.id == "app"), None)
        if app_host is None:
            raise ValueError("ingress contract must define the app host")
        if app_host.e2e_hostname is None:
            raise ValueError("ingress contract app host needs an E2E hostname")
        return self
