"""Routing decisions for completed jobs."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from stresslab.des.node import EdgeState
from stresslab.systemspec.schema import ResolvedSystemSpec


def choose_downstream_edge(
    spec: ResolvedSystemSpec,
    edge_states: dict[str, EdgeState],
    node_id: str,
    rng: np.random.Generator,
) -> EdgeState | None:
    """Choose the next enabled edge using normalized probabilities."""

    candidates = []
    total = 0.0
    for edge in spec.outgoing_edges.get(node_id, []):
        edge_key = f"{edge.from_node}->{edge.to_node}"
        edge_state = edge_states[edge_key]
        if not edge_state.enabled:
            continue
        probability = max(edge.routing.probability, 0.0)
        if probability <= 0:
            continue
        candidates.append((edge_state, probability))
        total += probability
    if not candidates:
        return None
    draw = rng.random()
    if total < 1.0 and draw > total:
        return None
    threshold = draw * total if total > 0 else 0.0
    cumulative = 0.0
    for edge_state, probability in candidates:
        cumulative += probability
        if threshold <= cumulative:
            return edge_state
    return candidates[-1][0]


def enabled_edge_names(edges: Sequence[EdgeState]) -> list[str]:
    """Return enabled edge identifiers."""

    return [f"{edge.spec.from_node}->{edge.spec.to_node}" for edge in edges if edge.enabled]
