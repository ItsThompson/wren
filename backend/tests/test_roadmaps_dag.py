"""Exhaustive + property-based tests for the pure ``dag`` deep module.

The sharpest correctness surface in the epic: a false negative lets a
structurally broken roadmap publish. So the four structural checks
(``check_acyclic``, ``find_dangling_prereqs``, and ``validate_suggested_path``'s
V3 coverage + V4 topological order) are covered with exhaustive example cases and
with ``hypothesis`` invariants (random DAGs are always acyclic; one injected
back-edge is always caught; a topological order always validates; any permutation
that violates a prereq edge is always rejected).

Edge convention: ``edges[x]`` lists ``x``'s prerequisites, so ``x -> y`` means
"``x`` depends on ``y``" and a valid order places every prereq before its
dependent.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from wren.roadmaps.dag import (
    CycleReport,
    DagRule,
    RuleViolation,
    check_acyclic,
    find_dangling_prereqs,
    validate_suggested_path,
)

# --- check_acyclic: exhaustive example cases --------------------------------


def test_acyclic_graph_returns_none() -> None:
    nodes = {"sub_a", "sub_b", "sub_c"}
    # c depends on b, b depends on a: a straight chain, acyclic.
    edges = {"sub_b": ["sub_a"], "sub_c": ["sub_b"]}
    assert check_acyclic(nodes, edges) is None


def test_empty_graph_is_acyclic() -> None:
    assert check_acyclic(set(), {}) is None


def test_simple_two_node_cycle_is_reported() -> None:
    nodes = {"sub_a", "sub_b"}
    edges = {"sub_a": ["sub_b"], "sub_b": ["sub_a"]}

    report = check_acyclic(nodes, edges)

    assert isinstance(report, CycleReport)
    # A closed walk: the first node repeats at the end.
    assert report.cycle[0] == report.cycle[-1]
    assert set(report.cycle) == {"sub_a", "sub_b"}


def test_self_edge_is_reported_as_a_trivial_cycle() -> None:
    report = check_acyclic({"sub_x"}, {"sub_x": ["sub_x"]})

    assert isinstance(report, CycleReport)
    assert report.cycle == ["sub_x", "sub_x"]
    assert report.message == "prerequisite cycle: sub_x -> sub_x"


def test_multi_node_cycle_is_reported() -> None:
    nodes = {"sub_a", "sub_b", "sub_c"}
    edges = {"sub_a": ["sub_b"], "sub_b": ["sub_c"], "sub_c": ["sub_a"]}

    report = check_acyclic(nodes, edges)

    assert isinstance(report, CycleReport)
    assert report.cycle[0] == report.cycle[-1]
    assert set(report.cycle) == {"sub_a", "sub_b", "sub_c"}
    assert report.message.startswith("prerequisite cycle: ")


def test_disconnected_components_stay_acyclic() -> None:
    nodes = {"sub_a", "sub_b", "sub_c", "sub_d"}
    # Two independent chains a<-b and c<-d, no path between them.
    edges = {"sub_b": ["sub_a"], "sub_d": ["sub_c"]}
    assert check_acyclic(nodes, edges) is None


def test_cycle_in_one_of_two_components_is_reported() -> None:
    nodes = {"sub_a", "sub_b", "sub_c", "sub_d"}
    # First component acyclic (a<-b); second component is a 2-cycle (c<->d).
    edges = {"sub_b": ["sub_a"], "sub_c": ["sub_d"], "sub_d": ["sub_c"]}

    report = check_acyclic(nodes, edges)

    assert isinstance(report, CycleReport)
    assert set(report.cycle) == {"sub_c", "sub_d"}


def test_nodes_shared_across_roots_are_visited_once() -> None:
    # sub_a depends on sub_b depends on sub_c. The DFS from the first sorted root
    # (sub_a) colors the whole chain, so the later roots sub_b/sub_c are already
    # fully explored and skipped rather than re-traversed.
    nodes = {"sub_a", "sub_b", "sub_c"}
    edges = {"sub_a": ["sub_b"], "sub_b": ["sub_c"]}
    assert check_acyclic(nodes, edges) is None


def test_diamond_dependency_is_acyclic() -> None:
    # d depends on b and c; b and c both depend on a. A node reached by two paths
    # (a) must not be misreported as a cycle.
    nodes = {"sub_a", "sub_b", "sub_c", "sub_d"}
    edges = {"sub_d": ["sub_b", "sub_c"], "sub_b": ["sub_a"], "sub_c": ["sub_a"]}
    assert check_acyclic(nodes, edges) is None


# --- find_dangling_prereqs: exhaustive example cases ------------------------


def test_no_dangling_prereqs_returns_empty() -> None:
    nodes = {"sub_a", "sub_b"}
    edges = {"sub_b": ["sub_a"]}
    assert find_dangling_prereqs(nodes, edges) == []


def test_dangling_prereq_names_owner_and_missing_reference() -> None:
    nodes = {"sub_a"}
    edges = {"sub_a": ["sub_ghost"]}

    violations = find_dangling_prereqs(nodes, edges)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.rule is DagRule.NO_DANGLING_PREREQ
    assert violation.ids == ["sub_a", "sub_ghost"]
    assert "sub_a" in violation.message
    assert "sub_ghost" in violation.message


def test_dangling_prereqs_deduped_and_sorted_per_owner() -> None:
    nodes = {"sub_a"}
    edges = {"sub_a": ["sub_z", "sub_x", "sub_z"]}

    violations = find_dangling_prereqs(nodes, edges)

    assert len(violations) == 1
    assert violations[0].ids == ["sub_a", "sub_x", "sub_z"]


def test_multiple_owners_each_get_their_own_violation() -> None:
    nodes = {"sub_a", "sub_b"}
    edges = {"sub_b": ["sub_missing"], "sub_a": ["sub_gone"]}

    violations = find_dangling_prereqs(nodes, edges)

    # One violation per owning subsection, owners visited in sorted order.
    assert [violation.ids[0] for violation in violations] == ["sub_a", "sub_b"]


# --- validate_suggested_path: V3 coverage + V4 order ------------------------


def _complete_dag() -> tuple[set[str], dict[str, list[str]]]:
    """b depends on a, c depends on b: a valid path is [a, b, c]."""
    nodes = {"sub_a", "sub_b", "sub_c"}
    edges = {"sub_b": ["sub_a"], "sub_c": ["sub_b"]}
    return nodes, edges


def test_complete_and_valid_order_has_no_violations() -> None:
    nodes, edges = _complete_dag()
    assert validate_suggested_path(["sub_a", "sub_b", "sub_c"], nodes, edges) == []


def test_missing_node_is_a_v3_coverage_violation() -> None:
    nodes, edges = _complete_dag()

    violations = validate_suggested_path(["sub_a", "sub_b"], nodes, edges)

    coverage = [v for v in violations if v.rule is DagRule.PATH_COVERAGE]
    assert len(coverage) == 1
    assert coverage[0].ids == ["sub_c"]
    assert "missing" in coverage[0].message


def test_duplicate_node_is_a_v3_coverage_violation() -> None:
    nodes, edges = _complete_dag()

    violations = validate_suggested_path(["sub_a", "sub_b", "sub_b", "sub_c"], nodes, edges)

    coverage = [v for v in violations if v.rule is DagRule.PATH_COVERAGE]
    assert len(coverage) == 1
    assert coverage[0].ids == ["sub_b"]
    assert "more than once" in coverage[0].message


def test_unknown_path_entry_is_a_v3_coverage_violation() -> None:
    nodes, edges = _complete_dag()

    violations = validate_suggested_path(["sub_a", "sub_b", "sub_c", "sub_ghost"], nodes, edges)

    coverage = [v for v in violations if v.rule is DagRule.PATH_COVERAGE]
    assert len(coverage) == 1
    assert coverage[0].ids == ["sub_ghost"]
    assert "unknown" in coverage[0].message


def test_out_of_order_prereq_is_a_v4_violation() -> None:
    nodes, edges = _complete_dag()
    # b listed before its prereq a -> V4 (a must precede b).
    violations = validate_suggested_path(["sub_b", "sub_a", "sub_c"], nodes, edges)

    order = [v for v in violations if v.rule is DagRule.PATH_ORDER]
    assert len(order) == 1
    assert order[0].ids == ["sub_a", "sub_b"]
    assert "sub_a" in order[0].message
    assert "sub_b" in order[0].message


def test_v4_reports_only_the_first_out_of_order_pair() -> None:
    # Both b<-a and c<-b are violated by the fully-reversed order, but V4 names
    # only the first pair encountered.
    nodes, edges = _complete_dag()

    violations = validate_suggested_path(["sub_c", "sub_b", "sub_a"], nodes, edges)

    order = [v for v in violations if v.rule is DagRule.PATH_ORDER]
    assert len(order) == 1
    assert order[0].ids == ["sub_b", "sub_c"]


def test_coverage_and_order_violations_returned_together() -> None:
    nodes, edges = _complete_dag()
    # Missing sub_c (V3) AND b before its prereq a (V4), both in one pass.
    violations = validate_suggested_path(["sub_b", "sub_a"], nodes, edges)

    rules = {v.rule for v in violations}
    assert DagRule.PATH_COVERAGE in rules
    assert DagRule.PATH_ORDER in rules


def test_empty_path_over_empty_graph_validates() -> None:
    assert validate_suggested_path([], set(), {}) == []


def test_prereq_missing_from_path_is_coverage_not_order() -> None:
    # a is a prereq of b but absent from the path: that is a V3 coverage gap,
    # not a V4 order violation (there is no position to compare against).
    nodes, edges = _complete_dag()

    violations = validate_suggested_path(["sub_b", "sub_c"], nodes, edges)

    assert all(v.rule is not DagRule.PATH_ORDER for v in violations)
    assert any(v.rule is DagRule.PATH_COVERAGE for v in violations)


# --- property-based invariants (hypothesis) ---------------------------------


@st.composite
def acyclic_graphs(draw: st.DrawFn) -> tuple[set[str], dict[str, list[str]]]:
    """A random DAG. Every edge points from a higher-index node to a lower-index
    one (dependent -> prereq), which is acyclic by construction and makes the
    index order ``[sub_0, sub_1, ...]`` a valid topological order.
    """
    n = draw(st.integers(min_value=0, max_value=8))
    labels = [f"sub_{i}" for i in range(n)]
    edges: dict[str, list[str]] = {label: [] for label in labels}
    for j in range(n):
        for i in range(j):
            if draw(st.booleans()):
                edges[labels[j]].append(labels[i])
    return set(labels), edges


@st.composite
def dags_with_at_least_one_edge(
    draw: st.DrawFn,
) -> tuple[set[str], dict[str, list[str]]]:
    """An acyclic graph guaranteed to contain at least one edge (sub_1 -> sub_0)."""
    n = draw(st.integers(min_value=2, max_value=8))
    labels = [f"sub_{i}" for i in range(n)]
    edges: dict[str, list[str]] = {label: [] for label in labels}
    edges[labels[1]].append(labels[0])
    for j in range(n):
        for i in range(j):
            if (j, i) != (1, 0) and draw(st.booleans()):
                edges[labels[j]].append(labels[i])
    return set(labels), edges


@st.composite
def dags_with_a_reversed_edge(
    draw: st.DrawFn,
) -> tuple[set[str], dict[str, list[str]], str, str]:
    """An acyclic graph with one existing edge reversed, guaranteeing a cycle."""
    nodes, edges = draw(dags_with_at_least_one_edge())
    existing = [(dep, prereq) for dep, prereqs in edges.items() for prereq in prereqs]
    dep, prereq = draw(st.sampled_from(existing))
    perturbed = {node: list(prereqs) for node, prereqs in edges.items()}
    perturbed[prereq].append(dep)  # prereq now also depends on dep, closing a cycle
    return nodes, perturbed, dep, prereq


@st.composite
def dags_with_node_permutation(
    draw: st.DrawFn,
) -> tuple[set[str], dict[str, list[str]], list[str]]:
    """An acyclic graph plus a random permutation of all its nodes (a complete,
    duplicate-free cover, so V3 never fires and only V4 is under test)."""
    nodes, edges = draw(acyclic_graphs())
    permutation = draw(st.permutations(sorted(nodes)))
    return nodes, edges, list(permutation)


@given(acyclic_graphs())
def test_random_dags_are_always_acyclic(graph: tuple[set[str], dict[str, list[str]]]) -> None:
    nodes, edges = graph
    assert check_acyclic(nodes, edges) is None


@given(dags_with_a_reversed_edge())
def test_injecting_one_back_edge_always_reports_a_cycle(
    bundle: tuple[set[str], dict[str, list[str]], str, str],
) -> None:
    nodes, edges, dep, prereq = bundle

    report = check_acyclic(nodes, edges)

    assert isinstance(report, CycleReport)
    assert dep in report.cycle
    assert prereq in report.cycle


@given(acyclic_graphs())
def test_index_order_is_always_a_valid_topological_order(
    graph: tuple[set[str], dict[str, list[str]]],
) -> None:
    nodes, edges = graph
    topological = sorted(nodes)  # sub_0..sub_n; matches the build's index order
    assert validate_suggested_path(topological, nodes, edges) == []


@given(dags_with_node_permutation())
def test_permutation_rejected_exactly_when_it_violates_an_edge(
    bundle: tuple[set[str], dict[str, list[str]], list[str]],
) -> None:
    nodes, edges, permutation = bundle
    position = {node: index for index, node in enumerate(permutation)}
    violates_edge = any(
        position[prereq] > position[node] for node in nodes for prereq in edges[node]
    )

    violations = validate_suggested_path(permutation, nodes, edges)
    has_order_violation = any(v.rule is DagRule.PATH_ORDER for v in violations)

    # A permutation is a complete, duplicate-free cover, so there is never a V3
    # coverage violation; V4 fires iff some prereq edge is out of order.
    assert all(v.rule is not DagRule.PATH_COVERAGE for v in violations)
    assert has_order_violation == violates_edge


@given(acyclic_graphs())
def test_dags_never_have_dangling_prereqs(
    graph: tuple[set[str], dict[str, list[str]]],
) -> None:
    nodes, edges = graph
    # Every edge target is a real node by construction.
    assert find_dangling_prereqs(nodes, edges) == []


@given(dags_with_at_least_one_edge())
def test_replacing_a_prereq_with_a_ghost_is_always_dangling(
    graph: tuple[set[str], dict[str, list[str]]],
) -> None:
    nodes, edges = graph
    perturbed = {node: list(prereqs) for node, prereqs in edges.items()}
    perturbed["sub_1"] = ["sub_ghost"]  # sub_1 had at least the sub_0 edge

    violations = find_dangling_prereqs(nodes, perturbed)

    assert any(
        violation.rule is DagRule.NO_DANGLING_PREREQ and "sub_ghost" in violation.ids
        for violation in violations
    )


def test_report_and_violation_are_equality_comparable_value_types() -> None:
    # Value types (frozen dataclasses): tests assert on them by value equality.
    assert CycleReport(cycle=["sub_x", "sub_x"]) == CycleReport(cycle=["sub_x", "sub_x"])
    violation = RuleViolation(rule=DagRule.PATH_ORDER, ids=["sub_a", "sub_b"], message="m")
    assert violation == RuleViolation(rule=DagRule.PATH_ORDER, ids=["sub_a", "sub_b"], message="m")
