"""``dag``: the pure structural validator for the prerequisite DAG.

This is the highest test-density deep module in the epic: a false
negative here lets a structurally broken roadmap publish and break followers, so
the module is covered exhaustively *and* with ``hypothesis`` property tests.

It is deliberately **pure** and framework-free. Its functions operate only over
primitive graph structures (``set[str]`` of subsection IDs and
``dict[str, list[str]]`` mapping each subsection to its ``prereq_ids``), so the
module imports no FastAPI, DB, request, or token and is importable and testable
in complete isolation. It returns its own small report types
(:class:`CycleReport`, :class:`RuleViolation`); ticket #11's ``validation.py``
composes these into the ``validate_structure`` contract and maps them onto the
wire ``wren.core.errors.Violation`` (which lives with the HTTP boundary and pulls
in FastAPI, hence is kept out of this pure module).

Edge convention: ``edges[x]`` is the list of ``x``'s prerequisites, so
an edge ``x -> y`` reads "``x`` depends on ``y``" and a valid learning order
places every prerequisite *before* its dependent.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

# Sentinel colors for the iterative depth-first cycle search.
_WHITE, _GRAY, _BLACK = 0, 1, 2


class DagRule(StrEnum):
    """Structural-rule codes this module emits, carried in ``RuleViolation.rule``.

    The values match the ``Violation.rule`` wire codes (spec §04 validation
    contract); ticket #11 extends the enumeration with the remaining
    non-DAG rules (V5..V8) it owns.
    """

    ACYCLIC = "V1_ACYCLIC"  # V1: the prerequisite DAG is acyclic
    NO_DANGLING_PREREQ = "V2_NO_DANGLING_PREREQ"  # V2: every prereq_id exists
    PATH_COVERAGE = "V3_PATH_COVERAGE"  # V3: suggested_path covers each node once
    PATH_ORDER = "V4_PATH_ORDER"  # V4: suggested_path is a valid topological order


@dataclass(frozen=True)
class CycleReport:
    """Names one prerequisite cycle found by :func:`check_acyclic`.

    ``cycle`` is a closed walk in dependency order: the first node repeats at the
    end, so a self-edge is ``["sub_x", "sub_x"]`` and a two-node cycle is
    ``["sub_x", "sub_y", "sub_x"]``. Naming the cycle is what makes the failure
    model-recoverable: the agent can see exactly which edge to remove.
    """

    cycle: list[str]

    @property
    def message(self) -> str:
        return "prerequisite cycle: " + " -> ".join(self.cycle)


@dataclass(frozen=True)
class RuleViolation:
    """One structural-rule failure naming the rule and the offending IDs.

    Mirrors the field shape of the wire ``wren.core.errors.Violation`` so #11 can
    map it across with no restructuring, while keeping this module free of the
    FastAPI-coupled error contract.
    """

    rule: DagRule
    ids: list[str]
    message: str


def check_acyclic(nodes: set[str], edges: Mapping[str, list[str]]) -> CycleReport | None:
    """Return ``None`` if the prerequisite graph is acyclic, else a report naming
    one cycle.

    Detects self-edges, multi-node cycles, and cycles in any disconnected
    component. Roots are visited in sorted order so the reported cycle is
    deterministic for a given graph.
    """
    color: dict[str, int] = {}
    for root in sorted(nodes | set(edges)):
        if color.get(root, _WHITE) != _WHITE:
            continue
        cycle = _find_cycle_from(root, edges, color)
        if cycle is not None:
            return CycleReport(cycle=cycle)
    return None


def find_dangling_prereqs(nodes: set[str], edges: Mapping[str, list[str]]) -> list[RuleViolation]:
    """Return a V2 violation per subsection whose ``prereq_ids`` reference a node
    that does not exist. Each violation names the owning subsection
    followed by its unknown references, so the agent can fix the edge in place.
    """
    violations: list[RuleViolation] = []
    for node in sorted(edges):
        dangling = sorted({ref for ref in edges[node] if ref not in nodes})
        if dangling:
            violations.append(
                RuleViolation(
                    rule=DagRule.NO_DANGLING_PREREQ,
                    ids=[node, *dangling],
                    message=(
                        f"subsection {node} lists prerequisite(s) that do not exist: "
                        + ", ".join(dangling)
                    ),
                )
            )
    return violations


def validate_suggested_path(
    path: list[str], nodes: set[str], edges: Mapping[str, list[str]]
) -> list[RuleViolation]:
    """Validate ``suggested_path`` against V3 (coverage) and V4 (topological order).

    V3: the path must list every subsection exactly once (surfacing missing,
    duplicated, and unknown IDs). V4: no prerequisite may appear after its
    dependent; the first such out-of-order pair is reported. All applicable
    violations are returned in one pass so the author sees the complete fix list.
    """
    violations = _coverage_violations(path, nodes)
    order_violation = _first_order_violation(path, nodes, edges)
    if order_violation is not None:
        violations.append(order_violation)
    return violations


def _find_cycle_from(
    root: str, edges: Mapping[str, list[str]], color: dict[str, int]
) -> list[str] | None:
    """Iterative DFS from ``root``; returns the closed cycle walk or ``None``.

    ``path`` mirrors the gray (on-stack) frontier exactly, so a gray neighbor is
    always already on ``path`` and closing the cycle is a slice from its position.
    """
    color[root] = _GRAY
    path = [root]
    stack: list[tuple[str, Iterable[str]]] = [(root, iter(edges.get(root, ())))]
    while stack:
        node, neighbors = stack[-1]
        descended = False
        for neighbor in neighbors:
            state = color.get(neighbor, _WHITE)
            if state == _GRAY:
                start = path.index(neighbor)
                return [*path[start:], neighbor]
            if state == _WHITE:
                color[neighbor] = _GRAY
                path.append(neighbor)
                stack.append((neighbor, iter(edges.get(neighbor, ()))))
                descended = True
                break
            # _BLACK: fully explored already; no cycle reachable through it.
        if not descended:
            color[node] = _BLACK
            stack.pop()
            path.pop()
    return None


def _coverage_violations(path: list[str], nodes: set[str]) -> list[RuleViolation]:
    counts = Counter(path)
    violations: list[RuleViolation] = []

    missing = sorted(nodes - set(counts))
    if missing:
        violations.append(
            RuleViolation(
                rule=DagRule.PATH_COVERAGE,
                ids=missing,
                message="suggested_path is missing subsection(s): " + ", ".join(missing),
            )
        )

    duplicated = sorted(entry for entry, count in counts.items() if entry in nodes and count > 1)
    if duplicated:
        violations.append(
            RuleViolation(
                rule=DagRule.PATH_COVERAGE,
                ids=duplicated,
                message="suggested_path lists subsection(s) more than once: "
                + ", ".join(duplicated),
            )
        )

    unknown = sorted(entry for entry in counts if entry not in nodes)
    if unknown:
        violations.append(
            RuleViolation(
                rule=DagRule.PATH_COVERAGE,
                ids=unknown,
                message="suggested_path references unknown subsection(s): " + ", ".join(unknown),
            )
        )

    return violations


def _first_order_violation(
    path: list[str], nodes: set[str], edges: Mapping[str, list[str]]
) -> RuleViolation | None:
    first_index: dict[str, int] = {}
    for index, node in enumerate(path):
        first_index.setdefault(node, index)

    for index, node in enumerate(path):
        if node not in nodes:
            continue
        for prereq in edges.get(node, ()):
            prereq_index = first_index.get(prereq)
            if prereq_index is not None and prereq_index > index:
                return RuleViolation(
                    rule=DagRule.PATH_ORDER,
                    ids=[prereq, node],
                    message=(
                        f"suggested_path lists prerequisite {prereq} after its dependent {node}"
                    ),
                )
    return None
