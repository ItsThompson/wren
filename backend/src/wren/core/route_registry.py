"""Declarative route -> access-level registry with fail-safe coverage.

Every mounted product route must have a declared access level. A coverage test
(``tests/test_route_registry.py``) compares the mounted routes against the
registries below and **fails safe (deny)** if any mounted route has no entry, so
an unscoped endpoint cannot ship. This mirrors gofin's ``VerifyRegistration``
(route registration cross-checked against a central access registry).

The registries are declared centrally and separately from where routers are
mounted, on purpose: forgetting to declare a route is exactly what the coverage
test catches. The same path can carry different access levels on the two apps
(e.g. ``POST /roadmaps`` is external-cookie on :8000 and internal-trusted on
:8001), so the registries are per-app.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import FastAPI


class AccessLevel(StrEnum):
    """How a route resolves and gates identity."""

    PUBLIC = "public"  # no authentication (landing, well-known metadata, /skill)
    EXTERNAL_COOKIE = "external-cookie"  # require_user (human session cookie)
    INTERNAL_TRUSTED = "internal-trusted"  # require_internal_user (trusted X-User-ID)
    OAUTH = "oauth"  # OAuth 2.1 bearer / AS handshake endpoints


@dataclass(frozen=True, order=True)
class RouteKey:
    """A mounted route identified by method + matched path template."""

    method: str
    path: str


RouteRegistry = Mapping[RouteKey, AccessLevel]

# Declarative per-app registries. Product routes are declared here by the slice
# that mounts them (accounts #6, roadmaps #7+, OAuth #18); until then both apps
# expose only infra/docs routes, so these are empty. The coverage test fails safe
# (deny) the moment a mounted product route is missing an entry.
EXTERNAL_ROUTE_ACCESS: RouteRegistry = {}
INTERNAL_ROUTE_ACCESS: RouteRegistry = {}

# OpenAPI operation keys that are HTTP methods (a path item also carries non-method
# keys such as "parameters").
_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


def mounted_product_routes(app: FastAPI) -> list[RouteKey]:
    """Every access-controlled route on ``app``, read from its OpenAPI document.

    The product/API surface is exactly the OpenAPI paths. Framework and infra
    endpoints (liveness, readiness, the metrics scrape, the docs) are mounted with
    ``include_in_schema=False`` and so are excluded by construction; only real
    product endpoints (which clients and codegen also consume) require a declared
    access level. This reads a stable public API rather than walking FastAPI's
    internal route tree.
    """
    paths: dict[str, Any] = app.openapi().get("paths", {})
    keys: list[RouteKey] = []
    for path, operations in paths.items():
        for method in operations:
            if method.lower() in _HTTP_METHODS:
                keys.append(RouteKey(method=method.upper(), path=path))
    return keys


@dataclass(frozen=True)
class CoverageReport:
    """Result of cross-checking mounted routes against a registry."""

    undeclared: list[RouteKey]  # mounted but no declared level -> DENY (coverage fails)
    orphaned: list[RouteKey]  # declared but not mounted -> stale registry entry

    @property
    def is_covered(self) -> bool:
        return not self.undeclared and not self.orphaned


def verify_route_coverage(app: FastAPI, registry: RouteRegistry) -> CoverageReport:
    """Compare mounted routes against ``registry`` in both directions.

    ``undeclared`` (mounted without a declared level) is the security-critical,
    fail-safe-deny direction; ``orphaned`` (declared but never bound) catches a
    stale or mistyped registry entry.
    """
    mounted = mounted_product_routes(app)
    mounted_set = set(mounted)
    undeclared = sorted(key for key in mounted if key not in registry)
    orphaned = sorted(key for key in registry if key not in mounted_set)
    return CoverageReport(undeclared=undeclared, orphaned=orphaned)
