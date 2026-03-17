"""Regime-aware response planning across scenario families."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from stresslab.models import (
    ClusterResponseRecommendation,
    InterventionCoverageSummary,
    RankedIntervention,
    RegimePlanSummary,
    ScenarioClusterAssignment,
    ScenarioSummary,
)


def build_regime_response_plan(
    *,
    untreated: list[ScenarioSummary],
    treated_by_intervention: dict[str, list[ScenarioSummary]],
    intervention_coverage: list[InterventionCoverageSummary],
    scenario_clusters: list[ScenarioClusterAssignment],
    ranked_interventions: list[RankedIntervention],
    budget: float | None,
    fairness_weight: float = 0.0,
    max_candidates_per_cluster: int = 6,
) -> tuple[RegimePlanSummary | None, list[ClusterResponseRecommendation]]:
    """Build a cluster-aware response map using intervention reuse under a standby budget."""

    if not untreated or not scenario_clusters or not intervention_coverage or not ranked_interventions:
        return None, []

    scenario_ids_by_cluster: dict[str, list[str]] = defaultdict(list)
    cluster_labels: dict[str, str] = {}
    cluster_sizes: dict[str, int] = {}
    for assignment in scenario_clusters:
        scenario_ids_by_cluster[assignment.cluster_id].append(assignment.scenario_id)
        cluster_labels[assignment.cluster_id] = assignment.cluster_label
    cluster_sizes.update({cluster_id: len(ids) for cluster_id, ids in scenario_ids_by_cluster.items()})

    ranked_lookup = {item.intervention_id: item for item in ranked_interventions}
    coverage_by_cluster: dict[str, list[InterventionCoverageSummary]] = defaultdict(list)
    for summary in intervention_coverage:
        if summary.intervention_id not in ranked_lookup:
            continue
        coverage_by_cluster[summary.cluster_id].append(summary)
    if not coverage_by_cluster:
        return None, []

    cluster_order = sorted(
        scenario_ids_by_cluster,
        key=lambda cluster_id: (
            -cluster_sizes.get(cluster_id, 0),
            cluster_id,
        ),
    )
    for cluster_id in cluster_order:
        coverage_by_cluster[cluster_id].sort(
            key=lambda summary: (
                _assignment_score(summary, ranked_lookup[summary.intervention_id], fairness_weight=fairness_weight),
                summary.coverage_score,
                summary.mean_resilience_delta,
            ),
            reverse=True,
        )

    remaining_clusters = set(cluster_order)
    assignments: dict[str, InterventionCoverageSummary] = {}
    selected_interventions: set[str] = set()
    spent = 0.0
    effective_budget = float("inf") if budget is None else float(max(budget, 0.0))

    while remaining_clusters:
        best_choice: tuple[float, float, float, str, InterventionCoverageSummary] | None = None
        for cluster_id in sorted(remaining_clusters):
            cluster_weight = cluster_sizes.get(cluster_id, 0) / max(len(untreated), 1)
            for summary in coverage_by_cluster.get(cluster_id, [])[:max_candidates_per_cluster]:
                ranked = ranked_lookup[summary.intervention_id]
                marginal_cost = 0.0 if summary.intervention_id in selected_interventions else ranked.cost
                if spent + marginal_cost > effective_budget + 1e-9:
                    continue
                gain = cluster_weight * _assignment_score(
                    summary,
                    ranked,
                    fairness_weight=fairness_weight,
                )
                efficiency = gain / max(marginal_cost, 1.0)
                choice = (
                    efficiency + (1.0 if marginal_cost == 0.0 else 0.0),
                    gain,
                    -marginal_cost,
                    cluster_id,
                    summary,
                )
                if best_choice is None or choice > best_choice:
                    best_choice = choice
        if best_choice is None:
            break
        _, _, _, cluster_id, summary = best_choice
        assignments[cluster_id] = summary
        remaining_clusters.remove(cluster_id)
        if summary.intervention_id not in selected_interventions:
            selected_interventions.add(summary.intervention_id)
            spent += ranked_lookup[summary.intervention_id].cost

    if selected_interventions:
        for cluster_id in sorted(remaining_clusters):
            reuse_candidates = [
                summary
                for summary in coverage_by_cluster.get(cluster_id, [])
                if summary.intervention_id in selected_interventions
            ]
            if reuse_candidates:
                assignments[cluster_id] = reuse_candidates[0]
        remaining_clusters = remaining_clusters.difference(assignments)

    plan_rows: list[ClusterResponseRecommendation] = []
    scenario_to_cluster = {
        assignment.scenario_id: assignment.cluster_id
        for assignment in scenario_clusters
    }
    baseline_by_id = {scenario.scenario_id: scenario for scenario in untreated}
    treated_lookup = {
        intervention_id: {scenario.scenario_id: scenario for scenario in summaries}
        for intervention_id, summaries in treated_by_intervention.items()
    }

    treated_scenarios: list[ScenarioSummary] = []
    for scenario in untreated:
        cluster_id = scenario_to_cluster.get(scenario.scenario_id)
        summary = assignments.get(cluster_id) if cluster_id is not None else None
        if summary is None:
            treated_scenarios.append(scenario)
            continue
        treated_scenarios.append(
            treated_lookup.get(summary.intervention_id, {}).get(scenario.scenario_id, scenario)
        )

    running_cost = 0.0
    seen_cost_ids: set[str] = set()
    for cluster_id in cluster_order:
        summary = assignments.get(cluster_id)
        if summary is None:
            plan_rows.append(
                ClusterResponseRecommendation(
                    cluster_id=cluster_id,
                    cluster_label=cluster_labels.get(cluster_id, cluster_id),
                    scenario_count=cluster_sizes.get(cluster_id, 0),
                    selected_intervention_id=None,
                    selected_label=None,
                    selected_action_type=None,
                    selected_source=None,
                    selected_bundle_depth=0,
                    marginal_cost=0.0,
                    total_standby_cost=running_cost,
                    coverage_score=0.0,
                    failure_prevention_rate=0.0,
                    mean_resilience_delta=0.0,
                    worst_case_resilience_delta=0.0,
                    expected_cluster_resilience=None,
                    expected_cluster_fairness=None,
                    robust_score=None,
                    covered=False,
                    reused_intervention=False,
                )
            )
            continue
        ranked = ranked_lookup[summary.intervention_id]
        reused = summary.intervention_id in seen_cost_ids
        marginal_cost = 0.0 if reused else ranked.cost
        if not reused:
            seen_cost_ids.add(summary.intervention_id)
            running_cost += ranked.cost
        cluster_scenario_ids = scenario_ids_by_cluster.get(cluster_id, [])
        cluster_treated = [
            treated_lookup.get(summary.intervention_id, {}).get(scenario_id, baseline_by_id[scenario_id])
            for scenario_id in cluster_scenario_ids
        ]
        expected_cluster_resilience = float(
            np.mean([scenario.metrics.get("resilience_score", 0.0) for scenario in cluster_treated])
        ) if cluster_treated else None
        expected_cluster_fairness = float(
            np.mean([scenario.metrics.get("fairness_score", 0.0) for scenario in cluster_treated])
        ) if cluster_treated else None
        plan_rows.append(
            ClusterResponseRecommendation(
                cluster_id=cluster_id,
                cluster_label=cluster_labels.get(cluster_id, cluster_id),
                scenario_count=cluster_sizes.get(cluster_id, 0),
                selected_intervention_id=summary.intervention_id,
                selected_label=ranked.label,
                selected_action_type=ranked.action_type,
                selected_source=ranked.source,
                selected_bundle_depth=ranked.bundle_depth,
                marginal_cost=marginal_cost,
                total_standby_cost=running_cost,
                coverage_score=summary.coverage_score,
                failure_prevention_rate=summary.failure_prevention_rate,
                mean_resilience_delta=summary.mean_resilience_delta,
                worst_case_resilience_delta=summary.worst_case_resilience_delta,
                expected_cluster_resilience=expected_cluster_resilience,
                expected_cluster_fairness=expected_cluster_fairness,
                robust_score=ranked.robust_score,
                covered=_covered(summary),
                reused_intervention=reused,
            )
        )

    total_scenarios = max(len(untreated), 1)
    weighted_coverage_rate = sum(
        row.scenario_count for row in plan_rows if row.covered
    ) / total_scenarios
    mean_coverage_score = sum(
        row.coverage_score * row.scenario_count for row in plan_rows
    ) / total_scenarios
    expected_resilience = float(
        np.mean([scenario.metrics.get("resilience_score", 0.0) for scenario in treated_scenarios])
    ) if treated_scenarios else 0.0
    expected_fairness_score = float(
        np.mean([scenario.metrics.get("fairness_score", 0.0) for scenario in treated_scenarios])
    ) if treated_scenarios else 0.0
    untreated_failures = np.array([float(scenario.failure_triggered) for scenario in untreated], dtype=float)
    treated_failures = np.array([float(scenario.failure_triggered) for scenario in treated_scenarios], dtype=float)
    prevented = np.logical_and(untreated_failures > 0.0, treated_failures == 0.0)
    failing_baseline = max(int(untreated_failures.sum()), 1)
    failure_prevention_rate = float(prevented.sum()) / failing_baseline

    selected_ids = sorted(selected_interventions)
    plan_summary = RegimePlanSummary(
        plan_id="regime_plan__baseline" if not selected_ids else "regime_plan__" + "__".join(selected_ids),
        budget=budget,
        total_standby_cost=running_cost,
        unique_intervention_count=len(selected_ids),
        assigned_cluster_count=sum(1 for row in plan_rows if row.selected_intervention_id is not None),
        covered_cluster_count=sum(1 for row in plan_rows if row.covered),
        weighted_cluster_coverage_rate=weighted_coverage_rate,
        mean_cluster_coverage_score=mean_coverage_score,
        expected_resilience=expected_resilience,
        expected_fairness_score=expected_fairness_score,
        failure_prevention_rate=failure_prevention_rate,
        selected_intervention_ids=selected_ids,
        method="greedy_regime_map" if budget is not None else "cluster_best",
    )
    return plan_summary, plan_rows


def _assignment_score(
    summary: InterventionCoverageSummary,
    ranked: RankedIntervention,
    *,
    fairness_weight: float,
) -> float:
    fairness_gain = max(ranked.fairness_gain or 0.0, 0.0)
    robust_signal = max(ranked.robust_score or ranked.resilience_gain, 0.0)
    return (
        0.55 * summary.coverage_score
        + 0.20 * summary.failure_prevention_rate
        + 0.15 * max(summary.mean_resilience_delta, 0.0)
        + 0.05 * robust_signal
        + 0.05 * fairness_weight * fairness_gain
    )


def _covered(summary: InterventionCoverageSummary) -> bool:
    return bool(
        summary.coverage_score >= 0.1
        or summary.failure_prevention_rate > 0.0
        or summary.mean_resilience_delta >= 0.02
    )
