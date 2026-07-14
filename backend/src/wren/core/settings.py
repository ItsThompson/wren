"""Application settings.

Deployment-wide configuration is sourced from the environment once (``EnvSettings``)
and is identical for both apps. Per-app identity (``service`` name and ``port``) is
injected at construction time so the external and internal apps differ *only* by
their injected settings, per the two-app split (spec section 08).
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# Per-app identity. Service names are bound onto every structlog line so external
# and internal traffic is distinguishable in aggregated logs.
EXTERNAL_SERVICE = "wren-external"
INTERNAL_SERVICE = "wren-internal"
EXTERNAL_PORT = 8000
INTERNAL_PORT = 8001


class EnvSettings(BaseSettings):
    """Deployment-wide config shared by both apps, sourced from the environment.

    Field names mirror the shared ``.env`` keys (spec section 11): ``ENVIRONMENT``,
    ``LOG_LEVEL``. Unknown keys are ignored so the single sectioned root ``.env``
    can carry vars for other consumers.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"
    host: str = "0.0.0.0"  # noqa: S104 - container binds all interfaces; ingress is tunnel-only


class AppSettings(BaseModel):
    """Full settings for one ASGI app: shared env config plus per-app identity."""

    service: str
    port: int
    environment: str
    log_level: str
    host: str

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() == "development"


def build_app_settings(*, service: str, port: int, env: EnvSettings | None = None) -> AppSettings:
    """Compose per-app settings from injected identity and shared env config."""
    env = env or EnvSettings()
    return AppSettings(
        service=service,
        port=port,
        environment=env.environment,
        log_level=env.log_level,
        host=env.host,
    )
