"""Application factory.

``create_app`` assembles a configured :class:`~fastapi.FastAPI` app: structured
logging, the health router, request metrics, and mount points for the routers,
readiness checks, exception handlers, and lifespan that callers supply. Both
the external (:8000) and internal (:8001) apps are built from this one factory,
differing only by injected settings.

Wiring only. Do not import domain packages here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence

from fastapi import APIRouter, FastAPI
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Lifespan

from wren.core.health import ReadinessCheck, create_health_router
from wren.core.logging import configure_logging, get_logger
from wren.core.metrics import instrument
from wren.core.settings import AppSettings

# FastAPI keys handlers by exception type or status code.
ExceptionKey = type[Exception] | int
ExceptionHandler = Callable[[Request, Exception], Response | Awaitable[Response]]


def create_app(
    settings: AppSettings,
    *,
    routers: Sequence[APIRouter] = (),
    readiness_checks: Sequence[ReadinessCheck] = (),
    exception_handlers: Mapping[ExceptionKey, ExceptionHandler] | None = None,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Assemble a configured FastAPI app from injected settings and mount points."""
    configure_logging(environment=settings.environment, log_level=settings.log_level)
    log = get_logger(settings.service)

    app = FastAPI(title=f"wren ({settings.service})", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.log = log

    for key, handler in (exception_handlers or {}).items():
        app.add_exception_handler(key, handler)

    app.include_router(create_health_router(readiness_checks))
    for router in routers:
        app.include_router(router)

    instrument(app)

    log.info(
        "app_configured",
        environment=settings.environment,
        port=settings.port,
        routers=len(routers),
        readiness_checks=len(readiness_checks),
    )
    return app
