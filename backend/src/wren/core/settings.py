"""Application settings.

Deployment-wide configuration is sourced from the environment once (``EnvSettings``)
and is identical for both apps. Per-app identity (``service`` name and ``port``) is
injected at construction time so the external and internal apps differ *only* by
their injected settings, per the two-app split.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# `just dev-api`/`dev-api-internal` cd into backend/ before launching uvicorn, so
# a package-relative ".env" silently misses the canonical repo-root .env (F27).
# Anchor it to the repo root from this file's location so the host inner loop
# loads it regardless of CWD. Compose/CD inject real env vars, which always win
# over env_file, so this affects only the host-run inner loop.
ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"

# Per-app identity. Service names are bound onto every structlog line so external
# and internal traffic is distinguishable in aggregated logs.
EXTERNAL_SERVICE = "wren-external"
INTERNAL_SERVICE = "wren-internal"
EXTERNAL_PORT = 8000
INTERNAL_PORT = 8001
MCP_INSPECTOR_ORIGIN = "http://localhost:6274"


class EnvSettings(BaseSettings):
    """Deployment-wide config shared by both apps, sourced from the environment.

    Field names mirror the shared ``.env`` keys: ``ENVIRONMENT``,
    ``LOG_LEVEL``. Unknown keys are ignored so the single sectioned root ``.env``
    can carry vars for other consumers.
    """

    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    environment: str = "development"
    log_level: str = "info"
    host: str = "0.0.0.0"  # noqa: S104 - container binds all interfaces; ingress is tunnel-only
    # Async SQLAlchemy URL (asyncpg driver). Dev default targets the Postgres in
    # docker-compose.dev.yml published to localhost; prod injects the in-network
    # `@postgres:5432` form via the VPS.env.
    database_url: str = "postgresql+asyncpg://wren:wren@localhost:5432/wren"
    # Shared secret the MCP server sends to reach the internal app; the primary
    # boundary on :8001 (non-tunnel-routed, non-host-published). Empty by default
    # so an unconfigured internal app fail-safe denies (`require_internal_user`).
    # SecretStr so an accidental settings dump/log masks it (L12); read via
    # .get_secret_value() only at the constant-time compare in identity.py.
    internal_api_token: SecretStr = SecretStr("")
    # HS256 secret for human session JWTs, separate from the
    # agent OAuth keypair. Empty by default so an unconfigured external app
    # fail-safe denies every session (no cookie resolves). SecretStr for the same
    # leak-in-depth reason; read via .get_secret_value() only at JWT sign/verify.
    session_jwt_secret: SecretStr = SecretStr("")
    # Cookie Domain for the session cookie. Prod pins `.usewren.com` so the SPA
    # (usewren.com) and API (api.usewren.com) share it; empty in dev makes the
    # cookie host-only (localhost).
    cookie_domain: str = ""
    # Pinned public URLs (the "Site-URL gotcha"): cloudflared
    # reaches the origin over http://backend:8000, so ALL OAuth issuer/metadata/
    # endpoint URLs are built from these pinned values, never from the request
    # host. `public_base_url` is the AS origin (api.usewren.com); `app_public_url`
    # is the SPA that renders consent (usewren.com); `mcp_public_url` is the MCP
    # resource that agent access tokens are audience-bound to (mcp.usewren.com).
    public_base_url: str = "http://localhost:8000"
    app_public_url: str = "http://localhost:5173"
    mcp_public_url: str = "http://localhost:9000"
    # Agent OAuth 2.1 AS signing key: the AS holds a private PEM
    # and publishes the public key via JWKS; `oauth_key_id` is the active `kid`
    # (kid rotation publishes a new key, signs with it, retires the old). Empty
    # path lets development generate an ephemeral in-memory keypair so the app
    # boots without a mounted PEM; outside development a missing key fails fast.
    oauth_private_key_path: str = ""
    oauth_key_id: str = "wren-oauth-dev"
    # Agent token lifetimes: short-lived access token + long rotating refresh.
    oauth_access_ttl_seconds: int = 900
    oauth_refresh_ttl_seconds: int = 2_592_000
    # Allowed browser origin for the SPA's credentialed consent/login XHRs
    # (CORS). Empty falls back to `app_public_url`; prod pins
    # https://usewren.com so the cross-subdomain cookie flow works.
    cors_origin: str = ""
    # Discord Incoming Webhook the external app posts to on a successful signup
    # (best-effort, fire-and-forget). Empty by default so the notification path
    # is a no-op when unconfigured; the app boots and registers users normally.
    # SecretStr so any settings dump/log masks it (the webhook is a bearer URL);
    # read via .get_secret_value() only inside the notifier's delivery task.
    discord_webhook_url: SecretStr = SecretStr("")
    # Comma-separated proxy IPs/CIDRs the external app's ProxyHeadersMiddleware
    # trusts for X-Forwarded-* (the pinned app-net subnet). A DISTINCT name from
    # uvicorn's native FORWARDED_ALLOW_IPS on purpose: reusing that would move
    # proxy trust into uvicorn's server layer, whereas the app layer is the single
    # source of truth (uvicorn's layer stays a 127.0.0.1-only no-op since
    # cloudflared is not localhost). Read by both apps' env, but only the external
    # entrypoint mounts the middleware; empty disables it (dev).
    trusted_proxies: str = ""


class AppSettings(BaseModel):
    """Full settings for one ASGI app: shared env config plus per-app identity."""

    service: str
    port: int
    environment: str
    log_level: str
    host: str
    database_url: str
    internal_api_token: SecretStr
    session_jwt_secret: SecretStr
    cookie_domain: str
    public_base_url: str
    app_public_url: str
    mcp_public_url: str
    oauth_private_key_path: str
    oauth_key_id: str
    oauth_access_ttl_seconds: int
    oauth_refresh_ttl_seconds: int
    cors_origin: str
    discord_webhook_url: SecretStr
    # Trusted proxy IPs/CIDRs for the external app's ProxyHeadersMiddleware; empty
    # disables it (dev). Populated from TRUSTED_PROXIES (see EnvSettings). The
    # internal app carries the same value but never mounts the middleware.
    trusted_proxies: list[str] = Field(default_factory=list)

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Browser origins allowed to send credentialed XHRs.

        Defaults to the SPA's own public URL when ``CORS_ORIGIN`` is unset, so
        development (Vite on localhost) works without extra config. Development
        also allows the MCP Inspector callback page to complete the OAuth flow.
        """
        origins = [self.cors_origin or self.app_public_url]
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
        host=env.host,
        database_url=env.database_url,
        internal_api_token=env.internal_api_token,
        session_jwt_secret=env.session_jwt_secret,
        cookie_domain=env.cookie_domain,
        public_base_url=env.public_base_url,
        app_public_url=env.app_public_url,
        mcp_public_url=env.mcp_public_url,
        oauth_private_key_path=env.oauth_private_key_path,
        oauth_key_id=env.oauth_key_id,
        oauth_access_ttl_seconds=env.oauth_access_ttl_seconds,
        oauth_refresh_ttl_seconds=env.oauth_refresh_ttl_seconds,
        cors_origin=env.cors_origin,
        discord_webhook_url=env.discord_webhook_url,
        trusted_proxies=_parse_trusted_proxies(env.trusted_proxies),
    )


def _parse_trusted_proxies(raw: str) -> list[str]:
    """Split the comma-separated TRUSTED_PROXIES env into trimmed entries, dropping
    blanks so a trailing comma cannot trust an empty literal."""
    return [item.strip() for item in raw.split(",") if item.strip()]
