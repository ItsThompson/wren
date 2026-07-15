"""RoadmapService business rules, through its public methods with an in-memory
repository and the real slugs + assembly deep modules (sociable, spec §13)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from roadmaps_fakes import InMemoryRoadmapRepository, sequence_token_factory
from wren.core.errors import Conflict, ErrorCode, NotFound, Validation
from wren.roadmaps.schemas import (
    AddItemOp,
    AddSubsectionOp,
    ChecklistItemInput,
    ResourceInput,
    ResourceType,
    RoadmapInput,
    RoadmapStatus,
    SectionInput,
    SetTagsOp,
    SubsectionInput,
    Visibility,
)
from wren.roadmaps.service import RoadmapService
from wren.roadmaps.validation import StructuralRule

_FIXED_NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _service(
    repo: InMemoryRoadmapRepository | None = None,
    *,
    tokens: list[str] | None = None,
) -> tuple[RoadmapService, InMemoryRoadmapRepository]:
    repo = repo or InMemoryRoadmapRepository()
    service = RoadmapService(
        repo,
        token_factory=sequence_token_factory(tokens or ["7f3k", "9x2b", "abcd"]),
        clock=lambda: _FIXED_NOW,
    )
    return service, repo


def _minimal_doc(title: str = "Grokking DSA") -> RoadmapInput:
    return RoadmapInput(
        title=title,
        sections=[
            SectionInput(
                title="Foundations",
                subsections=[
                    SubsectionInput(
                        title="Arrays",
                        resources=[
                            ResourceInput(
                                title="Guide", url="https://x.test", type=ResourceType.ARTICLE
                            )
                        ],
                        checklist_items=[ChecklistItemInput(text="Read it")],
                    )
                ],
            )
        ],
    )


def _publishable_doc(title: str = "Grokking DSA") -> RoadmapInput:
    """A draft that satisfies the minimal structural contract: one non-empty
    section/subsection with a resource + item, and a present suggested_path."""
    doc = _minimal_doc(title)
    doc.sections[0].subsections[0].proposed_id = "sub_arrays"
    doc.suggested_path = ["sub_arrays"]
    return doc


def _replace_doc(title: str = "Grokking DSA v2") -> RoadmapInput:
    """A full-document import: one subsection carries a ``proposed_id`` (preserved),
    a second omits it (re-minted from its title)."""
    return RoadmapInput(
        title=title,
        sections=[
            SectionInput(
                proposed_id="sec_core",
                title="Core",
                subsections=[
                    SubsectionInput(
                        proposed_id="sub_arrays",
                        title="Arrays",
                        resources=[
                            ResourceInput(
                                title="Guide", url="https://x.test", type=ResourceType.ARTICLE
                            )
                        ],
                        checklist_items=[ChecklistItemInput(text="Read it")],
                    ),
                    SubsectionInput(
                        title="Graphs",  # no proposed_id -> re-minted to sub_graphs
                        prereq_ids=["sub_arrays"],
                        resources=[
                            ResourceInput(
                                title="G", url="https://x.test", type=ResourceType.ARTICLE
                            )
                        ],
                        checklist_items=[ChecklistItemInput(text="Do it")],
                    ),
                ],
            )
        ],
        suggested_path=["sub_arrays", "sub_graphs"],
    )


async def test_create_draft_mints_a_title_slug_random_id() -> None:
    service, repo = _service(tokens=["7f3k"])
    created = await service.create_draft("user-1", _minimal_doc())
    assert created.id == "grokking-dsa-7f3k"
    assert repo.commits == 1


async def test_create_draft_is_draft_revision_1_private() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _minimal_doc())
    assert created.status is RoadmapStatus.DRAFT
    assert created.revision == 1
    assert created.visibility is Visibility.PRIVATE
    assert created.owner == "user-1"


async def test_create_draft_mints_prefixed_child_ids() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _minimal_doc())
    section = created.sections["sec_foundations"]
    subsection = section.subsections["sub_arrays"]
    assert subsection.resource_order[0].startswith("res_")
    assert subsection.item_order[0].startswith("chk_")


async def test_create_draft_echoes_a_remap_for_deduped_proposals() -> None:
    doc = RoadmapInput(
        title="DSA",
        sections=[
            SectionInput(
                title="Basics",
                subsections=[
                    SubsectionInput(
                        proposed_id="sub_arrays",
                        title="Arrays",
                        resources=[
                            ResourceInput(
                                title="G", url="https://x.test", type=ResourceType.ARTICLE
                            )
                        ],
                        checklist_items=[ChecklistItemInput(text="x")],
                    ),
                    SubsectionInput(
                        proposed_id="sub_arrays",
                        title="Arrays again",
                        resources=[
                            ResourceInput(
                                title="G", url="https://x.test", type=ResourceType.ARTICLE
                            )
                        ],
                        checklist_items=[ChecklistItemInput(text="y")],
                    ),
                ],
            )
        ],
    )
    service, _ = _service()
    created = await service.create_draft("user-1", doc)
    assert created.remap == {"sub_arrays": "sub_arrays-2"}


async def test_create_draft_remap_is_empty_when_nothing_deduped() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _minimal_doc())
    assert created.remap == {}


async def test_roadmap_id_collision_silently_re_rolls_the_token() -> None:
    # Seed the repo so the first minted candidate already exists; the service must
    # re-roll to the next token with no client-visible sequential increment.
    service, repo = _service(tokens=["7f3k", "9x2b"])
    first = await service.create_draft("user-1", _minimal_doc())
    assert first.id == "grokking-dsa-7f3k"

    # A second create with the same title: first token collides, re-rolls to 9x2b.
    service2 = RoadmapService(
        repo,
        token_factory=sequence_token_factory(["7f3k", "9x2b"]),
        clock=lambda: _FIXED_NOW,
    )
    second = await service2.create_draft("user-1", _minimal_doc())
    assert second.id == "grokking-dsa-9x2b"
    # No sequential "-2" leak: the re-roll is a fresh random token.
    assert "-2" not in second.id.removeprefix("grokking-dsa")


async def test_proposed_roadmap_id_is_used_as_the_slug_base() -> None:
    service, _ = _service(tokens=["7f3k"])
    doc = _minimal_doc()
    doc.proposed_id = "my-custom-name"
    created = await service.create_draft("user-1", doc)
    # The proposed base is honored, but a fresh random token still guarantees
    # global uniqueness and no existence leak.
    assert created.id == "my-custom-name-7f3k"


async def test_get_returns_the_owners_roadmap() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _minimal_doc())
    fetched = await service.get("user-1", created.id)
    assert fetched.id == created.id
    assert fetched.title == created.title
    assert fetched.status is RoadmapStatus.DRAFT


async def test_get_is_404_for_a_non_owner() -> None:
    service, _ = _service()
    created = await service.create_draft("owner", _minimal_doc())
    with pytest.raises(NotFound):
        await service.get("intruder", created.id)


async def test_get_is_404_for_an_unknown_id() -> None:
    service, _ = _service()
    with pytest.raises(NotFound):
        await service.get("user-1", "does-not-exist-0000")


async def test_create_rolls_back_when_persistence_fails() -> None:
    # A PK collision at insert (the fake mirrors the real unique violation) must
    # roll back and propagate rather than commit a half-written row.
    service, repo = _service(tokens=["7f3k", "7f3k"])
    await service.create_draft("user-1", _minimal_doc())

    # Force the pre-check to miss so add() is reached with a colliding id: reuse
    # the same token but bypass the existence check by clearing it.
    from sqlalchemy.exc import IntegrityError

    async def always_absent(_roadmap_id: str) -> bool:
        return False

    repo.roadmap_id_exists = always_absent  # type: ignore[method-assign]
    service2 = _service(repo, tokens=["7f3k"])[0]
    with pytest.raises(IntegrityError):
        await service2.create_draft("user-1", _minimal_doc())
    assert repo.rollbacks == 1


# --- validate ---------------------------------------------------------------


async def test_validate_returns_no_violations_for_a_publishable_draft() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    violations = await service.validate("user-1", created.id)
    assert violations == []
    # Validate never mutates: no extra commit beyond the create.
    assert repo.commits == 1


async def test_validate_returns_violations_for_an_incomplete_draft() -> None:
    # The minimal doc omits suggested_path, so the minimal V3 gate fires.
    service, _ = _service()
    created = await service.create_draft("user-1", _minimal_doc())
    violations = await service.validate("user-1", created.id)
    assert [v.rule for v in violations] == [StructuralRule.V3_PATH_COVERAGE]
    # Still a draft afterwards (validate is read-only).
    assert (await service.get("user-1", created.id)).status is RoadmapStatus.DRAFT


async def test_validate_is_404_for_a_non_owner() -> None:
    service, _ = _service()
    created = await service.create_draft("owner", _publishable_doc())
    with pytest.raises(NotFound):
        await service.validate("intruder", created.id)


async def test_validate_is_a_conflict_on_a_published_roadmap() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    with pytest.raises(Conflict):
        await service.validate("user-1", created.id)


# --- publish ----------------------------------------------------------------


async def test_publish_transitions_a_valid_draft_to_published() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    published = await service.publish("user-1", created.id)
    assert published.status is RoadmapStatus.PUBLISHED
    assert published.id == created.id
    # Persisted: a fresh read reflects the transition, and publish committed once.
    assert (await service.get("user-1", created.id)).status is RoadmapStatus.PUBLISHED
    assert repo.commits == 2


async def test_publish_hard_blocks_on_violations_and_keeps_the_draft() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _minimal_doc())  # no suggested_path
    with pytest.raises(Validation) as excinfo:
        await service.publish("user-1", created.id)
    assert [v.rule for v in excinfo.value.violations] == [StructuralRule.V3_PATH_COVERAGE]
    # No transition and no commit for the blocked publish.
    assert (await service.get("user-1", created.id)).status is RoadmapStatus.DRAFT
    assert repo.commits == 1


async def test_publish_is_404_for_a_non_owner() -> None:
    service, _ = _service()
    created = await service.create_draft("owner", _publishable_doc())
    with pytest.raises(NotFound):
        await service.publish("intruder", created.id)


async def test_publish_is_one_way_republish_is_a_conflict() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    # A published roadmap is immutable: re-publishing is refused (draft-only guard).
    with pytest.raises(Conflict):
        await service.publish("user-1", created.id)


async def test_publish_rolls_back_when_the_transition_fails_to_persist() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())

    async def failing_save(_roadmap: object) -> None:
        raise RuntimeError("db down")

    repo.save = failing_save  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.publish("user-1", created.id)
    assert repo.rollbacks == 1


async def test_publish_hard_block_message_is_singular_for_one_violation() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _minimal_doc())  # exactly one V3 violation
    with pytest.raises(Validation) as excinfo:
        await service.publish("user-1", created.id)
    assert excinfo.value.detail == "1 structural rule failed."


# --- patch ------------------------------------------------------------------


async def test_patch_applies_ops_bumps_revision_and_persists() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    result = await service.patch_draft(
        "user-1",
        created.id,
        created.revision,
        [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["core"])],
    )
    assert result.roadmap_id == created.id
    assert result.revision == created.revision + 1
    # Persisted: a fresh read reflects the edit and the bumped revision.
    fetched = await service.get("user-1", created.id)
    assert fetched.revision == created.revision + 1
    assert fetched.sections["sec_foundations"].subsections["sub_arrays"].tags == ["core"]
    assert repo.commits == 2


async def test_patch_echoes_only_changed_nodes() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    result = await service.patch_draft(
        "user-1",
        created.id,
        created.revision,
        [
            AddItemOp(
                op="add_item", subsection_id="sub_arrays", text="Extra", proposed_id="chk_extra"
            )
        ],
    )
    assert [(node.kind.value, node.id, node.change.value) for node in result.changed_nodes] == [
        ("item", "chk_extra", "added")
    ]


async def test_patch_returns_a_remap_for_a_deduped_proposed_id() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    add = AddSubsectionOp(
        op="add_subsection",
        section_id="sec_foundations",
        subsection=SubsectionInput(
            proposed_id="sub_arrays",  # collides with the existing subsection
            title="Arrays II",
            resources=[ResourceInput(title="G", url="https://x.test", type=ResourceType.ARTICLE)],
            checklist_items=[ChecklistItemInput(text="x")],
        ),
    )
    result = await service.patch_draft("user-1", created.id, created.revision, [add])
    assert result.remap == {"sub_arrays": "sub_arrays-2"}


async def test_patch_with_a_stale_revision_is_a_stale_revision_conflict() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    with pytest.raises(Conflict) as excinfo:
        await service.patch_draft(
            "user-1",
            created.id,
            created.revision + 5,  # stale
            [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["x"])],
        )
    assert excinfo.value.code is ErrorCode.STALE_REVISION
    assert "re-read" in excinfo.value.detail.lower()
    # Nothing persisted on the stale write.
    assert repo.commits == 1


async def test_patch_is_404_for_a_non_owner() -> None:
    service, _ = _service()
    created = await service.create_draft("owner", _publishable_doc())
    with pytest.raises(NotFound):
        await service.patch_draft(
            "intruder",
            created.id,
            created.revision,
            [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["x"])],
        )


async def test_patch_on_a_published_roadmap_is_an_immutability_conflict() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    with pytest.raises(Conflict) as excinfo:
        await service.patch_draft(
            "user-1",
            created.id,
            created.revision,
            [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["x"])],
        )
    # A structural write against published content is the immutability boundary
    # (spec section 05): a distinct 409 IMMUTABLE pointing to fork-to-change.
    assert excinfo.value.code is ErrorCode.IMMUTABLE
    assert "fork" in excinfo.value.detail.lower()


async def test_patch_with_an_invalid_op_is_a_field_level_validation_error() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    with pytest.raises(Validation) as excinfo:
        await service.patch_draft(
            "user-1",
            created.id,
            created.revision,
            [SetTagsOp(op="set_tags", subsection_id="sub_ghost", tags=["x"])],
        )
    assert excinfo.value.fields is not None
    field, message = next(iter(excinfo.value.fields.items()))
    assert field == "operations[0].subsection_id"
    assert "sub_arrays" in message  # names the valid sibling
    # Atomic: the failed batch persisted nothing.
    assert repo.commits == 1
    assert (await service.get("user-1", created.id)).revision == created.revision


async def test_patch_rolls_back_when_persistence_fails() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())

    async def failing_save(_roadmap: object) -> None:
        raise RuntimeError("db down")

    repo.save = failing_save  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.patch_draft(
            "user-1",
            created.id,
            created.revision,
            [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["x"])],
        )
    assert repo.rollbacks == 1


# --- replace (full-document import escape hatch) -----------------------------


async def test_replace_rebuilds_the_draft_preserving_proposed_ids_and_reminting_rest() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())

    replaced = await service.replace_draft("user-1", created.id, created.revision, _replace_doc())

    # The roadmap ID (route param) is unchanged; the title comes from the import.
    assert replaced.id == created.id
    assert replaced.title == "Grokking DSA v2"
    core = replaced.sections["sec_core"]
    # proposed_ids preserved; the node without one is re-minted from its title.
    assert core.subsection_order == ["sub_arrays", "sub_graphs"]
    # References resolve to the final IDs, and the whole document was rebuilt.
    assert core.subsections["sub_graphs"].prereq_ids == ["sub_arrays"]
    assert replaced.suggested_path == ["sub_arrays", "sub_graphs"]
    assert replaced.remap == {}


async def test_replace_keeps_the_roadmap_id_and_bumps_the_revision() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())

    replaced = await service.replace_draft("user-1", created.id, created.revision, _replace_doc())

    assert replaced.revision == created.revision + 1
    # Persisted: a fresh read reflects the imported content and the bumped revision.
    fetched = await service.get("user-1", created.id)
    assert fetched.revision == created.revision + 1
    assert fetched.title == "Grokking DSA v2"
    assert "sub_graphs" in fetched.sections["sec_core"].subsections
    assert repo.commits == 2


async def test_replace_preserves_created_at_and_stays_a_draft() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    original_created_at = (await service.get("user-1", created.id)).created_at

    replaced = await service.replace_draft("user-1", created.id, created.revision, _replace_doc())

    assert replaced.created_at == original_created_at
    assert replaced.status is RoadmapStatus.DRAFT
    assert replaced.owner == "user-1"


async def test_replace_returns_a_remap_for_a_deduped_proposed_id() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    doc = _replace_doc()
    # Re-slugified/bare proposal: "arrays" normalizes to the prefixed "sub_arrays".
    doc.sections[0].subsections[0].proposed_id = "arrays"
    doc.sections[0].subsections[1].prereq_ids = ["arrays"]
    doc.suggested_path = ["arrays", "sub_graphs"]

    replaced = await service.replace_draft("user-1", created.id, created.revision, doc)

    assert replaced.remap == {"arrays": "sub_arrays"}
    # The de-duped reference was reconciled to the final minted ID.
    assert replaced.sections["sec_core"].subsections["sub_graphs"].prereq_ids == ["sub_arrays"]
    assert replaced.suggested_path == ["sub_arrays", "sub_graphs"]


async def test_replace_on_a_published_roadmap_is_an_immutability_conflict() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    commits_before = repo.commits
    with pytest.raises(Conflict) as excinfo:
        await service.replace_draft("user-1", created.id, created.revision, _replace_doc())
    assert excinfo.value.code is ErrorCode.IMMUTABLE
    assert "fork" in excinfo.value.detail.lower()
    # Rejected before any write: nothing persisted.
    assert repo.commits == commits_before


async def test_replace_on_an_archived_roadmap_is_an_immutability_conflict() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    # No archive path yet (#15); simulate the persisted archived state via the repo.
    await repo.save(created.model_copy(update={"status": RoadmapStatus.ARCHIVED}))
    with pytest.raises(Conflict) as excinfo:
        await service.replace_draft("user-1", created.id, created.revision, _replace_doc())
    assert excinfo.value.code is ErrorCode.IMMUTABLE


async def test_replace_is_404_for_a_non_owner() -> None:
    service, _ = _service()
    created = await service.create_draft("owner", _publishable_doc())
    with pytest.raises(NotFound):
        await service.replace_draft("intruder", created.id, created.revision, _replace_doc())


async def test_replace_with_a_stale_revision_is_a_stale_revision_conflict() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    with pytest.raises(Conflict) as excinfo:
        await service.replace_draft("user-1", created.id, created.revision + 5, _replace_doc())
    assert excinfo.value.code is ErrorCode.STALE_REVISION
    assert "re-read" in excinfo.value.detail.lower()
    # Nothing persisted on the stale import.
    assert repo.commits == 1
    assert (await service.get("user-1", created.id)).revision == created.revision


async def test_replace_rolls_back_when_persistence_fails() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())

    async def failing_save(_roadmap: object) -> None:
        raise RuntimeError("db down")

    repo.save = failing_save  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.replace_draft("user-1", created.id, created.revision, _replace_doc())
    assert repo.rollbacks == 1
