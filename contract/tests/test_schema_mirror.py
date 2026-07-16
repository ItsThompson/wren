"""Cross-package schema-mirror drift test (F18b, US-CON-01).

The MCP resource server re-declares ~35 backend types in :mod:`wren_mcp.schemas`
(a deliberately frozen contract: the RS is a separate image with no backend-code
dependency, per section 12). Before this test the mirror was sync-by-discipline:
the MCP snapshot froze only the MCP side, the OpenAPI drift check froze only the
backend side, and nothing asserted the two agreed. This test makes the mirror
sync-by-*test*, and can only live here in the dev/test-only ``contract`` project
because it is the sole interpreter where both ``wren.*`` and ``wren_mcp.*`` import
together.

The mirrored types fall into three groups, treated differently:

* **Group A (:data:`ASSERT_EQUAL` + the patch-op union)** are field-for-field
  mirrors: shared enums, authoring inputs, the 16 ``*Op`` ops + the ``PatchOp``
  union, ``Violation``, and the read projections. Their generated JSON Schemas
  must be equal (after dropping prose ``description``/class-name ``title`` and
  applying :data:`INTENTIONAL_DELTAS`).
* **Group B (:data:`LEAN_SUBSET`)** are deliberately lean write results. They are
  summary-first and diverge from the backend's fuller results, so we assert only
  that every MCP field maps to a backend field of the same JSON type (no MCP-only
  field, no type drift) rather than full equality.
* **Group C (:data:`EXCLUDED_MCP_ONLY` / :data:`EXCLUDED_BACKEND_ONLY`)** are not
  mirrored at all and are documented, never compared.

:data:`INTENTIONAL_DELTAS` is the allowlist of the two known, deliberate Group-A
divergences (``RoadmapDraftInput`` omits ``visibility``; ``Violation.ids`` is
required on the backend but defaulted on the current frozen MCP mirror). It
freezes the *current* pre-hardening contract: the input-hardening slice that
aligns ``Violation.ids`` and adds ``extra="forbid"`` must update this allowlist
and the MCP snapshot in the same change, so any such edit is caught deliberately.
:func:`test_intentional_deltas_are_load_bearing` fails if an allowlist entry ever
stops describing a real divergence, keeping the allowlist honest.
"""

from __future__ import annotations

import inspect
from enum import Enum
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter
from wren.core import errors as backend_errors
from wren.core import read_contract as backend_read_contract
from wren.progress import schemas as backend_progress
from wren.roadmaps import read_schemas as backend_read
from wren.roadmaps import schemas as backend
from wren_mcp import schemas as mcp

# A JSON Schema object type; ``object`` for the schema tree's leaf scalars.
Schema = dict[str, Any]


# --------------------------------------------------------------------------- #
# JSON-Schema normalization                                                   #
# --------------------------------------------------------------------------- #
#
# Two faithful mirrors still differ in cosmetic ways that are not part of the
# wire contract: Pydantic stamps each schema with a ``title`` derived from the
# class name (which legitimately differs for the name-mapped pairs) and a
# ``description`` taken from the docstring (prose, excluded from the frozen MCP
# snapshot for the same reason). Normalizing those away leaves only the
# structural contract to compare.


def _json_schema(obj: object) -> Schema:
    """The JSON Schema for a Pydantic model, enum, or ``Annotated`` union."""
    if isinstance(obj, type) and issubclass(obj, BaseModel):
        return obj.model_json_schema()
    return TypeAdapter(obj).json_schema()


def _without_keys(node: object, keys: frozenset[str]) -> object:
    """Recursively drop ``keys`` from every mapping in a JSON-Schema tree."""
    if isinstance(node, dict):
        return {k: _without_keys(v, keys) for k, v in node.items() if k not in keys}
    if isinstance(node, list):
        return [_without_keys(item, keys) for item in node]
    return node


