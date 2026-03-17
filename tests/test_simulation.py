from __future__ import annotations

from stresslab.des import Simulator
from stresslab.optimize.deployment_replay import resolve_intervention_sequence
from stresslab.systemspec import load_spec, resolve_spec
from stresslab.systemspec.schema import (
    ArrivalProcessConfig,
    ArrivalSpec,
    ClockConfig,
    EdgeSpec,
    FlowClassSpec,
    NodeSpec,
    PolicyScheduleSpec,
    PolicyStageSpec,
    ServiceTimeConfig,
    SystemMeta,
    SystemSpec,
)


def test_simulator_produces_nonnegative_metrics(toy_spec_path):
    spec = load_spec(toy_spec_path)
    simulator = Simulator(resolve_spec(spec), seed=spec.seed)
    result = simulator.run()
    assert result.status == "completed"
    assert result.metrics["queue_integral"] >= 0
    assert result.metrics["throughput"] >= 0
    assert result.metrics["mean_wait"] >= 0
    assert result.metrics["fairness_score"] >= 0
    assert result.class_metrics


def test_simulator_is_deterministic_for_fixed_seed(toy_spec_path):
    spec = load_spec(toy_spec_path)
    result_a = Simulator(resolve_spec(spec), seed=spec.seed).run()
    result_b = Simulator(resolve_spec(spec), seed=spec.seed).run()
    assert result_a.failure_triggered == result_b.failure_triggered
    assert result_a.metrics == result_b.metrics


def test_edge_capacity_creates_blocked_transfer_metrics():
    spec = SystemSpec(
        system=SystemMeta(name="edge_capacity", domain="test"),
        clock=ClockConfig(end=80),
        nodes=[
            NodeSpec(
                id="source",
                servers=2,
                service_time=ServiceTimeConfig(distribution="deterministic", value=1),
            ),
            NodeSpec(
                id="sink",
                servers=1,
                service_time=ServiceTimeConfig(distribution="deterministic", value=1),
            ),
        ],
        edges=[
            EdgeSpec.model_validate(
                {
                    "from": "source",
                    "to": "sink",
                    "travel_time": 1.0,
                    "transfer_capacity": 0.15,
                    "routing": {"probability": 1.0},
                }
            )
        ],
        arrivals=[
            ArrivalSpec(
                node="source",
                process=ArrivalProcessConfig(type="poisson", rate=0.6),
            )
        ],
        seed=7,
    )
    result = Simulator(resolve_spec(spec), seed=spec.seed).run()
    assert result.metrics["blocked_transfers"] > 0
    assert result.edge_metrics["source->sink"]["mean_delay"] >= 0


def test_scheduled_priority_policy_changes_class_wait_profile():
    baseline_spec = SystemSpec(
        system=SystemMeta(name="scheduled_policy", domain="test"),
        clock=ClockConfig(end=70),
        classes=[
            FlowClassSpec(id="urgent", priority=0),
            FlowClassSpec(id="routine", priority=1),
        ],
        nodes=[
            NodeSpec(
                id="triage",
                servers=1,
                queue_policy="fifo",
                priority_classes=["urgent", "routine"],
                buffer_capacity=50,
                service_time=ServiceTimeConfig(distribution="deterministic", value=3),
            )
        ],
        arrivals=[
            ArrivalSpec(
                node="triage",
                process=ArrivalProcessConfig(type="poisson", rate=0.48),
                class_mix={"urgent": 0.35, "routine": 0.65},
            )
        ],
        seed=17,
    )
    scheduled_spec = baseline_spec.model_copy(
        update={
            "policies": [
                PolicyScheduleSpec(
                    id="priority_surge",
                    target="triage",
                    action_type="priority_policy_change",
                    start=12,
                    duration=36,
                    replacement="priority",
                )
            ]
        }
    )
    baseline_result = Simulator(resolve_spec(baseline_spec), seed=baseline_spec.seed).run()
    scheduled_result = Simulator(resolve_spec(scheduled_spec), seed=scheduled_spec.seed).run()
    assert scheduled_result.metrics["policy_schedule_count"] == 1
    assert scheduled_result.metrics["policy_activation_count"] == 1
    assert scheduled_result.metrics["policy_active_time"] > 0
    assert scheduled_result.class_metrics["urgent"]["mean_wait"] < scheduled_result.class_metrics["routine"]["mean_wait"]
    assert scheduled_result.class_metrics["urgent"]["mean_wait"] <= baseline_result.class_metrics["urgent"]["mean_wait"]


