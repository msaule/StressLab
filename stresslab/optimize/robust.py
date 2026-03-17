"""Robust optimization helpers and scenario portfolio generation."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from stresslab.des import Simulator
from stresslab.models import ScenarioSummary
from stresslab.search import Searcher
from stresslab.search.common import apply_shock_vector, budget_from_vector, damage_score
from stresslab.search.random_search import sample_under_budget
from stresslab.systemspec.parser import resolve_spec
from stresslab.systemspec.schema import SystemSpec


def robust_objective(
    expected_resilience: float,
    worst_case_resilience: float,
    resilience_std: float,
    cost: float,
    *,
    fairness_score: float = 0.0,
    fairness_weight: float = 0.0,
    tail_weight: float = 0.75,
    variability_penalty: float = 0.3,
    cost_penalty: float = 0.0,
) -> float:
    """Compute a simple robust intervention score."""

    return (
        expected_resilience
        + tail_weight * worst_case_resilience
        + fairness_weight * fairness_score
        - variability_penalty * resilience_std
        - cost_penalty * cost
    )


def build_scenario_portfolio(
    spec: SystemSpec,
    *,
    seed: int,
    scenario_budget: float | None = None,
    random_samples: int = 4,
) -> list[ScenarioSummary]:
    """Construct a compact portfolio of baseline, adversarial, and random scenarios."""

    budget = scenario_budget if scenario_budget is not None else (spec.search.budget or 0.5)
    summaries: list[ScenarioSummary] = []
    seen: set[tuple[float, ...]] = set()

    configured_result = _run_vector(spec, {}, seed=seed, baseline_metrics={})
    summaries.append(
        _summary_from_result(
            scenario_id="configured",
            source="configured",
            shock_vector={},
            spec=spec,
            result=configured_result,
        )
    )
    seen.add(_vector_key(spec, {}))

    if not spec.search.search_space:
        return summaries

    searcher = Searcher(spec, objective="portfolio", seed=seed)
    min_failure = searcher.find_min_failure()
    if min_failure.success and min_failure.best_shock_budget != float("inf"):
        _add_scenario_if_new(
            summaries,
            seen,
            spec,
            scenario_id="min_failure",
            source="min_failure",
            shock_vector=min_failure.best_shock_vector,
            seed=seed,
            baseline_metrics=configured_result.metrics,
        )

    worst_case = searcher.find_worst_case(budget)
    _add_scenario_if_new(
        summaries,
        seen,
        spec,
        scenario_id="worst_case",
        source="worst_case",
        shock_vector=worst_case.best_shock_vector,
        seed=seed,
        baseline_metrics=configured_result.metrics,
    )

    rng = np.random.default_rng(seed + 17)
    for index in range(random_samples):
        vector = sample_under_budget(rng, spec.search.search_space, budget)
        _add_scenario_if_new(
            summaries,
            seen,
            spec,
            scenario_id=f"random_{index + 1}",
            source="random_budget",
            shock_vector=vector,
            seed=seed,
            baseline_metrics=configured_result.metrics,
        )

    return summaries


def evaluate_intervention_portfolio(
    spec: SystemSpec,
    interventions: Iterable,
    scenarios: list[ScenarioSummary],
    *,
    seed: int,
) -> list[ScenarioSummary]:
    """Evaluate a set of interventions across an existing scenario portfolio."""

    from stresslab.optimize.interventions import apply_interventions

    updated_spec = apply_interventions(spec, interventions)
    evaluated: list[ScenarioSummary] = []
    for scenario in scenarios:
        result = _run_vector(
            updated_spec,
            scenario.shock_vector,
            seed=seed,
            baseline_metrics=scenario.metrics,
        )
        evaluated.append(
            _summary_from_result(
                scenario_id=scenario.scenario_id,
                source=scenario.source,
                shock_vector=scenario.shock_vector,
                spec=updated_spec,
                result=result,
            )
        )
    return evaluated


def _add_scenario_if_new(
    summaries: list[ScenarioSummary],
    seen: set[tuple[float, ...]],
    spec: SystemSpec,
    *,
    scenario_id: str,
    source: str,
    shock_vector: dict[str, float],
    seed: int,
    baseline_metrics: dict[str, float],
) -> None:
    key = _vector_key(spec, shock_vector)
    if key in seen:
        return
    result = _run_vector(spec, shock_vector, seed=seed, baseline_metrics=baseline_metrics)
    summaries.append(
        _summary_from_result(
            scenario_id=scenario_id,
            source=source,
            shock_vector=shock_vector,
            spec=spec,
            result=result,
        )
    )
    seen.add(key)


def _summary_from_result(
    *,
    scenario_id: str,
    source: str,
    shock_vector: dict[str, float],
    spec: SystemSpec,
    result,
) -> ScenarioSummary:
    return ScenarioSummary(
        scenario_id=scenario_id,
        source=source,
        shock_vector=shock_vector,
        shock_budget=budget_from_vector(shock_vector, spec.search.search_space),
        failure_triggered=result.failure_triggered,
        damage_score=damage_score(
            result,
            objective=spec.search.damage_function,
            weights=spec.search.damage_weights,
        ),
        metrics=result.metrics,
    )


def _run_vector(
    spec: SystemSpec,
    vector: dict[str, float],
    *,
    seed: int,
    baseline_metrics: dict[str, float],
):
    scenario_spec = apply_shock_vector(spec, vector)
    resolved = resolve_spec(scenario_spec)
    simulator = Simulator(resolved, seed=seed, baseline_metrics=baseline_metrics)
    return simulator.run()


def _vector_key(spec: SystemSpec, vector: dict[str, float]) -> tuple[float, ...]:
    return tuple(
        round(vector.get(dimension.id, dimension.min), 8)
        for dimension in spec.search.search_space
    )
