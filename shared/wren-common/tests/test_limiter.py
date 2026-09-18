from __future__ import annotations

import pytest

from wren_common.limiter import EventLimiter


def test_event_limiter_allows_limit_then_blocks_until_window_expires() -> None:
    now = 0.0
    limiter = EventLimiter(limit=2, window_seconds=10, clock=lambda: now)

    assert limiter.allow("database") is True
    assert limiter.allow("database") is True
    assert limiter.allow("database") is False

    now = 10.1
    assert limiter.allow("database") is True


def test_event_limiter_tracks_keys_independently() -> None:
    limiter = EventLimiter(limit=1, window_seconds=10, clock=lambda: 0.0)

    assert limiter.allow("database") is True
    assert limiter.allow("database") is False
    assert limiter.allow("oauth") is True


def test_event_limiter_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="limit"):
        EventLimiter(limit=0, window_seconds=1)
    with pytest.raises(ValueError, match="window_seconds"):
        EventLimiter(limit=1, window_seconds=0)
