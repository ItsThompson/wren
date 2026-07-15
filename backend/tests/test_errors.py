"""Error contract: WrenError hierarchy + RequestValidationError -> one RFC 9457
problem+json shape, rendered by the single injected handler pair."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

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
