"""Pareto frontier helpers for closed-loop controller candidates."""

from __future__ import annotations

from collections.abc import Callable

from stresslab.models import ControllerPolicyCandidate

ObjectiveValue = tuple[float, ...]


def controller_pareto_frontier(
    candidates: list[ControllerPolicyCandidate],
    *,
    fairness_weight: float = 0.0,
) -> list[ControllerPolicyCandidate]:
    """Return non-dominated controller candidates under performance-vs-burden tradeoffs."""

    if not candidates:
        return []
    frontier: list[ControllerPolicyCandidate] = []
    for candidate in candidates:
        candidate_values = _controller_objectives(candidate, fairness_weight=fairness_weight)
        dominated = False
        for other in candidates:
            if other is candidate:
                continue
            other_values = _controller_objectives(other, fairness_weight=fairness_weight)
            if _dominates(other_values, candidate_values):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    frontier.sort(key=_frontier_sort_key(fairness_weight=fairness_weight), reverse=True)
    return frontier


def _controller_objectives(
    candidate: ControllerPolicyCandidate,
    *,
    fairness_weight: float,
) -> ObjectiveValue:
    return (
        candidate.expected_resilience + fairness_weight * candidate.expected_fairness_score,
        candidate.deployment_accuracy,
        candidate.pre_degradation_rate,
        -candidate.monitoring_burden_score,
    )


def _dominates(left: ObjectiveValue, right: ObjectiveValue) -> bool:
    return all(left_value >= right_value for left_value, right_value in zip(left, right, strict=True)) and any(
        left_value > right_value
        for left_value, right_value in zip(left, right, strict=True)
    )


def _frontier_sort_key(
    *,
    fairness_weight: float,
) -> Callable[[ControllerPolicyCandidate], tuple[float, ...]]:
    return lambda candidate: (
        candidate.objective_score,
        candidate.expected_resilience + fairness_weight * candidate.expected_fairness_score,
        candidate.deployment_accuracy,
        -candidate.monitoring_burden_score,
    )
