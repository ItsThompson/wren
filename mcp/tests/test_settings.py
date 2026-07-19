"""Settings tests: pinned-config mapping from the environment."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from wren_mcp.settings import ROOT_ENV_FILE, SERVICE, EnvSettings, build_rs_settings


def test_build_rs_settings_maps_pinned_config() -> None:
    env = EnvSettings(
        environment="production",
        public_base_url="https://api.usewren.com",
        mcp_public_url="https://mcp.usewren.com",
        backend_internal_url="http://backend:8001",
        internal_api_token=SecretStr("tok"),
    )

    settings = build_rs_settings(env)

    assert settings.service == SERVICE
    # issuer/resource are derived from the pinned public URLs (Site-URL gotcha).
    assert settings.issuer == "https://api.usewren.com"
    assert settings.resource == "https://mcp.usewren.com"
    assert settings.backend_internal_url == "http://backend:8001"
    assert settings.internal_api_token.get_secret_value() == "tok"
    assert settings.is_dev is False


def test_internal_api_token_is_masked_in_repr_but_recoverable() -> None:
    """L12: an accidental settings dump/log must not leak the shared internal
    token. It is ``SecretStr``, so ``repr()``/``str()`` mask it, while
    ``.get_secret_value()`` still yields the real value where the internal-token
    header is constructed."""
    env = EnvSettings(internal_api_token=SecretStr("raw-internal-token-value"))
    settings = build_rs_settings(env)

    for dump in (repr(env), str(env), repr(settings), str(settings)):
        assert "raw-internal-token-value" not in dump
        assert "**********" in dump

    assert settings.internal_api_token.get_secret_value() == "raw-internal-token-value"


def test_is_dev_true_in_development() -> None:
    assert build_rs_settings(EnvSettings(environment="development")).is_dev is True


def test_trusted_proxies_parses_the_comma_separated_env() -> None:
    # MCP_TRUSTED_PROXIES is a comma-separated CIDR/IP list; blanks (e.g. a
    # trailing comma) are dropped so an empty literal can never be trusted.
    env = EnvSettings(mcp_trusted_proxies="172.20.0.0/24, 10.0.0.1 ,")
    assert build_rs_settings(env).trusted_proxies == ["172.20.0.0/24", "10.0.0.1"]


def test_trusted_proxies_defaults_empty() -> None:
    # Empty in dev, so create_rs_app mounts no ProxyHeadersMiddleware.
    assert build_rs_settings(EnvSettings()).trusted_proxies == []


def test_env_file_anchors_to_repo_root() -> None:
    """`just dev-mcp` cd's into mcp/ before launching uvicorn, so env_file must
    resolve to the canonical repo-root .env, not an mcp-relative path that
    silently misses it (F27). Compose/CD inject real env vars, which win over
    env_file regardless."""
    env_file = EnvSettings.model_config["env_file"]

    assert env_file == ROOT_ENV_FILE
    assert isinstance(env_file, Path)
    assert env_file.is_absolute()
    assert env_file.name == ".env"
    # The parent is the repo root `just` runs from: it holds the justfile and the
    # mcp/ package dir, so it is the root, not the mcp/ package itself.
    assert (env_file.parent / "justfile").exists()
    assert (env_file.parent / "mcp").is_dir()
