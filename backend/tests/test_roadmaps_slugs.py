"""Exhaustive + property-based tests for the pure ``slugs`` deep module.

The highest-density target (spec section 13): slugify rules, prefixing, numeric
collision suffixing, ASCII folding, and the roadmap-ID composition, plus
``hypothesis`` invariants (any title always yields a valid, unique, prefixed slug
within a growing ``existing`` set).
"""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wren.roadmaps.slugs import (
    SLUG_FALLBACK,
    TOKEN_ALPHABET,
    TOKEN_LENGTH,
    compose_roadmap_id,
    mint,
    mint_proposed,
    random_token,
    slugify,
)

_VALID_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# --- slugify: rules, ASCII fold, fallback -----------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Two Pointers", "two-pointers"),
        ("UPPER CASE", "upper-case"),
        ("  leading and trailing  ", "leading-and-trailing"),
        ("multiple   spaces", "multiple-spaces"),
        ("punctuation!!!here", "punctuation-here"),
        ("C++ basics", "c-basics"),
        ("snake_case_title", "snake-case-title"),
        ("already-a-slug", "already-a-slug"),
        ("dashes---collapse", "dashes-collapse"),
        ("123 numbers 456", "123-numbers-456"),
    ],
)
def test_slugify_normalizes_titles(text: str, expected: str) -> None:
    assert slugify(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Café au lait", "cafe-au-lait"),
        ("naïve résumé", "naive-resume"),
        ("Crème brûlée", "creme-brulee"),
        ("Ångström", "angstrom"),
        ("Zürich", "zurich"),
    ],
)
def test_slugify_folds_accents_to_ascii(text: str, expected: str) -> None:
    assert slugify(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "!!!", "🚀🚀", "日本語", "---"])
def test_slugify_falls_back_when_nothing_survives(text: str) -> None:
    assert slugify(text) == SLUG_FALLBACK


# --- mint: prefix + collision suffixing -------------------------------------


def test_mint_prefixes_and_slugifies() -> None:
    assert mint("Two Pointers", "sub_", set()) == "sub_two-pointers"


def test_mint_de_dupes_with_a_numeric_suffix() -> None:
    existing = {"sub_two-pointers"}
    assert mint("Two Pointers", "sub_", existing) == "sub_two-pointers-2"


def test_mint_walks_past_multiple_collisions() -> None:
    existing = {"sub_arrays", "sub_arrays-2", "sub_arrays-3"}
    assert mint("Arrays", "sub_", existing) == "sub_arrays-4"


def test_mint_uses_each_entity_prefix() -> None:
    assert mint("Intro", "sec_", set()) == "sec_intro"
    assert mint("Read the docs", "chk_", set()) == "chk_read-the-docs"
    assert mint("Guide", "res_", set()) == "res_guide"


# --- mint_proposed: normalize an already-prefixed or bare proposal -----------


def test_mint_proposed_accepts_an_already_prefixed_id() -> None:
    assert mint_proposed("sub_two-pointers", "sub_", set()) == "sub_two-pointers"


def test_mint_proposed_prefixes_a_bare_proposal() -> None:
    assert mint_proposed("two-pointers", "sub_", set()) == "sub_two-pointers"


def test_mint_proposed_reslugifies_a_malformed_proposal() -> None:
    assert mint_proposed("Two Pointers!", "sub_", set()) == "sub_two-pointers"


def test_mint_proposed_de_dupes_like_mint() -> None:
    assert mint_proposed("sub_arrays", "sub_", {"sub_arrays"}) == "sub_arrays-2"


# --- roadmap ID composition + token -----------------------------------------


def test_compose_roadmap_id_appends_the_token() -> None:
    assert compose_roadmap_id("Grokking DSA", "7f3k") == "grokking-dsa-7f3k"


def test_random_token_shape() -> None:
    token = random_token()
    assert len(token) == TOKEN_LENGTH
    assert all(char in TOKEN_ALPHABET for char in token)


def test_random_token_varies() -> None:
    # Not a strict guarantee, but over many draws a fixed value is effectively
    # impossible: catches a hard-coded/broken generator.
    assert len({random_token() for _ in range(50)}) > 1


# --- property-based invariants (hypothesis) ---------------------------------


@given(st.text())
def test_slugify_always_yields_a_valid_slug(text: str) -> None:
    slug = slugify(text)
    assert _VALID_SLUG.match(slug), slug


@given(st.text(), st.sampled_from(["sec_", "sub_", "chk_", "res_"]))
def test_mint_always_prefixed_and_valid(title: str, prefix: str) -> None:
    minted = mint(title, prefix, set())
    assert minted.startswith(prefix)
    assert _VALID_SLUG.match(minted[len(prefix) :])


@given(st.lists(st.text(), min_size=1, max_size=40))
def test_mint_is_unique_within_a_growing_set(titles: list[str]) -> None:
    existing: set[str] = set()
    for title in titles:
        minted = mint(title, "sub_", existing)
        assert minted not in existing
        existing.add(minted)
    # Every mint produced a distinct ID: no collisions slipped through.
    assert len(existing) == len(titles)
