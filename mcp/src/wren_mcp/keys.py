"""AS public-key discovery for Resource-Server token verification.

The AS holds the RSA private key and signs agent access tokens (RS256); this RS
verifies them against the AS's **public** JWKS. This module discovers the JWKS
URI from the AS metadata document (RFC 8414, built off the pinned issuer),
fetches the public keys (RFC 7517), and caches the resulting key set.

Key rotation by ``kid`` is supported: a token whose ``kid`` is absent from the
cached set triggers a single refetch, throttled by a cooldown so a stream of
unknown-``kid`` tokens cannot hammer the AS. Crypto is delegated to joserfc; this
module only fetches and shapes keys.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast

from joserfc.errors import InvalidKeyIdError
from joserfc.jwk import KeySet, KeySetSerialization

from wren_mcp.config import AS_METADATA_PATH

# Fetches and parses a JSON document from a URL. Injected so tests substitute the
# network without touching the discovery/caching logic.
JsonFetch = Callable[[str], Awaitable[dict[str, Any]]]

_DEFAULT_REFRESH_COOLDOWN_SECONDS = 10.0


class KeyProvider(Protocol):
    """Supplies the verifying key set, refreshing to pick up ``kid`` rotation."""

    async def key_set_for(self, kid: str | None) -> KeySet: ...

    async def load(self) -> KeySet: ...


def _has_kid(key_set: KeySet, kid: str) -> bool:
    try:
        key_set.get_by_kid(kid)
    except InvalidKeyIdError:
        return False
    return True


class RemoteKeyProvider:
    """Discovers, fetches, and caches the AS public JWKS for token verification."""

    def __init__(
        self,
        issuer: str,
        fetch_json: JsonFetch,
        *,
        refresh_cooldown_seconds: float = _DEFAULT_REFRESH_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._fetch_json = fetch_json
        self._cooldown = refresh_cooldown_seconds
        self._clock = clock
        self._key_set: KeySet | None = None
        self._last_refresh = 0.0
        self._lock = asyncio.Lock()

    async def key_set_for(self, kid: str | None) -> KeySet:
        """The cached key set, refetched once (throttled) if ``kid`` is unknown."""
        current = await self._ensure_loaded()
        if kid is not None and not _has_kid(current, kid):
            return await self._refresh_if_cool(current)
        return current

    async def load(self) -> KeySet:
        """Force a (re)load of the key set. Used at startup and by readiness."""
        async with self._lock:
            return await self._reload_locked()

    async def _ensure_loaded(self) -> KeySet:
        if self._key_set is not None:
            return self._key_set
        async with self._lock:
            if self._key_set is None:
                await self._reload_locked()
            assert self._key_set is not None
            return self._key_set

    async def _refresh_if_cool(self, current: KeySet) -> KeySet:
        async with self._lock:
            if self._clock() - self._last_refresh < self._cooldown:
                # Within the cooldown window: serve what we have rather than
                # refetching on every unknown-kid token (DoS guard).
                return self._key_set or current
            return await self._reload_locked()

    async def _reload_locked(self) -> KeySet:
        """(Re)fetch the JWKS. Caller holds ``self._lock``."""
        metadata = await self._fetch_json(f"{self._issuer}{AS_METADATA_PATH}")
        jwks_uri = str(metadata["jwks_uri"])
        jwks = await self._fetch_json(jwks_uri)
        self._key_set = KeySet.import_key_set(cast("KeySetSerialization", jwks))
        self._last_refresh = self._clock()
        return self._key_set
