"""RoadmapService business rules, through its public methods with an in-memory
repository and the real slugs + assembly deep modules (sociable, spec §13)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from progress_fakes import InMemoryProgressRepository
from roadmaps_fakes import (
    InMemoryRoadmapRepository,
    constant_follower_counter,
    sequence_token_factory,
)
from wren.core.errors import Conflict, ErrorCode, NotFound, Validation
from wren.progress.schemas import CompletionState
from wren.progress.service import ProgressService
from wren.roadmaps.schemas import (
    AddItemOp,
    AddSubsectionOp,
    ChecklistItemInput,
    ResourceInput,
    ResourceType,
    Roadmap,
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
    followers: int = 0,
) -> tuple[RoadmapService, InMemoryRoadmapRepository]:
    repo = repo or InMemoryRoadmapRepository()
    service = RoadmapService(
        repo,
        follower_counter=constant_follower_counter(followers),
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
        follower_counter=constant_follower_counter(),
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


async def test_patch_on_published_prefers_immutable_over_stale_revision() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    # Publish does not bump revision, so a published roadmap can still be targeted
    # with a stale If-Match: the immutability guard must win over the stale-revision
    # check (guard-before-revision precedence, since the guard loads before the
    # revision comparison).
    with pytest.raises(Conflict) as excinfo:
        await service.patch_draft(
            "user-1",
            created.id,
            created.revision + 5,  # stale, but immutability is checked first
            [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["x"])],
        )
    assert excinfo.value.code is ErrorCode.IMMUTABLE


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


async def test_replace_on_published_prefers_immutable_over_stale_revision() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    # Publish does not bump revision, so a published roadmap can still be targeted
    # with a stale If-Match: the immutability guard (loaded first) must win over the
    # stale-revision check, so this is 409 IMMUTABLE, never STALE_REVISION.
    with pytest.raises(Conflict) as excinfo:
        await service.replace_draft("user-1", created.id, created.revision + 5, _replace_doc())
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


# --- fork -------------------------------------------------------------------


async def _publish_public(repo: InMemoryRoadmapRepository, roadmap: Roadmap) -> None:
    """Persist ``roadmap`` as a published, public source (no visibility path yet,
    #15), mirroring what a real published-public roadmap looks like on disk. Uses
    the repository ``save`` seam, like the #13 archived-state simulation."""
    await repo.save(
        roadmap.model_copy(
            update={"status": RoadmapStatus.PUBLISHED, "visibility": Visibility.PUBLIC}
        )
    )


async def test_fork_creates_a_fresh_draft_owned_by_the_forker() -> None:
    service, _ = _service(tokens=["7f3k", "9x2b"])
    source = await service.create_draft("owner", _publishable_doc())
    fork = await service.fork("owner", source.id)
    # A brand-new roadmap ID (fresh slug + fresh random), not the source's.
    assert fork.id == "grokking-dsa-9x2b"
    assert fork.id != source.id
    assert fork.owner == "owner"
    assert fork.status is RoadmapStatus.DRAFT
    assert fork.visibility is Visibility.PRIVATE
    assert fork.revision == 1


async def test_fork_copies_content_and_persists_the_new_roadmap() -> None:
    service, repo = _service(tokens=["7f3k", "9x2b"])
    source = await service.create_draft("owner", _publishable_doc())
    fork = await service.fork("owner", source.id)
    # Content copied verbatim (same child IDs, uniqueness is within-roadmap).
    assert fork.section_order == source.section_order
    assert fork.suggested_path == source.suggested_path
    assert set(fork.sections["sec_foundations"].subsections) == {"sub_arrays"}
    # Persisted: a fresh read returns the fork owned by the forker.
    fetched = await service.get("owner", fork.id)
    assert fetched.id == fork.id
    assert repo.commits == 2


async def test_fork_leaves_the_source_untouched() -> None:
    service, _ = _service(tokens=["7f3k", "9x2b"])
    source = await service.create_draft("owner", _publishable_doc())
    await service.fork("owner", source.id)
    reread = await service.get("owner", source.id)
    assert reread.id == source.id
    assert reread.owner == "owner"
    assert reread.status is RoadmapStatus.DRAFT
    assert reread.revision == source.revision


async def test_fork_of_my_own_draft_succeeds() -> None:
    service, _ = _service(tokens=["7f3k", "9x2b"])
    source = await service.create_draft("owner", _publishable_doc())
    fork = await service.fork("owner", source.id)
    assert fork.status is RoadmapStatus.DRAFT
    assert fork.owner == "owner"


async def test_fork_of_a_public_roadmap_by_a_non_owner_succeeds() -> None:
    service, repo = _service(tokens=["7f3k", "9x2b"])
    source = await service.create_draft("author", _publishable_doc())
    await _publish_public(repo, source)
    # A different user forks the public roadmap: they own the fresh draft.
    fork = await service.fork("forker", source.id)
    assert fork.owner == "forker"
    assert fork.status is RoadmapStatus.DRAFT
    assert fork.visibility is Visibility.PRIVATE


async def test_fork_of_a_private_roadmap_i_do_not_own_is_404() -> None:
    service, _ = _service(tokens=["7f3k", "9x2b"])
    source = await service.create_draft("author", _publishable_doc())  # private draft
    with pytest.raises(NotFound):
        await service.fork("intruder", source.id)


async def test_fork_of_an_unknown_id_is_404() -> None:
    service, _ = _service()
    with pytest.raises(NotFound):
        await service.fork("user-1", "does-not-exist-0000")


async def test_fork_rolls_back_when_persistence_fails() -> None:
    service, repo = _service(tokens=["7f3k", "9x2b"])
    source = await service.create_draft("owner", _publishable_doc())

    async def failing_add(_record: object) -> None:
        raise RuntimeError("db down")

    repo.add = failing_add  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.fork("owner", source.id)
    assert repo.rollbacks == 1


async def test_fork_starts_with_fresh_progress_no_carry_over() -> None:
    # The gold no-carry-over proof: even though the fork copies checklist item IDs
    # verbatim, progress is keyed by (user, roadmap_id), so the forker's progress
    # on the source never bleeds into the fork.
    roadmap_repo = InMemoryRoadmapRepository()
    progress_repo = InMemoryProgressRepository()
    roadmaps = RoadmapService(
        roadmap_repo,
        follower_counter=progress_repo.count_followers,
        token_factory=sequence_token_factory(["7f3k", "9x2b"]),
        clock=lambda: _FIXED_NOW,
    )
    progress = ProgressService(roadmap_repo, progress_repo, clock=lambda: _FIXED_NOW)

    source = await roadmaps.create_draft("owner", _publishable_doc())
    await roadmaps.publish("owner", source.id)
    item_id = source.sections["sec_foundations"].subsections["sub_arrays"].item_order[0]
    # The owner checks an item on the source.
    await progress.update("owner", source.id, [item_id], CompletionState.COMPLETE)

    fork = await roadmaps.fork("owner", source.id)
    await roadmaps.publish("owner", fork.id)

    # The fork copied the same item ID verbatim...
    assert item_id in fork.sections["sec_foundations"].subsections["sub_arrays"].checklist_items
    # ...yet the forker starts the fork with zero checked items (fresh progress).
    fork_progress = await progress.get("owner", fork.id, detailed=True)
    assert fork_progress.checked_items == 0
    assert fork_progress.checked_ids == []
    # ...and the source progress is untouched (the item stays checked there).
    source_progress = await progress.get("owner", source.id, detailed=True)
    assert source_progress.checked_items == 1


# --- edit_metadata (presentation-only, published-mutable) --------------------


async def test_edit_metadata_changes_only_the_three_presentation_fields() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    edited = await service.edit_metadata(
        "user-1",
        created.id,
        title="Renamed",
        description="New blurb",
        subject_tags=["cs", "interview"],
    )
    assert edited.title == "Renamed"
    assert edited.description == "New blurb"
    assert edited.subject_tags == ["cs", "interview"]
    # Structure, visibility, and status are untouched.
    assert edited.sections == created.sections
    assert edited.section_order == created.section_order
    assert edited.suggested_path == created.suggested_path
    assert edited.visibility is created.visibility
    assert edited.status is RoadmapStatus.DRAFT


async def test_edit_metadata_works_on_a_published_roadmap() -> None:
    # The positive half of #13's deferred AC#4: edit_metadata SUCCEEDS on a
    # published roadmap while structural writes (patch/replace) are rejected 409.
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    edited = await service.edit_metadata(
        "user-1", created.id, title="Renamed live", description=None, subject_tags=None
    )
    assert edited.title == "Renamed live"
    # Still published (a presentation edit is not a lifecycle change).
    assert edited.status is RoadmapStatus.PUBLISHED


async def test_edit_metadata_does_not_bump_the_revision() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    edited = await service.edit_metadata(
        "user-1", created.id, title="Renamed", description=None, subject_tags=None
    )
    assert edited.revision == created.revision
    # Persisted without a revision bump (last-write-wins, no If-Match).
    assert (await service.get("user-1", created.id)).revision == created.revision


async def test_edit_metadata_leaves_unprovided_fields_unchanged() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    # Only the title is provided; description/subject_tags (None) are unchanged.
    edited = await service.edit_metadata(
        "user-1", created.id, title="Only title", description=None, subject_tags=None
    )
    assert edited.title == "Only title"
    assert edited.description == created.description
    assert edited.subject_tags == created.subject_tags


async def test_edit_metadata_can_edit_only_subject_tags_leaving_the_title() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    # No title/description provided (None): only subject_tags changes.
    edited = await service.edit_metadata(
        "user-1", created.id, title=None, description=None, subject_tags=["cs"]
    )
    assert edited.title == created.title
    assert edited.description == created.description
    assert edited.subject_tags == ["cs"]


async def test_edit_metadata_is_404_for_a_non_owner() -> None:
    service, _ = _service()
    created = await service.create_draft("owner", _publishable_doc())
    with pytest.raises(NotFound):
        await service.edit_metadata(
            "intruder", created.id, title="Hijack", description=None, subject_tags=None
        )


async def test_edit_metadata_rolls_back_when_persistence_fails() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())

    async def failing_save(_roadmap: object) -> None:
        raise RuntimeError("db down")

    repo.save = failing_save  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.edit_metadata(
            "user-1", created.id, title="Renamed", description=None, subject_tags=None
        )
    assert repo.rollbacks == 1


