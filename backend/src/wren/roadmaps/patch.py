"""``patch``: the pure, atomic op-list applier.

The primary iterative-edit path. :func:`apply` takes a draft and an
``operations[]`` list and returns the mutated roadmap plus the changed-node echo
and the ``proposed_id -> minted_id`` remap, applying **all-or-nothing**: it works
over a deep copy, so a failure on any op raises :class:`PatchError` and the input
draft is left byte-for-byte unchanged (the service persists the result only on
full success). No I/O: like ``dag``/``assembly`` this is a pure deep module,
exhaustively and property-tested in isolation.

Addressing: every op targets nodes by slug ID, never by
array index; ordering is expressed with ``before_id``/``after_id`` resolved into
positions in the sibling ``*_order`` array. IDs are resolved through the running
remap first, so an op may reference a ``proposed_id`` an earlier ``add_*`` in the
same batch minted (or had de-duped). Errors are model-recoverable: an unknown ID
names its valid siblings, and a cycle-creating edge explains the cycle (reusing
``dag.check_acyclic``).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import assert_never

from wren.roadmaps import dag
from wren.roadmaps.assembly import IdMinter
from wren.roadmaps.config import (
    CHECKLIST_PREFIX,
    RESOURCE_PREFIX,
    SECTION_PREFIX,
    SUBSECTION_PREFIX,
)
from wren.roadmaps.schemas import (
    AddEdgeOp,
    AddItemOp,
    AddSectionOp,
    AddSubsectionOp,
    ChangedNode,
    ChangedNodeKind,
    ChangeType,
    ChecklistItem,
    PatchOp,
    RemoveEdgeOp,
    RemoveItemOp,
    RemoveSectionOp,
    RemoveSubsectionOp,
    ReorderOp,
    Resource,
    Roadmap,
    Section,
    SetEffortOp,
    SetResourcesOp,
    SetSuggestedPathOp,
    SetTagsOp,
    Subsection,
    SubsectionInput,
    UpdateItemOp,
    UpdateSectionOp,
    UpdateSubsectionOp,
)


class PatchError(Exception):
    """A model-recoverable failure applying one op.

    ``field`` is the dotted path to the offending input (e.g.
    ``operations[2].subsection_id``) and ``message`` names valid sibling IDs or
    explains the cycle, so the service maps it straight onto a field-level 422 the
    agent can self-correct from. The pure module stays framework-free: mapping to
    the wire ``WrenError`` is the service's job.
    """

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(message)

    def at(self, index: int) -> PatchError:
        """Re-scope this error under its op's position in the batch."""
        return PatchError(f"operations[{index}].{self.field}", self.message)


@dataclass(frozen=True)
class PatchOutcome:
    """The result of a successful batch: the mutated roadmap (revision **not**
    bumped: that is the service's optimistic-concurrency rule), the changed-node
    echo, and the de-dup remap."""

    roadmap: Roadmap
    changed_nodes: list[ChangedNode]
    remap: dict[str, str]


def apply(draft: Roadmap, operations: list[PatchOp]) -> PatchOutcome:
    """Apply ``operations`` atomically over a copy of ``draft``.

    Raises :class:`PatchError` (scoped to the failing op) on the first invalid op,
    leaving ``draft`` unchanged. On success returns the fully-mutated working copy.
    """
    applier = _Applier(draft)
    for index, op in enumerate(operations):
        try:
            applier.dispatch(op)
        except PatchError as err:
            raise err.at(index) from None
    return applier.outcome()


