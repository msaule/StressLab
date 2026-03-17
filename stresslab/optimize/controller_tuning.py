"""Learn lightweight closed-loop controller policies on representative scenarios."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from stresslab.models import (
    ClosedLoopRegimeSummary,
    ClusterResponseRecommendation,
    ControllerPolicyCandidate,
    ControllerTuningSummary,
    ScenarioClusterAssignment,
    ScenarioSummary,
)
from stresslab.optimize.closed_loop_regime_control import evaluate_closed_loop_regime_control
from stresslab.systemspec.schema import SystemSpec

_SCHEDULE_LIBRARY: dict[str, dict[str, float]] = {
    "balanced": {"start": 0.18, "interval": 0.16, "growth": 1.10, "limit": 5},
    "early_dense": {"start": 0.10, "interval": 0.10, "growth": 1.20, "limit": 6},
    "late_confirm": {"start": 0.32, "interval": 0.18, "growth": 1.15, "limit": 4},
    "early_sparse": {"start": 0.14, "interval": 0.20, "growth": 1.10, "limit": 4},
}
_THRESHOLDS = (0.45, 0.6)
_RETARGETING = (True, False)
_CONFIRMATION_COUNTS = (1, 2)
_MAX_CONFIRMATION_COUNT = 3
_LOCAL_SEARCH_STEPS = (
    {"start": 0.04, "interval": 0.04, "growth": 0.14, "threshold": 0.10},
    {"start": 0.02, "interval": 0.03, "growth": 0.08, "threshold": 0.05},
    {"start": 0.01, "interval": 0.02, "growth": 0.05, "threshold": 0.03},
)


@dataclass(frozen=True, slots=True)
class _ControllerSpec:
    policy_id: str
    schedule_id: str
    schedule_start_fraction: float
    schedule_interval_fraction: float
    schedule_growth: float
    schedule_observation_limit: int
    confidence_threshold: float
    allow_retargeting: bool
    confirmation_count: int
    search_method: str
    generation: int = 0
    parent_policy_id: str | None = None


def tune_closed_loop_controller(
    *,
    spec: SystemSpec,
    untreated: list[ScenarioSummary],
    scenario_clusters: list[ScenarioClusterAssignment],
    cluster_response_plan: list[ClusterResponseRecommendation],
    regime_plan_summary,
    seed: int,
    fairness_weight: float = 0.0,
    max_tuning_scenarios: int = 3,
) -> tuple[
    ControllerTuningSummary | None,
    list[ControllerPolicyCandidate],
    ClosedLoopRegimeSummary | None,
    list,
    ]:
    """Tune a closed-loop controller on representative scenarios and replay the winner."""

    if not untreated or not scenario_clusters or not cluster_response_plan:
        return None, [], None, []

    tuning_scenarios = _representative_scenarios(
        untreated=untreated,
        scenario_clusters=scenario_clusters,
        limit=max_tuning_scenarios,
    )
    tuning_ids = {scenario.scenario_id for scenario in tuning_scenarios}
    tuning_clusters = [
        assignment
        for assignment in scenario_clusters
        if assignment.scenario_id in tuning_ids
    ]
    candidates: list[ControllerPolicyCandidate] = []
    evaluated_specs: set[tuple[tuple[float, ...], float, bool, int]] = set()
    beam_specs = _seed_specs()
    search_rounds = 0

    candidates.extend(
        _evaluate_specs(
            beam_specs,
            spec=spec,
            tuning_scenarios=tuning_scenarios,
            tuning_clusters=tuning_clusters,
            cluster_response_plan=cluster_response_plan,
            regime_plan_summary=regime_plan_summary,
            seed=seed,
            fairness_weight=fairness_weight,
            evaluated_specs=evaluated_specs,
        )
    )

    beam_width = 4
    for round_index in range(2):
        top_specs = [
            _spec_from_candidate(candidate)
            for candidate in sorted(candidates, key=_candidate_key, reverse=True)[:beam_width]
        ]
        mutated_specs = _mutate_specs(top_specs, round_index=round_index)
        new_candidates = _evaluate_specs(
            mutated_specs,
            spec=spec,
            tuning_scenarios=tuning_scenarios,
            tuning_clusters=tuning_clusters,
            cluster_response_plan=cluster_response_plan,
            regime_plan_summary=regime_plan_summary,
            seed=seed,
            fairness_weight=fairness_weight,
            evaluated_specs=evaluated_specs,
        )
        if not new_candidates:
            break
        candidates.extend(new_candidates)
        search_rounds += 1

    for local_round, steps in enumerate(_LOCAL_SEARCH_STEPS, start=2):
        top_specs = [
            _spec_from_candidate(candidate)
            for candidate in sorted(candidates, key=_candidate_key, reverse=True)[:beam_width]
        ]
        local_specs = _local_search_neighbors(
            top_specs,
            round_index=local_round,
            steps=steps,
        )
        new_candidates = _evaluate_specs(
            local_specs,
            spec=spec,
            tuning_scenarios=tuning_scenarios,
            tuning_clusters=tuning_clusters,
            cluster_response_plan=cluster_response_plan,
            regime_plan_summary=regime_plan_summary,
            seed=seed,
            fairness_weight=fairness_weight,
            evaluated_specs=evaluated_specs,
        )
        if not new_candidates:
            continue
        candidates.extend(new_candidates)
        search_rounds += 1

    best_candidate = max(candidates, key=_candidate_key, default=None)

    if best_candidate is None:
        return None, [], None, []

    best_summary, best_rows = evaluate_closed_loop_regime_control(
        spec=spec,
        untreated=untreated,
        scenario_clusters=scenario_clusters,
        cluster_response_plan=cluster_response_plan,
        regime_plan_summary=regime_plan_summary,
        seed=seed,
        observation_fractions=tuple(best_candidate.observation_fractions),
        confidence_threshold=best_candidate.confidence_threshold,
        allow_retargeting=best_candidate.allow_retargeting,
        confirmation_count=best_candidate.confirmation_count,
    )
    if best_summary is None:
        return None, candidates, None, []

    tuning_summary = ControllerTuningSummary(
        method="beam_local_search_representative_scenarios",
        candidate_count=len(candidates),
        tuning_scenario_count=len(tuning_scenarios),
        selected_policy_id=best_candidate.policy_id,
        selected_schedule_id=best_candidate.schedule_id,
        selected_confidence_threshold=best_candidate.confidence_threshold,
        selected_allow_retargeting=best_candidate.allow_retargeting,
        selected_confirmation_count=best_candidate.confirmation_count,
        selected_schedule_start_fraction=best_candidate.schedule_start_fraction,
        selected_schedule_interval_fraction=best_candidate.schedule_interval_fraction,
        selected_schedule_growth=best_candidate.schedule_growth,
        selected_schedule_observation_limit=best_candidate.schedule_observation_limit,
        selected_mean_observation_count=best_candidate.mean_observation_count,
        selected_mean_deployment_count=best_candidate.mean_deployment_count,
        selected_monitoring_burden_score=best_candidate.monitoring_burden_score,
        search_rounds=search_rounds,
        objective_score=best_candidate.objective_score,
        expected_resilience=best_summary.expected_resilience,
        expected_fairness_score=best_summary.expected_fairness_score,
        failure_prevention_rate=best_summary.failure_prevention_rate,
        deployment_accuracy=best_summary.deployment_accuracy,
        pre_degradation_rate=best_summary.pre_degradation_deployment_rate,
        resilience_regret=best_summary.resilience_regret,
    )
    candidates.sort(key=_candidate_key, reverse=True)
    return tuning_summary, candidates, best_summary, best_rows


def _seed_specs() -> list[_ControllerSpec]:
    specs: list[_ControllerSpec] = []
    for schedule_id, params in _SCHEDULE_LIBRARY.items():
        for confidence_threshold in _THRESHOLDS:
            for allow_retargeting in _RETARGETING:
                for confirmation_count in _CONFIRMATION_COUNTS:
                    specs.append(
                        _ControllerSpec(
                            policy_id=(
                                f"controller__{schedule_id}__thr_{str(confidence_threshold).replace('.', '_')}"
                                f"__c{confirmation_count}__{'retarget' if allow_retargeting else 'lock'}"
                            ),
                            schedule_id=schedule_id,
                            schedule_start_fraction=float(params["start"]),
                            schedule_interval_fraction=float(params["interval"]),
                            schedule_growth=float(params["growth"]),
                            schedule_observation_limit=int(params["limit"]),
                            confidence_threshold=confidence_threshold,
                            allow_retargeting=allow_retargeting,
                            confirmation_count=confirmation_count,
                            search_method="seed_grid",
                            generation=0,
                        )
                    )
    return specs


def _mutate_specs(specs: list[_ControllerSpec], *, round_index: int) -> list[_ControllerSpec]:
    mutated: list[_ControllerSpec] = []
    for spec in specs:
        mutated.extend(
            [
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_earlier_r{round_index + 1}",
                    schedule_start_fraction=max(0.05, round(spec.schedule_start_fraction - 0.04, 2)),
                    search_method="beam_mutation",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_confirm_up_r{round_index + 1}",
                    confirmation_count=min(spec.confirmation_count + 1, _MAX_CONFIRMATION_COUNT),
                    search_method="beam_mutation",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_retoggle_r{round_index + 1}",
                    allow_retargeting=not spec.allow_retargeting,
                    search_method="beam_mutation",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_looser_r{round_index + 1}",
                    confidence_threshold=max(0.35, round(spec.confidence_threshold - 0.1, 2)),
                    search_method="beam_mutation",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_denser_r{round_index + 1}",
                    schedule_interval_fraction=max(0.06, round(spec.schedule_interval_fraction * 0.8, 2)),
                    schedule_observation_limit=min(7, spec.schedule_observation_limit + 1),
                    search_method="beam_mutation",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_faster_growth_r{round_index + 1}",
                    schedule_growth=min(1.5, round(spec.schedule_growth + 0.12, 2)),
                    search_method="beam_mutation",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_slower_growth_r{round_index + 1}",
                    schedule_growth=max(0.9, round(spec.schedule_growth - 0.10, 2)),
                    search_method="beam_mutation",
                    generation=round_index + 1,
                ),
            ]
        )
    return mutated


def _local_search_neighbors(
    specs: list[_ControllerSpec],
    *,
    round_index: int,
    steps: dict[str, float],
) -> list[_ControllerSpec]:
    neighbors: list[_ControllerSpec] = []
    start_step = float(steps["start"])
    interval_step = float(steps["interval"])
    growth_step = float(steps["growth"])
    threshold_step = float(steps["threshold"])
    for spec in specs:
        neighbors.extend(
            [
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_start_early_r{round_index + 1}",
                    schedule_start_fraction=max(0.05, round(spec.schedule_start_fraction - start_step, 2)),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_start_late_r{round_index + 1}",
                    schedule_start_fraction=min(0.65, round(spec.schedule_start_fraction + start_step, 2)),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_interval_dense_r{round_index + 1}",
                    schedule_interval_fraction=max(0.05, round(spec.schedule_interval_fraction - interval_step, 2)),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_interval_sparse_r{round_index + 1}",
                    schedule_interval_fraction=min(0.32, round(spec.schedule_interval_fraction + interval_step, 2)),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_growth_up_r{round_index + 1}",
                    schedule_growth=min(1.6, round(spec.schedule_growth + growth_step, 2)),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_growth_down_r{round_index + 1}",
                    schedule_growth=max(0.85, round(spec.schedule_growth - growth_step, 2)),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_threshold_low_r{round_index + 1}",
                    confidence_threshold=max(0.35, round(spec.confidence_threshold - threshold_step, 2)),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_threshold_high_r{round_index + 1}",
                    confidence_threshold=min(0.8, round(spec.confidence_threshold + threshold_step, 2)),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_limit_up_r{round_index + 1}",
                    schedule_observation_limit=min(7, spec.schedule_observation_limit + 1),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_limit_down_r{round_index + 1}",
                    schedule_observation_limit=max(3, spec.schedule_observation_limit - 1),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_confirm_up_r{round_index + 1}",
                    confirmation_count=min(spec.confirmation_count + 1, _MAX_CONFIRMATION_COUNT),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
                _replace_spec(
                    spec,
                    schedule_id=f"{spec.schedule_id}_confirm_down_r{round_index + 1}",
                    confirmation_count=max(1, spec.confirmation_count - 1),
                    search_method="local_search",
                    generation=round_index + 1,
                ),
            ]
        )
    return neighbors


def _evaluate_specs(
    specs: list[_ControllerSpec],
    *,
    spec: SystemSpec,
    tuning_scenarios: list[ScenarioSummary],
    tuning_clusters: list[ScenarioClusterAssignment],
    cluster_response_plan: list[ClusterResponseRecommendation],
    regime_plan_summary,
    seed: int,
    fairness_weight: float,
    evaluated_specs: set[tuple[float, float, float, int, float, bool, int]],
) -> list[ControllerPolicyCandidate]:
    candidates: list[ControllerPolicyCandidate] = []
    for controller_spec in specs:
        signature = (
            controller_spec.schedule_start_fraction,
            controller_spec.schedule_interval_fraction,
            controller_spec.schedule_growth,
            controller_spec.schedule_observation_limit,
            controller_spec.confidence_threshold,
            controller_spec.allow_retargeting,
            controller_spec.confirmation_count,
        )
        if signature in evaluated_specs:
            continue
        evaluated_specs.add(signature)
        observation_fractions = _schedule_from_params(
            start_fraction=controller_spec.schedule_start_fraction,
            base_interval_fraction=controller_spec.schedule_interval_fraction,
            interval_growth=controller_spec.schedule_growth,
            observation_limit=controller_spec.schedule_observation_limit,
        )
        summary, _ = evaluate_closed_loop_regime_control(
            spec=spec,
            untreated=tuning_scenarios,
            scenario_clusters=tuning_clusters,
            cluster_response_plan=cluster_response_plan,
            regime_plan_summary=regime_plan_summary,
            seed=seed,
            observation_fractions=observation_fractions,
            confidence_threshold=controller_spec.confidence_threshold,
            allow_retargeting=controller_spec.allow_retargeting,
            confirmation_count=controller_spec.confirmation_count,
        )
        if summary is None:
            continue
        objective_score = _controller_objective(summary, fairness_weight=fairness_weight)
        burden = _monitoring_burden(summary)
        candidates.append(
            ControllerPolicyCandidate(
                policy_id=controller_spec.policy_id,
                schedule_id=controller_spec.schedule_id,
                observation_fractions=list(observation_fractions),
                schedule_start_fraction=controller_spec.schedule_start_fraction,
                schedule_interval_fraction=controller_spec.schedule_interval_fraction,
                schedule_growth=controller_spec.schedule_growth,
                schedule_observation_limit=controller_spec.schedule_observation_limit,
                confidence_threshold=controller_spec.confidence_threshold,
                allow_retargeting=controller_spec.allow_retargeting,
                confirmation_count=controller_spec.confirmation_count,
                tuning_scenario_count=len(tuning_scenarios),
                mean_observation_count=summary.mean_observation_count,
                mean_deployment_count=summary.mean_deployment_count,
                monitoring_burden_score=burden,
                search_method=controller_spec.search_method,
                generation=controller_spec.generation,
                parent_policy_id=controller_spec.parent_policy_id,
                objective_score=objective_score,
                expected_resilience=summary.expected_resilience,
                expected_fairness_score=summary.expected_fairness_score,
                failure_prevention_rate=summary.failure_prevention_rate,
                prediction_accuracy=summary.prediction_accuracy,
                deployment_accuracy=summary.deployment_accuracy,
                pre_degradation_rate=summary.pre_degradation_deployment_rate,
                retarget_rate=summary.retarget_rate,
                resilience_regret=summary.resilience_regret,
            )
        )
    return candidates


def _representative_scenarios(
    *,
    untreated: list[ScenarioSummary],
    scenario_clusters: list[ScenarioClusterAssignment],
    limit: int,
) -> list[ScenarioSummary]:
    lookup = {scenario.scenario_id: scenario for scenario in untreated}
    grouped: dict[str, list[ScenarioSummary]] = defaultdict(list)
    for assignment in scenario_clusters:
        scenario = lookup.get(assignment.scenario_id)
        if scenario is not None:
            grouped[assignment.cluster_id].append(scenario)
    selected: list[ScenarioSummary] = []
    for cluster_id in sorted(grouped):
        ranked = sorted(
            grouped[cluster_id],
            key=lambda scenario: (
                scenario.failure_triggered,
                scenario.damage_score,
                scenario.shock_budget,
            ),
            reverse=True,
        )
        selected.append(ranked[0])
    if len(selected) < limit:
        selected_ids = {scenario.scenario_id for scenario in selected}
        overflow = [
            scenario
            for scenario in sorted(
                untreated,
                key=lambda scenario: (
                    scenario.failure_triggered,
                    scenario.damage_score,
                    scenario.shock_budget,
                ),
                reverse=True,
            )
            if scenario.scenario_id not in selected_ids
        ]
        selected.extend(overflow[: max(0, limit - len(selected))])
    return selected[:limit]


def _controller_objective(
    summary: ClosedLoopRegimeSummary,
    *,
    fairness_weight: float,
) -> float:
    burden = _monitoring_burden(summary)
    return (
        summary.expected_resilience
        + fairness_weight * summary.expected_fairness_score
        + 0.12 * summary.deployment_accuracy
        + 0.08 * summary.pre_degradation_deployment_rate
        + 0.05 * summary.failure_prevention_rate
        - 0.06 * summary.retarget_rate
        - 0.12 * summary.resilience_regret
        - 0.02 * burden
    )


def _candidate_key(candidate: ControllerPolicyCandidate) -> tuple[float, float, float, float]:
    return (
        candidate.objective_score,
        candidate.expected_resilience,
        candidate.deployment_accuracy,
        candidate.pre_degradation_rate,
        -candidate.monitoring_burden_score,
    )


def _spec_from_candidate(candidate: ControllerPolicyCandidate) -> _ControllerSpec:
    return _ControllerSpec(
        policy_id=candidate.policy_id,
        schedule_id=candidate.schedule_id,
        schedule_start_fraction=float(candidate.schedule_start_fraction or 0.2),
        schedule_interval_fraction=float(candidate.schedule_interval_fraction or 0.15),
        schedule_growth=float(candidate.schedule_growth or 1.1),
        schedule_observation_limit=int(candidate.schedule_observation_limit or max(len(candidate.observation_fractions), 3)),
        confidence_threshold=candidate.confidence_threshold,
        allow_retargeting=candidate.allow_retargeting,
        confirmation_count=candidate.confirmation_count,
        search_method=candidate.search_method,
        generation=candidate.generation,
        parent_policy_id=candidate.parent_policy_id,
    )


def _replace_spec(
    spec: _ControllerSpec,
    *,
    schedule_id: str,
    schedule_start_fraction: float | None = None,
    schedule_interval_fraction: float | None = None,
    schedule_growth: float | None = None,
    schedule_observation_limit: int | None = None,
    confidence_threshold: float | None = None,
    allow_retargeting: bool | None = None,
    confirmation_count: int | None = None,
    search_method: str,
    generation: int,
) -> _ControllerSpec:
    start_fraction = schedule_start_fraction if schedule_start_fraction is not None else spec.schedule_start_fraction
    interval_fraction = schedule_interval_fraction if schedule_interval_fraction is not None else spec.schedule_interval_fraction
    growth = schedule_growth if schedule_growth is not None else spec.schedule_growth
    observation_limit = schedule_observation_limit if schedule_observation_limit is not None else spec.schedule_observation_limit
    threshold = confidence_threshold if confidence_threshold is not None else spec.confidence_threshold
    retargeting = allow_retargeting if allow_retargeting is not None else spec.allow_retargeting
    confirms = confirmation_count if confirmation_count is not None else spec.confirmation_count
    policy_id = (
        f"controller__{schedule_id}__thr_{str(round(threshold, 2)).replace('.', '_')}"
        f"__c{confirms}__{'retarget' if retargeting else 'lock'}"
    )
    return _ControllerSpec(
        policy_id=policy_id,
        schedule_id=schedule_id,
        schedule_start_fraction=round(start_fraction, 2),
        schedule_interval_fraction=round(interval_fraction, 2),
        schedule_growth=round(growth, 2),
        schedule_observation_limit=int(observation_limit),
        confidence_threshold=round(threshold, 2),
        allow_retargeting=retargeting,
        confirmation_count=int(confirms),
        search_method=search_method,
        generation=generation,
        parent_policy_id=spec.policy_id,
    )


def _schedule_from_params(
    *,
    start_fraction: float,
    base_interval_fraction: float,
    interval_growth: float,
    observation_limit: int,
) -> tuple[float, ...]:
    limit = max(3, min(int(observation_limit), 7))
    current = min(max(float(start_fraction), 0.05), 0.95)
    interval = min(max(float(base_interval_fraction), 0.05), 0.45)
    growth = min(max(float(interval_growth), 0.85), 1.6)
    fractions: list[float] = []
    while current < 1.0 - 1e-9 and len(fractions) < limit - 1:
        fractions.append(round(current, 2))
        current += interval
        interval *= growth
    fractions.append(1.0)
    normalized = sorted({min(max(value, 0.05), 1.0) for value in fractions})
    if len(normalized) < 3:
        normalized = sorted({0.2, 0.5, 1.0} | set(normalized))
    return tuple(round(value, 2) for value in normalized)


def _monitoring_burden(summary: ClosedLoopRegimeSummary) -> float:
    return float(summary.mean_observation_count + 1.5 * summary.mean_deployment_count)
