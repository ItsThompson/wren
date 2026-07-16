"""Asymmetric signing keys and the published JWKS.

The AS holds an RSA private key and signs agent access tokens with RS256; the MCP
Resource Server verifies them via the public JWKS this module publishes. Key
rotation is by ``kid``: the JWKS can carry more than one public key, so a new
signing key is published (and used to sign) while previously issued tokens still
verify against the retired ``kid`` until they expire.

Crypto is delegated to joserfc (the JOSE implementation Authlib now ships); this
module only loads/generates keys and shapes the key set, never hand-rolling
signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from joserfc.jwk import KeyParameters, KeySet, RSAKey

if TYPE_CHECKING:
    from wren.oauth.config import OAuthConfig

# joserfc JWK parameters marking a key as an RS256 signing key.
_SIG_PARAMS: KeyParameters = {"use": "sig", "alg": "RS256"}
_EPHEMERAL_KEY_BITS = 2048


@dataclass(frozen=True)
class SigningKeySet:
    """The active signing key plus any retired public keys still in the JWKS.

    ``active`` is the private key new tokens are signed with; ``retired`` are
    public-only keys kept in the JWKS so tokens signed before a rotation still
    verify until they expire.
    """

    active: RSAKey
    retired: tuple[RSAKey, ...] = field(default_factory=tuple)

    @property
    def active_kid(self) -> str:
        return str(self.active.kid)

    def signing_header(self) -> dict[str, str]:
        """The JWS header binding a token to the active key via ``kid``."""
        return {"alg": "RS256", "kid": self.active_kid}

    def verifying_key_set(self) -> KeySet:
        """A joserfc :class:`KeySet` of every public key, for signature checks."""
        return KeySet([self.active, *self.retired])

    def jwks(self) -> dict[str, Any]:
        """The public JWKS document (RFC 7517): no private material leaves here."""
        return dict(self.verifying_key_set().as_dict(private=False))


def _import_signing_key(pem: str | bytes, kid: str) -> RSAKey:
    parameters: KeyParameters = {**_SIG_PARAMS, "kid": kid}
    return RSAKey.import_key(pem, parameters=parameters)


def load_signing_key_set(config: OAuthConfig, *, is_dev: bool) -> SigningKeySet:
    """Load the AS signing key from the mounted PEM, or generate an ephemeral one.

    Production mounts the private key at ``OAUTH_PRIVATE_KEY_PATH`` (``chmod 600``)
    and this loads it. With no configured path, development generates an ephemeral
    in-memory keypair so the app boots without a mounted secret; outside
    development a missing key raises at startup rather than serving a JWKS the RS
    cannot use (fail fast, mirroring the session-secret guard).
    """
    if config.key_path:
        pem = Path(config.key_path).read_bytes()
        return SigningKeySet(active=_import_signing_key(pem, config.key_id))
    if not is_dev:
        raise RuntimeError(
            "OAUTH_PRIVATE_KEY_PATH must point to a signing key PEM outside development."
        )
    ephemeral = RSAKey.generate_key(
        _EPHEMERAL_KEY_BITS,
        parameters={**_SIG_PARAMS, "kid": config.key_id},
        private=True,
    )
    return SigningKeySet(active=ephemeral)
