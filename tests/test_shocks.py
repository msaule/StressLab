from __future__ import annotations

from stresslab.des.node import NodeState
from stresslab.shocks.base import Shock, apply_shock, remove_shock
from stresslab.systemspec.schema import NodeSpec, ServiceTimeConfig


def test_capacity_shock_application_and_removal_restores_state():
    node = NodeSpec(
        id="imaging",
        servers=4,
        service_time=ServiceTimeConfig(distribution="deterministic", value=5),
    )
    state = NodeState(spec=node, effective_servers=node.servers, effective_buffer_capacity=None)
    shock = Shock(id="loss", type="capacity_fraction", target="imaging", start=0, duration=5, fraction=0.5)
    apply_shock(state, shock, now=0)
    assert state.effective_servers == 2
    remove_shock(state, shock, now=5)
    assert state.effective_servers == 4
