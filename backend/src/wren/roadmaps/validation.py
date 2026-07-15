"""Structural validation of a draft roadmap (spec sections 04, 05).

Pure functions over the domain :class:`Roadmap`: no I/O, no request, no database,
so they are exhaustively and property-tested in isolation (spec section 13).

This slice (ticket 8) implements the MINIMAL subset that needs no graph analysis,
enough to gate publish for the walking skeleton:

* V5: every section has >= 1 subsection
* V6: every subsection has >= 1 checklist item
* V7: every subsection has >= 1 resource
* V8: non-empty titles (roadmap, every section / subsection / checklist item)
* V3 (minimal): ``suggested_path`` must be present once there is a subsection to
  sequence

The graph rules (V1 acyclic, V2 no dangling prereqs) and the FULL V3 coverage +
V4 topological-order checks are pure-``dag`` concerns delivered separately and
composed here later (spec section 05). :data:`_CHECKS` is that seam: additional
rule checks are appended, and the minimal V3 gate is superseded by the full path
validator, all without changing the ``Violation`` wire shape.

:func:`validate_structure` returns ALL violations in one pass (never fail-fast),
so an author sees the complete fix list at once.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from enum import StrEnum

from wren.core.errors import Violation
from wren.roadmaps.schemas import Roadmap, Section, Subsection


class StructuralRule(StrEnum):
    """Machine-readable ``Violation.rule`` codes for the structural contract.

    Values are stable wire identifiers (spec section 06); the full contract adds
    V1/V2/V4 and expands V3, but never restructures an existing code.
    """

    V3_PATH_COVERAGE = "V3_PATH_COVERAGE"
    V5_SUBSECTION_REQUIRED = "V5_SUBSECTION_REQUIRED"
    V6_ITEM_REQUIRED = "V6_ITEM_REQUIRED"
    V7_RESOURCE_REQUIRED = "V7_RESOURCE_REQUIRED"
    V8_TITLE_REQUIRED = "V8_TITLE_REQUIRED"


def validate_structure(draft: Roadmap) -> list[Violation]:
    """Run every structural check over ``draft`` and return all violations.

    An empty list means the draft satisfies the (currently minimal) structural
    contract and may be published.
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


def _check_suggested_path_present(draft: Roadmap) -> list[Violation]:
    """Minimal V3 gate: once there is a subsection to sequence, ``suggested_path``
    must be present. The FULL V3 coverage + V4 topological-order checks are
    composed here later from the pure ``dag`` module (spec section 05); this gate
    is superseded then, keeping the ``V3_PATH_COVERAGE`` wire code stable.
    """
    subsection_ids = [subsection.id for subsection in _subsections_in_order(draft)]
    if not subsection_ids or draft.suggested_path:
        return []
    return [
        Violation(
            rule=StructuralRule.V3_PATH_COVERAGE.value,
            ids=subsection_ids,
            message="suggested_path is empty; it must sequence every subsection before publish",
        )
    ]


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
    """One violation naming a single offending entity (spec section 06 shape)."""
    return Violation(rule=rule.value, ids=[offending_id], message=message)


def _is_blank(text: str) -> bool:
    return not text.strip()


# The composition seam: ticket 11 appends the pure-``dag`` V1/V2 checks and the
# full V3/V4 path validator here (superseding _check_suggested_path_present),
# without touching the Violation wire shape.
_CHECKS: tuple[Callable[[Roadmap], list[Violation]], ...] = (
    _check_titles,
    _check_sections_have_subsections,
    _check_subsections_have_items,
    _check_subsections_have_resources,
    _check_suggested_path_present,
)
