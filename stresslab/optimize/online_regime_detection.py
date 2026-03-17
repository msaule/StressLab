"""Partial-observation regime detection and delayed-response evaluation."""

from __future__ import annotations

import numpy as np

from stresslab.des import Simulator
from stresslab.models import (
    ClusterResponseRecommendation,
    OnlineRegimeDetectionSummary,
    OnlineRegimeHorizonSummary,
    OnlineRegimeScenarioResult,
    ScenarioClusterAssignment,
    ScenarioSummary,
)
from stresslab.optimize.deployment_replay import run_scenario_with_deployment
from stresslab.search.common import apply_shock_vector
from stresslab.systemspec import resolve_spec
from stresslab.systemspec.schema import SystemSpec

_OBSERVATION_FRACTIONS = (0.2, 0.35, 0.5, 0.7, 1.0)


def evaluate_online_regime_detection(
    *,
    spec: SystemSpec,
    untreated: list[ScenarioSummary],
    scenario_clusters: list[ScenarioClusterAssignment],
    cluster_response_plan: list[ClusterResponseRecommendation],
    treated_by_intervention: dict[str, list[ScenarioSummary]],
    regime_plan_summary,
    seed: int,
    observation_fractions: tuple[float, ...] = _OBSERVATION_FRACTIONS,
    confidence_threshold: float = 0.6,
) -> tuple[
    OnlineRegimeDetectionSummary | None,
    list[OnlineRegimeScenarioResult],
    list[OnlineRegimeHorizonSummary],
]:
    """Evaluate early regime detection from partial run observations.

    Decision quality is evaluated by replaying the scenario and deploying the chosen
    intervention at the inferred decision time.
    """

    if not untreated or not scenario_clusters or not cluster_response_plan:
        return None, [], []

    fractions = tuple(sorted({min(max(float(fraction), 0.0), 1.0) for fraction in observation_fractions} | {1.0}))
    scenario_order = [scenario.scenario_id for scenario in untreated]
    cluster_by_scenario = {assignment.scenario_id: assignment.cluster_id for assignment in scenario_clusters}
    label_by_cluster = {assignment.cluster_id: assignment.cluster_label for assignment in scenario_clusters}
    ordered_clusters = sorted({assignment.cluster_id for assignment in scenario_clusters})
    if not ordered_clusters:
        return None, [], []

    observations: dict[str, dict[float, np.ndarray]] = {}
    timing: dict[str, tuple[float, float | None]] = {}
    for scenario in untreated:
        profile, horizon, first_degraded_time = _scenario_observations(
            spec,
            scenario,
            seed=seed,
            observation_fractions=fractions,
        )
        observations[scenario.scenario_id] = profile
        timing[scenario.scenario_id] = (horizon, first_degraded_time)

    predictions_by_fraction: dict[float, dict[str, tuple[str, float, float]]] = {}
    horizon_rows: list[OnlineRegimeHorizonSummary] = []
    for fraction in fractions:
        feature_matrix = np.asarray(
            [observations[scenario_id][fraction] for scenario_id in scenario_order],
            dtype=float,
        )
        fraction_predictions: dict[str, tuple[str, float, float]] = {}
        for index, scenario_id in enumerate(scenario_order):
            true_cluster = cluster_by_scenario[scenario_id]
            predicted_cluster, confidence, true_probability = _predict_cluster_leave_one_out(
                features=feature_matrix,
                scenario_index=index,
                ordered_clusters=ordered_clusters,
                cluster_by_scenario=cluster_by_scenario,
                scenario_order=scenario_order,
                true_cluster=true_cluster,
            )
            fraction_predictions[scenario_id] = (predicted_cluster, confidence, true_probability)
        predictions_by_fraction[fraction] = fraction_predictions
        accuracies = [
            float(fraction_predictions[scenario_id][0] == cluster_by_scenario[scenario_id])
            for scenario_id in scenario_order
        ]
        horizon = timing[scenario_order[0]][0] if scenario_order else 0.0
        horizon_rows.append(
            OnlineRegimeHorizonSummary(
                observation_fraction=fraction,
                observation_time=horizon * fraction,
                scenario_count=len(scenario_order),
                detection_accuracy=float(np.mean(accuracies)) if accuracies else 0.0,
                mean_confidence=float(
                    np.mean([fraction_predictions[scenario_id][1] for scenario_id in scenario_order])
                ) if scenario_order else 0.0,
                mean_true_cluster_probability=float(
                    np.mean([fraction_predictions[scenario_id][2] for scenario_id in scenario_order])
                ) if scenario_order else 0.0,
            )
        )

    plan_by_cluster = {row.cluster_id: row for row in cluster_response_plan}
    scenario_rows: list[OnlineRegimeScenarioResult] = []
    adjusted_resilience: list[float] = []
    adjusted_fairness: list[float] = []
    adjusted_failure_rate: list[float] = []
    adjusted_prevention_rate: list[float] = []
    decision_fractions: list[float] = []
    decision_confidences: list[float] = []
    pre_degradation_flags: list[float] = []
    prediction_correct_flags: list[float] = []

    for scenario in untreated:
        true_cluster = cluster_by_scenario.get(scenario.scenario_id)
        if true_cluster is None:
            continue
        decision_fraction = fractions[-1]
        predicted_cluster, confidence, true_probability = predictions_by_fraction[decision_fraction][scenario.scenario_id]
        for fraction in fractions:
            candidate_cluster, candidate_confidence, candidate_true_probability = predictions_by_fraction[fraction][scenario.scenario_id]
            predicted_cluster = candidate_cluster
            confidence = candidate_confidence
            true_probability = candidate_true_probability
            decision_fraction = fraction
            if candidate_confidence >= confidence_threshold or fraction >= 1.0 - 1e-9:
                break

        horizon, first_degraded_time = timing[scenario.scenario_id]
        decision_time = horizon * decision_fraction
        lead_time = (
            first_degraded_time - decision_time
            if first_degraded_time is not None
            else None
        )
        pre_degradation = bool(first_degraded_time is None or decision_time <= first_degraded_time + 1e-9)
        plan_row = plan_by_cluster.get(predicted_cluster)
        intervention_id = plan_row.selected_intervention_id if plan_row is not None else None
        treated = run_scenario_with_deployment(
            spec,
            scenario,
            intervention_ids=[intervention_id] if intervention_id is not None else [],
            decision_time=decision_time,
            seed=seed,
        )
        delay_factor = max(0.0, 1.0 - decision_fraction)
        baseline_resilience = float(scenario.metrics.get("resilience_score", 0.0))
        treated_resilience = float(treated.metrics.get("resilience_score", baseline_resilience))
        baseline_fairness = float(scenario.metrics.get("fairness_score", 0.0))
        treated_fairness = float(treated.metrics.get("fairness_score", baseline_fairness))
        baseline_failure = float(scenario.failure_triggered)
        treated_failure = float(treated.failure_triggered)
        delay_adjusted_resilience = treated_resilience
        delay_adjusted_fairness = treated_fairness
        delay_adjusted_failure = treated_failure
        delay_adjusted_prevention = max(0.0, baseline_failure - delay_adjusted_failure)

        scenario_rows.append(
            OnlineRegimeScenarioResult(
                scenario_id=scenario.scenario_id,
                true_cluster_id=true_cluster,
                true_cluster_label=label_by_cluster.get(true_cluster, true_cluster),
                predicted_cluster_id=predicted_cluster,
                predicted_cluster_label=label_by_cluster.get(predicted_cluster, predicted_cluster),
                decision_fraction=decision_fraction,
                decision_time=decision_time,
                first_degraded_time=first_degraded_time,
                lead_time_to_degradation=lead_time,
                pre_degradation_decision=pre_degradation,
                prediction_correct=predicted_cluster == true_cluster,
                decision_confidence=confidence,
                true_cluster_probability=true_probability,
                selected_intervention_id=intervention_id,
                selected_label=plan_row.selected_label if plan_row is not None else None,
                selected_source=plan_row.selected_source if plan_row is not None else None,
                delay_factor=delay_factor,
                delay_adjusted_resilience=delay_adjusted_resilience,
                delay_adjusted_fairness_score=delay_adjusted_fairness,
                delay_adjusted_failure_rate=delay_adjusted_failure,
                delay_adjusted_failure_prevention_rate=delay_adjusted_prevention,
            )
        )
        adjusted_resilience.append(delay_adjusted_resilience)
        adjusted_fairness.append(delay_adjusted_fairness)
        adjusted_failure_rate.append(delay_adjusted_failure)
        adjusted_prevention_rate.append(delay_adjusted_prevention)
        decision_fractions.append(decision_fraction)
        decision_confidences.append(confidence)
        pre_degradation_flags.append(float(pre_degradation))
        prediction_correct_flags.append(float(predicted_cluster == true_cluster))

    if not scenario_rows:
        return None, [], horizon_rows

    summary = OnlineRegimeDetectionSummary(
        method="online_partial_observation_centroid",
        confidence_threshold=confidence_threshold,
        scenario_count=len(scenario_rows),
        cluster_count=len(ordered_clusters),
        mean_decision_fraction=float(np.mean(decision_fractions)),
        mean_decision_time=float(
            np.mean([row.decision_time for row in scenario_rows])
        ),
        pre_degradation_decision_rate=float(np.mean(pre_degradation_flags)),
        detection_accuracy=float(np.mean(prediction_correct_flags)),
        mean_confidence=float(np.mean(decision_confidences)),
        expected_resilience=float(np.mean(adjusted_resilience)),
        expected_fairness_score=float(np.mean(adjusted_fairness)),
        expected_failure_rate=float(np.mean(adjusted_failure_rate)),
        failure_prevention_rate=float(np.mean(adjusted_prevention_rate)),
        resilience_regret=max(
            float(getattr(regime_plan_summary, "expected_resilience", 0.0)) - float(np.mean(adjusted_resilience)),
            0.0,
        ),
        fairness_regret=max(
            float(getattr(regime_plan_summary, "expected_fairness_score", 0.0)) - float(np.mean(adjusted_fairness)),
            0.0,
        ),
    )
    scenario_rows.sort(key=lambda row: (row.true_cluster_id, row.scenario_id))
    return summary, scenario_rows, horizon_rows


