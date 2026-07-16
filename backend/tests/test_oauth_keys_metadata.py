"""Signing key loading/rotation, the published JWKS, and AS metadata.

Covers: an ephemeral dev key when no PEM is configured; loading a mounted PEM;
fail-fast outside development; the JWKS never leaking private material and
supporting multiple ``kid`` entries (rotation); and AS metadata built from the
pinned issuer advertising S256.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc.jwk import RSAKey

from tests.oauth_fakes import build_test_config, build_test_keyset
from wren.oauth.keys import SigningKeySet, load_signing_key_set
from wren.oauth.metadata import build_as_metadata

if TYPE_CHECKING:
    from pathlib import Path


def _write_pem(path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def test_dev_generates_an_ephemeral_key_when_no_pem_is_configured() -> None:
    config = build_test_config()
    keyset = load_signing_key_set(config, is_dev=True)
    assert keyset.active_kid == config.key_id
    assert keyset.active.is_private is True


def test_missing_key_fails_fast_outside_development() -> None:
    config = build_test_config()
    with pytest.raises(RuntimeError, match="OAUTH_PRIVATE_KEY_PATH"):
        load_signing_key_set(config, is_dev=False)


def test_loads_a_mounted_pem_with_the_configured_kid(tmp_path: Path) -> None:
    pem_path = tmp_path / "oauth_private.pem"
    _write_pem(pem_path)
    config = build_test_config()
    mounted = config.__class__(**{**config.__dict__, "key_path": str(pem_path)})
    keyset = load_signing_key_set(mounted, is_dev=False)
    assert keyset.active_kid == config.key_id
    assert keyset.active.is_private is True


def test_jwks_publishes_public_keys_without_private_material() -> None:
    keyset = build_test_keyset(build_test_config())
    jwks = keyset.jwks()
    assert list(jwks.keys()) == ["keys"]
    (public_key,) = jwks["keys"]
    assert public_key["kid"] == "test-kid"
    assert public_key["kty"] == "RSA"
    # No private exponent or CRT parameters ever leave the AS.
    for private_field in ("d", "p", "q", "dp", "dq", "qi"):
        assert private_field not in public_key


def test_jwks_carries_every_kid_for_rotation() -> None:
    config = build_test_config()
    active = build_test_keyset(config).active
    retired = RSAKey.generate_key(2048, parameters={"use": "sig", "alg": "RS256", "kid": "old"})
    keyset = SigningKeySet(active=active, retired=(retired,))
    kids = {key["kid"] for key in keyset.jwks()["keys"]}
    assert kids == {"test-kid", "old"}


def test_signing_header_binds_the_active_kid() -> None:
    keyset = build_test_keyset(build_test_config())
    assert keyset.signing_header() == {"alg": "RS256", "kid": "test-kid"}


def test_as_metadata_urls_are_all_built_from_the_issuer() -> None:
    metadata = build_as_metadata(build_test_config())
    assert metadata["issuer"] == "https://api.usewren.com"
    assert metadata["authorization_endpoint"] == "https://api.usewren.com/authorize"
    assert metadata["token_endpoint"] == "https://api.usewren.com/token"
    assert metadata["registration_endpoint"] == "https://api.usewren.com/register"
    assert metadata["revocation_endpoint"] == "https://api.usewren.com/revoke"
    assert metadata["jwks_uri"] == "https://api.usewren.com/jwks"


def test_as_metadata_advertises_s256_and_public_client_capabilities() -> None:
    metadata = build_as_metadata(build_test_config())
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert metadata["response_types_supported"] == ["code"]
    assert "authorization_code" in metadata["grant_types_supported"]
    assert "refresh_token" in metadata["grant_types_supported"]
    assert metadata["token_endpoint_auth_methods_supported"] == ["none"]
    assert set(metadata["scopes_supported"]) == {
        "roadmaps:read",
        "roadmaps:write",
        "progress:write",
    }
