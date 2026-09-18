from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

Trace = tuple[str, ...]

CanonicalMarking = tuple[tuple[int, int], ...]


def _canonical(counts: dict[int, int]) -> CanonicalMarking:
    return tuple(sorted((place, count) for place, count in counts.items() if count))


@dataclass
class ReachabilityGraph:
    status: str
    initial: int = -1
    accepting: frozenset[int] = frozenset()
    # edges[state] = list of (label_or_None, target_state); label is None for
    # a silent (epsilon) transition.
    edges: list[list[tuple[str | None, int]]] = field(default_factory=list)
    state_count: int = 0
    elapsed_seconds: float = 0.0


def build_reachability_graph(
    net: Any,
    initial_marking: Any,
    final_marking: Any,
    state_limit: int = 200_000,
    time_limit_seconds: float = 120.0,
) -> ReachabilityGraph:
    """Build the epsilon-NFA over reachable markings.

    Silent Petri-net transitions become ``None``-labeled epsilon edges in the
    same graph, per Section 6.1 of experiments.MD: reachability, epsilon
    behavior, and the accepting predicate are the same structure, so no
    separate epsilon-NFA construction step is needed.
    """
    places = sorted(net.places, key=lambda place: place.name)
    place_index = {place: index for index, place in enumerate(places)}

    transitions = []
    for transition in net.transitions:
        inputs = [(place_index[arc.source], arc.weight) for arc in transition.in_arcs]
        outputs = [(place_index[arc.target], arc.weight) for arc in transition.out_arcs]
        transitions.append((transition.label, inputs, outputs))

    def marking_counts(marking: Any) -> dict[int, int]:
        return {place_index[place]: count for place, count in marking.items() if count}

    start = _canonical(marking_counts(initial_marking))
    target = _canonical(marking_counts(final_marking))

    state_id: dict[CanonicalMarking, int] = {start: 0}
    edges: list[list[tuple[str | None, int]]] = [[]]
    accepting: set[int] = set()
    if start == target:
        accepting.add(0)

    started = time.perf_counter()
    frontier: deque[CanonicalMarking] = deque([start])
    while frontier:
        if time.perf_counter() - started > time_limit_seconds:
            return ReachabilityGraph(status="reachability_timeout", elapsed_seconds=time.perf_counter() - started)
        marking = frontier.popleft()
        source_id = state_id[marking]
        current = dict(marking)
        for label, inputs, outputs in transitions:
            if not all(current.get(place, 0) >= weight for place, weight in inputs):
                continue
            successor = dict(current)
            for place, weight in inputs:
                successor[place] -= weight
            for place, weight in outputs:
                successor[place] = successor.get(place, 0) + weight
            canonical_successor = _canonical(successor)
            target_id = state_id.get(canonical_successor)
            if target_id is None:
                if len(state_id) >= state_limit:
                    return ReachabilityGraph(status="reachability_state_limit", elapsed_seconds=time.perf_counter() - started)
                target_id = len(state_id)
                state_id[canonical_successor] = target_id
                edges.append([])
                if canonical_successor == target:
                    accepting.add(target_id)
                frontier.append(canonical_successor)
            edges[source_id].append((label, target_id))

    return ReachabilityGraph(
        status="ok",
        initial=0,
        accepting=frozenset(accepting),
        edges=edges,
        state_count=len(state_id),
        elapsed_seconds=time.perf_counter() - started,
    )


@dataclass
class DeterministicAutomaton:
    status: str
    initial: int = -1
    accepting: frozenset[int] = frozenset()
    # transitions[state][label] = target_state
    transitions: list[dict[str, int]] = field(default_factory=list)
    state_count: int = 0
    alphabet: frozenset[str] = frozenset()


def _epsilon_closures(graph: ReachabilityGraph) -> list[frozenset[int]]:
    closures: list[frozenset[int]] = [frozenset()] * graph.state_count
    for state in range(graph.state_count):
        visited = {state}
        stack = [state]
        while stack:
            current = stack.pop()
            for label, target in graph.edges[current]:
                if label is None and target not in visited:
                    visited.add(target)
                    stack.append(target)
        closures[state] = frozenset(visited)
    return closures


