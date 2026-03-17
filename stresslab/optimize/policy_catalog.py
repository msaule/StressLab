"""Synthetic policy intervention generation."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from stresslab.shocks import flatten_shocks
from stresslab.systemspec.schema import InterventionSpec, PolicyStageSpec, SystemSpec


def synthesize_policy_interventions(
    spec: SystemSpec,
    *,
    queue_policy_base_cost: float = 220.0,
    reroute_base_cost: float = 320.0,
    backup_edge_base_cost: float = 550.0,
    reroute_step: float = 0.2,
) -> list[InterventionSpec]:
    """Generate policy and routing candidates from the current system topology."""

    existing = {_signature(intervention) for intervention in spec.interventions}
    generated: list[InterventionSpec] = []
    class_ids = [flow_class.id for flow_class in spec.classes]

    for node in spec.nodes:
        available_classes = node.priority_classes or class_ids
        if available_classes:
            if node.queue_policy != "priority":
                candidate = InterventionSpec(
                    id=f"policy_priority__{node.id}",
                    label=f"Promote {node.id} to priority queue",
                    target=node.id,
                    action_type="priority_policy_change",
                    replacement="priority",
                    cost=queue_policy_base_cost + 20.0 * max(node.servers, 1),
                    implementation_difficulty=0.5,
                    fairness_impact=0.15,
                    applicability_constraints={
                        "generated": True,
                        "source": "generated_policy",
                        "policy_type": "queue_policy",
                    },
                )
                if _signature(candidate) not in existing:
                    generated.append(candidate)
                    existing.add(_signature(candidate))
            if node.queue_policy != "fifo":
                candidate = InterventionSpec(
                    id=f"policy_fifo__{node.id}",
                    label=f"Rebalance {node.id} to FIFO queue",
                    target=node.id,
                    action_type="priority_policy_change",
                    replacement="fifo",
                    cost=queue_policy_base_cost,
                    implementation_difficulty=0.35,
                    fairness_impact=0.05,
                    applicability_constraints={
                        "generated": True,
                        "source": "generated_policy",
                        "policy_type": "queue_policy",
                    },
                )
                if _signature(candidate) not in existing:
                    generated.append(candidate)
                    existing.add(_signature(candidate))

    outgoing: dict[str, list] = defaultdict(list)
    for edge in spec.edges:
        outgoing[edge.from_node].append(edge)

    for node_id, edges in outgoing.items():
        enabled_edges = [edge for edge in edges if edge.enabled]
        if len(enabled_edges) >= 2:
            for edge in enabled_edges:
                delta = min(reroute_step, max(0.0, 1.0 - edge.routing.probability))
                if delta <= 1e-9:
                    continue
                candidate = InterventionSpec(
                    id=f"routing_bias__{node_id}__{edge.to_node}",
                    label=f"Bias routing from {node_id} to {edge.to_node}",
                    target=f"{edge.from_node}->{edge.to_node}",
                    action_type="reroute_fraction",
                    delta=delta,
                    cost=reroute_base_cost,
                    implementation_difficulty=0.65,
                    fairness_impact=0.1,
                    applicability_constraints={
                        "generated": True,
                        "source": "generated_policy",
                        "policy_type": "routing_bias",
                    },
                )
                if _signature(candidate) not in existing:
                    generated.append(candidate)
                    existing.add(_signature(candidate))

        for edge in edges:
            if edge.enabled:
                continue
            candidate = InterventionSpec(
                id=f"enable_backup__{edge.from_node}__{edge.to_node}",
                label=f"Enable backup route {edge.from_node} to {edge.to_node}",
                target=f"{edge.from_node}->{edge.to_node}",
                action_type="enable_backup_edge",
                cost=backup_edge_base_cost,
                implementation_difficulty=0.9,
                fairness_impact=0.0,
                applicability_constraints={
                    "generated": True,
                    "source": "generated_policy",
                    "policy_type": "backup_route",
                },
            )
            if _signature(candidate) not in existing:
                generated.append(candidate)
                existing.add(_signature(candidate))

    return generated


def synthesize_dynamic_policy_interventions(
    spec: SystemSpec,
    *,
    queue_policy_base_cost: float = 260.0,
    reroute_base_cost: float = 340.0,
    reroute_step: float = 0.2,
    max_windows: int = 3,
) -> list[InterventionSpec]:
    """Generate timed policy candidates anchored to stress windows."""

    existing = {_signature(intervention) for intervention in spec.interventions}
    generated: list[InterventionSpec] = []
    class_ids = [flow_class.id for flow_class in spec.classes]
    windows = _policy_windows(spec, max_windows=max_windows)
    outgoing: dict[str, list] = defaultdict(list)
    for edge in spec.edges:
        outgoing[edge.from_node].append(edge)

    for window in windows:
        for node in spec.nodes:
            available_classes = node.priority_classes or class_ids
            if available_classes and node.queue_policy != "priority":
                candidate = InterventionSpec(
                    id=f"timed_policy_priority__{node.id}__{window['window_id']}",
                    label=f"Prioritize {node.id} during {window['window_label']}",
                    target=node.id,
                    action_type="scheduled_priority_policy_change",
                    policy_mode="scheduled",
                    replacement="priority",
                    start=window["start"],
                    duration=window["duration"],
                    cost=queue_policy_base_cost + 25.0 * max(node.servers, 1),
                    implementation_difficulty=0.7,
                    fairness_impact=0.2,
                    applicability_constraints={
                        "generated": True,
                        "dynamic": True,
                        "source": "generated_dynamic_policy",
                        "policy_type": "queue_policy_schedule",
                        "window_id": window["window_id"],
                        "window_label": window["window_label"],
                    },
                )
                if _signature(candidate) not in existing:
                    generated.append(candidate)
                    existing.add(_signature(candidate))

        for node_id, edges in outgoing.items():
            enabled_edges = [edge for edge in edges if edge.enabled]
            if len(enabled_edges) < 2:
                continue
            for edge in enabled_edges:
                delta = min(reroute_step, max(0.0, 1.0 - edge.routing.probability))
                if delta <= 1e-9:
                    continue
                candidate = InterventionSpec(
                    id=f"timed_routing_bias__{node_id}__{edge.to_node}__{window['window_id']}",
                    label=f"Bias routing {node_id} to {edge.to_node} during {window['window_label']}",
                    target=f"{edge.from_node}->{edge.to_node}",
                    action_type="scheduled_reroute_fraction",
                    policy_mode="scheduled",
                    start=window["start"],
                    duration=window["duration"],
                    delta=delta,
                    cost=reroute_base_cost,
                    implementation_difficulty=0.8,
                    fairness_impact=0.1,
                    applicability_constraints={
                        "generated": True,
                        "dynamic": True,
                        "source": "generated_dynamic_policy",
                        "policy_type": "routing_bias_schedule",
                        "window_id": window["window_id"],
                        "window_label": window["window_label"],
                    },
                )
                if _signature(candidate) not in existing:
                    generated.append(candidate)
                    existing.add(_signature(candidate))

    return generated


def synthesize_adaptive_policy_interventions(
    spec: SystemSpec,
    *,
    queue_policy_base_cost: float = 290.0,
    reroute_base_cost: float = 360.0,
    reroute_step: float = 0.2,
) -> list[InterventionSpec]:
    """Generate threshold-triggered policy candidates from topology and capacity."""

    existing = {_signature(intervention) for intervention in spec.interventions}
    generated: list[InterventionSpec] = []
    class_ids = [flow_class.id for flow_class in spec.classes]
    outgoing: dict[str, list] = defaultdict(list)
    for edge in spec.edges:
        outgoing[edge.from_node].append(edge)

    for node in spec.nodes:
        available_classes = node.priority_classes or class_ids
        queue_threshold = float(max(2, min(node.buffer_capacity or 8, max(node.servers * 3, 4))))
        clear_threshold = max(0.0, queue_threshold - max(1.0, 0.25 * queue_threshold))
        if available_classes and node.queue_policy != "priority":
            candidate = InterventionSpec(
                id=f"adaptive_priority__{node.id}",
                label=f"Prioritize {node.id} when backlog spikes",
                target=node.id,
                action_type="threshold_priority_policy_change",
                policy_mode="threshold",
                replacement="priority",
                trigger_metric="queue_length",
                trigger_node=node.id,
                trigger_threshold=queue_threshold,
                clear_threshold=clear_threshold,
                min_active_duration=12.0,
                cooldown=8.0,
                cost=queue_policy_base_cost + 25.0 * max(node.servers, 1),
                implementation_difficulty=0.8,
                fairness_impact=0.18,
                applicability_constraints={
                    "generated": True,
                    "dynamic": True,
                    "adaptive": True,
                    "source": "generated_adaptive_policy",
                    "policy_type": "queue_policy_threshold",
                },
            )
            if _signature(candidate) not in existing:
                generated.append(candidate)
                existing.add(_signature(candidate))

    for node_id, edges in outgoing.items():
        enabled_edges = [edge for edge in edges if edge.enabled]
        if len(enabled_edges) < 2:
            continue
        trigger_threshold = 0.9
        clear_threshold = 0.7
        for edge in enabled_edges:
            delta = min(reroute_step, max(0.0, 1.0 - edge.routing.probability))
            if delta <= 1e-9:
                continue
            candidate = InterventionSpec(
                id=f"adaptive_routing_bias__{node_id}__{edge.to_node}",
                label=f"Bias routing {node_id} to {edge.to_node} under congestion",
                target=f"{edge.from_node}->{edge.to_node}",
                action_type="threshold_reroute_fraction",
                policy_mode="threshold",
                delta=delta,
                trigger_metric="utilization",
                trigger_node=node_id,
                trigger_threshold=trigger_threshold,
                clear_threshold=clear_threshold,
                min_active_duration=10.0,
                cooldown=6.0,
                cost=reroute_base_cost,
                implementation_difficulty=0.85,
                fairness_impact=0.08,
                applicability_constraints={
                    "generated": True,
                    "dynamic": True,
                    "adaptive": True,
                    "source": "generated_adaptive_policy",
                    "policy_type": "routing_bias_threshold",
                },
            )
            if _signature(candidate) not in existing:
                generated.append(candidate)
                existing.add(_signature(candidate))

            ladder_delta = min(max(reroute_step, 0.25), max(0.0, 1.0 - edge.routing.probability))
            if ladder_delta <= max(delta, 1e-9):
                continue
            ladder_candidate = InterventionSpec(
                id=f"adaptive_routing_ladder__{node_id}__{edge.to_node}",
                label=f"Escalate routing {node_id} to {edge.to_node} as congestion worsens",
                target=f"{edge.from_node}->{edge.to_node}",
                action_type="threshold_reroute_fraction",
                policy_mode="threshold",
                delta=delta,
                trigger_metric="utilization",
                trigger_node=node_id,
                trigger_threshold=0.75,
                clear_threshold=0.6,
                min_active_duration=10.0,
                cooldown=6.0,
                stages=[
                    PolicyStageSpec(
                        id="stage_watch",
                        label="watch",
                        trigger_threshold=0.75,
                        clear_threshold=0.6,
                        action_type="reroute_fraction",
                        delta=delta,
                    ),
                    PolicyStageSpec(
                        id="stage_surge",
                        label="surge",
                        trigger_threshold=0.9,
                        clear_threshold=0.75,
                        action_type="reroute_fraction",
                        delta=ladder_delta,
                    ),
                ],
                cost=reroute_base_cost + 90.0,
                implementation_difficulty=0.92,
                fairness_impact=0.08,
                applicability_constraints={
                    "generated": True,
                    "dynamic": True,
                    "adaptive": True,
                    "multistage": True,
                    "source": "generated_adaptive_policy",
                    "policy_type": "routing_bias_ladder",
                },
            )
            if _signature(ladder_candidate) not in existing:
                generated.append(ladder_candidate)
                existing.add(_signature(ladder_candidate))

    return generated


def synthesize_controller_bundles(
    spec: SystemSpec,
    candidates: list[InterventionSpec],
    *,
    bundle_discount: float = 0.92,
    max_bundle_members: int = 2,
    max_bundles_per_trigger: int = 3,
) -> list[InterventionSpec]:
    """Generate coordinated controller bundles from existing adaptive candidates."""

    existing = {_signature(intervention) for intervention in spec.interventions}
    existing.update(_signature(intervention) for intervention in candidates if intervention.action_type == "bundle")
    generated: list[InterventionSpec] = []
    grouped: dict[str, list[InterventionSpec]] = defaultdict(list)
    for intervention in candidates:
        constraints = intervention.applicability_constraints or {}
        if intervention.action_type == "bundle":
            continue
        if not constraints.get("adaptive", False):
            continue
        if not intervention.trigger_node:
            continue
        grouped[intervention.trigger_node].append(intervention)

    for trigger_node, interventions in grouped.items():
        ranked = sorted(
            interventions,
            key=lambda item: (
                0 if (item.applicability_constraints or {}).get("multistage", False) else 1,
                item.cost,
                item.id,
            ),
        )
        created = 0
        for combo in combinations(ranked, min(max_bundle_members, len(ranked))):
            if len({member.target for member in combo}) < len(combo):
                continue
            bundle = _bundle_from_members(
                trigger_node=trigger_node,
                members=list(combo),
                discount=bundle_discount,
            )
            if _signature(bundle) in existing:
                continue
            generated.append(bundle)
            existing.add(_signature(bundle))
            created += 1
            if created >= max_bundles_per_trigger:
                break
    return generated


def synthesize_hierarchical_playbooks(
    spec: SystemSpec,
    candidates: list[InterventionSpec],
    *,
    playbook_discount: float = 0.9,
    max_playbooks_per_trigger: int = 2,
) -> list[InterventionSpec]:
    """Generate nested playbooks from controller bundles and adaptive members."""

    lookup = {intervention.id: intervention for intervention in [*spec.interventions, *candidates]}
    existing = {_signature(intervention) for intervention in spec.interventions}
    existing.update(_signature(intervention) for intervention in candidates)
    generated: list[InterventionSpec] = []
    grouped: dict[str, list[InterventionSpec]] = defaultdict(list)
    adaptive_candidates = [
        intervention
        for intervention in candidates
        if (intervention.applicability_constraints or {}).get("adaptive", False)
    ]

    for intervention in candidates:
        if intervention.action_type != "bundle":
            continue
        trigger_node = _intervention_trigger_node(intervention, lookup)
        if not trigger_node:
            continue
        grouped[trigger_node].append(intervention)

    for trigger_node, bundles in grouped.items():
        support_candidates = [
            candidate
            for candidate in adaptive_candidates
            if _intervention_trigger_node(candidate, lookup) == trigger_node
        ]
        created = 0
        for bundle in sorted(bundles, key=lambda item: (item.cost, item.id)):
            support = next(
                (
                    candidate
                    for candidate in support_candidates
                    if candidate.id != bundle.id and candidate.id not in bundle.bundle_members
                ),
                None,
            )
            if support is None:
                continue
            playbook = _playbook_from_members(
                trigger_node=trigger_node,
                members=[bundle, support],
                discount=playbook_discount,
                lookup=lookup,
            )
            if _signature(playbook) in existing:
                continue
            generated.append(playbook)
            existing.add(_signature(playbook))
            created += 1
            if created >= max_playbooks_per_trigger:
                break
    return generated


def expand_intervention_catalog(
    spec: SystemSpec,
    *,
    expand_policies: bool,
    expand_dynamic_policies: bool = False,
    expand_adaptive_policies: bool = False,
    expand_controller_bundles: bool = False,
    expand_hierarchical_playbooks: bool = False,
    policy_only: bool = False,
    dynamic_only: bool = False,
    adaptive_only: bool = False,
    bundle_only: bool = False,
    playbook_only: bool = False,
) -> tuple[SystemSpec, list[InterventionSpec]]:
    """Return a copied spec with optional generated policy candidates appended."""

    if (
        not expand_policies
        and not expand_dynamic_policies
        and not expand_adaptive_policies
        and not expand_controller_bundles
        and not expand_hierarchical_playbooks
        and not policy_only
        and not dynamic_only
        and not adaptive_only
        and not bundle_only
        and not playbook_only
    ):
        return spec, list(spec.interventions)

    updated = spec.model_copy(deep=True)
    generated_static = (
        synthesize_policy_interventions(updated)
        if expand_policies or policy_only
        else []
    )
    generated_dynamic = (
        synthesize_dynamic_policy_interventions(updated)
        if expand_dynamic_policies or dynamic_only
        else []
    )
    generated_adaptive = (
        synthesize_adaptive_policy_interventions(updated)
        if expand_adaptive_policies or adaptive_only
        else []
    )
    bundle_source = [*updated.interventions, *generated_static, *generated_dynamic, *generated_adaptive]
    generated_bundles = (
        synthesize_controller_bundles(updated, bundle_source)
        if expand_controller_bundles or bundle_only or expand_hierarchical_playbooks or playbook_only
        else []
    )
    playbook_source = [*bundle_source, *generated_bundles]
    generated_playbooks = (
        synthesize_hierarchical_playbooks(updated, playbook_source)
        if expand_hierarchical_playbooks or playbook_only
        else []
    )
    generated = [
        *generated_static,
        *generated_dynamic,
        *generated_adaptive,
        *generated_bundles,
        *generated_playbooks,
    ]
    if playbook_only:
        shadow_members = [
            member.model_copy(
                deep=True,
                update={
                    "applicability_constraints": {
                        **(member.applicability_constraints or {}),
                        "shadow_reference": True,
                    }
                },
            )
            for member in playbook_source
        ]
        updated.interventions = [*generated_playbooks, *shadow_members]
    elif bundle_only:
        shadow_members = [
            member.model_copy(
                deep=True,
                update={
                    "applicability_constraints": {
                        **(member.applicability_constraints or {}),
                        "shadow_reference": True,
                    }
                },
            )
            for member in bundle_source
        ]
        updated.interventions = [*generated_bundles, *shadow_members]
    elif adaptive_only:
        updated.interventions = generated_adaptive
    elif dynamic_only:
        updated.interventions = generated_dynamic
    elif policy_only:
        updated.interventions = generated
    else:
        updated.interventions.extend(generated)
    return updated, list(updated.interventions)


def intervention_catalog_rows(interventions: list[InterventionSpec]) -> list[dict[str, object]]:
    """Serialize catalog metadata for reporting."""

    rows: list[dict[str, object]] = []
    lookup = {intervention.id: intervention for intervention in interventions}
    for intervention in interventions:
        constraints = intervention.applicability_constraints or {}
        rows.append(
            {
                "intervention_id": intervention.id,
                "label": intervention.label,
                "target": intervention.target,
                "action_type": intervention.action_type,
                "cost": intervention.cost,
                "implementation_difficulty": intervention.implementation_difficulty,
                "fairness_impact": intervention.fairness_impact,
                "generated": bool(constraints.get("generated", False)),
                "dynamic": bool(constraints.get("dynamic", False)),
                "adaptive": bool(constraints.get("adaptive", False)),
                "multistage": bool(constraints.get("multistage", False)),
                "hierarchical_bundle": bool(constraints.get("hierarchical_bundle", False)),
                "shadow_reference": bool(constraints.get("shadow_reference", False)),
                "source": constraints.get("source", "authored"),
                "policy_type": constraints.get("policy_type", ""),
                "policy_mode": intervention.policy_mode,
                "stage_count": len(intervention.stages),
                "bundle_size": len(intervention.bundle_members),
                "bundle_depth": _bundle_depth(intervention, lookup),
                "bundle_members": ";".join(intervention.bundle_members),
                "schedule_start": intervention.start,
                "schedule_duration": intervention.duration,
                "schedule_end": intervention.end_time(),
                "trigger_metric": intervention.trigger_metric,
                "trigger_node": _intervention_trigger_node(intervention, lookup),
                "trigger_threshold": intervention.trigger_threshold,
                "clear_threshold": intervention.clear_threshold,
            }
        )
    return rows


def bundle_hierarchy_rows(interventions: list[InterventionSpec]) -> list[dict[str, object]]:
    """Serialize bundle and playbook membership trees for reporting."""

    lookup = {intervention.id: intervention for intervention in interventions}
    rows: list[dict[str, object]] = []
    for intervention in interventions:
        if intervention.action_type != "bundle":
            continue
        _append_bundle_rows(
            intervention=intervention,
            lookup=lookup,
            rows=rows,
            root_bundle_id=intervention.id,
            parent_bundle_id=None,
            depth=0,
        )
    return rows


def _signature(intervention: InterventionSpec) -> tuple[object, ...]:
    return (
        intervention.target,
        intervention.action_type,
        round(float(intervention.start or 0.0), 8),
        round(float(intervention.duration or 0.0), 8),
        intervention.policy_mode,
        intervention.trigger_metric,
        intervention.trigger_node,
        round(float(intervention.trigger_threshold or 0.0), 8),
        round(float(intervention.clear_threshold or 0.0), 8),
        tuple(_stage_signature(stage) for stage in intervention.stages),
        tuple(intervention.bundle_members),
        intervention.parameter,
        intervention.replacement,
        round(float(intervention.delta or 0.0), 8),
    )


def _stage_signature(stage: PolicyStageSpec) -> tuple[object, ...]:
    return (
        stage.id,
        stage.action_type,
        round(float(stage.trigger_threshold), 8),
        round(float(stage.clear_threshold or 0.0), 8),
        stage.parameter,
        stage.replacement,
        round(float(stage.delta or 0.0), 8),
    )


def _bundle_from_members(
    *,
    trigger_node: str,
    members: list[InterventionSpec],
    discount: float,
) -> InterventionSpec:
    member_ids = [member.id for member in members]
    total_cost = sum(member.cost for member in members)
    total_difficulty = sum(member.implementation_difficulty or 0.0 for member in members)
    fairness_impact = sum(abs(member.fairness_impact or 0.0) for member in members) / max(len(members), 1)
    return InterventionSpec(
        id=f"controller_bundle__{trigger_node}__{'__'.join(_slug_member_id(member_id) for member_id in member_ids)}",
        label=f"Controller bundle for {trigger_node}: " + ", ".join(member.label or member.id for member in members),
        target="__bundle__",
        action_type="bundle",
        bundle_members=member_ids,
        cost=round(total_cost * discount, 3),
        implementation_difficulty=round(total_difficulty * 0.9, 3),
        fairness_impact=round(fairness_impact, 3),
        applicability_constraints={
            "generated": True,
            "dynamic": True,
            "adaptive": True,
            "bundle": True,
            "bundle_depth": 1,
            "source": "generated_bundle",
            "policy_type": "controller_bundle",
        },
    )


def _playbook_from_members(
    *,
    trigger_node: str,
    members: list[InterventionSpec],
    discount: float,
    lookup: dict[str, InterventionSpec],
) -> InterventionSpec:
    member_ids = [member.id for member in members]
    total_cost = sum(member.cost for member in members)
    total_difficulty = sum(member.implementation_difficulty or 0.0 for member in members)
    fairness_impact = sum(abs(member.fairness_impact or 0.0) for member in members) / max(len(members), 1)
    bundle_depth = max(_bundle_depth(member, lookup) for member in members) + 1
    return InterventionSpec(
        id=f"hierarchical_playbook__{trigger_node}__{'__'.join(_slug_member_id(member_id) for member_id in member_ids)}",
        label=f"Hierarchical playbook for {trigger_node}: " + ", ".join(member.label or member.id for member in members),
        target="__bundle__",
        action_type="bundle",
        bundle_members=member_ids,
        cost=round(total_cost * discount, 3),
        implementation_difficulty=round(total_difficulty * 0.88, 3),
        fairness_impact=round(fairness_impact, 3),
        applicability_constraints={
            "generated": True,
            "dynamic": True,
            "adaptive": True,
            "bundle": True,
            "hierarchical_bundle": True,
            "bundle_depth": bundle_depth,
            "source": "generated_playbook",
            "policy_type": "hierarchical_playbook",
        },
    )


def _slug_member_id(member_id: str) -> str:
    return (
        member_id.replace("->", "_to_")
        .replace("__", "_")
        .replace("-", "_")
    )


def _intervention_trigger_node(
    intervention: InterventionSpec,
    lookup: dict[str, InterventionSpec],
    *,
    visited: set[str] | None = None,
) -> str | None:
    if intervention.trigger_node:
        return intervention.trigger_node
    if not intervention.bundle_members:
        return None
    seen = set() if visited is None else set(visited)
    if intervention.id in seen:
        return None
    seen.add(intervention.id)
    trigger_nodes: set[str] = set()
    for member_id in intervention.bundle_members:
        member = lookup.get(member_id)
        if member is None:
            continue
        trigger_node = _intervention_trigger_node(member, lookup, visited=seen)
        if trigger_node:
            trigger_nodes.add(trigger_node)
    if not trigger_nodes:
        return None
    return sorted(trigger_nodes)[0]


def _bundle_depth(
    intervention: InterventionSpec,
    lookup: dict[str, InterventionSpec],
    *,
    visited: set[str] | None = None,
) -> int:
    if not intervention.bundle_members:
        return 0
    seen = set() if visited is None else set(visited)
    if intervention.id in seen:
        return 0
    seen.add(intervention.id)
    child_depths = [
        _bundle_depth(member, lookup, visited=seen)
        for member_id in intervention.bundle_members
        if (member := lookup.get(member_id)) is not None
    ]
    if not child_depths:
        return 1
    return 1 + max(child_depths)


def _append_bundle_rows(
    *,
    intervention: InterventionSpec,
    lookup: dict[str, InterventionSpec],
    rows: list[dict[str, object]],
    root_bundle_id: str,
    parent_bundle_id: str | None,
    depth: int,
    visited: set[str] | None = None,
) -> None:
    seen = set() if visited is None else set(visited)
    if intervention.id in seen:
        return
    seen.add(intervention.id)
    constraints = intervention.applicability_constraints or {}
    rows.append(
        {
            "root_bundle_id": root_bundle_id,
            "parent_bundle_id": parent_bundle_id,
            "intervention_id": intervention.id,
            "label": intervention.label,
            "action_type": intervention.action_type,
            "source": constraints.get("source", "authored"),
            "trigger_node": _intervention_trigger_node(intervention, lookup),
            "bundle_size": len(intervention.bundle_members),
            "bundle_depth": _bundle_depth(intervention, lookup),
            "depth": depth,
            "is_bundle": bool(intervention.bundle_members),
            "hierarchical_bundle": bool(constraints.get("hierarchical_bundle", False)),
            "shadow_reference": bool(constraints.get("shadow_reference", False)),
        }
    )
    for member_id in intervention.bundle_members:
        member = lookup.get(member_id)
        if member is None:
            continue
        _append_bundle_rows(
            intervention=member,
            lookup=lookup,
            rows=rows,
            root_bundle_id=root_bundle_id,
            parent_bundle_id=intervention.id,
            depth=depth + 1,
            visited=seen,
        )


def _policy_windows(spec: SystemSpec, *, max_windows: int) -> list[dict[str, object]]:
    horizon = max(spec.clock.end - spec.clock.start, 1.0)
    windows: list[dict[str, object]] = []
    for shock in flatten_shocks(spec.shocks):
        start = max(spec.clock.start, shock.start)
        duration = shock.duration if shock.duration is not None else min(horizon * 0.25, 120.0)
        duration = min(float(duration), max(spec.clock.end - start, 0.0))
        if duration <= 0:
            continue
        windows.append(
            {
                "window_id": shock.id,
                "window_label": shock.label if hasattr(shock, "label") and shock.label else shock.id,
                "start": float(start),
                "duration": float(duration),
            }
        )
    if not windows:
        duration = min(max(horizon * 0.25, 30.0), horizon)
        start = spec.clock.start + max(0.0, (horizon - duration) / 2.0)
        windows.append(
            {
                "window_id": "mid_horizon",
                "window_label": "mid_horizon",
                "start": float(start),
                "duration": float(duration),
            }
        )
    deduped: list[dict[str, object]] = []
    seen: set[tuple[float, float]] = set()
    for window in windows:
        key = (
            round(float(window["start"]), 6),
            round(float(window["duration"]), 6),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(window)
        if len(deduped) >= max_windows:
            break
    return deduped