class _Applier:
    """Holds the working copy and applies ops in place; instantiated per batch."""

    def __init__(self, draft: Roadmap) -> None:
        # Deep copy so the input is never mutated: the all-or-nothing guarantee is
        # that a mid-batch failure discards this copy and never touches ``draft``.
        self._roadmap = draft.model_copy(deep=True)
        self._minter = IdMinter(self._all_ids())
        # Keyed by (kind, id) so repeated touches collapse to one final entry.
        self._changes: dict[tuple[ChangedNodeKind, str], ChangedNode] = {}

    def dispatch(self, op: PatchOp) -> None:
        # L6 decision: kept as an explicit isinstance spine (not a dict handler
        # table) on purpose. The assert_never fallback below gives mypy
        # compile-time exhaustiveness, so adding a PatchOp subtype fails type-check
        # until it is handled here; a dict dispatch would only be worth it if it
        # preserved that guarantee (a plain dict that no-ops an unhandled op is a
        # net loss).
        if isinstance(op, AddSubsectionOp):
            self._add_subsection(op)
        elif isinstance(op, UpdateSubsectionOp):
            self._update_subsection(op)
        elif isinstance(op, RemoveSubsectionOp):
            self._remove_subsection(op)
        elif isinstance(op, AddEdgeOp):
            self._add_edge(op)
        elif isinstance(op, RemoveEdgeOp):
            self._remove_edge(op)
        elif isinstance(op, SetTagsOp):
            self._set_tags(op)
        elif isinstance(op, SetResourcesOp):
            self._set_resources(op)
        elif isinstance(op, SetEffortOp):
            self._set_effort(op)
        elif isinstance(op, AddItemOp):
            self._add_item(op)
        elif isinstance(op, UpdateItemOp):
            self._update_item(op)
        elif isinstance(op, RemoveItemOp):
            self._remove_item(op)
        elif isinstance(op, ReorderOp):
            self._reorder(op)
        elif isinstance(op, SetSuggestedPathOp):
            self._set_suggested_path(op)
        elif isinstance(op, AddSectionOp):
            self._add_section(op)
        elif isinstance(op, UpdateSectionOp):
            self._update_section(op)
        elif isinstance(op, RemoveSectionOp):
            self._remove_section(op)
        else:  # pragma: no cover - exhaustive over the PatchOp union
            assert_never(op)

    def outcome(self) -> PatchOutcome:
        return PatchOutcome(
            roadmap=self._roadmap,
            changed_nodes=list(self._changes.values()),
            remap=dict(self._minter.remap),
        )

    # --- sections -----------------------------------------------------------

    def _add_section(self, op: AddSectionOp) -> None:
        section_id = self._minter.mint(op.proposed_id, op.title, SECTION_PREFIX)
        self._roadmap.sections[section_id] = Section(id=section_id, title=op.title)
        self._place(self._roadmap.section_order, section_id, op.before_id, op.after_id, "section")
        self._record(ChangedNodeKind.SECTION, section_id, ChangeType.ADDED)

    def _update_section(self, op: UpdateSectionOp) -> None:
        section = self._require_section(op.section_id)
        section.title = op.title
        self._record(ChangedNodeKind.SECTION, section.id, ChangeType.UPDATED)

    def _remove_section(self, op: RemoveSectionOp) -> None:
        section = self._require_section(op.section_id)
        del self._roadmap.sections[section.id]
        self._roadmap.section_order.remove(section.id)
        self._record(ChangedNodeKind.SECTION, section.id, ChangeType.REMOVED)

    # --- subsections --------------------------------------------------------

    def _add_subsection(self, op: AddSubsectionOp) -> None:
        section = self._require_section(op.section_id)
        subsection = self._build_subsection(op.subsection)
        section.subsections[subsection.id] = subsection
        self._place(
            section.subsection_order, subsection.id, op.before_id, op.after_id, "subsection"
        )
        self._assert_acyclic("subsection")
        self._record(ChangedNodeKind.SUBSECTION, subsection.id, ChangeType.ADDED)

    def _update_subsection(self, op: UpdateSubsectionOp) -> None:
        _, sub = self._require_subsection(op.subsection_id)
        provided = op.model_fields_set
        # A blank title is a V8 concern caught at publish; only guard against
        # nulling the required field when the caller omitted it entirely.
        if op.title is not None:
            sub.title = op.title
        if "description" in provided:
            sub.description = op.description
        if "effort_estimate" in provided:
            sub.effort_estimate = op.effort_estimate
        self._record(ChangedNodeKind.SUBSECTION, sub.id, ChangeType.UPDATED)

    def _remove_subsection(self, op: RemoveSubsectionOp) -> None:
        section, sub = self._require_subsection(op.subsection_id)
        del section.subsections[sub.id]
        section.subsection_order.remove(sub.id)
        self._record(ChangedNodeKind.SUBSECTION, sub.id, ChangeType.REMOVED)

    def _set_tags(self, op: SetTagsOp) -> None:
        _, sub = self._require_subsection(op.subsection_id)
        sub.tags = list(op.tags)
        self._record(ChangedNodeKind.SUBSECTION, sub.id, ChangeType.UPDATED)

    def _set_resources(self, op: SetResourcesOp) -> None:
        _, sub = self._require_subsection(op.subsection_id)
        resources: dict[str, Resource] = {}
        order: list[str] = []
        for res in op.resources:
            res_id = self._minter.mint(res.proposed_id, res.title, RESOURCE_PREFIX)
            resources[res_id] = Resource(id=res_id, title=res.title, url=res.url, type=res.type)
            order.append(res_id)
        sub.resources = resources
        sub.resource_order = order
        self._record(ChangedNodeKind.SUBSECTION, sub.id, ChangeType.UPDATED)

    def _set_effort(self, op: SetEffortOp) -> None:
        _, sub = self._require_subsection(op.subsection_id)
        sub.effort_estimate = op.effort_estimate
        self._record(ChangedNodeKind.SUBSECTION, sub.id, ChangeType.UPDATED)

    # --- edges --------------------------------------------------------------

    def _add_edge(self, op: AddEdgeOp) -> None:
        from_sub = self._require_subsection(op.from_id, field="from_id")[1]
        to_sub = self._require_subsection(op.to_id, field="to_id")[1]
        if from_sub.id not in to_sub.prereq_ids:
            to_sub.prereq_ids.append(from_sub.id)
        self._assert_acyclic("to_id")
        self._record(ChangedNodeKind.SUBSECTION, to_sub.id, ChangeType.UPDATED)

    def _remove_edge(self, op: RemoveEdgeOp) -> None:
        to_sub = self._require_subsection(op.to_id, field="to_id")[1]
        # Idempotent: removing an edge that is not present is a no-op, so a replay
        # (or the inverse of an add that was never applied) never errors.
        from_id = self._resolve(op.from_id)
        if from_id in to_sub.prereq_ids:
            to_sub.prereq_ids.remove(from_id)
        self._record(ChangedNodeKind.SUBSECTION, to_sub.id, ChangeType.UPDATED)

    # --- items --------------------------------------------------------------

    def _add_item(self, op: AddItemOp) -> None:
        _, sub = self._require_subsection(op.subsection_id)
        item_id = self._minter.mint(op.proposed_id, op.text, CHECKLIST_PREFIX)
        sub.checklist_items[item_id] = ChecklistItem(id=item_id, text=op.text)
        self._place(sub.item_order, item_id, op.before_id, op.after_id, "item")
        self._record(ChangedNodeKind.ITEM, item_id, ChangeType.ADDED)

    def _update_item(self, op: UpdateItemOp) -> None:
        _, item = self._require_item(op.item_id)
        item.text = op.text
        self._record(ChangedNodeKind.ITEM, item.id, ChangeType.UPDATED)

    def _remove_item(self, op: RemoveItemOp) -> None:
        sub, item = self._require_item(op.item_id)
        del sub.checklist_items[item.id]
        sub.item_order.remove(item.id)
        self._record(ChangedNodeKind.ITEM, item.id, ChangeType.REMOVED)

    # --- ordering & path ----------------------------------------------------

    def _reorder(self, op: ReorderOp) -> None:
        target = self._resolve(op.target_id)
        order, kind = self._locate_order(target)
        remaining = [entry for entry in order if entry != target]
        index = self._position(remaining, op.before_id, op.after_id, kind.value)
        remaining.insert(index, target)
        order[:] = remaining
        self._record(kind, target, ChangeType.UPDATED)

    def _set_suggested_path(self, op: SetSuggestedPathOp) -> None:
        self._roadmap.suggested_path = [self._resolve(ref) for ref in op.path]
        self._record(ChangedNodeKind.ROADMAP, self._roadmap.id, ChangeType.UPDATED)

    # --- lookups & helpers --------------------------------------------------

    def _build_subsection(self, inp: SubsectionInput) -> Subsection:
        sub_id = self._minter.mint(inp.proposed_id, inp.title, SUBSECTION_PREFIX)
        resources: dict[str, Resource] = {}
        resource_order: list[str] = []
        for res in inp.resources:
            res_id = self._minter.mint(res.proposed_id, res.title, RESOURCE_PREFIX)
            resources[res_id] = Resource(id=res_id, title=res.title, url=res.url, type=res.type)
            resource_order.append(res_id)
        items: dict[str, ChecklistItem] = {}
        item_order: list[str] = []
        for item in inp.checklist_items:
            item_id = self._minter.mint(item.proposed_id, item.text, CHECKLIST_PREFIX)
            items[item_id] = ChecklistItem(id=item_id, text=item.text)
            item_order.append(item_id)
        return Subsection(
            id=sub_id,
            title=inp.title,
            description=inp.description,
            tags=list(inp.tags),
            effort_estimate=inp.effort_estimate,
            prereq_ids=[self._resolve(ref) for ref in inp.prereq_ids],
            resources=resources,
            resource_order=resource_order,
            checklist_items=items,
            item_order=item_order,
        )

    def _require_section(self, section_id: str) -> Section:
        resolved = self._resolve(section_id)
        section = self._roadmap.sections.get(resolved)
        if section is None:
            raise _unknown("section_id", "section", resolved, self._roadmap.sections)
        return section

    def _require_subsection(
        self, subsection_id: str, *, field: str = "subsection_id"
    ) -> tuple[Section, Subsection]:
        resolved = self._resolve(subsection_id)
        for section in self._sections():
            sub = section.subsections.get(resolved)
            if sub is not None:
                return section, sub
        raise _unknown(field, "subsection", resolved, self._subsection_ids())

    def _require_item(self, item_id: str) -> tuple[Subsection, ChecklistItem]:
        resolved = self._resolve(item_id)
        for section in self._sections():
            for sub in section.subsections.values():
                item = sub.checklist_items.get(resolved)
                if item is not None:
                    return sub, item
        raise _unknown("item_id", "item", resolved, self._item_ids())

    def _locate_order(self, target: str) -> tuple[list[str], ChangedNodeKind]:
        """The sibling order list ``target`` belongs to, plus its node kind."""
        if target in self._roadmap.sections:
            return self._roadmap.section_order, ChangedNodeKind.SECTION
        for section in self._sections():
            if target in section.subsections:
                return section.subsection_order, ChangedNodeKind.SUBSECTION
            for sub in section.subsections.values():
                if target in sub.checklist_items:
                    return sub.item_order, ChangedNodeKind.ITEM
        raise _unknown("target_id", "node", target, self._reorderable_ids())

    def _place(
        self, order: list[str], new_id: str, before: str | None, after: str | None, kind: str
    ) -> None:
        order.insert(self._position(order, before, after, kind), new_id)

    def _position(self, order: list[str], before: str | None, after: str | None, kind: str) -> int:
        """Resolve ``before_id``/``after_id`` into an insertion index in ``order``.

        Both must name a sibling in ``order``; ``before_id`` wins if both are set.
        Neither given appends to the end.
        """
        if before is not None:
            resolved = self._resolve(before)
            if resolved not in order:
                raise _unknown("before_id", kind, resolved, order)
            return order.index(resolved)
        if after is not None:
            resolved = self._resolve(after)
            if resolved not in order:
                raise _unknown("after_id", kind, resolved, order)
            return order.index(resolved) + 1
        return len(order)

    def _assert_acyclic(self, field: str) -> None:
        nodes = set(self._subsection_ids())
        edges = {sub.id: list(sub.prereq_ids) for _, sub in self._all_subsections()}
        report = dag.check_acyclic(nodes, edges)
        if report is not None:
            raise PatchError(field, report.message)

    def _resolve(self, ref: str) -> str:
        """Redirect a reference through the running remap so a batch can address a
        ``proposed_id`` an earlier ``add_*`` minted or de-duped.
        """
        return self._minter.remap.get(ref, ref)

    def _record(self, kind: ChangedNodeKind, node_id: str, change: ChangeType) -> None:
        self._changes[(kind, node_id)] = ChangedNode(kind=kind, id=node_id, change=change)

    def _sections(self) -> Iterator[Section]:
        for section_id in self._roadmap.section_order:
            section = self._roadmap.sections.get(section_id)
            if section is not None:
                yield section

    def _all_subsections(self) -> Iterator[tuple[Section, Subsection]]:
        for section in self._sections():
            for sub in section.subsections.values():
                yield section, sub

    def _subsection_ids(self) -> list[str]:
        return [sub.id for _, sub in self._all_subsections()]

    def _item_ids(self) -> list[str]:
        return [item_id for _, sub in self._all_subsections() for item_id in sub.checklist_items]

    def _reorderable_ids(self) -> list[str]:
        return [*self._roadmap.sections, *self._subsection_ids(), *self._item_ids()]

    def _all_ids(self) -> set[str]:
        """Every child slug ID already in the roadmap, seeding the minter so a new
        ID never collides with a pre-existing one (IDs are unique per roadmap)."""
        ids: set[str] = set()
        for section in self._roadmap.sections.values():
            ids.add(section.id)
            for sub in section.subsections.values():
                ids.add(sub.id)
                ids.update(sub.resources)
                ids.update(sub.checklist_items)
        return ids


def _unknown(field: str, kind: str, missing_id: str, valid: Iterable[str]) -> PatchError:
    """A model-recoverable unknown-ID error that names the valid siblings so the
    agent can retry without a human."""
    names = ", ".join(sorted(valid))
    detail = f"valid {kind} ids: {names}" if names else f"no {kind} exists yet"
    return PatchError(field, f"no {kind} '{missing_id}'; {detail}")
