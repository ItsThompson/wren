"""Error contract: WrenError hierarchy + RequestValidationError -> one RFC 9457
problem+json shape, rendered by the single injected handler pair; plus the
catch-all 500 handler and its single structured fault log."""

from __future__ import annotations

from collections.abc import Callable

import pytest
import structlog
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from structlog.processors import format_exc_info

from wren.core.app_factory import ExceptionHandler, ExceptionKey, create_app
from wren.core.errors import (
    Conflict,
    ErrorCode,
    Forbidden,
    NotFound,
    Unauthorized,
    Validation,
    Violation,
    build_exception_handlers,
)
from wren.core.logging import _build_processors
from wren.core.settings import AppSettings
from wren.oauth.errors import build_oauth_exception_handlers

MakeSettings = Callable[..., AppSettings]
MakeHandlers = Callable[[], dict[ExceptionKey, ExceptionHandler]]

# The exception-handler maps the two real apps wire: the internal app mounts the
# shared handlers, the external app merges the OAuth handler on top. Both must
# render an unhandled fault as the generic 500 problem+json.
_HANDLER_MAPS = [
    pytest.param(build_exception_handlers, id="internal-app"),
    pytest.param(
        lambda: {**build_exception_handlers(), **build_oauth_exception_handlers()},
        id="external-app",
    ),
]


class _Item(BaseModel):
    title: str


def _client() -> TestClient:
    app = FastAPI()
    for key, handler in build_exception_handlers().items():
        app.add_exception_handler(key, handler)

    router = APIRouter()

    @router.get("/not-found")
    async def not_found() -> None:
        raise NotFound("no roadmap grokking-dsa-7f3k; siblings: intro-ml-9a2b")

    @router.get("/forbidden")
    async def forbidden() -> None:
        raise Forbidden("not your roadmap")

    @router.get("/unauthorized")
    async def unauthorized() -> None:
        raise Unauthorized("no session")

    @router.get("/conflict")
    async def conflict() -> None:
        raise Conflict(
            "Your edit targeted revision 16 but the current revision is 17.",
            code=ErrorCode.STALE_REVISION,
        )

    @router.get("/validation")
    async def validation() -> None:
        raise Validation(
            "3 structural rules failed.",
            violations=[
                Violation(rule="V1_ACYCLIC", ids=["sub_x", "sub_y"], message="cycle"),
            ],
        )

    @router.get("/validation-fields")
    async def validation_fields() -> None:
        raise Validation("registration failed", fields={"email": "already registered"})

    @router.post("/items")
    async def create_item(item: _Item) -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router)
    return TestClient(app)


_LEAKY_DETAIL = "secret internal detail: db dsn postgres://admin:hunter2@host"


def _boom_router() -> APIRouter:
    """A router whose handler raises a non-WrenError with a sensitive message."""
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError(_LEAKY_DETAIL)

    return router


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/not-found", 404, "NOT_FOUND"),
        ("/forbidden", 403, "FORBIDDEN"),
        ("/unauthorized", 401, "UNAUTHORIZED"),
        ("/conflict", 409, "STALE_REVISION"),
        ("/validation", 422, "VALIDATION"),
    ],
)
def test_each_error_maps_to_its_status_and_code(path: str, status: int, code: str) -> None:
    response = _client().get(path)

    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == status
    assert body["code"] == code
    # type/title/detail/instance are always present.
    assert body["type"].endswith(f"/{code.lower().replace('_', '-')}")
    assert body["title"]
    assert body["detail"]
    assert body["instance"] == path


def test_conflict_code_override_drives_the_type_uri() -> None:
    body = _client().get("/conflict").json()
    assert body["code"] == "STALE_REVISION"
    assert body["type"] == "https://usewren.com/errors/stale-revision"
    # A plain Conflict has no violations/fields extension members on the wire.
    assert "violations" not in body
    assert "fields" not in body


