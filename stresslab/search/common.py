"""Shared search helpers."""

from __future__ import annotations

from stresslab.des import Simulator
from stresslab.errors import SearchError
from stresslab.systemspec.parser import resolve_spec
from stresslab.systemspec.schema import SearchDimensionConfig, ShockSpec, SystemSpec


def budget_from_vector(vector: dict[str, float], search_space: list[SearchDimensionConfig]) -> float:
    """Compute the standard v0.1 shock budget."""

    total = 0.0
    for dimension in search_space:
        span = dimension.max - dimension.min
        value = vector.get(dimension.id, dimension.min)
        magnitude = 0.0 if span <= 0 else max(0.0, min(1.0, (value - dimension.min) / span))
        total += dimension.cost_weight * magnitude
    return total


def apply_shock_vector(spec: SystemSpec, vector: dict[str, float]) -> SystemSpec:
    """Attach search-generated shocks to a copied spec."""

    updated = spec.model_copy(deep=True)
    generated: list[ShockSpec] = []
    for dimension in updated.search.search_space:
        value = vector.get(dimension.id, dimension.min)
        if abs(value - dimension.min) <= 1e-9:
            continue
        generated.append(
            ShockSpec(
                id=f"search__{dimension.id}",
                type=dimension.kind,
                target=dimension.target,
                start=dimension.start,
                duration=dimension.duration,
                factor=value if "multiplier" in dimension.kind or "factor" in dimension.kind else None,
                fraction=value if "fraction" in dimension.kind else None,
                delta=value if "delta" in dimension.kind else None,
                value=value,
            )
        )
    updated.shocks.extend(generated)
    return updated


def run_vector(
    spec: SystemSpec,
    vector: dict[str, float],
    *,
    seed: int,
    baseline_metrics: dict[str, float],
) -> tuple[SystemSpec, dict[str, float], object]:
    """Run a scenario defined by a shock vector."""

    scenario_spec = apply_shock_vector(spec, vector)
    resolved = resolve_spec(scenario_spec)
    simulator = Simulator(resolved, seed=seed, baseline_metrics=baseline_metrics)
    result = simulator.run()
    return scenario_spec, result.metrics, result


def damage_score(
    result,
    *,
    objective: str,
    weights: dict[str, float],
) -> float:
    """Evaluate one of the required damage functionals."""

    metrics = result.metrics
    if objective == "failure_only":
        return 1.0 if result.failure_triggered else 0.0
    if objective == "throughput_loss":
        return metrics.get("throughput_loss", 0.0)
    if objective == "delay_damage":
        return (
            metrics.get("mean_wait_norm", 0.0)
            + metrics.get("p95_wait_norm", 0.0)
            + metrics.get("backlog_norm", 0.0)
        )
    if objective == "recovery_damage":
        return metrics.get("recovery_norm", 0.0) + metrics.get("cascade_norm", 0.0)
    if objective == "composite_damage":
        return (
            weights.get("throughput_loss", 0.0) * metrics.get("throughput_loss", 0.0)
            + weights.get("mean_wait_norm", 0.0) * metrics.get("mean_wait_norm", 0.0)
            + weights.get("p95_wait_norm", 0.0) * metrics.get("p95_wait_norm", 0.0)
            + weights.get("backlog_norm", 0.0) * metrics.get("backlog_norm", 0.0)
            + weights.get("holding_norm", 0.0) * metrics.get("holding_norm", 0.0)
            + weights.get("recovery_norm", 0.0) * metrics.get("recovery_norm", 0.0)
            + weights.get("cascade_norm", 0.0) * metrics.get("cascade_norm", 0.0)
            + weights.get("edge_cascade_norm", 0.0) * metrics.get("edge_cascade_norm", 0.0)
            + weights.get("fairness_degradation", 0.0) * metrics.get("fairness_degradation", 0.0)
        )
    raise SearchError(f"Unsupported damage function '{objective}'.")