# --- replace preserves the stored visibility (#13 review item) --------------


async def test_replace_preserves_the_stored_drafts_visibility() -> None:
    # A full-document import replaces content but must NOT silently flip the
    # draft's visibility: visibility is a web-only lifecycle toggle, not part of
    # the imported document's authority (#13 review; spec sections 04/06).
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    # Make the draft public via the sanctioned lifecycle path.
    await service.set_visibility("user-1", created.id, Visibility.PUBLIC)
    # _replace_doc() defaults to visibility=private; the replace must ignore it.
    replaced = await service.replace_draft("user-1", created.id, created.revision, _replace_doc())
    assert replaced.visibility is Visibility.PUBLIC
    # And it is persisted public, not reset to the imported doc's private default.
    assert (await service.get("user-1", created.id)).visibility is Visibility.PUBLIC


# --- web-only lifecycle: set_visibility -------------------------------------


async def test_set_visibility_toggles_public_and_back_to_private() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    assert created.visibility is Visibility.PRIVATE

    made_public = await service.set_visibility("user-1", created.id, Visibility.PUBLIC)
    assert made_public.visibility is Visibility.PUBLIC
    assert (await service.get("user-1", created.id)).visibility is Visibility.PUBLIC

    made_private = await service.set_visibility("user-1", created.id, Visibility.PRIVATE)
    assert made_private.visibility is Visibility.PRIVATE
    assert (await service.get("user-1", created.id)).visibility is Visibility.PRIVATE