def test_validation_carries_violations_array() -> None:
    body = _client().get("/validation").json()
    assert body["violations"] == [
        {"rule": "V1_ACYCLIC", "ids": ["sub_x", "sub_y"], "message": "cycle"},
    ]
    assert "fields" not in body


def test_validation_can_carry_a_field_map_without_violations() -> None:
    body = _client().get("/validation-fields").json()
    assert body["fields"] == {"email": "already registered"}
    assert "violations" not in body


def test_request_validation_error_uses_the_same_field_map_shape() -> None:
    response = _client().post("/items", json={})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "VALIDATION"
    assert body["type"] == "https://usewren.com/errors/validation"
    # The missing body field is surfaced under a dotted path in the field map.
    assert "body.title" in body["fields"]
    # RequestValidationError maps to fields, not the structural violations array.
    assert "violations" not in body


# --- catch-all 500 handler (F2) ---------------------------------------------


@pytest.mark.parametrize("make_handlers", _HANDLER_MAPS)
def test_unhandled_exception_renders_generic_500_problem_json(
    make_settings: MakeSettings, make_handlers: MakeHandlers
) -> None:
    app = create_app(
        make_settings(),
        routers=[_boom_router()],
        exception_handlers=make_handlers(),
    )
    # raise_server_exceptions=False so the client returns the handler's 500 rather
    # than re-raising the RuntimeError into the test.
    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body == {
        "type": "https://usewren.com/errors/internal",
        "title": "Internal server error",
        "status": 500,
        "code": "INTERNAL",
        "detail": "An unexpected error occurred.",
        "instance": "/boom",
    }


@pytest.mark.parametrize("make_handlers", _HANDLER_MAPS)
def test_unhandled_exception_leaks_no_internal_detail(
    make_settings: MakeSettings, make_handlers: MakeHandlers
) -> None:
    app = create_app(
        make_settings(),
        routers=[_boom_router()],
        exception_handlers=make_handlers(),
    )
    raw = TestClient(app, raise_server_exceptions=False).get("/boom").text

    # Neither the original exception message nor a rendered stack trace reaches
    # the client.
    assert "hunter2" not in raw
    assert _LEAKY_DETAIL not in raw
    assert "RuntimeError" not in raw
    assert "Traceback" not in raw


# --- single structured fault log (F3) ---------------------------------------


def _bare_boom_client() -> TestClient:
    app = FastAPI()
    for key, handler in build_exception_handlers().items():
        app.add_exception_handler(key, handler)
    app.include_router(_boom_router())
    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_emits_exactly_one_error_log_with_exc_info_and_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Capture at the logging boundary: the configured logger caches its processor
    # chain on first use, so a double is more reliable here than capture_logs.
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("wren.core.errors._log", cap)

    _bare_boom_client().get("/boom")

    error_calls = [call for call in cap.calls if call.method_name == "error"]
    assert len(error_calls) == 1
    assert error_calls[0].args == ("unhandled_exception",)
    assert error_calls[0].kwargs["path"] == "/boom"
    # exc_info carries the actual exception so the log chain can render its stack.
    assert isinstance(error_calls[0].kwargs["exc_info"], RuntimeError)


def test_routine_4xx_does_not_hit_the_fault_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("wren.core.errors._log", cap)

    _client().get("/not-found")

    # A routine 4xx renders via handle_wren_error and never reaches the fault log.
    assert cap.calls == []


def test_format_exc_info_is_wired_and_renders_the_fault_traceback() -> None:
    # format_exc_info was dead until the catch-all handler started feeding exc_info;
    # assert it is in the chain and turns an exc_info field into a rendered stack.
    assert format_exc_info in _build_processors(is_dev=False)

    try:
        raise RuntimeError("boom detail")
    except RuntimeError as exc:
        rendered = format_exc_info(None, "error", {"event": "unhandled_exception", "exc_info": exc})

    assert isinstance(rendered, dict)
    exception_text = rendered["exception"]
    assert isinstance(exception_text, str)
    assert "RuntimeError: boom detail" in exception_text
    assert "Traceback" in exception_text
