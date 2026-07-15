"""RemoteKeyProvider tests: JWKS discovery, caching, and throttled rotation.

The provider discovers the JWKS URI from AS metadata (RFC 8414) and caches the
fetched key set; an unknown ``kid`` triggers a single refetch, bounded by a
cooldown so a stream of unknown-kid tokens cannot hammer the AS. The network is
faked; the discovery/caching logic runs for real.
"""

from __future__ import annotations

from token_factory import ISSUER, make_fetch, new_key, public_jwks
from wren_mcp.config import AS_METADATA_PATH
from wren_mcp.keys import RemoteKeyProvider


async def test_discovers_jwks_uri_from_as_metadata() -> None:
    key = new_key(kid="kid-1")
    fetch = make_fetch(public_jwks(key))
    provider = RemoteKeyProvider(ISSUER, fetch)

    key_set = await provider.load()

    assert key_set.get_by_kid("kid-1") is not None
    # Discovery reads AS metadata first, then the advertised jwks_uri.
    assert fetch.calls == [f"{ISSUER}{AS_METADATA_PATH}", f"{ISSUER}/jwks"]  # type: ignore[attr-defined]


async def test_caches_the_key_set_across_lookups() -> None:
    key = new_key(kid="kid-1")
    fetch = make_fetch(public_jwks(key))
    provider = RemoteKeyProvider(ISSUER, fetch)

    await provider.key_set_for("kid-1")
    await provider.key_set_for("kid-1")

    # One discovery pass (2 fetches) despite two lookups: the set is cached.
    assert len(fetch.calls) == 2  # type: ignore[attr-defined]


async def test_unknown_kid_triggers_a_single_refetch() -> None:
    key = new_key(kid="kid-1")
    fetch = make_fetch(public_jwks(key))
    provider = RemoteKeyProvider(ISSUER, fetch, refresh_cooldown_seconds=0.0)

    await provider.key_set_for("kid-1")  # prime cache (2 fetches)
    await provider.key_set_for("kid-unknown")  # unknown -> refetch (2 more)

    assert len(fetch.calls) == 4  # type: ignore[attr-defined]


async def test_unknown_kid_refetch_is_throttled_by_the_cooldown() -> None:
    key = new_key(kid="kid-1")
    fetch = make_fetch(public_jwks(key))
    ticks = iter([0.0, 0.0, 1.0, 2.0, 3.0])
    provider = RemoteKeyProvider(
        ISSUER, fetch, refresh_cooldown_seconds=100.0, clock=lambda: next(ticks)
    )

    await provider.key_set_for("kid-1")  # prime cache (2 fetches)
    await provider.key_set_for("kid-unknown")  # within cooldown -> no refetch
    await provider.key_set_for("kid-unknown")  # still within cooldown -> no refetch

    assert len(fetch.calls) == 2  # type: ignore[attr-defined]


async def test_load_forces_a_reload() -> None:
    key = new_key(kid="kid-1")
    fetch = make_fetch(public_jwks(key))
    provider = RemoteKeyProvider(ISSUER, fetch)

    await provider.load()
    await provider.load()

    assert len(fetch.calls) == 4  # type: ignore[attr-defined]
