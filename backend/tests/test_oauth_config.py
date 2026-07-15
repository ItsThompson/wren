"""OAuthConfig: every URL is built from pinned config, and resource canonicalization.

Guards the Site-URL gotcha at the unit level: endpoint/issuer URLs come only from
the configured issuer, and the RFC 8707 ``resource`` is pinned to the one MCP
resource the AS serves.
"""

from __future__ import annotations

from oauth_fakes import build_test_config
from wren.core.settings import AppSettings
from wren.oauth.config import (
    AUTHORIZE_PATH,
    JWKS_PATH,
    TOKEN_PATH,
    build_oauth_config,
)


def test_endpoint_urls_are_built_from_the_pinned_issuer() -> None:
    config = build_test_config()
    assert config.endpoint(TOKEN_PATH) == "https://api.usewren.com/token"
    assert config.endpoint(JWKS_PATH) == "https://api.usewren.com/jwks"
    assert config.endpoint(AUTHORIZE_PATH) == "https://api.usewren.com/authorize"


def test_consent_url_is_built_from_the_app_public_url() -> None:
    config = build_test_config()
    assert config.consent_url == "https://usewren.com/authorize"


def test_endpoint_url_does_not_double_slash_when_issuer_has_trailing_slash() -> None:
    config = build_test_config()
    trailing = config.__class__(**{**config.__dict__, "issuer": "https://api.usewren.com/"})
    assert trailing.endpoint(TOKEN_PATH) == "https://api.usewren.com/token"


def test_canonical_resource_defaults_missing_to_the_mcp_resource() -> None:
    config = build_test_config()
    assert config.canonical_resource(None) == "https://mcp.usewren.com"
    assert config.canonical_resource("") == "https://mcp.usewren.com"


def test_canonical_resource_accepts_the_matching_resource() -> None:
    config = build_test_config()
    assert config.canonical_resource("https://mcp.usewren.com") == "https://mcp.usewren.com"
    # A trailing slash is tolerated (canonicalized).
    assert config.canonical_resource("https://mcp.usewren.com/") == "https://mcp.usewren.com"


def test_canonical_resource_rejects_a_foreign_resource() -> None:
    config = build_test_config()
    assert config.canonical_resource("https://evil.example.com") is None


def test_build_oauth_config_reads_only_pinned_settings() -> None:
    settings = AppSettings(
        service="wren-test",
        port=8000,
        environment="production",
        log_level="info",
        host="127.0.0.1",
        database_url="postgresql+asyncpg://wren:wren@localhost:5432/wren",
        internal_api_token="t",
        session_jwt_secret="s",
        cookie_domain="",
        public_base_url="https://api.usewren.com",
        app_public_url="https://usewren.com",
        mcp_public_url="https://mcp.usewren.com",
        oauth_private_key_path="",
        oauth_key_id="kid-1",
        oauth_access_ttl_seconds=900,
        oauth_refresh_ttl_seconds=1000,
        cors_origin="https://usewren.com",
    )
    config = build_oauth_config(settings)
    assert config.issuer == "https://api.usewren.com"
    assert config.resource == "https://mcp.usewren.com"
    assert config.key_id == "kid-1"
    assert int(config.access_ttl.total_seconds()) == 900
