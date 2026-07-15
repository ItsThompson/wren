"""Password hashing (bcrypt cost 12) and strength validation."""

from __future__ import annotations

import bcrypt
import pytest

from wren.accounts.passwords import (
    BCRYPT_COST,
    BcryptPasswordHasher,
    validate_password_strength,
)


def test_default_hasher_uses_bcrypt_cost_12() -> None:
    hasher = BcryptPasswordHasher()
    stored = hasher.hash("Sup3rSecret")
    # A bcrypt hash encodes its cost as the second field: $2b$12$...
    assert stored.startswith("$2b$12$")
    assert BCRYPT_COST == 12


def test_hash_is_not_plaintext_and_verifies() -> None:
    hasher = BcryptPasswordHasher(cost=4)
    stored = hasher.hash("Sup3rSecret")
    assert "Sup3rSecret" not in stored
    assert hasher.verify("Sup3rSecret", stored) is True


def test_wrong_password_does_not_verify() -> None:
    hasher = BcryptPasswordHasher(cost=4)
    stored = hasher.hash("Sup3rSecret")
    assert hasher.verify("wrong-password", stored) is False


def test_verify_of_malformed_hash_is_false_not_error() -> None:
    hasher = BcryptPasswordHasher(cost=4)
    assert hasher.verify("anything", "not-a-bcrypt-hash") is False


def test_each_hash_is_salted_and_distinct() -> None:
    hasher = BcryptPasswordHasher(cost=4)
    assert hasher.hash("Sup3rSecret") != hasher.hash("Sup3rSecret")


def test_cost_12_hash_round_trips() -> None:
    # Guards the production cost end-to-end (slower, so a single case).
    hasher = BcryptPasswordHasher(cost=12)
    stored = hasher.hash("Another1Pass")
    assert bcrypt.checkpw(b"Another1Pass", stored.encode("utf-8"))


@pytest.mark.parametrize(
    "password",
    [
        "Str0ngPass",
        "aB3aB3aB",
        "P@ssw0rd123",
    ],
)
def test_strong_passwords_pass(password: str) -> None:
    assert validate_password_strength(password) is None


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("Ab3", "too short"),
        ("alllowercase1", "no uppercase"),
        ("ALLUPPERCASE1", "no lowercase"),
        ("NoDigitsHere", "no digit"),
        ("Ab3" + "x" * 71, "over 72 bytes"),
    ],
)
def test_weak_passwords_are_rejected_with_a_message(password: str, reason: str) -> None:
    message = validate_password_strength(password)
    assert message is not None
    assert isinstance(message, str) and message


def test_over_72_bytes_has_a_specific_message() -> None:
    message = validate_password_strength("Aa1" + "x" * 70)
    assert message is not None
    assert "72" in message
