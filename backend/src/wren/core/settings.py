"""Settings shared by the external and internal ASGI apps."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Local commands launch from backend/, so the env file must not depend on the
# process working directory. Deployed environment variables take precedence.
ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"

EXTERNAL_SERVICE = "wren-external"
INTERNAL_SERVICE = "wren-internal"
EXTERNAL_PORT = 8000
INTERNAL_PORT = 8001
MCP_INSPECTOR_ORIGIN = "http://localhost:6274"


class EnvSettings(BaseSettings):
    """Deployment-wide environment settings shared by both apps."""

    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    environment: str = "development"
    log_level: str = "info"
    sentry_dsn: str = Field(
        default="", validation_alias=AliasChoices("SENTRY_DSN_BACKEND", "sentry_dsn")
    )
    sentry_release: str = Field(
        default="", validation_alias=AliasChoices("SENTRY_RELEASE", "sentry_release")
    )
    host: str = "0.0.0.0"  # noqa: S104 - container ingress controls public access
    database_url: str = "postgresql+asyncpg://wren:wren@localhost:5432/wren"
    # Empty auth secrets fail closed. SecretStr prevents accidental settings dumps.
    internal_api_token: SecretStr = SecretStr("")
    session_jwt_secret: SecretStr = SecretStr("")
    # Empty keeps the session cookie host-only during local development.
    cookie_domain: str = ""
    # OAuth URLs remain pinned because the tunnel-facing host differs from the origin.
    oauth_issuer_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("PUBLIC_BASE_URL", "oauth_issuer_url"),
    )
    web_app_url: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("APP_PUBLIC_URL", "web_app_url"),
    )
    mcp_resource_url: str = Field(
        default="http://localhost:9000",
        validation_alias=AliasChoices("MCP_PUBLIC_URL", "mcp_resource_url"),
    )
    # Development generates an ephemeral key; other environments require a PEM.
    oauth_private_key_path: str = ""
    oauth_key_id: str = "wren-oauth-dev"
    oauth_access_ttl_seconds: int = 900
    oauth_refresh_ttl_seconds: int = 2_592_000
    # Cleanup uses registration age, not refresh activity. A nonpositive interval disables it.
    oauth_client_cleanup_interval_seconds: int = 21_600
    oauth_stale_client_max_age_seconds: int = 2_592_000
    # Empty falls back to the web app URL.
    cors_origin: str = ""
    # Empty disables signup notifications. SecretStr masks the bearer URL.
    discord_webhook_url: SecretStr = SecretStr("")
    # Application middleware owns proxy trust; uvicorn only trusts localhost.
    trusted_proxies_csv: str = Field(
        default="", validation_alias=AliasChoices("TRUSTED_PROXIES", "trusted_proxies_csv")
    )


class AppSettings(BaseModel):
    """Full settings for one ASGI app: shared env config plus per-app identity."""

    service: str
    port: int
    environment: str
    log_level: str
    sentry_dsn: str = ""
    sentry_release: str = ""
    host: str
    database_url: str
    internal_api_token: SecretStr
    session_jwt_secret: SecretStr
    cookie_domain: str
    oauth_issuer_url: str
    web_app_url: str
    mcp_resource_url: str
    oauth_private_key_path: str
    oauth_key_id: str
    oauth_access_ttl_seconds: int
    oauth_refresh_ttl_seconds: int
    oauth_client_cleanup_interval_seconds: int = 21_600
    oauth_stale_client_max_age_seconds: int = 2_592_000
    cors_origin: str
    discord_webhook_url: SecretStr
    trusted_proxies: list[str] = Field(default_factory=list)

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Browser origins allowed to send credentialed XHRs.

        Defaults to the web app URL. Development also permits the MCP Inspector.
        """
        origins = [self.cors_origin or self.web_app_url]
        if self.is_dev and MCP_INSPECTOR_ORIGIN not in origins:
            origins.append(MCP_INSPECTOR_ORIGIN)
        return origins


def build_app_settings(*, service: str, port: int, env: EnvSettings | None = None) -> AppSettings:
    """Compose per-app settings from injected identity and shared env config."""
    env = env or EnvSettings()
    return AppSettings(
        service=service,
        port=port,
        environment=env.environment,
        log_level=env.log_level,
        sentry_dsn=env.sentry_dsn,
        sentry_release=env.sentry_release,
        host=env.host,
        database_url=env.database_url,
        internal_api_token=env.internal_api_token,
        session_jwt_secret=env.session_jwt_secret,
        cookie_domain=env.cookie_domain,
        oauth_issuer_url=env.oauth_issuer_url,
        web_app_url=env.web_app_url,
        mcp_resource_url=env.mcp_resource_url,
        oauth_private_key_path=env.oauth_private_key_path,
        oauth_key_id=env.oauth_key_id,
        oauth_access_ttl_seconds=env.oauth_access_ttl_seconds,
        oauth_refresh_ttl_seconds=env.oauth_refresh_ttl_seconds,
        oauth_client_cleanup_interval_seconds=env.oauth_client_cleanup_interval_seconds,
        oauth_stale_client_max_age_seconds=env.oauth_stale_client_max_age_seconds,
        cors_origin=env.cors_origin,
        discord_webhook_url=env.discord_webhook_url,
        trusted_proxies=_parse_trusted_proxies(env.trusted_proxies_csv),
    )


def _parse_trusted_proxies(raw: str) -> list[str]:
    """Parse proxy IPs and CIDRs while rejecting blank entries."""
    return [item.strip() for item in raw.split(",") if item.strip()]
