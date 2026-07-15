"""Session-secret startup validation: lenient in dev, fail-fast elsewhere."""

from __future__ import annotations

import pytest

from wren.accounts.config import SessionConfig, validate_session_secret

_STRONG = "x" * 32
_WEAK = "x" * 31


def test_dev_tolerates_an_empty_secret() -> None:
    # Dev boots with sessions unconfigured (they fail-safe deny); no raise.
    validate_session_secret(SessionConfig(secret=""), is_dev=True)


def test_dev_tolerates_a_short_secret() -> None:
    validate_session_secret(SessionConfig(secret=_WEAK), is_dev=True)


def test_non_dev_accepts_a_32_byte_secret() -> None:
    validate_session_secret(SessionConfig(secret=_STRONG), is_dev=False)


@pytest.mark.parametrize("secret", ["", _WEAK])
def test_non_dev_rejects_a_missing_or_weak_secret(secret: str) -> None:
    with pytest.raises(RuntimeError, match="SESSION_JWT_SECRET"):
        validate_session_secret(SessionConfig(secret=secret), is_dev=False)
