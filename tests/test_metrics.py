from __future__ import annotations

from stresslab.des.metrics import summarize_metrics
from stresslab.des.node import NodeState
from stresslab.systemspec.schema import (
    ClockConfig,
    NodeSpec,
    ResolvedSystemSpec,
    ServiceTimeConfig,
    SystemMeta,
    SystemSpec,
)


def test_summarize_metrics_includes_throughput_efficiency():
    spec = SystemSpec(
        system=SystemMeta(name="metrics", domain="test"),
        clock=ClockConfig(end=100),
        nodes=[
            NodeSpec(
                id="queue",
                servers=1,
                service_time=ServiceTimeConfig(distribution="deterministic", value=5),
            )
        ],
    )
    resolved = ResolvedSystemSpec(
        spec=spec,
        node_index={spec.nodes[0].id: spec.nodes[0]},
        outgoing_edges={"queue": []},
        incoming_edges={"queue": []},
        class_priorities={},
    )
    state = NodeState(spec=spec.nodes[0], effective_servers=1, effective_buffer_capacity=None)
    state.completion_count = 8
    state.arrival_count = 10
    metrics, node_metrics, class_metrics = summarize_metrics(
        resolved,
        {"queue": state},
        {},
        event_count=10,
        horizon=100,
        departed_jobs=8,
        external_arrivals=10,
        external_arrival_class_counts={"default": 10},
        departed_class_counts={"default": 8},
    )
    assert metrics["throughput_efficiency"] == 0.8
    assert "queue" in node_metrics
    assert class_metrics["default"]["throughput_efficiency"] == 0.8


def test_summarize_metrics_computes_fairness_gaps():
    spec = SystemSpec(
        system=SystemMeta(name="metrics_fairness", domain="test"),
        clock=ClockConfig(end=100),
        classes=[],
        nodes=[
            NodeSpec(
                id="queue",
                servers=1,
                service_time=ServiceTimeConfig(distribution="deterministic", value=5),
            )
        ],
    )
    resolved = ResolvedSystemSpec(
        spec=spec,
        node_index={spec.nodes[0].id: spec.nodes[0]},
        outgoing_edges={"queue": []},
        incoming_edges={"queue": []},
        class_priorities={"fast": 0, "slow": 1},
    )
    state = NodeState(spec=spec.nodes[0], effective_servers=1, effective_buffer_capacity=None)
    state.class_wait_times = {"fast": [1.0, 2.0], "slow": [8.0, 9.0]}
    state.class_dropped_counts = {"fast": 0, "slow": 1}
    metrics, _, class_metrics = summarize_metrics(
        resolved,
        {"queue": state},
        {},
        event_count=10,
        horizon=100,
        departed_jobs=6,
        external_arrivals=8,
        external_arrival_class_counts={"fast": 4, "slow": 4},
        departed_class_counts={"fast": 4, "slow": 2},
        baseline_metrics={"fairness_score": 1.0},
    )
    assert metrics["fairness_score"] < 1.0
    assert metrics["fairness_degradation"] > 0.0
    assert metrics["wait_inequity"] > 0.0
    assert metrics["priority_wait_gradient"] > 0.0
    assert class_metrics["slow"]["mean_wait"] > class_metrics["fast"]["mean_wait"]
