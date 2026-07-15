"""RoadmapService business rules, through its public methods with an in-memory
repository and the real slugs + assembly deep modules (sociable, spec §13)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from roadmaps_fakes import InMemoryRoadmapRepository, sequence_token_factory
from wren.core.errors import NotFound
from wren.roadmaps.schemas import (
    ChecklistItemInput,
    ResourceInput,
    ResourceType,
    RoadmapInput,
    RoadmapStatus,
    SectionInput,
    SubsectionInput,
    Visibility,
)
from wren.roadmaps.service import RoadmapService

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
