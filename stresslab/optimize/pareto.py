"""Pareto frontier helpers for intervention analysis."""

from __future__ import annotations

from collections.abc import Callable

from stresslab.models import RankedIntervention

ObjectiveValue = tuple[float, ...]


def pareto_frontier(
    interventions: list[RankedIntervention],
    *,
    robust_mode: bool,
) -> list[RankedIntervention]:
    """Return non-dominated interventions under the selected objective set."""

    if not interventions:
        return []
    scorer = _robust_objectives if robust_mode else _standard_objectives
    frontier: list[RankedIntervention] = []
    for candidate in interventions:
        candidate_values = scorer(candidate)
        dominated = False
        for other in interventions:
            if other is candidate:
                continue
            other_values = scorer(other)
            if _dominates(other_values, candidate_values):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    frontier.sort(key=_frontier_sort_key(robust_mode), reverse=True)
    return frontier


def _dominates(left: ObjectiveValue, right: ObjectiveValue) -> bool:
    return all(left_value >= right_value for left_value, right_value in zip(left, right, strict=True)) and any(
        left_value > right_value
        for left_value, right_value in zip(left, right, strict=True)
    )


def _standard_objectives(item: RankedIntervention) -> ObjectiveValue:
    return (
        item.resilience_gain,
        1.0 if item.failure_prevented else 0.0,
        -item.cost,
    )


def _robust_objectives(item: RankedIntervention) -> ObjectiveValue:
    return (
        item.expected_resilience or 0.0,
        item.worst_case_resilience or 0.0,
        item.failure_prevention_rate or 0.0,
        -item.cost,
    )


def _frontier_sort_key(robust_mode: bool) -> Callable[[RankedIntervention], tuple[float, ...]]:
    if robust_mode:
        return lambda item: (
            item.robust_score or 0.0,
            item.expected_resilience or 0.0,
            -(item.cost),
        )
    return lambda item: (
        item.resilience_gain,
        item.roi,
        -(item.cost),
    )
