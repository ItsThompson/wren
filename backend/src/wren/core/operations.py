"""Backend error-reporting adapter."""

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


_DOMAIN_BY_ROUTE_TAG = {
    "accounts": Domain.ACCOUNTS,
    "auth": Domain.ACCOUNTS,
    "listing": Domain.ACCOUNTS,
    "onboarding": Domain.ACCOUNTS,
    "oauth": Domain.OAUTH,
    "progress": Domain.PROGRESS,
    "roadmaps": Domain.ROADMAPS,
    "skill": Domain.SKILL,
}


def _template_for_request(request: Request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) else "http.500"


def operation_for_request(request: Request) -> str:
    """Return a domain-scoped OpenAPI operation ID for a matched request."""
    route = request.scope.get("route")
    operation_id = getattr(route, "unique_id", None)
    domain = _domain_for_request(request)
    if not isinstance(operation_id, str) or not operation_id or domain is None:
        return "http.500"
    return f"{domain.value}.{operation_id}"


def _log_event(value: str) -> LogEvent:
    try:
        return LogEvent(value)
    except ValueError:
        return LogEvent.UNHANDLED_EXCEPTION


def _domain_for_request(request: Request) -> Domain | None:
    route = request.scope.get("route")
    tags = getattr(route, "tags", None)
    if not isinstance(tags, list) or len(tags) != 1:
        return None
    return _DOMAIN_BY_ROUTE_TAG.get(tags[0])


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
        domain_name=_domain_for_request(request),
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
    "operation_for_request",
    "report_backend_failure",
    "report_cleanup_failure",
]
