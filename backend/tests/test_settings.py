"""Settings: per-app identity injected over shared env config."""

from __future__ import annotations

from wren.core.settings import (
    EXTERNAL_PORT,
    EXTERNAL_SERVICE,
    INTERNAL_PORT,
    INTERNAL_SERVICE,
    EnvSettings,
    build_app_settings,
)


def test_build_app_settings_injects_identity_over_shared_env() -> None:
    env = EnvSettings(environment="production", log_level="warning", host="0.0.0.0")
    settings = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT, env=env)

    assert settings.service == "wren-external"
    assert settings.port == 8000
    assert settings.environment == "production"
    assert settings.log_level == "warning"
    assert settings.is_dev is False


def test_internal_and_external_differ_only_by_identity() -> None:
    env = EnvSettings(environment="production", log_level="info")
    external = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT, env=env)
    internal = build_app_settings(service=INTERNAL_SERVICE, port=INTERNAL_PORT, env=env)

    assert (external.service, external.port) == ("wren-external", 8000)
    assert (internal.service, internal.port) == ("wren-internal", 8001)
    assert external.environment == internal.environment
    assert external.log_level == internal.log_level
    assert external.host == internal.host


def test_is_dev_true_for_development() -> None:
    settings = build_app_settings(service="x", port=1, env=EnvSettings(environment="development"))
    assert settings.is_dev is True
