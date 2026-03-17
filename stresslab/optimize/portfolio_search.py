"""Budget-aware robust portfolio selection."""

from __future__ import annotations

from itertools import combinations

import numpy as np

from stresslab.models import PortfolioCandidate, PortfolioClusterCoverageSummary, ScenarioSummary
from stresslab.optimize.portfolio_analysis import summarize_portfolio_coverage
from stresslab.optimize.robust import evaluate_intervention_portfolio
from stresslab.systemspec.schema import InterventionSpec, SystemSpec


def select_robust_portfolio(
    spec: SystemSpec,
    *,
    budget: float,
    untreated: list[ScenarioSummary],
    scenario_clusters,
    baseline_resilience: float,
    baseline_fairness: float,
    seed: int,
    fairness_weight: float = 0.0,
    max_exact_interventions: int = 12,
    beam_width: int = 8,
    top_k: int = 10,
) -> tuple[list[PortfolioCandidate], list[PortfolioClusterCoverageSummary], str]:
    """Select high-value intervention portfolios under budget."""

    interventions = [
        intervention
        for intervention in spec.interventions
        if not (intervention.applicability_constraints or {}).get("shadow_reference", False)
    ]
    if budget <= 0 or not interventions or not untreated:
        return [], [], "none"

    lookup = {intervention.id: intervention for intervention in spec.interventions}
    ordered_ids = [intervention.id for intervention in interventions]
    cache: dict[
        tuple[str, ...],
        tuple[PortfolioCandidate, list[PortfolioClusterCoverageSummary], list[ScenarioSummary]],
    ] = {}
    leaf_cache: dict[str, set[str]] = {}

    def leaf_ids(intervention_id: str, trail: tuple[str, ...] = ()) -> set[str]:
        if intervention_id in leaf_cache:
            return leaf_cache[intervention_id]
        if intervention_id in trail:
            raise ValueError(f"Bundle cycle detected involving '{intervention_id}'.")
        intervention = lookup[intervention_id]
        if intervention.action_type != "bundle" and not intervention.bundle_members:
            leaf_cache[intervention_id] = {intervention_id}
            return leaf_cache[intervention_id]
        members: set[str] = set()
        for member_id in intervention.bundle_members:
            members.update(leaf_ids(member_id, (*trail, intervention_id)))
        leaf_cache[intervention_id] = members
        return members

    def has_overlap(combo_ids: tuple[str, ...]) -> bool:
        seen_leaves: set[str] = set()
        for intervention_id in combo_ids:
            leaves = leaf_ids(intervention_id)
            if seen_leaves.intersection(leaves):
                return True
            seen_leaves.update(leaves)
        return False

    def evaluate(combo_ids: tuple[str, ...]):
        if combo_ids in cache:
            return cache[combo_ids]
        selected_specs = [lookup[intervention_id] for intervention_id in combo_ids]
        treated = evaluate_intervention_portfolio(spec, selected_specs, untreated, seed=seed)
        coverage = summarize_portfolio_coverage(
            portfolio_id=_portfolio_id(combo_ids),
            untreated=untreated,
            treated=treated,
            scenario_clusters=scenario_clusters,
        )
        candidate = _candidate_from_treated(
            combo_ids=combo_ids,
            interventions=selected_specs,
            treated=treated,
            untreated=untreated,
            coverage=coverage,
            baseline_resilience=baseline_resilience,
            baseline_fairness=baseline_fairness,
            budget=budget,
            fairness_weight=fairness_weight,
        )
        cache[combo_ids] = (candidate, coverage, treated)
        return cache[combo_ids]

    combos: set[tuple[str, ...]] = {tuple()}
    if len(interventions) <= max_exact_interventions:
        search_method = "exact_subset"
        for size in range(1, len(ordered_ids) + 1):
            for combo_ids in combinations(ordered_ids, size):
                if has_overlap(combo_ids):
                    continue
                if _total_cost([lookup[intervention_id] for intervention_id in combo_ids]) <= budget:
                    combos.add(combo_ids)
    else:
        search_method = "beam_search"
        frontier = [tuple()]
        seen = {tuple()}
        for _ in range(len(ordered_ids)):
            expanded: list[tuple[str, ...]] = []
            for combo_ids in frontier:
                start_index = ordered_ids.index(combo_ids[-1]) + 1 if combo_ids else 0
                for index in range(start_index, len(ordered_ids)):
                    candidate_ids = tuple([*combo_ids, ordered_ids[index]])
                    if candidate_ids in seen:
                        continue
                    seen.add(candidate_ids)
                    if has_overlap(candidate_ids):
                        continue
                    if _total_cost([lookup[intervention_id] for intervention_id in candidate_ids]) <= budget:
                        expanded.append(candidate_ids)
                        combos.add(candidate_ids)
            if not expanded:
                break
            ranked_expanded = sorted(
                expanded,
                key=lambda combo: evaluate(combo)[0].objective_score,
                reverse=True,
            )
            frontier = ranked_expanded[:beam_width]

    evaluated = [
        evaluate(combo_ids)
        for combo_ids in combos
    ]
    ordered_candidates = sorted(
        [candidate for candidate, _, _ in evaluated],
        key=lambda item: (
            item.objective_score,
            item.cluster_coverage_rate or 0.0,
            item.failure_prevention_rate or 0.0,
            -(item.total_cost),
            -(item.intervention_count),
        ),
        reverse=True,
    )
    best = ordered_candidates[:top_k]
    best_ids = {candidate.portfolio_id for candidate in best}
    coverage = [
        summary
        for _, summaries, _ in evaluated
        for summary in summaries
        if summary.portfolio_id in best_ids
    ]
    return best, coverage, search_method