def _referenced_defs(node: object, acc: set[str]) -> None:
    """Collect the names of every ``#/$defs/<name>`` ``$ref`` under ``node``."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("#/$defs/"):
                acc.add(value.rsplit("/", 1)[-1])
            else:
                _referenced_defs(value, acc)
    elif isinstance(node, list):
        for item in node:
            _referenced_defs(item, acc)


def _prune_unreferenced_defs(schema: Schema) -> Schema:
    """Drop ``$defs`` entries no longer reachable from the root.

    Removing an optional field (an :data:`INTENTIONAL_DELTAS` ``omit``) can orphan
    the enum/model it referenced; pruning keeps the two sides comparable.
    """
    defs = schema.get("$defs")
    if not defs:
        return schema
    root = {key: value for key, value in schema.items() if key != "$defs"}
    frontier: set[str] = set()
    _referenced_defs(root, frontier)
    reachable: set[str] = set()
    while frontier:
        name = frontier.pop()
        if name in reachable:
            continue
        reachable.add(name)
        nested: set[str] = set()
        _referenced_defs(defs.get(name, {}), nested)
        frontier |= nested - reachable
    pruned = dict(schema)
    kept = {name: body for name, body in defs.items() if name in reachable}
    if kept:
        pruned["$defs"] = kept
    else:
        pruned.pop("$defs")
    return pruned


_COSMETIC_KEYS = frozenset({"description"})


def _canonical(
    obj: object, *, omit: tuple[str, ...] = (), optional: tuple[str, ...] = ()
) -> Schema:
    """Normalize a schema to its comparable structural contract.

    ``omit`` removes fields entirely (property + ``required`` + now-orphaned
    ``$defs``); ``optional`` only drops fields from ``required`` (a field the
    backend requires but the MCP mirror defaults). Both are applied to the side
    that carries the extra strictness so it matches the leaner mirror.
    """
    schema = _json_schema(obj)
    properties = schema.get("properties")
    if properties:
        for field in omit:
            properties.pop(field, None)
    if "required" in schema:
        dropped = set(omit) | set(optional)
        schema["required"] = [name for name in schema["required"] if name not in dropped]
    schema = _without_keys(schema, _COSMETIC_KEYS)  # type: ignore[assignment]
    schema.pop("title", None)
    return _prune_unreferenced_defs(schema)


_FIELD_TYPE_KEYS = frozenset({"title", "description", "default"})


def _field_type(model: type[BaseModel], field: str) -> object:
    """The JSON type of one field, stripped of naming/default cosmetics.

    Used for the Group-B type-drift check: two fields share a type when their
    property schemas match ignoring ``title`` (differs for the ``id`` ->
    ``roadmap_id`` rename), ``default``, and ``description``.
    """
    prop = model.model_json_schema().get("properties", {}).get(field, {})
    return _without_keys(prop, _FIELD_TYPE_KEYS)


# --------------------------------------------------------------------------- #
# Group A: field-for-field mirrors (assert JSON-Schema equal)                 #
# --------------------------------------------------------------------------- #
#
# Each tuple pairs a backend source type with its MCP mirror. Most share a name;
# the two renamed pairs (``RoadmapInput`` -> ``RoadmapDraftInput``) encode the
# spec's name map directly in the pairing. The patch-op *union* is asserted
# separately because it is an ``Annotated`` alias, not a class.

ASSERT_EQUAL: list[tuple[type, type]] = [
    # Shared enums.
    (backend.ResourceType, mcp.ResourceType),
    (backend.RoadmapStatus, mcp.RoadmapStatus),
    (backend.ChangedNodeKind, mcp.ChangedNodeKind),
    (backend.ChangeType, mcp.ChangeType),
    (backend_read_contract.ResponseFormat, mcp.ResponseFormat),
    (backend_read.SectionInclude, mcp.SectionInclude),
    (backend_read.SearchHitKind, mcp.SearchHitKind),
    (backend_progress.CompletionState, mcp.CompletionState),
    # Authoring inputs (RoadmapInput is name-mapped to RoadmapDraftInput).
    (backend.ResourceInput, mcp.ResourceInput),
    (backend.ChecklistItemInput, mcp.ChecklistItemInput),
    (backend.SubsectionInput, mcp.SubsectionInput),
    (backend.SectionInput, mcp.SectionInput),
    (backend.RoadmapInput, mcp.RoadmapDraftInput),
    # The 16 patch operations.
    (backend.AddSubsectionOp, mcp.AddSubsectionOp),
    (backend.UpdateSubsectionOp, mcp.UpdateSubsectionOp),
    (backend.RemoveSubsectionOp, mcp.RemoveSubsectionOp),
    (backend.AddEdgeOp, mcp.AddEdgeOp),
    (backend.RemoveEdgeOp, mcp.RemoveEdgeOp),
    (backend.SetTagsOp, mcp.SetTagsOp),
    (backend.SetResourcesOp, mcp.SetResourcesOp),
    (backend.SetEffortOp, mcp.SetEffortOp),
    (backend.AddItemOp, mcp.AddItemOp),
    (backend.UpdateItemOp, mcp.UpdateItemOp),
    (backend.RemoveItemOp, mcp.RemoveItemOp),
    (backend.ReorderOp, mcp.ReorderOp),
    (backend.SetSuggestedPathOp, mcp.SetSuggestedPathOp),
    (backend.AddSectionOp, mcp.AddSectionOp),
    (backend.UpdateSectionOp, mcp.UpdateSectionOp),
    (backend.RemoveSectionOp, mcp.RemoveSectionOp),
    # Changed-node echo (field-identical, so asserted equal rather than subset).
    (backend.ChangedNode, mcp.ChangedNode),
    # Structural-rule violation (ids is name-equal; the required delta is
    # allowlisted, so type drift on ids is still caught).
    (backend_errors.Violation, mcp.Violation),
    # Read projections (roadmaps).
    (backend_read.ResourceRef, mcp.ResourceRef),
    (backend_read.PrereqRef, mcp.PrereqRef),
    (backend_read.ItemState, mcp.ItemState),
    (backend_read.NodeDetail, mcp.NodeDetail),
    (backend_read.SectionOverview, mcp.SectionOverview),
    (backend_read.OverallProgress, mcp.OverallProgress),
    (backend_read.Overview, mcp.Overview),
    (backend_read.SectionPage, mcp.SectionPage),
    (backend_read.SearchHit, mcp.SearchHit),
    # Read projections (progress).
    (backend_progress.SectionProgress, mcp.SectionProgress),
    (backend_progress.ProgressSnapshot, mcp.ProgressSnapshot),
    (backend_progress.NextItem, mcp.NextItem),
    (backend_progress.NextResult, mcp.NextResult),
    (backend_progress.ResourceLink, mcp.ResourceLink),
    (backend_progress.ProgressUpdateResult, mcp.ProgressUpdateResult),
]

# The discriminated patch-op union, keyed by the ``op`` literal.
PATCH_OP_UNION: tuple[object, object] = (backend.PatchOp, mcp.PatchOp)

# Allowlist of deliberate Group-A divergences, keyed by MCP class name. Applied
# to the *backend* side (the stricter mirror) so it matches the current frozen
# MCP contract. Ticket 14 aligns these and removes the entries in the same slice.
INTENTIONAL_DELTAS: dict[str, dict[str, tuple[str, ...]]] = {
    # visibility is a web-only lifecycle control with no agent tool.
    "RoadmapDraftInput": {"omit": ("visibility",)},
    # ids is required on the backend but defaulted on the frozen MCP mirror. The
    # drift is latent (the backend always sends ids); aligning it is Ticket 14,
    # which also regenerates the MCP snapshot and drops this entry.
    "Violation": {"optional": ("ids",)},
}


def _delta_for(mcp_cls: type) -> dict[str, tuple[str, ...]]:
    return INTENTIONAL_DELTAS.get(mcp_cls.__name__, {})


@pytest.mark.parametrize(
    ("backend_cls", "mcp_cls"),
    ASSERT_EQUAL,
    ids=[f"{b.__name__}->{m.__name__}" for b, m in ASSERT_EQUAL],
)
def test_group_a_schemas_are_field_equal(backend_cls: type, mcp_cls: type) -> None:
    """Every Group-A mirror generates the same JSON Schema (minus allowed deltas)."""
    expected = _canonical(backend_cls, **_delta_for(mcp_cls))
    actual = _canonical(mcp_cls)
    assert actual == expected, (
        f"{mcp_cls.__name__} drifted from backend {backend_cls.__name__}. "
        "If deliberate, update the mirror and INTENTIONAL_DELTAS together."
    )


def test_patch_op_union_is_field_equal() -> None:
    """The 16-op discriminated ``PatchOp`` union mirrors the backend union."""
    backend_union, mcp_union = PATCH_OP_UNION
    assert _canonical(mcp_union) == _canonical(backend_union)


# --------------------------------------------------------------------------- #
# Group B: deliberately lean write results (assert MCP fields subset backend)  #
# --------------------------------------------------------------------------- #
#
# Each entry is (backend source, MCP lean result, intentional MCP-only fields).
# MCP write results expose the roadmap identity as ``roadmap_id``; in the fuller
# backend document that same value is the roadmap's ``id`` (consulted only when
# the MCP field has no same-named backend counterpart, since the backend's own
# lean PatchResult already calls it ``roadmap_id``).

WRITE_RESULT_RENAMES = {"roadmap_id": "id"}

LEAN_SUBSET: list[tuple[type[BaseModel], type[BaseModel], frozenset[str]]] = [
    (backend.RoadmapCreated, mcp.CreatedRoadmap, frozenset()),
    (backend.RoadmapReplaced, mcp.ReplacedRoadmap, frozenset()),
    (backend.PatchResult, mcp.PatchResult, frozenset()),
    # publishable is an MCP-only convenience (== violations is empty).
    (backend.ValidateResult, mcp.ValidationResult, frozenset({"publishable"})),
    (backend.Roadmap, mcp.PublishResult, frozenset()),
    # source_roadmap_id is injected by the fork tool, not returned by the backend.
    (backend.Roadmap, mcp.ForkResult, frozenset({"source_roadmap_id"})),
    (backend.Roadmap, mcp.MetadataResult, frozenset()),
]


@pytest.mark.parametrize(
    ("backend_cls", "mcp_cls", "mcp_only"),
    LEAN_SUBSET,
    ids=[f"{m.__name__}<-{b.__name__}" for b, m, _ in LEAN_SUBSET],
)
def test_group_b_mcp_fields_are_subset_of_backend(
    backend_cls: type[BaseModel], mcp_cls: type[BaseModel], mcp_only: frozenset[str]
) -> None:
    """Every MCP write-result field maps to a same-typed backend field.

    Guards against an accidental MCP-only field (unbacked by backend data) or a
    type drift on a shared field; the lean projection's smaller field set is
    intended, so no field-equality is asserted.
    """
    backend_fields = set(backend_cls.model_fields)
    for field in mcp_cls.model_fields:
        if field in mcp_only:
            continue
        mapped = field if field in backend_fields else WRITE_RESULT_RENAMES.get(field)
        assert mapped is not None, (
            f"{mcp_cls.__name__}.{field} has no backend counterpart in "
            f"{backend_cls.__name__} and is not an allowlisted MCP-only field."
        )
        assert _field_type(mcp_cls, field) == _field_type(backend_cls, mapped), (
            f"type drift: {mcp_cls.__name__}.{field} != {backend_cls.__name__}.{mapped}"
        )


# --------------------------------------------------------------------------- #
# Allowlist honesty + Group C completeness                                     #
# --------------------------------------------------------------------------- #

_GROUP_A_MCP_BY_NAME = {m.__name__: (b, m) for b, m in ASSERT_EQUAL}


@pytest.mark.parametrize("mcp_name", sorted(INTENTIONAL_DELTAS))
def test_intentional_deltas_are_load_bearing(mcp_name: str) -> None:
    """Each allowlist entry must describe a *real* divergence.

    Without the delta the pair must drift; otherwise the entry is stale (e.g.
    Ticket 14 aligned the field but forgot to drop the allowlist) and should be
    removed. Keeps the allowlist honest.
    """
    backend_cls, mcp_cls = _GROUP_A_MCP_BY_NAME[mcp_name]
    assert _canonical(mcp_cls) != _canonical(backend_cls), (
        f"INTENTIONAL_DELTAS['{mcp_name}'] no longer describes a divergence; "
        "the mirror matches without it, so drop the stale allowlist entry."
    )
    assert _canonical(mcp_cls) == _canonical(backend_cls, **INTENTIONAL_DELTAS[mcp_name])


# Group C: intentionally not mirrored. Documented here, never compared.
EXCLUDED_MCP_ONLY = frozenset({"SearchResults"})  # structured search-hit wrapper
EXCLUDED_BACKEND_ONLY = frozenset(
    {
        "Resource",
        "ChecklistItem",
        "Subsection",
        "Section",
        "Roadmap",  # the full domain model (Group B projects lean views of it)
        "Visibility",
        "VisibilityRequest",
        "PatchRequest",  # the operations=Field(min_length=1) wrapper; MCP takes the list
        "MetadataEditRequest",
        "Progress",
        "ProgressUpdateRequest",
        "DeadlineRequest",
    }
)


def _declared_contract_types(module: object) -> set[str]:
    """Names of the Pydantic models + enums declared in a schema module."""
    return {
        name
        for name, obj in inspect.getmembers(module)
        if inspect.isclass(obj)
        and obj.__module__ == module.__name__
        and issubclass(obj, (BaseModel, Enum))
    }


def test_every_mcp_type_is_classified() -> None:
    """No MCP schema type escapes the contract without a deliberate decision.

    Every model/enum in ``wren_mcp.schemas`` must be in Group A, Group B, or the
    documented Group-C exclusions. A newly added MCP type fails here until it is
    assigned a group.
    """
    classified = (
        {m.__name__ for _, m in ASSERT_EQUAL}
        | {m.__name__ for _, m, _ in LEAN_SUBSET}
        | EXCLUDED_MCP_ONLY
    )
    declared = _declared_contract_types(mcp)
    unclassified = declared - classified
    assert not unclassified, (
        f"unclassified MCP schema types: {sorted(unclassified)}. Add each to "
        "Group A (ASSERT_EQUAL), Group B (LEAN_SUBSET), or EXCLUDED_MCP_ONLY."
    )


def test_excluded_backend_only_types_have_no_mcp_mirror() -> None:
    """The documented backend-only exclusions are real and unmirrored."""
    backend_types = (
        _declared_contract_types(backend)
        | _declared_contract_types(backend_read)
        | _declared_contract_types(backend_progress)
    )
    mcp_types = _declared_contract_types(mcp)
    for name in EXCLUDED_BACKEND_ONLY:
        assert name in backend_types, f"{name} is no longer a backend type; update EXCLUDED."
        assert name not in mcp_types, f"{name} now has an MCP mirror; move it out of EXCLUDED."


def test_excluded_mcp_only_types_have_no_backend_mirror() -> None:
    """The documented MCP-only exclusions are real and unmirrored (symmetric guard)."""
    backend_types = (
        _declared_contract_types(backend)
        | _declared_contract_types(backend_read)
        | _declared_contract_types(backend_progress)
    )
    mcp_types = _declared_contract_types(mcp)
    for name in EXCLUDED_MCP_ONLY:
        assert name in mcp_types, f"{name} is no longer an MCP type; update EXCLUDED."
        assert name not in backend_types, (
            f"{name} now has a backend mirror; move it out of EXCLUDED."
        )
