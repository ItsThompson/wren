"""Settings tests: pinned-config mapping from the environment."""

from __future__ import annotations

from wren_mcp.settings import SERVICE, EnvSettings, build_rs_settings


def test_build_rs_settings_maps_pinned_config() -> None:
    env = EnvSettings(
        environment="production",
        public_base_url="https://api.usewren.com",
        mcp_public_url="https://mcp.usewren.com",
        backend_internal_url="http://backend:8001",
        internal_api_token="tok",
    )

    settings = build_rs_settings(env)

    assert settings.service == SERVICE
    # issuer/resource are derived from the pinned public URLs (Site-URL gotcha).
    assert settings.issuer == "https://api.usewren.com"
    assert settings.resource == "https://mcp.usewren.com"
    assert settings.backend_internal_url == "http://backend:8001"
    assert settings.internal_api_token == "tok"
    assert settings.is_dev is False


def test_is_dev_true_in_development() -> None:
    assert build_rs_settings(EnvSettings(environment="development")).is_dev is True
