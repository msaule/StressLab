from __future__ import annotations

import numpy as np

from stresslab.des.node import EdgeState
from stresslab.des.routing import choose_downstream_edge
from stresslab.systemspec.schema import (
    ArrivalProcessConfig,
    ArrivalSpec,
    ClockConfig,
    EdgeSpec,
    NodeSpec,
    ResolvedSystemSpec,
    ServiceTimeConfig,
    SystemMeta,
    SystemSpec,
)


def test_routing_ignores_disabled_edges():
    spec = SystemSpec(
        system=SystemMeta(name="routing", domain="test"),
        clock=ClockConfig(end=10),
        nodes=[
            NodeSpec(id="a", service_time=ServiceTimeConfig(distribution="deterministic", value=1)),
            NodeSpec(id="b", service_time=ServiceTimeConfig(distribution="deterministic", value=1)),
            NodeSpec(id="c", service_time=ServiceTimeConfig(distribution="deterministic", value=1)),
        ],
        edges=[
            EdgeSpec.model_validate({"from": "a", "to": "b", "routing": {"probability": 0.7}}),
            EdgeSpec.model_validate({"from": "a", "to": "c", "routing": {"probability": 0.3}}),
        ],
        arrivals=[ArrivalSpec(node="a", process=ArrivalProcessConfig(type="poisson", rate=0.1))],
    )
    resolved = ResolvedSystemSpec(
        spec=spec,
        node_index={node.id: node for node in spec.nodes},
        outgoing_edges={"a": spec.edges, "b": [], "c": []},
        incoming_edges={"a": [], "b": [spec.edges[0]], "c": [spec.edges[1]]},
        class_priorities={},
    )
    edge_states = {
        "a->b": EdgeState(spec=spec.edges[0], enabled=False, travel_time=0.0, transfer_capacity=None),
        "a->c": EdgeState(spec=spec.edges[1], enabled=True, travel_time=0.0, transfer_capacity=None),
    }
    chosen = choose_downstream_edge(resolved, edge_states, "a", np.random.default_rng(3))
    assert chosen is not None
    assert chosen.spec.to_node == "c"