def determinize(
    graph: ReachabilityGraph,
    state_limit: int = 200_000,
    time_limit_seconds: float = 120.0,
) -> DeterministicAutomaton:
    """Subset-construction determinization over the epsilon-NFA.

    Only labels actually reachable from a subset are explored, so the
    resulting DFA's alphabet is the model's own visible label set, not the
    full log alphabet.
    """
    if graph.status != "ok":
        return DeterministicAutomaton(status=graph.status)

    closures = _epsilon_closures(graph)
    start = closures[graph.initial]

    subset_id: dict[frozenset[int], int] = {start: 0}
    transitions: list[dict[str, int]] = [{}]
    accepting: set[int] = set()
    if start & graph.accepting:
        accepting.add(0)
    alphabet: set[str] = set()

    started = time.perf_counter()
    frontier: deque[frozenset[int]] = deque([start])
    while frontier:
        if time.perf_counter() - started > time_limit_seconds:
            return DeterministicAutomaton(status="reachability_timeout")
        subset = frontier.popleft()
        source_id = subset_id[subset]
        moves: dict[str, set[int]] = {}
        for nfa_state in subset:
            for label, target in graph.edges[nfa_state]:
                if label is not None:
                    moves.setdefault(label, set()).add(target)
        for label, targets in moves.items():
            alphabet.add(label)
            successor = frozenset().union(*(closures[state] for state in targets))
            target_id = subset_id.get(successor)
            if target_id is None:
                if len(subset_id) >= state_limit:
                    return DeterministicAutomaton(status="determinization_state_limit")
                target_id = len(subset_id)
                subset_id[successor] = target_id
                transitions.append({})
                if successor & graph.accepting:
                    accepting.add(target_id)
                frontier.append(successor)
            transitions[source_id][label] = target_id

    return DeterministicAutomaton(
        status="ok",
        initial=0,
        accepting=frozenset(accepting),
        transitions=transitions,
        state_count=len(subset_id),
        alphabet=frozenset(alphabet),
    )


def accepts(dfa: DeterministicAutomaton, trace: Trace) -> bool:
    if dfa.status != "ok":
        raise ValueError(f"Automaton is not complete: {dfa.status}")
    state = dfa.initial
    for symbol in trace:
        successors = dfa.transitions[state]
        if symbol not in successors:
            return False
        state = successors[symbol]
    return state in dfa.accepting


def batch_membership(dfa: DeterministicAutomaton, traces: Any) -> dict[Trace, bool]:
    return {trace: accepts(dfa, trace) for trace in traces}


def productive_states(dfa: DeterministicAutomaton) -> frozenset[int]:
    """States both reachable from the initial state and able to reach an
    accepting state; the subgraph induced on these states is what Section 6.4
    calls the "productive DFA" whose acyclicity permits an exact finite sum."""
    if dfa.status != "ok":
        return frozenset()
    reverse: dict[int, set[int]] = {state: set() for state in range(dfa.state_count)}
    for state, moves in enumerate(dfa.transitions):
        for target in moves.values():
            reverse[target].add(state)

    reachable = {dfa.initial}
    stack = [dfa.initial]
    while stack:
        current = stack.pop()
        for target in dfa.transitions[current].values():
            if target not in reachable:
                reachable.add(target)
                stack.append(target)

    co_reachable: set[int] = set(dfa.accepting)
    stack = list(dfa.accepting)
    while stack:
        current = stack.pop()
        for predecessor in reverse[current]:
            if predecessor not in co_reachable:
                co_reachable.add(predecessor)
                stack.append(predecessor)

    return frozenset(reachable & co_reachable)


def is_acyclic(dfa: DeterministicAutomaton, states: frozenset[int]) -> bool:
    """Kahn's algorithm restricted to the given state subset and edges that
    stay within it."""
    indegree = {state: 0 for state in states}
    adjacency: dict[int, list[int]] = {state: [] for state in states}
    for state in states:
        for target in dfa.transitions[state].values():
            if target in states:
                adjacency[state].append(target)
                indegree[target] += 1
    queue = deque(state for state in states if indegree[state] == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return visited == len(states)


def max_accepted_length(dfa: DeterministicAutomaton, states: frozenset[int]) -> int:
    """Longest path (edge count) from the initial state to any accepting
    state, restricted to an acyclic productive subgraph. Requires
    ``is_acyclic(dfa, states)``."""
    order: list[int] = []
    indegree = {state: 0 for state in states}
    adjacency: dict[int, list[int]] = {state: [] for state in states}
    for state in states:
        for target in dfa.transitions[state].values():
            if target in states:
                adjacency[state].append(target)
                indegree[target] += 1
    queue = deque(state for state in states if indegree[state] == 0)
    while queue:
        current = queue.popleft()
        order.append(current)
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    longest = {state: (0 if state == dfa.initial else -1) for state in states}
    longest[dfa.initial] = 0
    best = 0
    for state in order:
        if longest[state] < 0:
            continue
        if state in dfa.accepting:
            best = max(best, longest[state])
        for target in adjacency[state]:
            if longest[state] + 1 > longest[target]:
                longest[target] = longest[state] + 1
    return best