async def test_set_visibility_does_not_alter_content_or_the_revision() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    toggled = await service.set_visibility("user-1", created.id, Visibility.PUBLIC)
    # Structure and the structural revision are untouched by a visibility toggle.
    assert toggled.sections == created.sections
    assert toggled.section_order == created.section_order
    assert toggled.suggested_path == created.suggested_path
    assert toggled.revision == created.revision
    assert (await service.get("user-1", created.id)).revision == created.revision


async def test_set_visibility_works_on_a_published_roadmap() -> None:
    # Visibility is a lifecycle field editable on any status: a published roadmap
    # can still be toggled public/private (it governs discovery, not structure).
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    toggled = await service.set_visibility("user-1", created.id, Visibility.PUBLIC)
    assert toggled.visibility is Visibility.PUBLIC
    assert toggled.status is RoadmapStatus.PUBLISHED


async def test_set_visibility_is_404_for_a_non_owner() -> None:
    service, _ = _service()
    created = await service.create_draft("owner", _publishable_doc())
    with pytest.raises(NotFound):
        await service.set_visibility("intruder", created.id, Visibility.PUBLIC)


async def test_set_visibility_rolls_back_when_persistence_fails() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())

    async def failing_save(_roadmap: object) -> None:
        raise RuntimeError("db down")

    repo.save = failing_save  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.set_visibility("user-1", created.id, Visibility.PUBLIC)
    assert repo.rollbacks == 1


# --- web-only lifecycle: archive --------------------------------------------


