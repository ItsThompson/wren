"""Unit tests for the Group-A generation-input transforms.

``build_generation_input`` restricts the raw internal OpenAPI to the Group-A
component set and applies the deterministic transforms the frozen agent contract
requires. The committed artifact + the CI drift gate pin the output for the
current backend shapes; these tests pin the transform logic itself against
representative schema fragments, so a regression is caught even for a shape the
current backend does not yet emit.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from build_generation_input import (
    GROUP_A_COMPONENTS,
    _default_empty_non_null_arrays,
    _drop_visibility,
    _inline_nullable_constrained_scalars,
    _lift_patch_op_union,
    _select_group_a,
    build_generation_input,
)

# --- _inline_nullable_constrained_scalars ------------------------------------


def test_inline_rewrites_a_constrained_nullable_scalar() -> None:
    schema: dict[str, Any] = {
        "properties": {"title": {"anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}]}}
    }
    _inline_nullable_constrained_scalars(schema)
    prop = schema["properties"]["title"]
    assert "anyOf" not in prop
    assert prop["type"] == ["string", "null"]
    assert prop["minLength"] == 1


def test_inline_leaves_a_plain_nullable_scalar_untouched() -> None:
    # No constraint to hoist, so the anyOf inlines correctly as-is.
    schema: dict[str, Any] = {
        "properties": {"note": {"anyOf": [{"type": "string"}, {"type": "null"}]}}
    }
    before = deepcopy(schema)
    _inline_nullable_constrained_scalars(schema)
    assert schema == before


def test_inline_leaves_a_nullable_array_untouched() -> None:
    # Arrays are excluded on purpose: a nullable array keeps its null branch.
    schema: dict[str, Any] = {
        "properties": {
            "checked_ids": {
                "anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]
            }
        }
    }
    before = deepcopy(schema)
    _inline_nullable_constrained_scalars(schema)
    assert schema == before


# --- _default_empty_non_null_arrays ------------------------------------------


def test_default_added_to_an_optional_non_null_array() -> None:
    schema: dict[str, Any] = {
        "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
        "required": [],
    }
    _default_empty_non_null_arrays(schema)
    assert schema["properties"]["tags"]["default"] == []


def test_default_not_added_to_a_required_array() -> None:
    schema: dict[str, Any] = {
        "properties": {"tags": {"type": "array"}},
        "required": ["tags"],
    }
    _default_empty_non_null_arrays(schema)
    assert "default" not in schema["properties"]["tags"]


def test_default_not_added_to_a_nullable_array() -> None:
    # A nullable array carries anyOf (no top-level type "array"), so it is left
    # alone and keeps its null branch.
    schema: dict[str, Any] = {
        "properties": {"checked_ids": {"anyOf": [{"type": "array"}, {"type": "null"}]}},
        "required": [],
    }
    _default_empty_non_null_arrays(schema)
    assert "default" not in schema["properties"]["checked_ids"]


def test_default_preserves_an_existing_default() -> None:
    schema: dict[str, Any] = {
        "properties": {"tags": {"type": "array", "default": ["x"]}},
        "required": [],
    }
    _default_empty_non_null_arrays(schema)
    assert schema["properties"]["tags"]["default"] == ["x"]


# --- _drop_visibility --------------------------------------------------------


def test_drop_visibility_removes_the_property_and_required_entry() -> None:
    authoring: dict[str, Any] = {
        "properties": {"title": {"type": "string"}, "visibility": {"type": "string"}},
        "required": ["title", "visibility"],
    }
    _drop_visibility(authoring)
    assert "visibility" not in authoring["properties"]
    assert authoring["required"] == ["title"]


def test_drop_visibility_without_a_required_key() -> None:
    authoring: dict[str, Any] = {"properties": {"visibility": {"type": "string"}}}
    _drop_visibility(authoring)
    assert authoring["properties"] == {}


# --- _select_group_a ---------------------------------------------------------


def test_select_group_a_returns_only_group_a() -> None:
    raw: dict[str, Any] = {name: {"type": "object"} for name in GROUP_A_COMPONENTS}
    raw["Roadmap"] = {"type": "object"}  # a non-Group-A domain type
    selected = _select_group_a(raw)
    assert set(selected) == set(GROUP_A_COMPONENTS)
    assert "Roadmap" not in selected


def test_select_group_a_fails_loudly_on_a_missing_component() -> None:
    raw: dict[str, Any] = {name: {"type": "object"} for name in GROUP_A_COMPONENTS}
    del raw["Violation"]
    with pytest.raises(SystemExit, match="missing Group-A components"):
        _select_group_a(raw)


# --- _lift_patch_op_union ----------------------------------------------------


def test_lift_patch_op_union_accepts_a_discriminated_union() -> None:
    raw: dict[str, Any] = {
        "PatchRequest": {
            "properties": {
                "operations": {"items": {"oneOf": [], "discriminator": {"propertyName": "op"}}}
            }
        }
    }
    _lift_patch_op_union(raw)  # no raise


def test_lift_patch_op_union_rejects_a_degraded_union() -> None:
    raw: dict[str, Any] = {
        "PatchRequest": {"properties": {"operations": {"items": {"type": "object"}}}}
    }
    with pytest.raises(SystemExit, match="discriminated oneOf"):
        _lift_patch_op_union(raw)


# --- build_generation_input (end to end) -------------------------------------


def _raw_schemas() -> dict[str, Any]:
    """A minimal component set: every Group-A name plus the excluded PatchRequest."""
    schemas: dict[str, Any] = {
        name: {"type": "object", "properties": {}} for name in GROUP_A_COMPONENTS
    }
    schemas["RoadmapInput"]["properties"] = {
        "title": {"type": "string"},
        "visibility": {"type": "string"},
    }
    schemas["RoadmapInput"]["required"] = ["title", "visibility"]
    # PatchRequest is excluded from Group A but must still carry the union the
    # hand-authored PatchOp alias mirrors, for the union guard to pass.
    schemas["PatchRequest"] = {
        "properties": {
            "operations": {"items": {"oneOf": [], "discriminator": {"propertyName": "op"}}}
        }
    }
    return schemas


def test_build_generation_input_selects_renames_and_drops_visibility() -> None:
    doc: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "0"},
        "components": {"schemas": _raw_schemas()},
    }
    result = build_generation_input(doc)
    schemas = result["components"]["schemas"]

    expected = (set(GROUP_A_COMPONENTS) - {"RoadmapInput"}) | {"RoadmapDraftInput"}
    assert set(schemas) == expected
    assert "RoadmapInput" not in schemas  # renamed
    assert "PatchRequest" not in schemas  # excluded from Group A

    draft = schemas["RoadmapDraftInput"]
    assert "visibility" not in draft["properties"]
    assert "visibility" not in draft["required"]
    assert result["paths"] == {}
