from __future__ import annotations

from stresslab.optimize import (
    bundle_hierarchy_rows,
    expand_intervention_catalog,
    synthesize_adaptive_policy_interventions,
    synthesize_controller_bundles,
    synthesize_dynamic_policy_interventions,
    synthesize_hierarchical_playbooks,
    synthesize_policy_interventions,
)
from stresslab.systemspec import load_spec


def test_synthesize_policy_interventions_generates_queue_policy_candidates():
    spec = load_spec("examples/markets/liquidity_withdrawal.yml")
    generated = synthesize_policy_interventions(spec)

    generated_ids = {intervention.id for intervention in generated}
    assert "policy_fifo__order_gateway" in generated_ids
    assert any(
        (intervention.applicability_constraints or {}).get("source") == "generated_policy"
        for intervention in generated
    )


def test_expand_intervention_catalog_policy_only_replaces_authored_interventions():
    spec = load_spec("examples/markets/liquidity_withdrawal.yml")
    expanded, catalog = expand_intervention_catalog(
        spec,
        expand_policies=True,
        policy_only=True,
    )

    assert expanded.interventions
    assert catalog == expanded.interventions
    assert all(
        (intervention.applicability_constraints or {}).get("generated", False)
        for intervention in expanded.interventions
    )


def test_synthesize_dynamic_policy_interventions_generates_timed_candidates():
    spec = load_spec("examples/healthcare/ed_basic.yml")
    generated = synthesize_dynamic_policy_interventions(spec)

    assert generated
    assert any(intervention.action_type == "scheduled_priority_policy_change" for intervention in generated)
    assert all(intervention.start is not None for intervention in generated)
    assert any(
        (intervention.applicability_constraints or {}).get("dynamic", False)
        for intervention in generated
    )


def test_synthesize_adaptive_policy_interventions_generates_threshold_candidates():
    spec = load_spec("examples/healthcare/ed_basic.yml")
    generated = synthesize_adaptive_policy_interventions(spec)

    assert generated
    assert any(intervention.action_type == "threshold_priority_policy_change" for intervention in generated)
    assert any(intervention.trigger_metric == "queue_length" for intervention in generated)
    assert any(intervention.stages for intervention in generated)
    assert any(
        (intervention.applicability_constraints or {}).get("adaptive", False)
        for intervention in generated
    )


def test_synthesize_controller_bundles_generates_cross_target_playbooks():
    spec = load_spec("examples/healthcare/ed_basic.yml")
    adaptive = synthesize_adaptive_policy_interventions(spec)
    bundles = synthesize_controller_bundles(spec, adaptive)

    assert bundles
    assert all(intervention.action_type == "bundle" for intervention in bundles)
    assert any(len(intervention.bundle_members) >= 2 for intervention in bundles)
    assert len({intervention.id for intervention in bundles}) == len(bundles)


def test_synthesize_hierarchical_playbooks_generates_nested_bundles():
    spec = load_spec("examples/healthcare/ed_basic.yml")
    adaptive = synthesize_adaptive_policy_interventions(spec)
    bundles = synthesize_controller_bundles(spec, adaptive)
    playbooks = synthesize_hierarchical_playbooks(spec, [*adaptive, *bundles])

    assert playbooks
    assert all(intervention.action_type == "bundle" for intervention in playbooks)
    assert any(intervention.id.startswith("hierarchical_playbook__") for intervention in playbooks)
    assert all(
        (intervention.applicability_constraints or {}).get("hierarchical_bundle", False)
        for intervention in playbooks
    )
    hierarchy_rows = bundle_hierarchy_rows([*adaptive, *bundles, *playbooks])
    assert any(row["root_bundle_id"].startswith("hierarchical_playbook__") for row in hierarchy_rows)
