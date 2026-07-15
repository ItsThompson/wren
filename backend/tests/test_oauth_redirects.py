"""Redirect-URI policy (RFC 8252): exact match plus loopback any-port."""

from __future__ import annotations

import pytest

from wren.oauth.redirects import is_allowed_redirect, is_loopback


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("http://127.0.0.1:52001/callback", True),
        ("http://localhost:8080/cb", True),
        ("http://[::1]:9000/callback", True),
        ("https://usewren.com/cb", False),  # https is not loopback
        ("http://example.com/cb", False),  # non-loopback http
    ],
)
def test_is_loopback(uri: str, expected: bool) -> None:
    assert is_loopback(uri) is expected


def test_exact_match_is_allowed() -> None:
    registered = ["https://app.example.com/callback"]
    assert is_allowed_redirect("https://app.example.com/callback", registered) is True


def test_https_redirect_requires_exact_match() -> None:
    registered = ["https://app.example.com/callback"]
    assert is_allowed_redirect("https://app.example.com/other", registered) is False


def test_loopback_allows_any_port_when_a_loopback_uri_is_registered() -> None:
    registered = ["http://127.0.0.1:1234/callback"]
    # A different ephemeral port on the same host+path is allowed (RFC 8252).
    assert is_allowed_redirect("http://127.0.0.1:59999/callback", registered) is True


def test_loopback_still_requires_matching_host_and_path() -> None:
    registered = ["http://127.0.0.1:1234/callback"]
    assert is_allowed_redirect("http://127.0.0.1:59999/evil", registered) is False
    assert is_allowed_redirect("http://localhost:59999/callback", registered) is False


def test_unregistered_loopback_without_a_loopback_registration_is_rejected() -> None:
    registered = ["https://app.example.com/callback"]
    assert is_allowed_redirect("http://127.0.0.1:5000/callback", registered) is False
