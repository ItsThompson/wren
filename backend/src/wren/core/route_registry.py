"""Declarative route -> access-level registry with fail-safe coverage.

Every mounted product route must have a declared access level. A coverage test
(``tests/test_route_registry.py``) compares the mounted routes against the
registries below and **fails safe (deny)** if any mounted route has no entry, so
an unscoped endpoint cannot ship: route registration is cross-checked against a
central access registry.

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
# that mounts them (accounts, roadmaps, OAuth). The coverage test fails
# safe (deny) the moment a mounted product route is missing an entry.
#
# The /auth endpoints are PUBLIC: they establish or tear down a session rather
# than resolving one via require_user, so they gate no caller identity. They are
# mounted on the external app only (no internal-app auth surface).
EXTERNAL_ROUTE_ACCESS: RouteRegistry = {
    RouteKey(method="POST", path="/auth/register"): AccessLevel.PUBLIC,
    RouteKey(method="POST", path="/auth/login"): AccessLevel.PUBLIC,
    RouteKey(method="POST", path="/auth/refresh"): AccessLevel.PUBLIC,
    RouteKey(method="POST", path="/auth/logout"): AccessLevel.PUBLIC,
    # Roadmap authoring: create a draft and read an owned roadmap. Both
    # resolve the human session via require_user (owner-scoped in the service).
    RouteKey(method="POST", path="/roadmaps"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}"): AccessLevel.EXTERNAL_COOKIE,
    # Iterative edit: the atomic op-list PATCH under If-Match optimistic
    # concurrency. Owner-scoped draft-only write, resolving the human session via
    # require_user (the service rejects a stale revision with 409 and an invalid
    # op with 422).
    RouteKey(method="PATCH", path="/roadmaps/{roadmap_id}"): AccessLevel.EXTERNAL_COOKIE,
    # Full-document import: the PUT escape hatch replacing the entire draft
    # under If-Match optimistic concurrency. Owner-scoped draft-only content write
    # (published/archived -> 409 IMMUTABLE), resolving the human session via
    # require_user.
    RouteKey(method="PUT", path="/roadmaps/{roadmap_id}"): AccessLevel.EXTERNAL_COOKIE,
    # Roadmap validate + publish lifecycle: owner-scoped draft actions on
    # the :verb sub-resource. Publish is the one-way draft -> published
    # transition; both resolve the human session via require_user.
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}:validate"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}:publish"): AccessLevel.EXTERNAL_COOKIE,
    # Fork + presentation-only metadata edit, both agent+web callable.
    # Fork seeds a new draft from any readable roadmap (own or
    # public); the metadata PATCH edits title/description/subject_tags and stays
    # allowed post-publish (not If-Match-guarded). Both resolve the human session
    # via require_user and are owner-scoped in the service (fork's source read is
    # readability-scoped, not owner-scoped).
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}:fork"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="PATCH", path="/roadmaps/{roadmap_id}/metadata"): AccessLevel.EXTERNAL_COOKIE,
    # Study-time read projections: the purpose-built reads the web views and
    # (mirrored on the internal app) the MCP read tools consume. All resolve the
    # human session via require_user; readability is enforced in the service
    # (owner draft preview, or a non-owner reading a public published/archived
    # roadmap; private -> 404, no existence leak).
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}/overview"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(
        method="GET", path="/roadmaps/{roadmap_id}/nodes/{subsection_id}"
    ): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(
        method="GET", path="/roadmaps/{roadmap_id}/sections/{section_id}"
    ): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}/search"): AccessLevel.EXTERNAL_COOKIE,
    # Web-only lifecycle: visibility toggle, archive, and delete. Mounted on
    # the external (human) app ONLY: no internal-app route and no MCP tool.
    # All resolve the human session via require_user and are
    # owner-scoped in the service; delete is guarded by a zero-followers check.
    RouteKey(method="PUT", path="/roadmaps/{roadmap_id}/visibility"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}:archive"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="DELETE", path="/roadmaps/{roadmap_id}"): AccessLevel.EXTERNAL_COOKIE,
    # Follow, progress, and server-computed next: the study-time surface over
    # the progress service. All resolve the human session via require_user and are
    # scoped to that user (another user's progress is never returned).
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}/follow"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}/progress"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}/progress"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}/next"): AccessLevel.EXTERNAL_COOKIE,
    # Per-user deadline set/clear: editable anytime, drives a countdown
    # only (no pacing/forecast). Resolves the human session via require_user and
    # is scoped to that user's progress record.
    RouteKey(method="PUT", path="/roadmaps/{roadmap_id}/deadline"): AccessLevel.EXTERNAL_COOKIE,
    # OAuth 2.1 AS, external-only. The AS-handshake endpoints are OAUTH
    # (unauthenticated protocol surface: discovery, DCR, authorize, token,
    # revoke); the SPA-driven consent decision and connected-clients management
    # resolve the human session via require_user (EXTERNAL_COOKIE).
    RouteKey(method="GET", path="/.well-known/oauth-authorization-server"): AccessLevel.OAUTH,
    RouteKey(method="GET", path="/jwks"): AccessLevel.OAUTH,
    RouteKey(method="POST", path="/register"): AccessLevel.OAUTH,
    RouteKey(method="GET", path="/authorize"): AccessLevel.OAUTH,
    RouteKey(method="GET", path="/authorize/context"): AccessLevel.OAUTH,
    RouteKey(method="POST", path="/authorize/decision"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="POST", path="/token"): AccessLevel.OAUTH,
    RouteKey(method="POST", path="/revoke"): AccessLevel.OAUTH,
    RouteKey(method="GET", path="/me/clients"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="DELETE", path="/me/clients/{client_id}"): AccessLevel.EXTERNAL_COOKIE,
    # Dashboard + public profile. The private
    # dashboard resolves the human session via require_user (EXTERNAL_COOKIE) and
    # is caller-scoped (authored + followed). The public profile is PUBLIC: it
    # resolves no identity and returns only the handle owner's published-public
    # roadmaps (no draft/private/archived or social-graph leak). Both are mounted
    # on the external app only.
    RouteKey(method="GET", path="/me/dashboard"): AccessLevel.EXTERNAL_COOKIE,
    RouteKey(method="GET", path="/users/{handle}"): AccessLevel.PUBLIC,
    # Shipped SKILL.md authoring guidance. PUBLIC:
    # generic agent guidance served for download/copy, not user data, so it
    # resolves no identity. Referenced from the MCP tool descriptions so an agent
    # can discover it. Mounted on the external app only.
    RouteKey(method="GET", path="/skill"): AccessLevel.PUBLIC,
}
# Internal app routes (:8001), reachable only by the MCP server on compute-net.
# Every route resolves identity via require_internal_user (the trusted X-User-ID
# header behind INTERNAL_API_TOKEN), so all are INTERNAL_TRUSTED. These mirror the
# external roadmap surface op-for-op (see wren.roadmaps.api_internal); the MCP
# tools are thin clients of exactly these endpoints.
INTERNAL_ROUTE_ACCESS: RouteRegistry = {
    RouteKey(method="POST", path="/roadmaps"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="PATCH", path="/roadmaps/{roadmap_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="PUT", path="/roadmaps/{roadmap_id}"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}:validate"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}:publish"): AccessLevel.INTERNAL_TRUSTED,
    # Fork + metadata edit mirrored on the internal app so the MCP tools
    # call them: both resolve the trusted X-User-ID and are scoped in
    # the service the same way as the external routes.
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}:fork"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="PATCH", path="/roadmaps/{roadmap_id}/metadata"): AccessLevel.INTERNAL_TRUSTED,
    # Study-time read projections mirrored on the internal app so the MCP
    # read tools call them: overview / node / paginated section /
    # search, each resolving the trusted X-User-ID and readability-scoped in the
    # service the same way as the external routes.
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}/overview"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(
        method="GET", path="/roadmaps/{roadmap_id}/nodes/{subsection_id}"
    ): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(
        method="GET", path="/roadmaps/{roadmap_id}/sections/{section_id}"
    ): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}/search"): AccessLevel.INTERNAL_TRUSTED,
    # Progress surface, mirrored on the internal app so the MCP progress
    # tools call it: follow / snapshot / explicit-set / next, each
    # resolving the trusted X-User-ID and scoped to that user.
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}/follow"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}/progress"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="POST", path="/roadmaps/{roadmap_id}/progress"): AccessLevel.INTERNAL_TRUSTED,
    RouteKey(method="GET", path="/roadmaps/{roadmap_id}/next"): AccessLevel.INTERNAL_TRUSTED,
    # Per-user deadline set/clear, mirrored on the internal app so the MCP
    # progress tools can call it: resolves the trusted X-User-ID and
    # is scoped to that user's progress record (countdown only, no pacing).
    RouteKey(method="PUT", path="/roadmaps/{roadmap_id}/deadline"): AccessLevel.INTERNAL_TRUSTED,
}

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
