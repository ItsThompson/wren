"""Restrict the raw internal OpenAPI to the Group-A component set for codegen.

Reads the committed raw internal-OpenAPI artifact (the unfiltered export of
``wren.api_internal.main:app``) and writes, to stdout, a reduced OpenAPI document
carrying exactly the Group-A component schemas the MCP server mirrors, with the
two deterministic transforms the frozen agent contract requires:

* the authoring input drops its ``visibility`` property (a web-only lifecycle
  control with no agent tool), which also makes the ``Visibility`` enum
  unreferenced and therefore absent from generation;
* the authoring input component is renamed ``RoadmapInput`` -> ``RoadmapDraftInput``
  (the name the frozen contract and ``tools_write`` import).

The output feeds ``datamodel-codegen`` (see ``just codegen-mcp``). Restricting the
input here, rather than re-exporting only Group A from the backend, keeps the raw
artifact the drift source of truth: a backend change to a non-Group-A schema moves
the raw artifact but not the generated module.

The Group-A allowlist below is maintained by hand. It is cross-checked against the
generated module by ``contract/tests/test_schema_mirror.py`` (``EXPECTED_GROUP_A``),
which is declared independently, so an over- or under-inclusion here fails CI.
"""

from __future__ import annotations

import json
import sys
from typing import Any

# The authoring input is emitted under the frozen contract name; the raw artifact
# carries the backend class name.
_AUTHORING_INPUT_SOURCE = "RoadmapInput"
_AUTHORING_INPUT_TARGET = "RoadmapDraftInput"

# The synthetic discriminated-union component name is intentionally NOT
# generated here. datamodel-codegen emits a top-level ``oneOf`` component as a
# ``RootModel`` subclass, not the ``Annotated[Union[...], Field(discriminator=...)]``
# type alias the frozen contract and ``tools_write`` use, and a RootModel wrapper
# would change the tool input schema at every ``list[PatchOp]`` use site. So
# ``PatchOp`` is hand-authored in ``schemas.py`` as a union alias over the generated
# member classes, and the union is not lifted here.
_PATCH_REQUEST = "PatchRequest"

# The Group-A component set, keyed by the raw artifact's (backend) component names.
# ``RoadmapInput`` is listed under its source name; the rename happens after
# selection.
GROUP_A_COMPONENTS: frozenset[str] = frozenset(
    {
        # Shared enums.
        "ResourceType",
        "RoadmapStatus",
        "ChangedNodeKind",
        "ChangeType",
        "ResponseFormat",
        "SectionInclude",
        "SearchHitKind",
        "CompletionState",
        # Authoring inputs (RoadmapInput is renamed to RoadmapDraftInput below).
        "ResourceInput",
        "ChecklistItemInput",
        "SubsectionInput",
        "SectionInput",
        _AUTHORING_INPUT_SOURCE,
        # The 16 patch operations.
        "AddSubsectionOp",
        "UpdateSubsectionOp",
        "RemoveSubsectionOp",
        "AddEdgeOp",
        "RemoveEdgeOp",
        "SetTagsOp",
        "SetResourcesOp",
        "SetEffortOp",
        "AddItemOp",
        "UpdateItemOp",
        "RemoveItemOp",
        "ReorderOp",
        "SetSuggestedPathOp",
        "AddSectionOp",
        "UpdateSectionOp",
        "RemoveSectionOp",
        # Changed-node echo + structural-rule violation.
        "ChangedNode",
        "Violation",
        # Read projections (roadmaps).
        "ResourceRef",
        "PrereqRef",
        "ItemState",
        "NodeDetail",
        "SectionOverview",
        "OverallProgress",
        "Overview",
        "SectionPage",
        "SearchHit",
        # Read projections (progress).
        "SectionProgress",
        "ProgressSnapshot",
        "NextItem",
        "NextResult",
        "ResourceLink",
        "ProgressUpdateResult",
    }
)

# The property the authoring input omits, plus the enum it references. Dropping
# the property makes the enum unreferenced, so Group A is a closed component set.
_OMITTED_INPUT_PROPERTY = "visibility"

# Scalar JSON types whose constrained-nullable form the generator would hoist
# into a shared model. Arrays are excluded on purpose (see below).
_SCALAR_TYPES = frozenset({"string", "integer", "number", "boolean"})


