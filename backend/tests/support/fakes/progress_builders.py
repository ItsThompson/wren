"""Shared builders for the progress tests.

Constructs a realistic published :class:`Roadmap` (two sections, a prereq DAG,
and a ``suggested_path`` that is a valid topological order) plus the persisted
:class:`RoadmapRecord`, so the pure-module, service, and contract tests all
exercise the same shape. Keeping one builder here (rather than re-declaring the
nested literal per file) matches the testing-practices "factories over inline
objects" rule.
"""

from __future__ import annotations

from datetime import UTC, datetime

from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.schemas import (
    ChecklistItem,
    Resource,
    ResourceType,
    Roadmap,
    RoadmapStatus,
    Section,
    Subsection,
    Visibility,
)

_NOW = datetime(2026, 7, 15, tzinfo=UTC)

# The canonical progress fixture ids (referenced by assertions across the tests).
SUB_ARRAYS = "sub_arrays"
SUB_HASHING = "sub_hashing"
SUB_GRAPHS = "sub_graphs"
CHK_ARRAYS_READ = "chk_arrays-read"
CHK_ARRAYS_DRILL = "chk_arrays-drill"
CHK_HASH = "chk_hash"
CHK_GRAPHS = "chk_graphs"

ALL_ITEM_IDS = frozenset({CHK_ARRAYS_READ, CHK_ARRAYS_DRILL, CHK_HASH, CHK_GRAPHS})


def _subsection(
    sub_id: str,
    title: str,
    item_ids: list[str],
    *,
    prereq_ids: list[str],
    with_resource: bool = True,
) -> Subsection:
    resources: dict[str, Resource] = {}
    resource_order: list[str] = []
    if with_resource:
        resource_id = f"res_{sub_id}"
        resources[resource_id] = Resource(
            id=resource_id,
            title=f"{title} guide",
            url=f"https://x.test/{sub_id}",
            type=ResourceType.ARTICLE,
        )
        resource_order.append(resource_id)
    return Subsection(
        id=sub_id,
        title=title,
        prereq_ids=prereq_ids,
        resources=resources,
        resource_order=resource_order,
        checklist_items={item_id: ChecklistItem(id=item_id, text=item_id) for item_id in item_ids},
        item_order=list(item_ids),
    )


def build_roadmap(
    *,
    roadmap_id: str = "grokking-dsa-7f3k",
    owner: str = "owner",
    status: RoadmapStatus = RoadmapStatus.PUBLISHED,
    visibility: Visibility = Visibility.PUBLIC,
) -> Roadmap:
    """A two-section published roadmap with a prereq DAG and a valid path.

    ``suggested_path`` = [arrays, hashing, graphs]; hashing needs arrays, graphs
    needs hashing. Arrays has two items, the rest one each (four items total)."""
    foundations = Section(
        id="sec_foundations",
        title="Foundations",
        subsections={
            SUB_ARRAYS: _subsection(
                SUB_ARRAYS, "Arrays", [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL], prereq_ids=[]
            ),
            SUB_HASHING: _subsection(SUB_HASHING, "Hashing", [CHK_HASH], prereq_ids=[SUB_ARRAYS]),
        },
        subsection_order=[SUB_ARRAYS, SUB_HASHING],
    )
    advanced = Section(
        id="sec_advanced",
        title="Advanced",
        subsections={
            SUB_GRAPHS: _subsection(SUB_GRAPHS, "Graphs", [CHK_GRAPHS], prereq_ids=[SUB_HASHING]),
        },
        subsection_order=[SUB_GRAPHS],
    )
    return Roadmap(
        id=roadmap_id,
        owner=owner,
        title="Grokking DSA",
        subject_tags=["cs"],
        visibility=visibility,
        status=status,
        revision=1,
        sections={"sec_foundations": foundations, "sec_advanced": advanced},
        section_order=["sec_foundations", "sec_advanced"],
        suggested_path=[SUB_ARRAYS, SUB_HASHING, SUB_GRAPHS],
        created_at=_NOW,
        updated_at=_NOW,
    )


def make_record(roadmap: Roadmap) -> RoadmapRecord:
    """Serialize a roadmap into the persisted row the repository stores."""
    return RoadmapRecord(
        id=roadmap.id,
        owner=roadmap.owner,
        title=roadmap.title,
        status=roadmap.status.value,
        visibility=roadmap.visibility.value,
        revision=roadmap.revision,
        document=roadmap.model_dump(mode="json"),
        created_at=roadmap.created_at,
        updated_at=roadmap.updated_at,
    )
