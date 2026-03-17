from __future__ import annotations

from stresslab.optimize import apply_interventions
from stresslab.systemspec.schema import (
    ClockConfig,
    InterventionSpec,
    NodeSpec,
    ServiceTimeConfig,
    SystemMeta,
    SystemSpec,
)


def test_apply_interventions_expands_bundle_members_once():
    spec = SystemSpec(
        system=SystemMeta(name="bundle_test", domain="test"),
        clock=ClockConfig(end=60),
        nodes=[
            NodeSpec(
                id="ward",
                servers=1,
                buffer_capacity=5,
                service_time=ServiceTimeConfig(distribution="deterministic", value=5),
            )
        ],
        interventions=[
            InterventionSpec(
                id="add_staff",
                target="ward",
                action_type="add_servers",
                delta=1,
                cost=100,
            ),
            InterventionSpec(
                id="add_buffer",
                target="ward",
                action_type="increase_buffer_capacity",
                delta=3,
                cost=50,
            ),
            InterventionSpec(
                id="ward_playbook",
                target="__bundle__",
                action_type="bundle",
                bundle_members=["add_staff", "add_buffer"],
                cost=130,
            ),
        ],
    )

    updated = apply_interventions(spec, [spec.interventions[2], spec.interventions[0]])
    ward = updated.nodes[0]
    assert ward.servers == 2
    assert ward.buffer_capacity == 8


def test_apply_interventions_expands_nested_bundles_without_double_counting():
    spec = SystemSpec(
        system=SystemMeta(name="nested_bundle_test", domain="test"),
        clock=ClockConfig(end=60),
        nodes=[
            NodeSpec(
                id="ward",
                servers=1,
                buffer_capacity=5,
                service_time=ServiceTimeConfig(distribution="deterministic", value=5),
            )
        ],
        interventions=[
            InterventionSpec(
                id="add_staff",
                target="ward",
                action_type="add_servers",
                delta=1,
                cost=100,
            ),
            InterventionSpec(
                id="add_buffer",
                target="ward",
                action_type="increase_buffer_capacity",
                delta=3,
                cost=50,
            ),
            InterventionSpec(
                id="ward_bundle",
                target="__bundle__",
                action_type="bundle",
                bundle_members=["add_staff", "add_buffer"],
                cost=130,
            ),
            InterventionSpec(
                id="ward_playbook",
                target="__bundle__",
                action_type="bundle",
                bundle_members=["ward_bundle", "add_staff"],
                cost=180,
            ),
        ],
    )

    updated = apply_interventions(spec, [spec.interventions[3]])
    ward = updated.nodes[0]
    assert ward.servers == 2
    assert ward.buffer_capacity == 8