async def test_archive_transitions_a_published_roadmap_to_archived() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    archived = await service.archive("user-1", created.id)
    assert archived.status is RoadmapStatus.ARCHIVED
    assert (await service.get("user-1", created.id)).status is RoadmapStatus.ARCHIVED


async def test_archive_a_draft_is_a_conflict() -> None:
    # The lifecycle is linear (draft -> published -> archived): a draft is deleted,
    # not archived, so archiving one is a 409.
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    with pytest.raises(Conflict):
        await service.archive("user-1", created.id)
    assert (await service.get("user-1", created.id)).status is RoadmapStatus.DRAFT


async def test_archive_an_already_archived_roadmap_is_a_conflict() -> None:
    service, _ = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    await service.archive("user-1", created.id)
    with pytest.raises(Conflict):
        await service.archive("user-1", created.id)


async def test_archive_is_404_for_a_non_owner() -> None:
    service, _ = _service()
    created = await service.create_draft("owner", _publishable_doc())
    await service.publish("owner", created.id)
    with pytest.raises(NotFound):
        await service.archive("intruder", created.id)


async def test_archive_rolls_back_when_persistence_fails() -> None:
    service, repo = _service()
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)

    async def failing_save(_roadmap: object) -> None:
        raise RuntimeError("db down")

    repo.save = failing_save  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.archive("user-1", created.id)
    assert repo.rollbacks == 1


# --- web-only lifecycle: delete (zero-followers guard) ----------------------


async def test_delete_removes_a_roadmap_with_zero_followers() -> None:
    service, repo = _service(followers=0)
    created = await service.create_draft("user-1", _publishable_doc())
    await service.delete("user-1", created.id)
    # The row is gone: a subsequent read is a 404.
    assert await repo.get(created.id) is None
    with pytest.raises(NotFound):
        await service.get("user-1", created.id)


async def test_delete_with_followers_is_a_409_and_keeps_the_roadmap() -> None:
    service, repo = _service(followers=3)
    created = await service.create_draft("user-1", _publishable_doc())
    await service.publish("user-1", created.id)
    with pytest.raises(Conflict) as excinfo:
        await service.delete("user-1", created.id)
    assert excinfo.value.code is ErrorCode.DELETE_HAS_FOLLOWERS
    assert "archive" in excinfo.value.detail.lower()
    # Not deleted: still readable by the owner.
    assert await repo.get(created.id) is not None


async def test_delete_is_404_for_a_non_owner() -> None:
    service, repo = _service(followers=0)
    created = await service.create_draft("owner", _publishable_doc())
    with pytest.raises(NotFound):
        await service.delete("intruder", created.id)
    # A non-owner delete never removes the row (owner-scoped, no existence leak).
    assert await repo.get(created.id) is not None


async def test_delete_rolls_back_when_persistence_fails() -> None:
    service, repo = _service(followers=0)
    created = await service.create_draft("user-1", _publishable_doc())

    async def failing_delete(_roadmap_id: str) -> None:
        raise RuntimeError("db down")

    repo.delete = failing_delete  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.delete("user-1", created.id)
    assert repo.rollbacks == 1


async def test_delete_guard_reads_a_real_follower_count() -> None:
    # The sociable proof: the delete guard reads the actual progress-row count via
    # the injected counter, so a published roadmap with a real follower is blocked
    # while the same roadmap with none is deletable.
    roadmap_repo = InMemoryRoadmapRepository()
    progress_repo = InMemoryProgressRepository()
    roadmaps = RoadmapService(
        roadmap_repo,
        follower_counter=progress_repo.count_followers,
        token_factory=sequence_token_factory(["7f3k", "9x2b"]),
        clock=lambda: _FIXED_NOW,
    )
    progress = ProgressService(roadmap_repo, progress_repo, clock=lambda: _FIXED_NOW)

    source = await roadmaps.create_draft("owner", _publishable_doc())
    await roadmaps.publish("owner", source.id)
    # Public so a different user can reach and follow it.
    await roadmaps.set_visibility("owner", source.id, Visibility.PUBLIC)
    # A different user follows it: the delete guard now sees one follower.
    await progress.follow("follower", source.id)
    with pytest.raises(Conflict) as excinfo:
        await roadmaps.delete("owner", source.id)
    assert excinfo.value.code is ErrorCode.DELETE_HAS_FOLLOWERS

    # A second, unfollowed roadmap by the same owner deletes cleanly.
    other = await roadmaps.create_draft("owner", _publishable_doc("Untouched Path"))
    await roadmaps.delete("owner", other.id)
    assert await roadmap_repo.get(other.id) is None
