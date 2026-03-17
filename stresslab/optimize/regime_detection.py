"""Signal-based regime detection for response-map evaluation."""

from __future__ import annotations

from collections import Counter

import numpy as np

from stresslab.models import (
    ClusterResponseRecommendation,
    RegimeDetectionScenarioResult,
    RegimeDetectionSummary,
    ScenarioClusterAssignment,
    ScenarioSummary,
)

_OBSERVED_METRICS = (
    "throughput",
    "mean_wait",
    "blocked_transfers",
    "recovery_time",
    "queue_integral",
    "throughput_loss",
    "fairness_score",
    "wait_inequity",
    "drop_inequity",
)


def evaluate_regime_detection(
    *,
    untreated: list[ScenarioSummary],
    scenario_clusters: list[ScenarioClusterAssignment],
    cluster_response_plan: list[ClusterResponseRecommendation],
    treated_by_intervention: dict[str, list[ScenarioSummary]],
    regime_plan_summary,
    seed: int,
    noise_scale: float = 0.12,
    trials_per_scenario: int = 32,
) -> tuple[RegimeDetectionSummary | None, list[RegimeDetectionScenarioResult], list[dict[str, object]]]:
    """Evaluate a noisy leave-one-out detector against a regime response plan."""

    if not untreated or not scenario_clusters or not cluster_response_plan:
        return None, [], []

    scenario_order = [scenario.scenario_id for scenario in untreated]
    cluster_by_scenario = {
        assignment.scenario_id: assignment.cluster_id
        for assignment in scenario_clusters
    }
    label_by_cluster = {
        assignment.cluster_id: assignment.cluster_label
        for assignment in scenario_clusters
    }
    ordered_clusters = sorted({assignment.cluster_id for assignment in scenario_clusters})
    if not ordered_clusters:
        return None, [], []
    plan_by_cluster = {
        row.cluster_id: row
        for row in cluster_response_plan
    }
    treated_lookup = {
        intervention_id: {scenario.scenario_id: scenario for scenario in summaries}
        for intervention_id, summaries in treated_by_intervention.items()
    }

    features = np.asarray([_feature_vector(scenario) for scenario in untreated], dtype=float)
    feature_scale = np.ptp(features, axis=0)
    feature_scale[feature_scale <= 1e-9] = 1.0
    rng = np.random.default_rng(seed + 311)

    scenario_rows: list[RegimeDetectionScenarioResult] = []
    confusion_counts = {
        (true_cluster, predicted_cluster): 0
        for true_cluster in ordered_clusters
        for predicted_cluster in ordered_clusters
    }
    detection_resilience: list[float] = []
    detection_fairness: list[float] = []
    detection_failure_flags: list[float] = []
    detection_prevented: list[float] = []

    for index, scenario in enumerate(untreated):
        true_cluster = cluster_by_scenario.get(scenario.scenario_id)
        if true_cluster is None:
            continue
        trial_predictions: list[str] = []
        trial_confidences: list[float] = []
        trial_true_probabilities: list[float] = []
        trial_interventions: list[str | None] = []
        trial_labels: list[str | None] = []
        trial_sources: list[str | None] = []
        trial_resilience: list[float] = []
        trial_fairness: list[float] = []
        trial_failure_flags: list[float] = []
        trial_prevented: list[float] = []

        for _ in range(trials_per_scenario):
            observed = features[index] + rng.normal(0.0, feature_scale * noise_scale)
            predicted_cluster, confidence, true_probability = _predict_cluster(
                observed,
                features=features,
                scenario_index=index,
                ordered_clusters=ordered_clusters,
                cluster_by_scenario=cluster_by_scenario,
                scenario_order=scenario_order,
                true_cluster=true_cluster,
            )
            confusion_counts[(true_cluster, predicted_cluster)] += 1
            plan_row = plan_by_cluster.get(predicted_cluster)
            intervention_id = plan_row.selected_intervention_id if plan_row is not None else None
            treated = (
                treated_lookup.get(intervention_id, {}).get(scenario.scenario_id, scenario)
                if intervention_id is not None
                else scenario
            )
            trial_predictions.append(predicted_cluster)
            trial_confidences.append(confidence)
            trial_true_probabilities.append(true_probability)
            trial_interventions.append(intervention_id)
            trial_labels.append(plan_row.selected_label if plan_row is not None else None)
            trial_sources.append(plan_row.selected_source if plan_row is not None else None)
            trial_resilience.append(float(treated.metrics.get("resilience_score", 0.0)))
            trial_fairness.append(float(treated.metrics.get("fairness_score", 0.0)))
            trial_failure_flags.append(float(treated.failure_triggered))
            trial_prevented.append(float(scenario.failure_triggered and not treated.failure_triggered))

        predicted_cluster = Counter(trial_predictions).most_common(1)[0][0]
        selected_intervention = Counter(trial_interventions).most_common(1)[0][0]
        selected_label = Counter(trial_labels).most_common(1)[0][0]
        selected_source = Counter(trial_sources).most_common(1)[0][0]
        scenario_rows.append(
            RegimeDetectionScenarioResult(
                scenario_id=scenario.scenario_id,
                true_cluster_id=true_cluster,
                true_cluster_label=label_by_cluster.get(true_cluster, true_cluster),
                predicted_cluster_id=predicted_cluster,
                predicted_cluster_label=label_by_cluster.get(predicted_cluster, predicted_cluster),
                prediction_accuracy=float(np.mean([prediction == true_cluster for prediction in trial_predictions])),
                mean_confidence=float(np.mean(trial_confidences)),
                true_cluster_probability=float(np.mean(trial_true_probabilities)),
                selected_intervention_id=selected_intervention,
                selected_label=selected_label,
                selected_source=selected_source,
                expected_resilience=float(np.mean(trial_resilience)),
                expected_fairness_score=float(np.mean(trial_fairness)),
                expected_failure_rate=float(np.mean(trial_failure_flags)),
                failure_prevention_rate=float(np.mean(trial_prevented)),
            )
        )
        detection_resilience.extend(trial_resilience)
        detection_fairness.extend(trial_fairness)
        detection_failure_flags.extend(trial_failure_flags)
        detection_prevented.extend(trial_prevented)

    confusion_rows = _confusion_rows(
        confusion_counts=confusion_counts,
        ordered_clusters=ordered_clusters,
        label_by_cluster=label_by_cluster,
        trials_per_scenario=trials_per_scenario,
        scenario_clusters=scenario_clusters,
    )
    if not scenario_rows:
        return None, [], confusion_rows

    baseline_failures = max(sum(1 for scenario in untreated if scenario.failure_triggered), 1)
    failure_prevention_rate = float(sum(detection_prevented)) / max(baseline_failures * trials_per_scenario, 1)
    summary = RegimeDetectionSummary(
        method="leave_one_out_noisy_centroid",
        noise_scale=noise_scale,
        trials_per_scenario=trials_per_scenario,
        scenario_count=len(scenario_rows),
        cluster_count=len(ordered_clusters),
        detection_accuracy=float(np.mean([row.prediction_accuracy for row in scenario_rows])),
        expected_resilience=float(np.mean(detection_resilience)) if detection_resilience else 0.0,
        expected_fairness_score=float(np.mean(detection_fairness)) if detection_fairness else 0.0,
        expected_failure_rate=float(np.mean(detection_failure_flags)) if detection_failure_flags else 0.0,
        failure_prevention_rate=failure_prevention_rate,
        resilience_regret=max(
            float(getattr(regime_plan_summary, "expected_resilience", 0.0))
            - (float(np.mean(detection_resilience)) if detection_resilience else 0.0),
            0.0,
        ),
        fairness_regret=max(
            float(getattr(regime_plan_summary, "expected_fairness_score", 0.0))
            - (float(np.mean(detection_fairness)) if detection_fairness else 0.0),
            0.0,
        ),
    )
    scenario_rows.sort(key=lambda row: (row.true_cluster_id, row.scenario_id))
    return summary, scenario_rows, confusion_rows


