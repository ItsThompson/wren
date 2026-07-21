"""Cross-package schema-mirror drift test.

``wren_mcp.schemas`` exposes the agent-facing contract for the MCP server, which
ships as a separate image with no backend-code dependency. This test can only
live in the dev/test-only ``contract`` project, the sole interpreter that imports
both ``wren.*`` and ``wren_mcp.*``.

The contract types fall into three groups, treated differently:

* **Group A** (shared enums, authoring inputs, the 16 ``*Op`` ops, ``ChangedNode``,
  ``Violation``, and the read projections) is GENERATED from the internal app's
  OpenAPI document into :mod:`wren_mcp._schemas_generated` (see ``just
  codegen-mcp``). Field equality with the backend is guaranteed by construction,
  so nothing is asserted field-by-field here. Instead
  :func:`test_generated_module_is_exactly_group_a` pins the generated set to
  :data:`EXPECTED_GROUP_A`, so a leaked domain type (over-inclusion) or a missing
  Group-A type (under-inclusion) fails.
* **Group B (:data:`LEAN_SUBSET`)** are hand-authored, deliberately lean write
  results. They diverge from the backend's fuller results, so we assert only that
  every MCP field maps to a backend field of the same JSON type (no MCP-only
  field, no type drift) rather than full equality.
* **Group C (:data:`EXCLUDED_MCP_ONLY` / :data:`EXCLUDED_BACKEND_ONLY`)** are not
  mirrored at all and are documented, never compared.

``visibility`` is dropped from the generated authoring input (a web-only lifecycle
control with no agent tool), which also prunes the orphaned ``Visibility`` enum:
:func:`test_excluded_backend_only_types_have_no_mcp_mirror` enforces that neither
appears anywhere in the MCP surface.
"""

from __future__ import annotations

import inspect
from enum import Enum

import pytest
from pydantic import BaseModel
from wren.accounts import schemas as backend_accounts
from wren.progress import schemas as backend_progress
from wren.roadmaps import read_schemas as backend_read
from wren.roadmaps import schemas as backend
from wren_mcp import _schemas_generated as mcp_generated
from wren_mcp import schemas as mcp

# --------------------------------------------------------------------------- #
# Type-drift helper (Group B)                                                 #
# --------------------------------------------------------------------------- #


def _without_keys(node: object, keys: frozenset[str]) -> object:
    """Recursively drop ``keys`` from every mapping in a JSON-Schema tree."""
    if isinstance(node, dict):
        return {k: _without_keys(v, keys) for k, v in node.items() if k not in keys}
    if isinstance(node, list):
        return [_without_keys(item, keys) for item in node]
    return node


_FIELD_TYPE_KEYS = frozenset({"title", "description", "default"})


def _field_type(model: type[BaseModel], field: str) -> object:
    """The JSON type of one field, stripped of naming/default cosmetics.

    Used for the Group-B type-drift check: two fields share a type when their
    property schemas match ignoring ``title`` (differs for the ``id`` ->
    ``roadmap_id`` rename), ``default``, and ``description``.
    """
    prop = model.model_json_schema().get("properties", {}).get(field, {})
    return _without_keys(prop, _FIELD_TYPE_KEYS)


def _declared_contract_types(module: object) -> set[str]:
    """Names of the Pydantic models + enums declared in a schema module."""
    return {
        name
        for name, obj in inspect.getmembers(module)
        if inspect.isclass(obj)
        and obj.__module__ == module.__name__
        and issubclass(obj, (BaseModel, Enum))
    }


def _mcp_contract_types() -> set[str]:
    """Every contract model/enum reachable through ``wren_mcp.schemas``.

    The generated Group-A types are re-exported through ``wren_mcp.schemas`` but
    their ``__module__`` is ``wren_mcp._schemas_generated``, so a check reading
    only ``wren_mcp.schemas`` would miss them. Union both modules to see the whole
    surface: the hand-authored Group B/C declared in ``schemas`` plus the generated
    Group A.
    """
    return _declared_contract_types(mcp) | _declared_contract_types(mcp_generated)