def _candidate_from_treated(
    *,
    combo_ids: tuple[str, ...],
    interventions: list[InterventionSpec],
    treated: list[ScenarioSummary],
    untreated: list[ScenarioSummary],
    coverage: list[PortfolioClusterCoverageSummary],
    baseline_resilience: float,
    baseline_fairness: float,
    budget: float,
    fairness_weight: float,
) -> PortfolioCandidate:
    resilience_values = np.array(
        [scenario.metrics.get("resilience_score", 0.0) for scenario in treated],
        dtype=float,
    )
    fairness_values = np.array(
        [scenario.metrics.get("fairness_score", 0.0) for scenario in treated],
        dtype=float,
    )
    expected_resilience = float(resilience_values.mean()) if resilience_values.size else 0.0
    worst_case_resilience = float(resilience_values.min()) if resilience_values.size else 0.0
    expected_fairness_score = float(fairness_values.mean()) if fairness_values.size else 0.0
    untreated_failures = np.array([float(scenario.failure_triggered) for scenario in untreated], dtype=float)
    treated_failures = np.array([float(scenario.failure_triggered) for scenario in treated], dtype=float)
    prevented = np.logical_and(untreated_failures > 0.0, treated_failures == 0.0)
    failing_baseline = max(int(untreated_failures.sum()), 1)
    failure_prevention_rate = float(prevented.sum()) / failing_baseline

    total_cost = _total_cost(interventions)
    total_difficulty = float(sum(intervention.implementation_difficulty or 0.0 for intervention in interventions))
    fairness_impact = float(sum(abs(intervention.fairness_impact or 0.0) for intervention in interventions))
    total_weight = max(sum(summary.scenario_count for summary in coverage), 1)
    weighted_coverage_rate = sum(
        summary.scenario_count for summary in coverage if summary.covered
    ) / total_weight
    mean_coverage_score = sum(
        min(summary.coverage_score, 1.0) * summary.scenario_count
        for summary in coverage
    ) / total_weight
    objective_score = robust_portfolio_objective(
        expected_resilience=expected_resilience,
        worst_case_resilience=worst_case_resilience,
        cluster_coverage_rate=weighted_coverage_rate,
        mean_cluster_coverage_score=mean_coverage_score,
        failure_prevention_rate=failure_prevention_rate,
        expected_fairness_score=expected_fairness_score,
        total_cost=total_cost,
        budget=budget,
        intervention_count=len(combo_ids),
        implementation_difficulty=total_difficulty,
        fairness_impact=fairness_impact,
        fairness_weight=fairness_weight,
    )
    return PortfolioCandidate(
        portfolio_id=_portfolio_id(combo_ids),
        intervention_ids=list(combo_ids),
        total_cost=total_cost,
        intervention_count=len(combo_ids),
        resilience_gain=expected_resilience - baseline_resilience,
        expected_resilience=expected_resilience,
        worst_case_resilience=worst_case_resilience,
        fairness_gain=expected_fairness_score - baseline_fairness,
        expected_fairness_score=expected_fairness_score,
        failure_prevention_rate=failure_prevention_rate,
        cluster_coverage_rate=weighted_coverage_rate,
        mean_cluster_coverage_score=mean_coverage_score,
        implementation_difficulty=total_difficulty,
        fairness_impact=fairness_impact,
        objective_score=objective_score,
    )


def robust_portfolio_objective(
    *,
    expected_resilience: float,
    worst_case_resilience: float,
    cluster_coverage_rate: float,
    mean_cluster_coverage_score: float,
    failure_prevention_rate: float,
    expected_fairness_score: float,
    total_cost: float,
    budget: float,
    intervention_count: int,
    implementation_difficulty: float,
    fairness_impact: float,
    fairness_weight: float,
) -> float:
    """Coverage-aware robust portfolio score."""

    cost_ratio = total_cost / max(budget, 1e-9)
    count_penalty = intervention_count / 10.0
    return (
        0.30 * cluster_coverage_rate
        + 0.20 * mean_cluster_coverage_score
        + 0.15 * failure_prevention_rate
        + 0.20 * expected_resilience
        + 0.10 * worst_case_resilience
        + fairness_weight * expected_fairness_score
        - 0.03 * cost_ratio
        - 0.01 * count_penalty
        - 0.0075 * implementation_difficulty
        - 0.005 * fairness_impact
    )


def _portfolio_id(combo_ids: tuple[str, ...]) -> str:
    if not combo_ids:
        return "portfolio__baseline"
    return "portfolio__" + "__".join(combo_ids)


def _total_cost(interventions: list[InterventionSpec]) -> float:
    return float(sum(intervention.cost for intervention in interventions))
