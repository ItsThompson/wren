"""Error contract: the single boundary between the service layer and HTTP.

The service layer raises :class:`WrenError` subclasses; this module maps the whole
hierarchy to RFC 9457 ``application/problem+json`` in one exception handler, so
every transport (external REST, internal REST, MCP over internal REST) emits one
error contract (spec sections 05, 06). FastAPI's ``RequestValidationError`` is
mapped into the same field-map shape so clients handle a single format.

Error codes are single-sourced as :class:`ErrorCode`; the machine-readable ``code``
and the human ``title`` travel in the body so an agent can self-correct without a
human (a stale-revision 409 says "re-read", a 422 names the offending IDs).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

from wren.core.app_factory import ExceptionHandler, ExceptionKey

PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"

# Stable identifier base for the ``type`` member. RFC 9457 ``type`` URIs need not
# be dereferenceable; they are stable identifiers keyed off the error code.
ERROR_TYPE_BASE = "https://usewren.com/errors/"


class ErrorCode(StrEnum):
    """Single source of machine-readable error codes carried in ``problem.code``.

    Later slices extend this with further domain-specific codes (e.g.
    ``DELETE_HAS_FOLLOWERS``). ``STALE_REVISION`` and ``IMMUTABLE`` are the two
    409 sub-codes the write contract needs: ``STALE_REVISION`` for an optimistic-
    concurrency mismatch (re-read) and ``IMMUTABLE`` for a structural write against
    a published/archived roadmap (fork-to-change), both defined in spec section 06.
    """

    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"
    UNAUTHORIZED = "UNAUTHORIZED"
    VALIDATION = "VALIDATION"
    CONFLICT = "CONFLICT"
    STALE_REVISION = "STALE_REVISION"
    IMMUTABLE = "IMMUTABLE"


def _type_uri(code: ErrorCode) -> str:
    """Derive the ``type`` URI from a code: ``STALE_REVISION`` -> ``.../stale-revision``."""
    return f"{ERROR_TYPE_BASE}{code.value.lower().replace('_', '-')}"


class Violation(BaseModel):
    """One structural rule failure, model-recoverable by naming the rule and IDs.

    Produced by the structural validator (spec section 05 ``validation.py``, a
    later slice) and carried in a ``Validation`` error's problem+json body. Lives
    in the error contract because it is part of the wire shape every client reads.
    """

    rule: str
    ids: list[str]
    message: str


class WrenError(Exception):
    """Base of the service-layer error hierarchy mapped to problem+json.

    Subclasses fix the HTTP ``status``, default ``code``, and human ``title``.
    Callers pass a recoverable ``detail`` and may override ``code`` with a more
    specific value (e.g. ``Conflict(..., code=ErrorCode.STALE_REVISION)``) and
    attach a field-level ``fields`` map.
    """

    status: ClassVar[int]
    title: ClassVar[str]
    default_code: ClassVar[ErrorCode]

    def __init__(
        self,
        detail: str,
        *,
        code: ErrorCode | None = None,
        fields: Mapping[str, str] | None = None,
        instance: str | None = None,
    ) -> None:
        self.detail = detail
        self.code = code or self.default_code
        self.fields = dict(fields) if fields else None
        self.instance = instance
        super().__init__(detail)


class NotFound(WrenError):
    status = 404
    title = "Resource not found"
    default_code = ErrorCode.NOT_FOUND


class Forbidden(WrenError):
    status = 403
    title = "Access forbidden"
    default_code = ErrorCode.FORBIDDEN


class Unauthorized(WrenError):
    status = 401
    title = "Authentication required"
    default_code = ErrorCode.UNAUTHORIZED


class Conflict(WrenError):
    status = 409
    title = "Conflict with the current state"
    default_code = ErrorCode.CONFLICT


class Validation(WrenError):
    """422; additionally carries a ``violations`` array (publish hard-block)."""

    status = 422
    title = "Validation failed"
    default_code = ErrorCode.VALIDATION

    def __init__(
        self,
        detail: str,
        *,
        violations: list[Violation] | None = None,
        code: ErrorCode | None = None,
        fields: Mapping[str, str] | None = None,
        instance: str | None = None,
    ) -> None:
        super().__init__(detail, code=code, fields=fields, instance=instance)
        self.violations = list(violations) if violations else []


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details body. Extension members (``code``/``fields``/
    ``violations``) are omitted from the wire when unset (``exclude_none``)."""

    type: str
    title: str
    status: int
    code: ErrorCode
    detail: str
    instance: str | None = None
    fields: dict[str, str] | None = None
    violations: list[Violation] | None = None


def _loc_to_field(loc: tuple[int | str, ...]) -> str:
    """Flatten a Pydantic error location into a dotted field path (``body.title``)."""
    return ".".join(str(part) for part in loc)


def _problem_from_wren_error(exc: WrenError, instance: str | None) -> ProblemDetail:
    violations = exc.violations if isinstance(exc, Validation) else None
    return ProblemDetail(
        type=_type_uri(exc.code),
        title=exc.title,
        status=exc.status,
        code=exc.code,
        detail=exc.detail,
        instance=exc.instance or instance,
        fields=exc.fields,
        violations=violations or None,
    )


def _problem_from_request_validation(
    exc: RequestValidationError, instance: str | None
) -> ProblemDetail:
    fields = {_loc_to_field(error["loc"]): str(error["msg"]) for error in exc.errors()}
    return ProblemDetail(
        type=_type_uri(Validation.default_code),
        title="Request validation failed",
        status=Validation.status,
        code=Validation.default_code,
        detail=f"{len(fields)} request field(s) failed validation.",
        instance=instance,
        fields=fields,
    )


def _render(problem: ProblemDetail) -> Response:
    return Response(
        content=problem.model_dump_json(exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_JSON_MEDIA_TYPE,
    )


async def handle_wren_error(request: Request, exc: Exception) -> Response:
    """Map any :class:`WrenError` subclass to problem+json (registered on the base)."""
    if not isinstance(exc, WrenError):  # pragma: no cover - registered only for WrenError
        raise exc
    return _render(_problem_from_wren_error(exc, request.url.path))


async def handle_request_validation_error(request: Request, exc: Exception) -> Response:
    """Map FastAPI's ``RequestValidationError`` into the same field-map shape."""
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registered for this type
        raise exc
    return _render(_problem_from_request_validation(exc, request.url.path))


def build_exception_handlers() -> dict[ExceptionKey, ExceptionHandler]:
    """The exception-handler map both apps wire through ``create_app``.

    One handler for the whole ``WrenError`` hierarchy (Starlette dispatches by
    MRO) plus the ``RequestValidationError`` override, so every error path renders
    the one RFC 9457 contract.
    """
    handlers: dict[ExceptionKey, ExceptionHandler] = {
        WrenError: handle_wren_error,
        RequestValidationError: handle_request_validation_error,
    }
    return handlers
