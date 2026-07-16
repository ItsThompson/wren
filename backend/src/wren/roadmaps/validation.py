"""Structural validation of a draft roadmap.

Pure functions over the domain :class:`Roadmap`: no I/O, no request, no database,
so they are exhaustively and property-tested in isolation.

This is the FULL structural contract (V1..V8). It composes the
pure :mod:`wren.roadmaps.dag` module with the local content rules:

* V1: the prerequisite DAG is acyclic (``dag.check_acyclic``)
* V2: no dangling ``prereq_ids`` (``dag.find_dangling_prereqs``)
* V3: ``suggested_path`` covers every subsection exactly once (``dag``)
* V4: ``suggested_path`` is a legal topological order (``dag``)
* V5: every section has >= 1 subsection
* V6: every subsection has >= 1 checklist item
* V7: every subsection has >= 1 resource
* V8: non-empty titles (roadmap, every section / subsection / checklist item)

:func:`validate_structure` returns ALL violations in one pass (never fail-fast),
so an author sees the complete fix list at once; :meth:`RoadmapService.publish`
hard-blocks on any violation and the ``422`` problem+json carries the
whole ``violations`` array.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from wren.core.errors import Violation
from wren.roadmaps.dag import (
    CycleReport,
    DagRule,
    RuleViolation,
    check_acyclic,
    find_dangling_prereqs,
    validate_suggested_path,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from wren.roadmaps.schemas import Roadmap, Section, Subsection


class StructuralRule(StrEnum):
    """The full ``Violation.rule`` contract (V1..V8).

    Single source of truth for the wire codes. The DAG-derived codes (V1..V4) are
    sourced from :class:`DagRule` (the pure ``dag`` module owns them and emits
    them in its report types), so each code has exactly one definition rather than
    two parallel enums; V5..V8 are the local content rules this module owns.
    """

    V1_ACYCLIC = DagRule.ACYCLIC.value
    V2_NO_DANGLING_PREREQ = DagRule.NO_DANGLING_PREREQ.value
    V3_PATH_COVERAGE = DagRule.PATH_COVERAGE.value
    V4_PATH_ORDER = DagRule.PATH_ORDER.value
    V5_SUBSECTION_REQUIRED = "V5_SUBSECTION_REQUIRED"
    V6_ITEM_REQUIRED = "V6_ITEM_REQUIRED"
    V7_RESOURCE_REQUIRED = "V7_RESOURCE_REQUIRED"
    V8_TITLE_REQUIRED = "V8_TITLE_REQUIRED"


def validate_structure(draft: Roadmap) -> list[Violation]:
    """Run every structural check over ``draft`` and return all violations.

    An empty list means the draft satisfies the structural contract and may be
    published. Checks run in rule order (V1..V8) and never short-circuit, so an
    author sees every problem at once.
    """
    violations: list[Violation] = []
    for check in _CHECKS:
        violations.extend(check(draft))
    return violations


def _check_titles(draft: Roadmap) -> list[Violation]:
    """V8: the roadmap and every section / subsection / checklist item needs a
    non-empty title (checklist items carry their title as ``text``)."""
    return [
        _violation(StructuralRule.V8_TITLE_REQUIRED, entity_id, f"{entity_id} has an empty title")
        for entity_id, text in _titled_entities(draft)
        if _is_blank(text)
    ]


def _check_sections_have_subsections(draft: Roadmap) -> list[Violation]:
    """V5: every section has at least one subsection."""
    return [
        _violation(
            StructuralRule.V5_SUBSECTION_REQUIRED, section.id, f"section {section.id} is empty"
        )
        for section in _sections_in_order(draft)
        if not section.subsections
    ]


def _check_subsections_have_items(draft: Roadmap) -> list[Violation]:
    """V6: every subsection has at least one checklist item."""
    return [
        _violation(
            StructuralRule.V6_ITEM_REQUIRED,
            subsection.id,
            f"subsection {subsection.id} has no checklist items",
        )
        for subsection in _subsections_in_order(draft)
        if not subsection.checklist_items
    ]


def _check_subsections_have_resources(draft: Roadmap) -> list[Violation]:
    """V7: every subsection has at least one resource."""
    return [
        _violation(
            StructuralRule.V7_RESOURCE_REQUIRED,
            subsection.id,
            f"subsection {subsection.id} has no resources",
        )
        for subsection in _subsections_in_order(draft)
        if not subsection.resources
    ]


def _check_dag(draft: Roadmap) -> list[Violation]:
    """V1..V4: compose the pure ``dag`` module over the prerequisite graph.

    ``nodes`` is every subsection ID; ``edges[x]`` is ``x``'s ``prereq_ids`` (the
    edge convention the ``dag`` module documents). V1 (cycle), V2 (dangling
    prereqs), and V3/V4 (``suggested_path`` coverage + topological order) each run
    independently, so a graph with several faults surfaces them all in one pass.
    """
    subsections = list(_subsections_in_order(draft))
    nodes = {subsection.id for subsection in subsections}
    edges = {subsection.id: list(subsection.prereq_ids) for subsection in subsections}

    violations: list[Violation] = []
    cycle = check_acyclic(nodes, edges)
    if cycle is not None:
        violations.append(_cycle_violation(cycle))
    dag_violations = [
        *find_dangling_prereqs(nodes, edges),
        *validate_suggested_path(draft.suggested_path, nodes, edges),
    ]
    violations.extend(_to_wire(rule_violation) for rule_violation in dag_violations)
    return violations


def _cycle_violation(report: CycleReport) -> Violation:
    """Map the V1 :class:`CycleReport` (an ordered closed walk) onto the wire.

    ``cycle`` repeats its first node to close the walk; ``ids`` carry the distinct
    nodes in cycle order and the report's ``message`` is
    used verbatim.
    """
    return Violation(
        rule=StructuralRule.V1_ACYCLIC.value,
        ids=list(dict.fromkeys(report.cycle)),
        message=report.message,
    )


def _to_wire(rule_violation: RuleViolation) -> Violation:
    """Re-wrap a pure ``dag`` :class:`RuleViolation` as the wire ``Violation``.

    The rule codes are identical strings (V2..V4); this only carries the fields
    across the framework boundary the pure module deliberately avoids.
    """
    return Violation(
        rule=rule_violation.rule.value,
        ids=rule_violation.ids,
        message=rule_violation.message,
    )


def _sections_in_order(draft: Roadmap) -> Iterator[Section]:
    """Yield sections in ``section_order`` (the authoritative structural order)."""
    for section_id in draft.section_order:
        section = draft.sections.get(section_id)
        if section is not None:
            yield section


def _subsections_in_order(draft: Roadmap) -> Iterator[Subsection]:
    """Yield every subsection across all sections in a deterministic order."""
    for section in _sections_in_order(draft):
        for subsection_id in section.subsection_order:
            subsection = section.subsections.get(subsection_id)
            if subsection is not None:
                yield subsection


def _titled_entities(draft: Roadmap) -> Iterator[tuple[str, str]]:
    """(entity_id, title/text) for every entity V8 requires to be non-empty."""
    yield (draft.id, draft.title)
    for section in _sections_in_order(draft):
        yield (section.id, section.title)
        for subsection_id in section.subsection_order:
            subsection = section.subsections.get(subsection_id)
            if subsection is None:
                continue
            yield (subsection.id, subsection.title)
            for item_id in subsection.item_order:
                item = subsection.checklist_items.get(item_id)
                if item is not None:
                    yield (item.id, item.text)


def _violation(rule: StructuralRule, offending_id: str, message: str) -> Violation:
    """One violation naming a single offending entity."""
    return Violation(rule=rule.value, ids=[offending_id], message=message)


def _is_blank(text: str) -> bool:
    return not text.strip()


# Every structural rule as an independent check, run in rule order (V1..V8). The
# DAG rules compose the pure ``dag`` module; the content rules (V5..V8) are local.
_CHECKS: tuple[Callable[[Roadmap], list[Violation]], ...] = (
    _check_dag,
    _check_sections_have_subsections,
    _check_subsections_have_items,
    _check_subsections_have_resources,
    _check_titles,
)