# --------------------------------------------------------------------------- #
# Group A: exactly the generated types (field equality is by construction)    #
# --------------------------------------------------------------------------- #
#
# EXPECTED_GROUP_A is the ~46 Group-A type names, maintained here BY HAND and
# declared INDEPENDENTLY of the generated module and of the generation-input
# allowlist (``mcp/scripts/build_generation_input.py``), so the equality assertion
# below is not tautological. A drift in either direction fails:
#   * over-inclusion (a leaked domain type such as Visibility, Roadmap, Section,
#     Subsection, Resource, or ChecklistItem) makes the generated set a superset;
#   * under-inclusion (a dropped Group-A type) makes it a subset.

EXPECTED_GROUP_A = frozenset(
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
        # Authoring inputs (RoadmapInput -> RoadmapDraftInput; no visibility field).
        "ResourceInput",
        "ChecklistItemInput",
        "SubsectionInput",
        "SectionInput",
        "RoadmapDraftInput",
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


def test_generated_module_is_exactly_group_a() -> None:
    """The generated module declares exactly the Group-A types: no more, no less.

    This is the concrete enforcement of the criterion that the generated module
    contains exactly Group A. Field equality is guaranteed by generation from the
    backend OpenAPI, so no per-field equality is asserted; this set equality plus
    the excluded-type symmetry guard below is what keeps the generated module free
    of leaked domain types (``Visibility``, the full ``Roadmap``, its nested types)
    and complete.
    """
    assert _declared_contract_types(mcp_generated) == EXPECTED_GROUP_A, (
        "generated Group-A set drifted from EXPECTED_GROUP_A. If deliberate, "
        "reconcile EXPECTED_GROUP_A and build_generation_input.GROUP_A_COMPONENTS."
    )


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
# Classification + Group C completeness                                        #
# --------------------------------------------------------------------------- #

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


def test_every_mcp_type_is_classified() -> None:
    """No MCP schema type escapes the contract without a deliberate decision.

    Every model/enum reachable through ``wren_mcp.schemas`` (the generated Group A
    plus the hand-authored Group B/C) must be in Group A, Group B, or the
    documented Group-C exclusions. A newly added MCP type fails here until it is
    assigned a group.
    """
    classified = EXPECTED_GROUP_A | {m.__name__ for _, m, _ in LEAN_SUBSET} | EXCLUDED_MCP_ONLY
    declared = _mcp_contract_types()
    unclassified = declared - classified
    assert not unclassified, (
        f"unclassified MCP schema types: {sorted(unclassified)}. Add each to "
        "Group A (EXPECTED_GROUP_A), Group B (LEAN_SUBSET), or EXCLUDED_MCP_ONLY."
    )


def test_excluded_backend_only_types_have_no_mcp_mirror() -> None:
    """The documented backend-only exclusions are real and unmirrored.

    Reads the whole MCP surface (generated Group A + hand-authored Group B/C), so a
    leaked domain type (for example ``Visibility`` or the full ``Roadmap``) in the
    generated module is caught here.
    """
    backend_types = (
        _declared_contract_types(backend)
        | _declared_contract_types(backend_read)
        | _declared_contract_types(backend_progress)
    )
    mcp_types = _mcp_contract_types()
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
    mcp_types = _mcp_contract_types()
    for name in EXCLUDED_MCP_ONLY:
        assert name in mcp_types, f"{name} is no longer an MCP type; update EXCLUDED."
        assert name not in backend_types, (
            f"{name} now has a backend mirror; move it out of EXCLUDED."
        )


# --------------------------------------------------------------------------- #
# Accounts wire contract: the onboarding flag                    #
# --------------------------------------------------------------------------- #
#
# ``AuthenticatedUser`` is the caller's own view returned by register/login/
# refresh (and the onboarding-complete endpoint). It is not an MCP mirror -- the
# resource server exposes no auth surface -- so it carries no Group-A/B/C entry
# above. This guards the one field onboarding adds to that wire schema,
# which flows to the frontend generated types via ``just codegen``.


def test_authenticated_user_carries_the_onboarding_flag() -> None:
    """``AuthenticatedUser`` exposes ``has_completed_onboarding`` as a required bool."""
    schema = backend_accounts.AuthenticatedUser.model_json_schema()
    prop = schema.get("properties", {}).get("has_completed_onboarding")
    assert prop is not None, "AuthenticatedUser must expose has_completed_onboarding."
    assert prop.get("type") == "boolean"
    assert "has_completed_onboarding" in schema.get("required", [])