def _scenario_observations(
    spec: SystemSpec,
    scenario: ScenarioSummary,
    *,
    seed: int,
    observation_fractions: tuple[float, ...],
) -> tuple[dict[float, np.ndarray], float, float | None]:
    scenario_spec = apply_shock_vector(spec, scenario.shock_vector)
    resolved = resolve_spec(scenario_spec)
    simulator = Simulator(resolved, seed=seed, baseline_metrics={})
    simulator.run()
    start = float(spec.clock.start)
    horizon = float(spec.clock.end - start)
    profile = {
        fraction: _observation_feature_vector(simulator, start=start, until=start + horizon * fraction)
        for fraction in observation_fractions
    }
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
    first_degraded_time = min(degraded_times) if degraded_times else None
    return profile, horizon, first_degraded_time


def _observation_feature_vector(simulator: Simulator, *, start: float, until: float) -> np.ndarray:
    elapsed = max(until - start, 1e-9)
    queue_means: list[float] = []
    queue_currents: list[float] = []
    queue_maxima: list[float] = []
    utilization_means: list[float] = []
    utilization_currents: list[float] = []

    for state in simulator.node_states.values():
        queue_mean, queue_current, queue_maximum = _step_profile(
            state.queue_times,
            state.queue_lengths,
            start=start,
            until=until,
        )
        util_mean, util_current, _ = _step_profile(
            state.utilization_times,
            state.utilization_values,
            start=start,
            until=until,
        )
        queue_means.append(queue_mean)
        queue_currents.append(queue_current)
        queue_maxima.append(queue_maximum)
        utilization_means.append(util_mean)
        utilization_currents.append(util_current)

    active_queue_nodes = sum(1 for value in queue_currents if value > 0.0)
    saturated_nodes = sum(1 for value in utilization_currents if value >= 0.95)
    return np.asarray(
        [
            elapsed,
            float(np.mean(queue_means)) if queue_means else 0.0,
            float(np.max(queue_maxima)) if queue_maxima else 0.0,
            float(np.mean(queue_currents)) if queue_currents else 0.0,
            float(np.mean(utilization_means)) if utilization_means else 0.0,
            float(np.max(utilization_currents)) if utilization_currents else 0.0,
            float(active_queue_nodes) / max(len(queue_currents), 1),
            float(saturated_nodes) / max(len(utilization_currents), 1),
        ],
        dtype=float,
    )


