"""The account service provider builds a request-scoped service."""

from __future__ import annotations

from tests.support.fakes.accounts_fakes import build_test_codec, build_test_hasher
from wren.accounts.service import AccountService
from wren.accounts.wiring import build_account_service_provider


def test_provider_builds_a_service_for_a_session() -> None:
    provider = build_account_service_provider(build_test_hasher(), build_test_codec())
    # The provider binds the repository to whatever session it is handed (FastAPI
    # supplies the request-scoped one at runtime); a placeholder proves the wiring.
    service = provider(session=object())  # type: ignore[arg-type]
    assert isinstance(service, AccountService)
