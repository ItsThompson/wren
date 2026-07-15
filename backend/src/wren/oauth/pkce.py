"""PKCE (RFC 7636) verification, S256 only.

The AS requires the ``S256`` challenge method (spec section 08). The challenge
transform (SHA-256 + base64url) is delegated to Authlib; this module only wraps
it with a constant-time comparison so a token exchange proves possession of the
original ``code_verifier``.
"""

from __future__ import annotations

import secrets

from authlib.oauth2.rfc7636 import create_s256_code_challenge


def is_valid_s256(code_verifier: str, code_challenge: str) -> bool:
    """True if ``code_verifier`` hashes (S256) to the stored ``code_challenge``."""
    if not code_verifier or not code_challenge:
        return False
    computed = create_s256_code_challenge(code_verifier)
    return secrets.compare_digest(computed, code_challenge)
