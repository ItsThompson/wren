"""External app entrypoint (:8000).

Internet-reachable via the Cloudflare tunnel. Authenticates humans by session
cookie and hosts the public REST surface + OAuth AS (later tickets). Built from
the shared factory with the external service identity injected.
"""

from __future__ import annotations

from fastapi import FastAPI

from wren.core.app_factory import create_app
from wren.core.settings import EXTERNAL_PORT, EXTERNAL_SERVICE, build_app_settings

settings = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT)
app: FastAPI = create_app(settings)


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("wren.api.main:app", host=settings.host, port=settings.port)
