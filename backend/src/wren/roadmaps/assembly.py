"""``assembly``: pure authoring-input -> persisted-roadmap transformation.

Turns a :class:`RoadmapInput` (ordered arrays, optional ``proposed_id``s) into a
:class:`Roadmap` (ID-keyed maps + ``*_order`` arrays) with every node's slug ID
minted (spec section 04). No I/O: the globally-unique roadmap ID is passed in
already resolved by the service (its collision check needs the database), so this
module stays a pure, exhaustively-testable deep function.

Two passes: first mint every child ID (so a ``prereq_id`` may reference a
subsection declared later in the payload), then build the nested objects,
resolving ``prereq_ids`` and ``suggested_path`` from the authors' ``proposed_id``s
to the final minted IDs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from wren.roadmaps import slugs
from wren.roadmaps.config import (
    CHECKLIST_PREFIX,
    RESOURCE_PREFIX,
    SECTION_PREFIX,
    SUBSECTION_PREFIX,
)
from wren.roadmaps.schemas import (
    ChecklistItem,
    ChecklistItemInput,
    Resource,
    ResourceInput,
    Roadmap,
    RoadmapInput,
    RoadmapStatus,
    Section,
    SectionInput,
    Subsection,
    SubsectionInput,
)

# An author's ``proposed_id`` -> the final minted ID, leaving unknown references
# unchanged (a dangling reference is caught later at publish, not here).
_ReferenceResolver = Callable[[str], str]


@dataclass(frozen=True)
class AssembledDraft:
    """The minted roadmap plus the ``proposed_id -> minted_id`` remap of every
    de-duped proposal (empty when nothing was changed)."""

    roadmap: Roadmap
    remap: dict[str, str]


@dataclass(frozen=True)
class _MintedSub:
    id: str
    source: SubsectionInput
    resources: list[tuple[str, ResourceInput]]
    items: list[tuple[str, ChecklistItemInput]]


@dataclass(frozen=True)
class _MintedSection:
    id: str
    source: SectionInput
    subsections: list[_MintedSub]


def assemble_draft(
    doc: RoadmapInput, roadmap_id: str, owner: str, *, now: datetime
) -> AssembledDraft:
    """Build the persisted draft roadmap from authoring input.

    ``roadmap_id`` is the already-minted, globally-unique ID; ``owner`` is the
    resolved session user. The result is a ``draft`` at ``revision`` 1.
    """
    minter = _Minter()
    minted_sections = [minter.section(section) for section in doc.sections]
    resolve = minter.reference_resolver()

    sections: dict[str, Section] = {}
    section_order: list[str] = []
    for minted_section in minted_sections:
        sections[minted_section.id] = _build_section(minted_section, resolve)
        section_order.append(minted_section.id)

    roadmap = Roadmap(
        id=roadmap_id,
        owner=owner,
        title=doc.title,
        description=doc.description,
        subject_tags=list(doc.subject_tags),
        visibility=doc.visibility,
        status=RoadmapStatus.DRAFT,
        revision=1,
        sections=sections,
        section_order=section_order,
        suggested_path=[resolve(ref) for ref in doc.suggested_path],
        created_at=now,
        updated_at=now,
    )
    return AssembledDraft(roadmap=roadmap, remap=dict(minter.remap))


class _Minter:
    """Accumulates minted IDs across one roadmap so collisions de-dupe within it,
    and records the remap plus the subsection reference map for edge resolution."""

    def __init__(self) -> None:
        self._existing: set[str] = set()
        self.remap: dict[str, str] = {}
        self._subsection_refs: dict[str, str] = {}

    def section(self, section: SectionInput) -> _MintedSection:
        section_id = self._mint(section.proposed_id, section.title, SECTION_PREFIX)
        return _MintedSection(
            id=section_id,
            source=section,
            subsections=[self._subsection(sub) for sub in section.subsections],
        )

    def _subsection(self, sub: SubsectionInput) -> _MintedSub:
        sub_id = self._mint(sub.proposed_id, sub.title, SUBSECTION_PREFIX)
        if sub.proposed_id is not None:
            # First occurrence of a proposed_id wins the reference mapping: a
            # duplicate proposal is de-duped to a suffixed ID and cannot be the
            # target of references to the bare handle.
            self._subsection_refs.setdefault(sub.proposed_id, sub_id)
        resources = [
            (self._mint(res.proposed_id, res.title, RESOURCE_PREFIX), res) for res in sub.resources
        ]
        items = [
            (self._mint(item.proposed_id, item.text, CHECKLIST_PREFIX), item)
            for item in sub.checklist_items
        ]
        return _MintedSub(id=sub_id, source=sub, resources=resources, items=items)

    def reference_resolver(self) -> _ReferenceResolver:
        """A closure mapping an author's ``proposed_id`` to the minted ID, leaving
        unknown references (e.g. a typo, caught later at publish) unchanged."""
        refs = dict(self._subsection_refs)
        return lambda ref: refs.get(ref, ref)

    def _mint(self, proposed_id: str | None, source_text: str, prefix: str) -> str:
        if proposed_id is not None:
            minted = slugs.mint_proposed(proposed_id, prefix, self._existing)
            if minted != proposed_id:
                self.remap[proposed_id] = minted
        else:
            minted = slugs.mint(source_text, prefix, self._existing)
        self._existing.add(minted)
        return minted


def _build_section(minted: _MintedSection, resolve: _ReferenceResolver) -> Section:
    subsections: dict[str, Subsection] = {}
    subsection_order: list[str] = []
    for minted_sub in minted.subsections:
        subsections[minted_sub.id] = _build_subsection(minted_sub, resolve)
        subsection_order.append(minted_sub.id)
    return Section(
        id=minted.id,
        title=minted.source.title,
        subsections=subsections,
        subsection_order=subsection_order,
    )


def _build_subsection(minted: _MintedSub, resolve: _ReferenceResolver) -> Subsection:
    source = minted.source
    resources = {
        res_id: Resource(id=res_id, title=res.title, url=res.url, type=res.type)
        for res_id, res in minted.resources
    }
    items = {item_id: ChecklistItem(id=item_id, text=item.text) for item_id, item in minted.items}
    return Subsection(
        id=minted.id,
        title=source.title,
        description=source.description,
        tags=list(source.tags),
        effort_estimate=source.effort_estimate,
        prereq_ids=[resolve(ref) for ref in source.prereq_ids],
        resources=resources,
        resource_order=[res_id for res_id, _ in minted.resources],
        checklist_items=items,
        item_order=[item_id for item_id, _ in minted.items],
    )
