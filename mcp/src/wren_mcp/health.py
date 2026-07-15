"""Liveness and readiness endpoints for the MCP server.

- ``GET /healthz`` is liveness: the process is up. Always 200.
- ``GET /readyz`` is readiness: every registered dependency check passes. Returns
  503 if any fails. The deploy health gate polls ``/readyz``.

Readiness checks are injected, so this module stays dependency-free. The RS wires
a JWKS check (:func:`jwks_readiness_check`): the RS cannot validate any token
without the AS public keys, so unreachable JWKS is "not ready".
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from wren_mcp.keys import KeyProvider

HEALTHZ_ENDPOINT = "/healthz"
READYZ_ENDPOINT = "/readyz"
JWKS_CHECK_NAME = "as_jwks"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one readiness check."""

    name: str
    ok: bool
    detail: str | None = None


# A readiness check resolves to a CheckResult. A well-behaved check reports
# failure as ``CheckResult(ok=False)`` rather than raising, but the aggregator is
# defensive: a check that raises is degraded to a 503 (not a 500).
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


def jwks_readiness_check(key_provider: KeyProvider) -> ReadinessCheck:
    """Readiness check that confirms the AS public JWKS is reachable and parseable.

    Never raises: a discovery/fetch failure resolves to a failed CheckResult, so
    the RS reports "not ready" (503) rather than crashing when the AS is down.
    """

    async def check() -> CheckResult:
        try:
            await key_provider.load()
        except Exception as exc:  # noqa: BLE001 - any fetch/parse error is "not ready"
            return CheckResult(name=JWKS_CHECK_NAME, ok=False, detail=str(exc))
        return CheckResult(name=JWKS_CHECK_NAME, ok=True)

    return check
