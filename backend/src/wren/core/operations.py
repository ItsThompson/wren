"""Backend operation identity and error-reporting adapter.

The route registry owns access policy. This module owns the separate reporting
identity for a mounted route, keeping operation names stable and low-cardinality
when FastAPI reports an exception after path parameters have been expanded.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import sqlalchemy.exc
import structlog

from wren_common.reporting import (
    Domain,
    Kind,
    LogEvent,
    Operation,
    ReportLevel,
    report_error,
)

if TYPE_CHECKING:
    from starlette.requests import Request


# Stable names are deliberately independent of the expanded URL. They are also
# useful to callers that need to report a failure before FastAPI has matched a
# route (for example malformed requests).
ROUTE_OPERATIONS: dict[tuple[str, str], str] = {
    ("POST", "/auth/register"): "accounts.register",
    ("POST", "/auth/login"): "accounts.login",
    ("POST", "/auth/refresh"): "accounts.refresh",
    ("POST", "/auth/logout"): "accounts.logout",
    ("POST", "/roadmaps"): "roadmaps.create",
    ("GET", "/roadmaps/{roadmap_id}"): "roadmaps.get",
    ("PATCH", "/roadmaps/{roadmap_id}"): "roadmaps.patch",
    ("PUT", "/roadmaps/{roadmap_id}"): "roadmaps.replace",
    ("POST", "/roadmaps/{roadmap_id}:validate"): "roadmaps.validate",
    ("POST", "/roadmaps/{roadmap_id}:publish"): "roadmaps.publish",
    ("POST", "/roadmaps/{roadmap_id}:fork"): "roadmaps.fork",
    ("PATCH", "/roadmaps/{roadmap_id}/metadata"): "roadmaps.edit_metadata",
    ("GET", "/roadmaps/{roadmap_id}/overview"): "roadmaps.overview",
    ("GET", "/roadmaps/{roadmap_id}/nodes/{subsection_id}"): "roadmaps.node",
    ("GET", "/roadmaps/{roadmap_id}/sections/{section_id}"): "roadmaps.section",
    ("GET", "/roadmaps/{roadmap_id}/search"): "roadmaps.search",
    ("PUT", "/roadmaps/{roadmap_id}/published-visibility"): "roadmaps.published_visibility",
    ("POST", "/roadmaps/{roadmap_id}:archive"): "roadmaps.archive",
    ("DELETE", "/roadmaps/{roadmap_id}"): "roadmaps.delete",
    ("POST", "/roadmaps/{roadmap_id}/follow"): "progress.follow",
    ("GET", "/roadmaps/{roadmap_id}/progress"): "progress.get",
    ("POST", "/roadmaps/{roadmap_id}/progress"): "progress.update",
    ("GET", "/roadmaps/{roadmap_id}/next"): "progress.next",
    ("PUT", "/roadmaps/{roadmap_id}/deadline"): "progress.deadline",
    ("GET", "/.well-known/oauth-authorization-server"): "oauth.metadata",
    ("GET", "/jwks"): "oauth.jwks",
    ("POST", "/register"): "oauth.register_client",
    ("GET", "/authorize"): "oauth.authorize",
    ("GET", "/authorize/context"): "oauth.authorize_context",
    ("POST", "/authorize/decision"): "oauth.authorize_decision",
    ("POST", "/token"): "oauth.token",
    ("POST", "/revoke"): "oauth.revoke",
    ("GET", "/me/clients"): "oauth.list_clients",
    ("DELETE", "/me/clients/{client_id}"): "oauth.revoke_client",
    ("GET", "/me/dashboard"): "roadmaps.dashboard",
    ("POST", "/me/onboarding:complete"): "accounts.complete_onboarding",
    ("GET", "/users/{handle}"): "accounts.profile",
    ("GET", "/skill"): "skill.get",
}

_DOMAIN_BY_PREFIX = {
    "accounts": "accounts",
    "oauth": "oauth",
    "progress": "progress",
    "roadmaps": "roadmaps",
    "skill": "skill",
}


def _template_for_request(request: Request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) else "http.500"


def operation_for_request(request: Request) -> str:
    """Return the bounded operation name for a matched request."""
    key = (request.method.upper(), _template_for_request(request))
    return ROUTE_OPERATIONS.get(key, "http.500")


def _log_event(value: str) -> LogEvent:
    try:
        return LogEvent(value)
    except ValueError:
        return LogEvent.UNHANDLED_EXCEPTION


def _domain_for_operation(operation: str) -> Domain | None:
    prefix = operation.split(".", 1)[0]
    value = _DOMAIN_BY_PREFIX.get(prefix)
    if value is None:
        return None
    return Domain(value)


def _error_kind(exception: BaseException) -> Kind:
    """Classify operational failures from the most specific boundary outward."""
    if isinstance(exception, (asyncio.TimeoutError, httpx.TimeoutException)):
        return Kind.TIMEOUT
    if isinstance(exception, sqlalchemy.exc.TimeoutError):
        return Kind.TIMEOUT
    if isinstance(exception, sqlalchemy.exc.SQLAlchemyError):
        return Kind.DATABASE
    if isinstance(exception, httpx.HTTPError):
        return Kind.UPSTREAM
    return Kind.INTERNAL


def _report(
    exception: BaseException,
    *,
    operation_name: str,
    domain_name: str | None,
    kind_name: str,
    log_event_name: str,
    level_name: str,
    user_id: str | None,
    context_data: dict[str, str | bool | int | float | None],
    bounded_tags: dict[str, str],
    group_key: str | None,
    logger: object | None = None,
) -> None:
    operation: Operation = operation_name
    domain = Domain(domain_name) if domain_name is not None else None
    try:
        report_error(
            exception,
            operation=operation,
            domain=domain,
            kind=Kind(kind_name),
            user_id=user_id,
            log_event=_log_event(log_event_name),
            level=ReportLevel(level_name),
            bounded_tags=bounded_tags,
            context_data=context_data,
            group_key=group_key,
            group_exact=True,
            logger=logger,
        )
    except Exception:  # noqa: BLE001 - reporting must never alter request behavior
        structlog.get_logger("wren-core").warning(
            "error_report_failed", operation=operation_name, exc_info=True
        )


def report_backend_failure(
    request: Request, exception: BaseException, *, logger: object | None = None
) -> None:
    """Report an unexpected backend exception without changing its behavior.

    The shared reporter classifies recoverable errors by status. This adapter
    supplies the stable route operation and correlation context while retaining
    the original exception for the exception handler to render and re-raise.
    """
    operation_name = operation_for_request(request)
    safe_template = _template_for_request(request)
    if safe_template == "http.500":
        safe_template = operation_name
    error_kind = _error_kind(exception)
    context: dict[str, str | bool | int | float | None] = {
        "method": request.method,
        "path": safe_template,
        "template": safe_template,
        "status": 500,
    }
    if error_kind is not Kind.INTERNAL:
        context["error_kind"] = error_kind.value
    user_id = structlog.contextvars.get_contextvars().get("user_id")
    _report(
        exception,
        operation_name=operation_name,
        domain_name=_domain_for_operation(operation_name),
        kind_name=error_kind.value,
        log_event_name="unhandled_exception",
        level_name="error",
        user_id=user_id if isinstance(user_id, str) else None,
        bounded_tags={
            "operation": operation_name,
            **({"error_kind": error_kind.value} if error_kind is not Kind.INTERNAL else {}),
        },
        context_data=context,
        group_key=operation_name,
        logger=logger,
    )


def report_cleanup_failure(exception: BaseException) -> None:
    """Report a failed OAuth cleanup sweep with a stable maintenance identity."""
    error_kind = _error_kind(exception)
    _report(
        exception,
        operation_name="oauth.cleanup",
        domain_name="oauth",
        kind_name=error_kind.value,
        log_event_name=LogEvent.UNHANDLED_EXCEPTION.value,
        level_name="error",
        user_id=None,
        bounded_tags={
            "operation": "oauth.cleanup",
            **({"error_kind": error_kind.value} if error_kind is not Kind.INTERNAL else {}),
        },
        context_data={
            "status": 500,
            **({"error_kind": error_kind.value} if error_kind is not Kind.INTERNAL else {}),
        },
        group_key=f"oauth.cleanup.{error_kind.value}",
    )


__all__ = [
    "ROUTE_OPERATIONS",
    "operation_for_request",
    "report_backend_failure",
    "report_cleanup_failure",
]
