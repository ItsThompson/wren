"""Settings: per-app identity injected over shared env config."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from wren.core.settings import (
    EXTERNAL_PORT,
    EXTERNAL_SERVICE,
    INTERNAL_PORT,
    INTERNAL_SERVICE,
    ROOT_ENV_FILE,
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


def test_bearer_secrets_are_masked_in_repr_but_recoverable() -> None:
    """L12: an accidental settings dump/log must not leak the two bearer secrets.
    They are ``SecretStr``, so ``repr()``/``str()`` mask them, while
    ``.get_secret_value()`` still yields the real value at the auth use sites."""
    env = EnvSettings(
        internal_api_token=SecretStr("raw-internal-token-value"),
        session_jwt_secret=SecretStr("raw-session-secret-value"),
    )
    settings = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT, env=env)

    for dump in (repr(env), str(env), repr(settings), str(settings)):
        assert "raw-internal-token-value" not in dump
        assert "raw-session-secret-value" not in dump
        assert "**********" in dump

    # The real values are preserved for the auth code paths that unwrap them.
    assert settings.internal_api_token.get_secret_value() == "raw-internal-token-value"
    assert settings.session_jwt_secret.get_secret_value() == "raw-session-secret-value"


def test_env_file_anchors_to_repo_root() -> None:
    """`just dev-api`/`dev-api-internal` cd into backend/ before launching
    uvicorn, so env_file must resolve to the canonical repo-root .env, not a
    backend-relative path that silently misses it (F27). Compose/CD inject real
    env vars, which win over env_file regardless."""
    env_file = EnvSettings.model_config["env_file"]

    assert env_file == ROOT_ENV_FILE
    assert isinstance(env_file, Path)
    assert env_file.is_absolute()
    assert env_file.name == ".env"
    # The parent is the repo root `just` runs from: it holds the justfile and the
    # backend/ package dir, so it is the root, not the backend/ package itself.
    assert (env_file.parent / "justfile").exists()
    assert (env_file.parent / "backend").is_dir()
