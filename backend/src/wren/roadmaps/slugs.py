"""``slugs``: the pure, deterministic slug-minting deep module.

No I/O, no request, no token: just functions over strings and sets, so they are
the highest-density test target. Two concerns:

- **Child-entity IDs** (``sec_``/``sub_``/``chk_``/``res_``) are minted from a
  title (or a caller-proposed ID), prefixed by entity, and de-duped *within one
  roadmap* with a numeric suffix (``sub_two-pointers-2``). The suffix is safe:
  all siblings share the same roadmap and owner, so it leaks nothing.
- **Roadmap IDs** are ``{title-slug}-{short-random}`` (e.g. ``grokking-dsa-7f3k``).
  The random token is what makes them globally unique and keeps minting from ever
  emitting a client-visible sequential ``-2`` that would leak another user's
  (possibly private) roadmap. Collision handling (re-roll) is the caller's job
  because global uniqueness needs the database; this module only composes the ID
  and generates a token.
"""

from __future__ import annotations

import re
import secrets
import unicodedata

# Fallback slug body for a title that folds to nothing (all punctuation / emoji /
# non-Latin), so ``mint`` always yields a valid, prefixable slug.
SLUG_FALLBACK = "untitled"

# Crockford base32 (lowercased), minus the ambiguous i/l/o/u. A 4-char token over
# this 32-symbol alphabet gives ~1M combinations: ample for the single-VPS,
# few-users deployment while keeping IDs short and readable.
TOKEN_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
TOKEN_LENGTH = 4

# One run of anything that is not an ASCII lowercase letter or digit becomes a
# single hyphen; leading/trailing hyphens are then stripped.
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, ASCII-fold, and hyphenate ``text`` into a slug body.

    ``"Two Pointers"`` -> ``"two-pointers"``; ``"Café au lait"`` -> ``"cafe-au-lait"``
    (accents folded via NFKD + ASCII drop). A title with no usable characters
    folds to :data:`SLUG_FALLBACK` so the result is always a valid slug.
    """
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _NON_SLUG.sub("-", folded.lower()).strip("-")
    return slug or SLUG_FALLBACK


def mint(title: str, prefix: str, existing_ids: set[str]) -> str:
    """Mint a prefixed, de-duped child-entity ID from a title.

    Slugifies ``title``, prepends ``prefix``, and appends the smallest ``-N``
    (N >= 2) needed to make it unique within ``existing_ids``.
    """
    return _dedupe(f"{prefix}{slugify(title)}", existing_ids)


def mint_proposed(proposed_id: str, prefix: str, existing_ids: set[str]) -> str:
    """Validate/slugify/de-dupe a caller-proposed child ID.

    A proposed ID may arrive already prefixed (``"sub_two-pointers"``) or bare
    (``"two-pointers"``); either way the prefix is normalized exactly once, the
    body is re-slugified (so a malformed proposal is still safe), and the result
    is de-duped like :func:`mint`.
    """
    body = proposed_id[len(prefix) :] if proposed_id.startswith(prefix) else proposed_id
    return _dedupe(f"{prefix}{slugify(body)}", existing_ids)


def compose_roadmap_id(base: str, token: str) -> str:
    """Compose a roadmap ID as ``{slug-of-base}-{token}``.

    ``base`` is the title (or a caller-proposed base); the random ``token`` is
    what guarantees global uniqueness, so the caller never emits a sequential
    suffix that could leak another roadmap's existence.
    """
    return f"{slugify(base)}-{token}"


def random_token() -> str:
    """A cryptographically random :data:`TOKEN_LENGTH`-char base32 token.

    The default token source injected into the service; overridable in tests to
    force a collision and prove the silent re-roll.
    """
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))


def _dedupe(candidate: str, existing_ids: set[str]) -> str:
    """Return ``candidate`` or the first ``candidate-N`` (N >= 2) not yet taken."""
    if candidate not in existing_ids:
        return candidate
    suffix = 2
    while f"{candidate}-{suffix}" in existing_ids:
        suffix += 1
    return f"{candidate}-{suffix}"