def _inline_nullable_constrained_scalars(schema: dict[str, Any]) -> None:
    """Rewrite ``anyOf: [<constrained scalar>, null]`` to the 3.1 nullable form.

    Pydantic exports an optional constrained scalar (e.g. ``str | None`` with
    ``min_length=1``) as ``{"anyOf": [{"type": "string", "minLength": 1}, {"type":
    "null"}]}``. The generator hoists the constrained branch into a shared
    ``RootModel`` (an extra module type and a ``$ref``), which both breaks the
    exact-Group-A guard and changes the tool schema from an inline constraint to a
    ``$ref``. Rewriting to the OpenAPI 3.1 union-type form (``{"type": ["string",
    "null"], "minLength": 1}``) makes the generator emit an inline
    ``str | None = Field(min_length=1)``, which Pydantic re-exports as the original
    ``anyOf`` shape. Only constrained scalars are rewritten: a plain nullable
    scalar and a nullable array already inline correctly, so they are left alone.
    """
    for prop in schema.get("properties", {}).values():
        branches = prop.get("anyOf")
        if not (isinstance(branches, list) and len(branches) == 2):
            continue
        non_null = [b for b in branches if b.get("type") != "null"]
        has_null = any(b.get("type") == "null" for b in branches)
        if not (has_null and len(non_null) == 1):
            continue
        scalar = non_null[0]
        constraints = {k: v for k, v in scalar.items() if k != "type"}
        if scalar.get("type") in _SCALAR_TYPES and constraints:
            prop.pop("anyOf")
            prop.update(constraints)
            prop["type"] = [scalar["type"], "null"]


def _default_empty_non_null_arrays(schema: dict[str, Any]) -> None:
    """Give every non-required, non-nullable array property a ``default: []``.

    The backend declares these collections with ``default_factory=list``, which
    Pydantic omits from the exported schema (no ``default`` key, absent from
    ``required``). Without a default the generator would treat them as nullable
    and emit ``list[...] | None = None``, adding a ``null`` the frozen contract
    does not carry. A ``default: []`` keeps the generated field a plain defaulted
    array (``list[...] = []``). Nullable arrays (``anyOf`` with ``null``, e.g.
    ``checked_ids``) are left untouched: they carry the ``null`` on purpose.
    """
    required = set(schema.get("required", ()))
    for name, prop in schema.get("properties", {}).items():
        if name not in required and prop.get("type") == "array" and "default" not in prop:
            prop["default"] = []


def _select_group_a(schemas: dict[str, Any]) -> dict[str, Any]:
    """Return the Group-A subset, failing loudly on any missing component."""
    missing = sorted(name for name in GROUP_A_COMPONENTS if name not in schemas)
    if missing:
        raise SystemExit(
            f"internal OpenAPI is missing Group-A components: {missing}. "
            "The backend surface changed; reconcile GROUP_A_COMPONENTS."
        )
    return {name: schemas[name] for name in GROUP_A_COMPONENTS}


def _drop_visibility(authoring_input: dict[str, Any]) -> None:
    """Remove the ``visibility`` property (and any required entry) in place."""
    authoring_input.get("properties", {}).pop(_OMITTED_INPUT_PROPERTY, None)
    if "required" in authoring_input:
        authoring_input["required"] = [
            name for name in authoring_input["required"] if name != _OMITTED_INPUT_PROPERTY
        ]


def _lift_patch_op_union(raw_schemas: dict[str, Any]) -> None:
    """Assert the excluded PatchRequest still carries the union PatchOp mirrors.

    ``PatchOp`` is hand-authored in ``schemas.py`` (see the module note), so nothing
    is lifted; this guards that the source union the alias mirrors still exists, so
    a backend rename surfaces here rather than as a silent alias drift.
    """
    items = raw_schemas[_PATCH_REQUEST]["properties"]["operations"]["items"]
    if "oneOf" not in items or "discriminator" not in items:
        raise SystemExit(
            "PatchRequest no longer carries a discriminated oneOf union; the "
            "hand-authored PatchOp alias in schemas.py may be stale."
        )


def build_generation_input(doc: dict[str, Any]) -> dict[str, Any]:
    """Build the reduced, transformed OpenAPI document for the generator."""
    raw_schemas = doc["components"]["schemas"]
    _lift_patch_op_union(raw_schemas)
    schemas = _select_group_a(raw_schemas)

    _drop_visibility(schemas[_AUTHORING_INPUT_SOURCE])
    schemas[_AUTHORING_INPUT_TARGET] = schemas.pop(_AUTHORING_INPUT_SOURCE)

    for schema in schemas.values():
        _inline_nullable_constrained_scalars(schema)
        _default_empty_non_null_arrays(schema)

    return {
        "openapi": doc.get("openapi", "3.1.0"),
        "info": doc.get("info", {"title": "wren-mcp-group-a", "version": "0.1.0"}),
        "paths": {},
        "components": {"schemas": schemas},
    }


def main() -> None:
    if len(sys.argv) < 2:
        doc = json.load(sys.stdin)
    else:
        with open(sys.argv[1]) as handle:
            doc = json.load(handle)
    json.dump(build_generation_input(doc), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
