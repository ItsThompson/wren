"""MCP Resource Server settings.

Config is sourced from the environment once (:class:`EnvSettings`) and composed
into the immutable :class:`RsSettings` the app wires from. Like the backend AS,
every externally-visible URL (the token ``iss`` the RS validates against, the
``aud`` it binds to, the AS discovery base) is built from **pinned** config, never
a request host: the RS sits behind the same Cloudflare tunnel, so a
request-derived issuer/audience would break token validation (the "Site-URL
gotcha").
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from wren_mcp.config import MCP_INSPECTOR_ORIGIN

# `just dev-mcp` cd's into mcp/ before launching uvicorn, so a package-relative
# ".env" silently misses the canonical repo-root .env (F27). Anchor it to the
# repo root from this file's location so the host inner loop loads it regardless
# of CWD. Compose/CD inject real env vars, which always win over env_file, so
# this affects only the host-run inner loop.
ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

SERVICE = "wren-mcp"
DEFAULT_PORT = 9000


class EnvSettings(BaseSettings):
    """Deployment config for the MCP server, sourced from the environment.

    Field names mirror the shared ``.env`` keys. Unknown keys
    are ignored so the single sectioned root ``.env`` can carry vars for other
    consumers.
    """

    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    environment: str = "development"
    log_level: str = "info"
    host: str = "0.0.0.0"  # noqa: S104 - container binds all interfaces; ingress is tunnel-only
    port: int = DEFAULT_PORT
    # AS origin (api.usewren.com): the expected token ``iss`` and the base the RS
    # discovers AS metadata + JWKS from. Pinned, never request-derived.
    public_base_url: str = "http://localhost:8000"
    # This RS's own public URL (mcp.usewren.com): the expected token ``aud`` and
    # the PRM ``resource`` value. Agent tokens are audience-bound to it.
    mcp_public_url: str = "http://localhost:9000"
    # Backend internal app base (compute-net only, e.g. http://backend:8001). Tool
    # calls are forwarded here with the resolved X-User-ID.
    backend_internal_url: str = "http://localhost:8001"
    # Shared secret the internal app requires (defense-in-depth behind compute-net
    # isolation). Empty by default; the internal app fail-safe denies without it.
    # SecretStr so an accidental settings dump/log masks it (L12); read via
    # .get_secret_value() only when the internal-token header is constructed.
    internal_api_token: SecretStr = SecretStr("")
    # Comma-separated proxy IPs/CIDRs the app-level ProxyHeadersMiddleware trusts
    # for X-Forwarded-* (the pinned edge-net subnet). A DISTINCT name from
    # uvicorn's native FORWARDED_ALLOW_IPS on purpose: reusing that would move
    # proxy trust into uvicorn's server layer, whereas the app layer is the single
    # source of truth (uvicorn's layer stays a 127.0.0.1-only no-op since
    # cloudflared is not localhost). Empty in dev, so the middleware is not
    # mounted and request scheme is untouched.
    mcp_trusted_proxies: str = ""


class RsSettings(BaseModel):
    """Full settings for the MCP Resource Server."""

    service: str
    environment: str
    log_level: str
    host: str
    port: int
    issuer: str  # expected token ``iss`` + AS discovery base (pinned)
    resource: str  # expected token ``aud`` + PRM ``resource`` (pinned)
    backend_internal_url: str
    internal_api_token: SecretStr
    # Trusted proxy IPs/CIDRs for the app-level ProxyHeadersMiddleware; empty
    # disables it (dev). Populated from MCP_TRUSTED_PROXIES (see EnvSettings).
    trusted_proxies: list[str] = Field(default_factory=list)

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Browser origins allowed to call the RS directly.

        Only the local MCP Inspector, and only in development: its browser runs
        OAuth discovery and token-exchange fetches from its own origin, so it
        needs CORS. Empty in production, where agents are not browsers, so
        ``create_rs_app`` mounts no CORS middleware and the origin stays locked.
        """
        return [MCP_INSPECTOR_ORIGIN] if self.is_dev else []


def build_rs_settings(env: EnvSettings | None = None) -> RsSettings:
    """Compose the RS settings from pinned deployment config."""
    env = env or EnvSettings()
    return RsSettings(
        service=SERVICE,
        environment=env.environment,
        log_level=env.log_level,
        host=env.host,
        port=env.port,
        issuer=env.public_base_url,
        resource=env.mcp_public_url,
        backend_internal_url=env.backend_internal_url,
        internal_api_token=env.internal_api_token,
        trusted_proxies=_parse_trusted_proxies(env.mcp_trusted_proxies),
    )


def _parse_trusted_proxies(raw: str) -> list[str]:
    """Split the comma-separated MCP_TRUSTED_PROXIES env into trimmed entries,
    dropping blanks so a trailing comma cannot trust an empty literal."""
    return [item.strip() for item in raw.split(",") if item.strip()]