def test_threshold_policy_activates_under_congestion():
    baseline_spec = SystemSpec(
        system=SystemMeta(name="adaptive_policy", domain="test"),
        clock=ClockConfig(end=90),
        classes=[
            FlowClassSpec(id="urgent", priority=0),
            FlowClassSpec(id="routine", priority=1),
        ],
        nodes=[
            NodeSpec(
                id="triage",
                servers=1,
                queue_policy="fifo",
                priority_classes=["urgent", "routine"],
                buffer_capacity=60,
                service_time=ServiceTimeConfig(distribution="deterministic", value=4),
            )
        ],
        arrivals=[
            ArrivalSpec(
                node="triage",
                process=ArrivalProcessConfig(type="poisson", rate=0.58),
                class_mix={"urgent": 0.35, "routine": 0.65},
            )
        ],
        seed=19,
    )
    adaptive_spec = baseline_spec.model_copy(
        update={
            "policies": [
                PolicyScheduleSpec(
                    id="adaptive_priority",
                    target="triage",
                    action_type="priority_policy_change",
                    mode="threshold",
                    replacement="priority",
                    trigger_metric="queue_length",
                    trigger_node="triage",
                    trigger_threshold=3,
                    clear_threshold=1,
                    min_active_duration=8,
                    cooldown=4,
                )
            ]
        }
    )
    baseline_result = Simulator(resolve_spec(baseline_spec), seed=baseline_spec.seed).run()
    adaptive_result = Simulator(resolve_spec(adaptive_spec), seed=adaptive_spec.seed).run()
    assert adaptive_result.metrics["policy_schedule_count"] == 1
    assert adaptive_result.metrics["policy_activation_count"] >= 1
    assert adaptive_result.metrics["adaptive_policy_activation_count"] >= 1
    assert adaptive_result.metrics["policy_active_time"] > 0
    assert adaptive_result.class_metrics["urgent"]["mean_wait"] <= baseline_result.class_metrics["urgent"]["mean_wait"]


def test_multistage_threshold_policy_escalates():
    spec = SystemSpec(
        system=SystemMeta(name="adaptive_ladder", domain="test"),
        clock=ClockConfig(end=90),
        nodes=[
            NodeSpec(
                id="gate",
                servers=1,
                queue_policy="fifo",
                buffer_capacity=60,
                service_time=ServiceTimeConfig(distribution="deterministic", value=1),
            ),
            NodeSpec(
                id="slow_lane",
                servers=1,
                service_time=ServiceTimeConfig(distribution="deterministic", value=6),
            ),
            NodeSpec(
                id="fast_lane",
                servers=2,
                service_time=ServiceTimeConfig(distribution="deterministic", value=1),
            ),
        ],
        edges=[
            EdgeSpec.model_validate({"from": "gate", "to": "slow_lane", "routing": {"probability": 0.8}}),
            EdgeSpec.model_validate({"from": "gate", "to": "fast_lane", "routing": {"probability": 0.2}}),
        ],
        arrivals=[
            ArrivalSpec(
                node="gate",
                process=ArrivalProcessConfig(type="poisson", rate=1.1),
            )
        ],
        policies=[
            PolicyScheduleSpec(
                id="adaptive_lane_ladder",
                target="gate->fast_lane",
                action_type="reroute_fraction",
                mode="threshold",
                delta=0.15,
                trigger_metric="queue_length",
                trigger_node="slow_lane",
                stages=[
                    PolicyStageSpec(
                        id="watch",
                        trigger_threshold=2,
                        clear_threshold=1,
                        action_type="reroute_fraction",
                        delta=0.15,
                    ),
                    PolicyStageSpec(
                        id="surge",
                        trigger_threshold=5,
                        clear_threshold=3,
                        action_type="reroute_fraction",
                        delta=0.35,
                    ),
                ],
                min_active_duration=5,
                cooldown=3,
            )
        ],
        seed=23,
    )
    simulator = Simulator(resolve_spec(spec), seed=spec.seed)
    result = simulator.run()
    assert result.metrics["adaptive_policy_activation_count"] >= 1
    assert result.metrics["policy_stage_change_count"] >= 1
    assert any(event["event"] == "stage_up" for event in simulator.policy_event_log)


def test_runtime_deployments_do_not_leak_between_runs():
    spec = load_spec("examples/healthcare/ed_basic.yml")
    simulator = Simulator(resolve_spec(spec), seed=spec.seed)

    baseline = simulator.run()
    deployment_result = simulator.run(
        deployments=[
            (30.0, intervention)
            for intervention in resolve_intervention_sequence(spec, ["add_ward_capacity"])
        ]
    )
    rerun = simulator.run()

    assert deployment_result.metrics["deployment_count"] >= 1
    assert rerun.failure_triggered == baseline.failure_triggered
    assert rerun.metrics == baseline.metrics
