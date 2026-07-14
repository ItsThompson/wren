"""Liveness and readiness endpoints.

- ``GET /healthz`` is liveness: the process is up. Always 200.
- ``GET /readyz`` is readiness: every registered dependency check passes. Returns
  503 if any fails.

Readiness checks are injected, so this module stays dependency-free. Ticket 1
mounts zero checks (``/readyz`` is a 200 placeholder); Ticket 2 injects a DB
connectivity check through the same seam (see ``core.db.db_readiness_check``).
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


# Contract: a readiness check resolves to a CheckResult. A well-behaved check
# reports failure as ``CheckResult(ok=False)`` rather than raising, but the
# aggregator below is defensive: a check that raises is still degraded to a 503
# (not a 500), so one misbehaving dependency probe cannot mask readiness.
ReadinessCheck = Callable[[], Awaitable[CheckResult]]


def create_health_router(readiness_checks: Sequence[ReadinessCheck] = ()) -> APIRouter:
    """Build the health router. Checks run concurrently; any failure -> 503."""
    router = APIRouter(tags=["health"])

    @router.get(HEALTHZ_ENDPOINT, include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get(READYZ_ENDPOINT, include_in_schema=False)
    async def readyz() -> JSONResponse:
        results = await asyncio.gather(
            *(check() for check in readiness_checks),
            return_exceptions=True,
        )
        checks: dict[str, dict[str, object]] = {}
        ready = True
        for index, result in enumerate(results):
            if isinstance(result, BaseException):
                ready = False
                checks[f"check_{index}"] = {"ok": False, "detail": str(result)}
                continue
            ready = ready and result.ok
            checks[result.name] = {"ok": result.ok, "detail": result.detail}
        payload = {"status": "ready" if ready else "not_ready", "checks": checks}
        return JSONResponse(payload, status_code=200 if ready else 503)

    return router
