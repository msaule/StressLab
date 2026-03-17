"""Deployment-delay sensitivity analysis for regime-aware response plans."""

from __future__ import annotations

import numpy as np

from stresslab.des import Simulator
from stresslab.models import (
    ClusterResponseRecommendation,
    ResponseTimingPoint,
    ResponseTimingSummary,
    ScenarioClusterAssignment,
    ScenarioSummary,
)
from stresslab.optimize.deployment_replay import run_scenario_with_deployment
from stresslab.search.common import apply_shock_vector
from stresslab.systemspec import resolve_spec
from stresslab.systemspec.schema import SystemSpec

_TIMING_FRACTIONS = (0.0, 0.1, 0.2, 0.35, 0.5, 0.7, 1.0)


def evaluate_response_timing(
    *,
    spec: SystemSpec,
    untreated: list[ScenarioSummary],
    scenario_clusters: list[ScenarioClusterAssignment],
    cluster_response_plan: list[ClusterResponseRecommendation],
    seed: int,
    deployment_fractions: tuple[float, ...] = _TIMING_FRACTIONS,
) -> tuple[ResponseTimingSummary | None, list[ResponseTimingPoint]]:
    """Measure how regime-plan value decays as deployment is delayed."""

    if not untreated or not scenario_clusters or not cluster_response_plan:
        return None, []

    fractions = tuple(
        sorted({min(max(float(fraction), 0.0), 1.0) for fraction in deployment_fractions} | {0.0, 1.0})
    )
    cluster_by_scenario = {assignment.scenario_id: assignment.cluster_id for assignment in scenario_clusters}
    plan_by_cluster = {row.cluster_id: row for row in cluster_response_plan}
    ordered_clusters = sorted({assignment.cluster_id for assignment in scenario_clusters})
    if not ordered_clusters:
        return None, []

    timing: dict[str, tuple[float, float | None]] = {}
    for scenario in untreated:
        timing[scenario.scenario_id] = _scenario_runtime_timing(spec, scenario, seed=seed)

    baseline_resilience = float(
        np.mean([scenario.metrics.get("resilience_score", 0.0) for scenario in untreated])
    )
    baseline_fairness = float(
        np.mean([scenario.metrics.get("fairness_score", 0.0) for scenario in untreated])
    )
    points: list[ResponseTimingPoint] = []

    for fraction in fractions:
        resilience_values: list[float] = []
        fairness_values: list[float] = []
        failure_values: list[float] = []
        prevention_values: list[float] = []
        pre_degradation_flags: list[float] = []
        lead_times: list[float] = []
        for scenario in untreated:
            true_cluster = cluster_by_scenario.get(scenario.scenario_id)
            if true_cluster is None:
                continue
            plan_row = plan_by_cluster.get(true_cluster)
            selected_ids = (
                [plan_row.selected_intervention_id]
                if plan_row is not None and plan_row.selected_intervention_id
                else []
            )
            horizon, first_degraded_time = timing[scenario.scenario_id]
            decision_time = horizon * fraction
            treated = run_scenario_with_deployment(
                spec,
                scenario,
                intervention_ids=selected_ids,
                decision_time=decision_time,
                seed=seed,
            )
            resilience = float(treated.metrics.get("resilience_score", scenario.metrics.get("resilience_score", 0.0)))
            fairness = float(treated.metrics.get("fairness_score", scenario.metrics.get("fairness_score", 0.0)))
            failure = float(treated.failure_triggered)
            lead_time = first_degraded_time - decision_time if first_degraded_time is not None else None
            pre_degradation = bool(first_degraded_time is None or decision_time <= first_degraded_time + 1e-9)
            resilience_values.append(resilience)
            fairness_values.append(fairness)
            failure_values.append(failure)
            prevention_values.append(max(0.0, float(scenario.failure_triggered) - failure))
            pre_degradation_flags.append(float(pre_degradation))
            if lead_time is not None:
                lead_times.append(lead_time)

        if not resilience_values:
            continue
        points.append(
            ResponseTimingPoint(
                deployment_fraction=fraction,
                deployment_time=float(spec.clock.end - spec.clock.start) * fraction,
                scenario_count=len(resilience_values),
                expected_resilience=float(np.mean(resilience_values)),
                expected_fairness_score=float(np.mean(fairness_values)),
                expected_failure_rate=float(np.mean(failure_values)),
                failure_prevention_rate=float(np.mean(prevention_values)),
                mean_resilience_gain=float(np.mean(resilience_values) - baseline_resilience),
                mean_fairness_gain=float(np.mean(fairness_values) - baseline_fairness),
                pre_degradation_deployment_rate=float(np.mean(pre_degradation_flags)),
                mean_lead_time_to_degradation=(
                    float(np.mean(lead_times))
                    if lead_times
                    else None
                ),
            )
        )

    if not points:
        return None, []

    best_point = max(points, key=lambda point: point.expected_resilience)
    zero_delay_point = min(points, key=lambda point: point.deployment_fraction)
    end_horizon_point = max(points, key=lambda point: point.deployment_fraction)
    summary = ResponseTimingSummary(
        method="perfect_information_deployment_replay",
        scenario_count=len(untreated),
        cluster_count=len(ordered_clusters),
        baseline_expected_resilience=baseline_resilience,
        zero_delay_resilience=zero_delay_point.expected_resilience,
        zero_delay_fairness_score=zero_delay_point.expected_fairness_score,
        best_deployment_fraction=best_point.deployment_fraction,
        best_expected_resilience=best_point.expected_resilience,
        best_failure_prevention_rate=best_point.failure_prevention_rate,
        latest_high_value_fraction=_latest_fraction_above(points, baseline_resilience, retention=0.9),
        resilience_half_life_fraction=_latest_fraction_above(points, baseline_resilience, retention=0.5),
        end_horizon_resilience=end_horizon_point.expected_resilience,
        response_value_decay=max(
            best_point.expected_resilience - end_horizon_point.expected_resilience,
            0.0,
        ),
        pre_degradation_rate_at_best=best_point.pre_degradation_deployment_rate,
    )
    points.sort(key=lambda point: point.deployment_fraction)
    return summary, points


def _scenario_runtime_timing(
    spec: SystemSpec,
    scenario: ScenarioSummary,
    *,
    seed: int,
) -> tuple[float, float | None]:
    scenario_spec = apply_shock_vector(spec, scenario.shock_vector)
    resolved = resolve_spec(scenario_spec)
    simulator = Simulator(resolved, seed=seed, baseline_metrics={})
    simulator.run()
    degraded_times = [
        state.first_degraded_time
        for state in simulator.node_states.values()
        if state.first_degraded_time is not None
    ]
    degraded_times.extend(
        state.first_degraded_time
        for state in simulator.edge_states.values()
        if state.first_degraded_time is not None
    )
    return (
        float(spec.clock.end - spec.clock.start),
        min(degraded_times) if degraded_times else None,
    )


def _latest_fraction_above(
    points: list[ResponseTimingPoint],
    baseline_resilience: float,
    *,
    retention: float,
) -> float:
    reference = max(point.expected_resilience for point in points)
    improvement = reference - baseline_resilience
    if improvement <= 1e-9:
        return max(point.deployment_fraction for point in points)
    threshold = baseline_resilience + retention * improvement
    eligible = [
        point.deployment_fraction
        for point in points
        if point.expected_resilience >= threshold - 1e-9
    ]
    if not eligible:
        return min(point.deployment_fraction for point in points)
    return max(eligible)
