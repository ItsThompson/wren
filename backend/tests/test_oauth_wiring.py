"""The OAuth service providers build request-scoped services."""

from __future__ import annotations

from tests.oauth_fakes import build_test_codec, build_test_config, build_test_keyset
from wren.oauth.authorization import AuthorizationService
from wren.oauth.token_exchange import TokenService
from wren.oauth.wiring import (
    build_authorization_service_provider,
    build_token_service_provider,
)


def test_authorization_provider_builds_a_service_for_a_session() -> None:
    config = build_test_config()
    provider = build_authorization_service_provider(config)
    # The provider binds the repository to whatever session it is handed (FastAPI
    # supplies the request-scoped one at runtime); a placeholder proves the wiring.
    service = provider(object())  # type: ignore[arg-type]
    assert isinstance(service, AuthorizationService)


def test_token_provider_builds_a_service_for_a_session() -> None:
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))
    provider = build_token_service_provider(config, codec)
    service = provider(object())  # type: ignore[arg-type]
    assert isinstance(service, TokenService)
