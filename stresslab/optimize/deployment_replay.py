"""Helpers for replaying scenarios with timed intervention deployment."""

from __future__ import annotations

from stresslab.des import Simulator
from stresslab.models import ScenarioSummary, SimulationResult
from stresslab.search.common import apply_shock_vector
from stresslab.systemspec import resolve_spec
from stresslab.systemspec.schema import InterventionSpec, SystemSpec


def resolve_intervention_sequence(
    spec: SystemSpec,
    intervention_ids: list[str],
) -> list[InterventionSpec]:
    """Expand bundles into a stable ordered list of unique leaf interventions."""

    lookup = {intervention.id: intervention for intervention in spec.interventions}
    ordered: list[InterventionSpec] = []
    seen_leaf_ids: set[str] = set()

    def visit(intervention_id: str, trail: tuple[str, ...] = ()) -> None:
        intervention = lookup.get(intervention_id)
        if intervention is None:
            raise ValueError(f"Unknown intervention '{intervention_id}' in deployment replay.")
        if intervention.id in trail:
            raise ValueError(f"Bundle cycle detected involving '{intervention.id}'.")
        if intervention.action_type == "bundle" or intervention.bundle_members:
            for member_id in intervention.bundle_members:
                visit(member_id, (*trail, intervention.id))
            return
        if intervention.id in seen_leaf_ids:
            return
        seen_leaf_ids.add(intervention.id)
        ordered.append(intervention)

    for intervention_id in intervention_ids:
        visit(intervention_id)
    return ordered


def run_scenario_with_deployment(
    spec: SystemSpec,
    scenario: ScenarioSummary,
    *,
    intervention_ids: list[str] | None,
    decision_time: float,
    seed: int,
) -> ScenarioSummary | SimulationResult:
    """Replay a stress scenario and deploy the chosen interventions at runtime."""

    if not intervention_ids:
        return scenario
    scenario_spec = apply_shock_vector(spec, scenario.shock_vector)
    deploy_at = min(max(float(decision_time), float(spec.clock.start)), float(spec.clock.end))
    deployments = [
        (deploy_at, intervention)
        for intervention in resolve_intervention_sequence(scenario_spec, intervention_ids)
    ]
    simulator = Simulator(
        resolve_spec(scenario_spec),
        seed=seed,
        baseline_metrics=scenario.metrics,
    )
    return simulator.run(deployments=deployments)
