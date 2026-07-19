"""Typed accessors for the auth-boundary ``app.state`` seams.

Each accessor centralizes the ``getattr`` plus a runtime type check for one seam
and returns the fail-safe default on a missing OR wrong-type attribute, so the
identity boundary stays fail-closed. Exercised against a real Starlette app's
``state`` (the datastructure :mod:`wren.core.identity` reads through)."""

from __future__ import annotations

from pydantic import SecretStr
from starlette.applications import Starlette

from wren.core.state import deny_all_sessions, get_internal_token, get_session_verifier


def _app() -> Starlette:
    return Starlette()


async def test_deny_all_sessions_returns_none() -> None:
    assert await deny_all_sessions("anything") is None


# --- get_session_verifier ---------------------------------------------------


def test_get_session_verifier_defaults_to_deny_all_when_unset() -> None:
    assert get_session_verifier(_app()) is deny_all_sessions


def test_get_session_verifier_returns_the_injected_verifier() -> None:
    async def verify(_cookie: str) -> str | None:
        return "user-1"

    app = _app()
    app.state.session_verifier = verify
    assert get_session_verifier(app) is verify


def test_get_session_verifier_falls_back_when_the_seam_is_not_callable() -> None:
    # A wrong-type wiring (e.g. a leftover string) must not be treated as a
    # verifier: the accessor returns the deny-all default instead of raising.
    app = _app()
    app.state.session_verifier = "not-callable"
    assert get_session_verifier(app) is deny_all_sessions


# --- get_internal_token -----------------------------------------------------


def test_get_internal_token_defaults_to_empty_when_unset() -> None:
    assert get_internal_token(_app()).get_secret_value() == ""


def test_get_internal_token_returns_the_configured_token() -> None:
    app = _app()
    app.state.internal_api_token = SecretStr("s3cret-internal-token")
    assert get_internal_token(app).get_secret_value() == "s3cret-internal-token"


def test_get_internal_token_falls_back_when_the_seam_is_not_a_secret_str() -> None:
    # A non-SecretStr wiring must fail closed (empty token denies every internal
    # call), not crash the .get_secret_value() unwrap or secrets.compare_digest
    # downstream. A bare str is rejected too: the seam is SecretStr end to end.
    app = _app()
    app.state.internal_api_token = 1234
    assert get_internal_token(app).get_secret_value() == ""
    app.state.internal_api_token = "plain-str-not-a-secret"
    assert get_internal_token(app).get_secret_value() == ""
