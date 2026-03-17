"""Counterfactual explanation helpers."""

from __future__ import annotations

from stresslab.models import CounterfactualResult


def counterfactuals(result, interventions) -> list[CounterfactualResult]:
    """Generate human-readable mitigation counterfactuals."""

    outputs: list[CounterfactualResult] = []
    for intervention in interventions:
        resilience = intervention.metrics.get("resilience_score", 0.0)
        baseline = result.metrics.get("resilience_score", 0.0)
        prevented_failure = bool(result.failure_triggered and intervention.failure_prevented)
        outputs.append(
            CounterfactualResult(
                intervention_id=intervention.intervention_id,
                prevented_failure=prevented_failure,
                resilience_delta=resilience - baseline,
                narrative=(
                    f"If '{intervention.intervention_id}' had been active, resilience would change by "
                    f"{resilience - baseline:.3f}."
                ),
            )
        )
    return outputs
