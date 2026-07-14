"""Liveness and readiness endpoints.

- ``GET /healthz`` is liveness: the process is up. Always 200.
- ``GET /readyz`` is readiness: every registered dependency check passes. Returns
  503 if any fails.

Readiness checks are injected, so this module stays dependency-free. Ticket 1
mounts zero checks (``/readyz`` is a 200 placeholder); Ticket 2 injects a DB
connectivity check without touching this module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from fastapi import APIRouter
from fastapi.responses import JSONResponse

HEALTHZ_ENDPOINT = "/healthz"
READYZ_ENDPOINT = "/readyz"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one readiness check."""

    name: str
    ok: bool
    detail: str | None = None


ReadinessCheck = Callable[[], Awaitable[CheckResult]]


def create_health_router(readiness_checks: Sequence[ReadinessCheck] = ()) -> APIRouter:
    """Build the health router. Checks run concurrently; any failure -> 503."""
    router = APIRouter(tags=["health"])

    @router.get(HEALTHZ_ENDPOINT, include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get(READYZ_ENDPOINT, include_in_schema=False)
    async def readyz() -> JSONResponse:
        results = await asyncio.gather(*(check() for check in readiness_checks))
        ready = all(result.ok for result in results)
        payload = {
            "status": "ready" if ready else "not_ready",
            "checks": {
                result.name: {"ok": result.ok, "detail": result.detail} for result in results
            },
        }
        return JSONResponse(payload, status_code=200 if ready else 503)

    return router