def _step_profile(
    times: list[float],
    values: list[float],
    *,
    start: float,
    until: float,
) -> tuple[float, float, float]:
    if not times or not values:
        return 0.0, 0.0, 0.0
    current_value = float(values[0])
    area = 0.0
    maximum = current_value
    current_time = start
    for time, value in zip(times, values, strict=True):
        if time <= start:
            current_value = float(value)
            maximum = max(maximum, current_value)
            continue
        if time >= until:
            break
        area += max(0.0, time - current_time) * current_value
        current_time = float(time)
        current_value = float(value)
        maximum = max(maximum, current_value)
    area += max(0.0, until - current_time) * current_value
    return area / max(until - start, 1e-9), current_value, maximum

def _predict_cluster_leave_one_out(
    *,
    features: np.ndarray,
    scenario_index: int,
    ordered_clusters: list[str],
    cluster_by_scenario: dict[str, str],
    scenario_order: list[str],
    true_cluster: str,
) -> tuple[str, float, float]:
    centroids: list[np.ndarray] = []
    for cluster_id in ordered_clusters:
        member_indexes = [
            index
            for index, scenario_id in enumerate(scenario_order)
            if cluster_by_scenario.get(scenario_id) == cluster_id and index != scenario_index
        ]
        if not member_indexes:
            member_indexes = [
                index
                for index, scenario_id in enumerate(scenario_order)
                if cluster_by_scenario.get(scenario_id) == cluster_id
            ]
        if not member_indexes:
            centroids.append(np.zeros(features.shape[1], dtype=float))
        else:
            centroids.append(features[member_indexes].mean(axis=0))
    centroid_matrix = np.asarray(centroids, dtype=float)
    distances = np.linalg.norm(centroid_matrix - features[scenario_index][None, :], axis=1)
    predicted_index = int(np.argmin(distances))
    probabilities = _softmax_inverse_distance(distances)
    true_index = ordered_clusters.index(true_cluster)
    return ordered_clusters[predicted_index], float(probabilities[predicted_index]), float(probabilities[true_index])


def _softmax_inverse_distance(distances: np.ndarray) -> np.ndarray:
    shifted = -distances
    shifted -= shifted.max()
    weights = np.exp(shifted)
    total = weights.sum()
    if total <= 1e-12:
        return np.full_like(weights, 1.0 / max(len(weights), 1))
    return weights / total
