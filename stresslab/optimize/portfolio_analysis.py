"""Scenario-family analysis for robust optimization portfolios."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from stresslab.models import (
    InterventionCoverageSummary,
    PortfolioClusterCoverageSummary,
    ScenarioClusterAssignment,
    ScenarioClusterSummary,
    ScenarioSummary,
)


def cluster_scenarios(
    scenarios: list[ScenarioSummary],
    *,
    shock_defaults: dict[str, float] | None = None,
    max_clusters: int = 4,
) -> tuple[list[ScenarioClusterAssignment], list[ScenarioClusterSummary]]:
    """Group scenarios into deterministic failure families."""

    if not scenarios:
        return [], []

    rows, feature_matrix, shock_columns = _scenario_feature_matrix(
        scenarios,
        shock_defaults=shock_defaults or {},
    )
    normalized = _minmax_scale(feature_matrix)
    cluster_count = _cluster_count(normalized.shape[0], max_clusters=max_clusters)
    if cluster_count <= 1 or np.allclose(normalized, normalized[:1]):
        labels = np.zeros(len(scenarios), dtype=int)
    else:
        labels = _fit_kmedoids(normalized, cluster_count)

    clusters = {}
    for index, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(index)

    overall_wait = np.array([row["mean_wait"] for row in rows], dtype=float)
    overall_blocked = np.array([row["blocked_transfers"] for row in rows], dtype=float)
    overall_damage = np.array([row["damage_score"] for row in rows], dtype=float)
    ordering = sorted(
        clusters,
        key=lambda cluster: (
            -float(np.mean([rows[index]["damage_score"] for index in clusters[cluster]])),
            -float(np.mean([rows[index]["failure_triggered"] for index in clusters[cluster]])),
            min(rows[index]["scenario_id"] for index in clusters[cluster]),
        ),
    )
    remap = {cluster: rank for rank, cluster in enumerate(ordering, start=1)}

    assignments: list[ScenarioClusterAssignment] = []
    summaries: list[ScenarioClusterSummary] = []
    for cluster in ordering:
        scenario_indexes = clusters[cluster]
        cluster_rows = [rows[index] for index in scenario_indexes]
        cluster_matrix = normalized[scenario_indexes]
        representative_index = scenario_indexes[_cluster_representative(cluster_matrix)]
        cluster_id = f"cluster_{remap[cluster]:02d}"
        dominant_shock = _dominant_shock_dimension(cluster_rows, shock_columns)
        cluster_label = _cluster_label(
            cluster_rows,
            dominant_shock=dominant_shock,
            overall_wait=overall_wait,
            overall_blocked=overall_blocked,
            overall_damage=overall_damage,
        )
        for row in cluster_rows:
            assignments.append(
                ScenarioClusterAssignment(
                    scenario_id=row["scenario_id"],
                    cluster_id=cluster_id,
                    cluster_label=cluster_label,
                    source=row["source"],
                    failure_triggered=bool(row["failure_triggered"]),
                    shock_budget=row["shock_budget"],
                    damage_score=row["damage_score"],
                    resilience_score=row["resilience_score"],
                    throughput=row["throughput"],
                    mean_wait=row["mean_wait"],
                    blocked_transfers=row["blocked_transfers"],
                )
            )
        summaries.append(
            ScenarioClusterSummary(
                cluster_id=cluster_id,
                cluster_label=cluster_label,
                scenario_count=len(cluster_rows),
                representative_scenario_id=rows[representative_index]["scenario_id"],
                representative_source=rows[representative_index]["source"],
                dominant_shock_dimension=dominant_shock,
                failure_rate=float(np.mean([row["failure_triggered"] for row in cluster_rows])),
                mean_shock_budget=float(np.mean([row["shock_budget"] for row in cluster_rows])),
                mean_damage_score=float(np.mean([row["damage_score"] for row in cluster_rows])),
                mean_resilience_score=float(np.mean([row["resilience_score"] for row in cluster_rows])),
                mean_throughput=float(np.mean([row["throughput"] for row in cluster_rows])),
                mean_wait=float(np.mean([row["mean_wait"] for row in cluster_rows])),
                mean_blocked_transfers=float(
                    np.mean([row["blocked_transfers"] for row in cluster_rows])
                ),
            )
        )
    return assignments, summaries


def summarize_intervention_coverage(
    *,
    untreated: list[ScenarioSummary],
    treated_by_intervention: dict[str, list[ScenarioSummary]],
    scenario_clusters: list[ScenarioClusterAssignment],
) -> list[InterventionCoverageSummary]:
    """Measure which scenario families each intervention actually covers."""

    if not untreated or not scenario_clusters:
        return []

    baseline_by_id = {scenario.scenario_id: scenario for scenario in untreated}
    scenario_ids_by_cluster: dict[str, list[str]] = {}
    cluster_labels: dict[str, str] = {}
    for assignment in scenario_clusters:
        scenario_ids_by_cluster.setdefault(assignment.cluster_id, []).append(assignment.scenario_id)
        cluster_labels[assignment.cluster_id] = assignment.cluster_label

    results: list[InterventionCoverageSummary] = []
    for intervention_id, treated_scenarios in treated_by_intervention.items():
        treated_by_id = {scenario.scenario_id: scenario for scenario in treated_scenarios}
        for cluster_id, scenario_ids in sorted(scenario_ids_by_cluster.items()):
            baseline_cluster = [baseline_by_id[scenario_id] for scenario_id in scenario_ids]
            treated_cluster = [
                treated_by_id.get(scenario_id, baseline_by_id[scenario_id])
                for scenario_id in scenario_ids
            ]
            baseline_failures = np.array(
                [float(scenario.failure_triggered) for scenario in baseline_cluster],
                dtype=float,
            )
            treated_failures = np.array(
                [float(scenario.failure_triggered) for scenario in treated_cluster],
                dtype=float,
            )
            prevented = np.logical_and(baseline_failures > 0.0, treated_failures == 0.0)
            failing_baseline = max(int(baseline_failures.sum()), 1)

            baseline_resilience = np.array(
                [scenario.metrics.get("resilience_score", 0.0) for scenario in baseline_cluster],
                dtype=float,
            )
            treated_resilience = np.array(
                [scenario.metrics.get("resilience_score", 0.0) for scenario in treated_cluster],
                dtype=float,
            )
            resilience_delta = treated_resilience - baseline_resilience

            baseline_wait = float(
                np.mean([scenario.metrics.get("mean_wait", 0.0) for scenario in baseline_cluster])
            )
            treated_wait = float(
                np.mean([scenario.metrics.get("mean_wait", 0.0) for scenario in treated_cluster])
            )
            baseline_blocked = float(
                np.mean([scenario.metrics.get("blocked_transfers", 0.0) for scenario in baseline_cluster])
            )
            treated_blocked = float(
                np.mean([scenario.metrics.get("blocked_transfers", 0.0) for scenario in treated_cluster])
            )
            wait_improvement = max(
                (baseline_wait - treated_wait) / max(abs(baseline_wait), 1e-9),
                0.0,
            )
            blocked_relief = max(
                (baseline_blocked - treated_blocked) / max(baseline_blocked, 1.0),
                0.0,
            )
            prevention_rate = float(prevented.sum()) / failing_baseline
            mean_resilience_delta = float(resilience_delta.mean()) if resilience_delta.size else 0.0
            coverage_score = (
                0.45 * prevention_rate
                + 0.35 * max(mean_resilience_delta, 0.0)
                + 0.10 * wait_improvement
                + 0.10 * blocked_relief
            )
            results.append(
                InterventionCoverageSummary(
                    intervention_id=intervention_id,
                    cluster_id=cluster_id,
                    cluster_label=cluster_labels[cluster_id],
                    scenario_count=len(scenario_ids),
                    baseline_failure_rate=float(baseline_failures.mean()) if baseline_failures.size else 0.0,
                    treated_failure_rate=float(treated_failures.mean()) if treated_failures.size else 0.0,
                    failure_prevention_rate=prevention_rate,
                    mean_resilience_delta=mean_resilience_delta,
                    worst_case_resilience_delta=float(resilience_delta.min()) if resilience_delta.size else 0.0,
                    wait_improvement_rate=wait_improvement,
                    blocked_transfer_relief_rate=blocked_relief,
                    coverage_score=coverage_score,
                )
            )
    results.sort(
        key=lambda item: (item.cluster_id, item.coverage_score, item.mean_resilience_delta),
        reverse=True,
    )
    return results


def summarize_portfolio_coverage(
    *,
    portfolio_id: str,
    untreated: list[ScenarioSummary],
    treated: list[ScenarioSummary],
    scenario_clusters: list[ScenarioClusterAssignment],
    coverage_threshold: float = 0.1,
) -> list[PortfolioClusterCoverageSummary]:
    """Measure how well a portfolio covers each scenario family."""

    if not untreated or not scenario_clusters:
        return []

    baseline_by_id = {scenario.scenario_id: scenario for scenario in untreated}
    treated_by_id = {scenario.scenario_id: scenario for scenario in treated}
    scenario_ids_by_cluster: dict[str, list[str]] = {}
    cluster_labels: dict[str, str] = {}
    for assignment in scenario_clusters:
        scenario_ids_by_cluster.setdefault(assignment.cluster_id, []).append(assignment.scenario_id)
        cluster_labels[assignment.cluster_id] = assignment.cluster_label

    results: list[PortfolioClusterCoverageSummary] = []
    for cluster_id, scenario_ids in sorted(scenario_ids_by_cluster.items()):
        baseline_cluster = [baseline_by_id[scenario_id] for scenario_id in scenario_ids]
        treated_cluster = [
            treated_by_id.get(scenario_id, baseline_by_id[scenario_id])
            for scenario_id in scenario_ids
        ]
        baseline_failures = np.array(
            [float(scenario.failure_triggered) for scenario in baseline_cluster],
            dtype=float,
        )
        treated_failures = np.array(
            [float(scenario.failure_triggered) for scenario in treated_cluster],
            dtype=float,
        )
        prevented = np.logical_and(baseline_failures > 0.0, treated_failures == 0.0)
        failing_baseline = max(int(baseline_failures.sum()), 1)

        baseline_resilience = np.array(
            [scenario.metrics.get("resilience_score", 0.0) for scenario in baseline_cluster],
            dtype=float,
        )
        treated_resilience = np.array(
            [scenario.metrics.get("resilience_score", 0.0) for scenario in treated_cluster],
            dtype=float,
        )
        resilience_delta = treated_resilience - baseline_resilience

        baseline_wait = float(
            np.mean([scenario.metrics.get("mean_wait", 0.0) for scenario in baseline_cluster])
        )
        treated_wait = float(
            np.mean([scenario.metrics.get("mean_wait", 0.0) for scenario in treated_cluster])
        )
        baseline_blocked = float(
            np.mean([scenario.metrics.get("blocked_transfers", 0.0) for scenario in baseline_cluster])
        )
        treated_blocked = float(
            np.mean([scenario.metrics.get("blocked_transfers", 0.0) for scenario in treated_cluster])
        )
        wait_improvement = max(
            (baseline_wait - treated_wait) / max(abs(baseline_wait), 1e-9),
            0.0,
        )
        blocked_relief = max(
            (baseline_blocked - treated_blocked) / max(baseline_blocked, 1.0),
            0.0,
        )
        prevention_rate = float(prevented.sum()) / failing_baseline
        mean_resilience_delta = float(resilience_delta.mean()) if resilience_delta.size else 0.0
        coverage_score = (
            0.45 * prevention_rate
            + 0.35 * max(mean_resilience_delta, 0.0)
            + 0.10 * wait_improvement
            + 0.10 * blocked_relief
        )
        results.append(
            PortfolioClusterCoverageSummary(
                portfolio_id=portfolio_id,
                cluster_id=cluster_id,
                cluster_label=cluster_labels[cluster_id],
                scenario_count=len(scenario_ids),
                baseline_failure_rate=float(baseline_failures.mean()) if baseline_failures.size else 0.0,
                treated_failure_rate=float(treated_failures.mean()) if treated_failures.size else 0.0,
                failure_prevention_rate=prevention_rate,
                mean_resilience_delta=mean_resilience_delta,
                worst_case_resilience_delta=float(resilience_delta.min()) if resilience_delta.size else 0.0,
                wait_improvement_rate=wait_improvement,
                blocked_transfer_relief_rate=blocked_relief,
                coverage_score=coverage_score,
                covered=bool(
                    coverage_score >= coverage_threshold
                    or prevention_rate > 0.0
                    or mean_resilience_delta >= 0.02
                ),
            )
        )
    results.sort(
        key=lambda item: (item.coverage_score, item.mean_resilience_delta, item.cluster_id),
        reverse=True,
    )
    return results


def _scenario_feature_matrix(
    scenarios: list[ScenarioSummary],
    *,
    shock_defaults: dict[str, float],
) -> tuple[list[dict[str, float | str]], np.ndarray, list[str]]:
    shock_columns = sorted({dimension for scenario in scenarios for dimension in scenario.shock_vector})
    rows: list[dict[str, float | str]] = []
    feature_rows: list[list[float]] = []
    for scenario in scenarios:
        row = {
            "scenario_id": scenario.scenario_id,
            "source": scenario.source,
            "shock_budget": float(scenario.shock_budget),
            "failure_triggered": float(scenario.failure_triggered),
            "damage_score": float(scenario.damage_score),
            "resilience_score": float(scenario.metrics.get("resilience_score", 0.0)),
            "throughput": float(scenario.metrics.get("throughput", 0.0)),
            "mean_wait": float(scenario.metrics.get("mean_wait", 0.0)),
            "blocked_transfers": float(scenario.metrics.get("blocked_transfers", 0.0)),
        }
        feature_values = [
            row["shock_budget"],
            row["failure_triggered"],
            row["damage_score"],
            row["resilience_score"],
            row["throughput"],
            row["mean_wait"],
            row["blocked_transfers"],
        ]
        for dimension in shock_columns:
            value = float(scenario.shock_vector.get(dimension, shock_defaults.get(dimension, 0.0)))
            row[f"shock__{dimension}"] = value
            feature_values.append(value)
        rows.append(row)
        feature_rows.append(feature_values)
    return rows, np.asarray(feature_rows, dtype=float), shock_columns


def _cluster_count(scenario_count: int, *, max_clusters: int) -> int:
    if scenario_count <= 2:
        return 1
    desired = int(round(np.sqrt(scenario_count)))
    if scenario_count >= 4:
        desired = max(2, desired)
    return min(max_clusters, scenario_count, desired)


def _fit_kmedoids(features: np.ndarray, cluster_count: int, *, max_iter: int = 8) -> np.ndarray:
    medoids = _initialize_medoids(features, cluster_count)
    labels = np.zeros(features.shape[0], dtype=int)
    for _ in range(max_iter):
        distances = _pairwise_distances(features, features[medoids])
        labels = np.argmin(distances, axis=1)
        updated = []
        for cluster in range(cluster_count):
            member_indexes = np.flatnonzero(labels == cluster)
            if member_indexes.size == 0:
                fallback = _farthest_unselected(features, selected=updated)
                updated.append(fallback)
                continue
            cluster_distances = _pairwise_distances(features[member_indexes], features[member_indexes])
            updated.append(int(member_indexes[int(np.argmin(cluster_distances.sum(axis=1)))]))
        if updated == medoids:
            break
        medoids = updated
    final_distances = _pairwise_distances(features, features[medoids])
    return np.argmin(final_distances, axis=1)


def _initialize_medoids(features: np.ndarray, cluster_count: int) -> list[int]:
    scores = np.linalg.norm(features, axis=1)
    medoids = [int(np.argmax(scores))]
    while len(medoids) < cluster_count:
        medoids.append(_farthest_unselected(features, selected=medoids))
    return medoids


def _farthest_unselected(features: np.ndarray, *, selected: Iterable[int]) -> int:
    selected_indexes = list(dict.fromkeys(int(index) for index in selected))
    if not selected_indexes:
        return 0
    distances = _pairwise_distances(features, features[selected_indexes])
    nearest = distances.min(axis=1)
    nearest[selected_indexes] = -1.0
    return int(np.argmax(nearest))


def _pairwise_distances(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    diff = left[:, None, :] - right[None, :, :]
    return np.sqrt(np.sum(diff * diff, axis=2))


def _cluster_representative(cluster_matrix: np.ndarray) -> int:
    if cluster_matrix.shape[0] <= 1:
        return 0
    distances = _pairwise_distances(cluster_matrix, cluster_matrix)
    return int(np.argmin(distances.sum(axis=1)))


def _cluster_label(
    cluster_rows: list[dict[str, float | str]],
    *,
    dominant_shock: str | None,
    overall_wait: np.ndarray,
    overall_blocked: np.ndarray,
    overall_damage: np.ndarray,
) -> str:
    failure_rate = float(np.mean([row["failure_triggered"] for row in cluster_rows]))
    mean_wait = float(np.mean([row["mean_wait"] for row in cluster_rows]))
    mean_blocked = float(np.mean([row["blocked_transfers"] for row in cluster_rows]))
    mean_damage = float(np.mean([row["damage_score"] for row in cluster_rows]))

    severity = "Failing" if failure_rate >= 0.5 else "Survivable"
    route_threshold = float(np.quantile(overall_blocked, 0.6)) if overall_blocked.size else 0.0
    wait_threshold = float(np.quantile(overall_wait, 0.6)) if overall_wait.size else 0.0
    damage_threshold = float(np.quantile(overall_damage, 0.6)) if overall_damage.size else 0.0
    if mean_blocked > max(route_threshold, 0.0):
        stress_type = "route stress"
    elif mean_wait > max(wait_threshold, 0.0):
        stress_type = "queue stress"
    elif mean_damage > max(damage_threshold, 0.0):
        stress_type = "system stress"
    else:
        stress_type = "mixed stress"
    if dominant_shock:
        shock_label = dominant_shock.replace("_", " ")
        return f"{severity} {stress_type} ({shock_label})"
    return f"{severity} {stress_type}"


def _dominant_shock_dimension(
    cluster_rows: list[dict[str, float | str]],
    shock_columns: list[str],
) -> str | None:
    if not shock_columns:
        return None
    means = {
        dimension: float(np.mean([row[f"shock__{dimension}"] for row in cluster_rows]))
        for dimension in shock_columns
    }
    dominant = max(means, key=means.get)
    if abs(means[dominant]) <= 1e-9:
        return None
    return dominant


def _minmax_scale(values: np.ndarray) -> np.ndarray:
    minimum = values.min(axis=0)
    maximum = values.max(axis=0)
    scale = maximum - minimum
    scale[scale <= 1e-9] = 1.0
    return (values - minimum) / scale