def _predict_cluster(
    observed: np.ndarray,
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
    distances = np.linalg.norm(centroid_matrix - observed[None, :], axis=1)
    predicted_index = int(np.argmin(distances))
    probabilities = _softmax_inverse_distance(distances)
    true_index = ordered_clusters.index(true_cluster)
    return (
        ordered_clusters[predicted_index],
        float(probabilities[predicted_index]),
        float(probabilities[true_index]),
    )


def _softmax_inverse_distance(distances: np.ndarray) -> np.ndarray:
    shifted = -distances
    shifted -= shifted.max()
    weights = np.exp(shifted)
    total = weights.sum()
    if total <= 1e-12:
        return np.full_like(weights, 1.0 / max(len(weights), 1))
    return weights / total


def _feature_vector(scenario: ScenarioSummary) -> list[float]:
    return [
        float(scenario.failure_triggered),
        *[float(scenario.metrics.get(metric, 0.0)) for metric in _OBSERVED_METRICS],
    ]


def _confusion_rows(
    *,
    confusion_counts: dict[tuple[str, str], int],
    ordered_clusters: list[str],
    label_by_cluster: dict[str, str],
    trials_per_scenario: int,
    scenario_clusters: list[ScenarioClusterAssignment],
) -> list[dict[str, object]]:
    scenario_counts = Counter(assignment.cluster_id for assignment in scenario_clusters)
    rows: list[dict[str, object]] = []
    for true_cluster in ordered_clusters:
        row_total = max(scenario_counts.get(true_cluster, 0) * trials_per_scenario, 1)
        for predicted_cluster in ordered_clusters:
            count = confusion_counts[(true_cluster, predicted_cluster)]
            rows.append(
                {
                    "true_cluster_id": true_cluster,
                    "true_cluster_label": label_by_cluster.get(true_cluster, true_cluster),
                    "predicted_cluster_id": predicted_cluster,
                    "predicted_cluster_label": label_by_cluster.get(predicted_cluster, predicted_cluster),
                    "count": count,
                    "row_rate": count / row_total,
                }
            )
    return rows
