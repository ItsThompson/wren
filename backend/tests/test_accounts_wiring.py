"""The account service provider builds a request-scoped service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.support.fakes.accounts_fakes import build_test_codec, build_test_hasher
from wren.accounts.notifications import BestEffortEventPublisher, NullEventPublisher
from wren.accounts.service import AccountService
from wren.accounts.wiring import build_account_service_provider, build_event_publisher

if TYPE_CHECKING:
    from tests.conftest import MakeSettings


def test_provider_builds_a_service_for_a_session() -> None:
    provider = build_account_service_provider(build_test_hasher(), build_test_codec())
    # The provider binds the repository to whatever session it is handed (FastAPI
    # supplies the request-scoped one at runtime); a placeholder proves the wiring.
    service = provider(object())  # type: ignore[arg-type]
    assert isinstance(service, AccountService)


def test_event_publisher_is_null_without_a_webhook(make_settings: MakeSettings) -> None:
    # unconfigured webhook -> the notification path is a no-op and the app boots.
    publisher = build_event_publisher(make_settings(discord_webhook_url=""))
    assert isinstance(publisher, NullEventPublisher)


def test_event_publisher_is_best_effort_with_a_webhook(make_settings: MakeSettings) -> None:
    settings = make_settings(discord_webhook_url="https://discord.test/webhooks/123/secret")
    publisher = build_event_publisher(settings)
    assert isinstance(publisher, BestEffortEventPublisher)
