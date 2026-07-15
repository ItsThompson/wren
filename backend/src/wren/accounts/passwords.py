"""Password hashing and strength validation (spec section 08: bcrypt cost 12).

The hasher is a small protocol so the service depends on an interface, not on
bcrypt directly: tests can substitute a fast fake and the production binding is
:class:`BcryptPasswordHasher`. Strength validation is a pure function returning
an error message (or ``None``) so the service can raise a field-level
``Validation`` with a specific, model-recoverable message.
"""

from __future__ import annotations

from typing import Protocol

import bcrypt

# Spec section 08: bcrypt cost 12.
BCRYPT_COST = 12

# bcrypt hashes at most the first 72 bytes of the password; a longer password is
# silently truncated, so reject it up front rather than hash a prefix.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


class PasswordHasher(Protocol):
    """Hashes and verifies passwords. Injected so the service is bcrypt-agnostic."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class BcryptPasswordHasher:
    """Production hasher: bcrypt at cost 12."""

    def __init__(self, cost: int = BCRYPT_COST) -> None:
        self._cost = cost

    def hash(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self._cost)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            # A malformed/rotated hash string never matches; treat as a failed
            # verification rather than a 500.
            return False


def validate_password_strength(password: str) -> str | None:
    """Return an error message if the password is too weak, else ``None``.

    Requires >= 8 characters with at least one uppercase, one lowercase, and one
    digit, and rejects passwords over bcrypt's 72-byte limit. Kept as one message
    for the combined rule so the client shows a single, actionable requirement.
    """
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return "Password must not exceed 72 bytes."
    requirement = (
        "Password must be at least 8 characters and include an uppercase letter, "
        "a lowercase letter, and a digit."
    )
    if len(password) < MIN_PASSWORD_LENGTH:
        return requirement
    has_upper = any(char.isupper() for char in password)
    has_lower = any(char.islower() for char in password)
    has_digit = any(char.isdigit() for char in password)
    if not (has_upper and has_lower and has_digit):
        return requirement
    return None
