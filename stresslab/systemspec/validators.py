"""Semantic validation for SystemSpec."""

from __future__ import annotations

from math import isclose

from stresslab.systemspec.schema import SystemSpec, ValidationResult


def validate_spec(spec: SystemSpec) -> ValidationResult:
    """Validate cross-reference and semantic rules."""

    errors: list[str] = []
    warnings: list[str] = []

    node_ids = [node.id for node in spec.nodes]
    node_set = set(node_ids)
    if len(node_ids) != len(node_set):
        errors.append("Node IDs must be unique.")

    class_ids = [flow_class.id for flow_class in spec.classes]
    if len(class_ids) != len(set(class_ids)):
        errors.append("Class IDs must be unique.")

    intervention_ids = [intervention.id for intervention in spec.interventions]
    if len(intervention_ids) != len(set(intervention_ids)):
        errors.append("Intervention IDs must be unique.")

    for node in spec.nodes:
        if node.queue_policy == "priority" and not node.priority_classes and not spec.classes:
            warnings.append(
                f"Node '{node.id}' uses priority policy without explicit class ordering; FIFO tie-breaking will be used."
            )

    outgoing_probability: dict[str, float] = {}
    edge_targets = {f"{edge.from_node}->{edge.to_node}" for edge in spec.edges}
    for edge in spec.edges:
        if edge.from_node not in node_set:
            errors.append(f"Edge from '{edge.from_node}' references an unknown source node.")
        if edge.to_node not in node_set:
            errors.append(f"Edge to '{edge.to_node}' references an unknown destination node.")
        outgoing_probability[edge.from_node] = outgoing_probability.get(edge.from_node, 0.0) + edge.routing.probability

    for node_id, total_probability in outgoing_probability.items():
        if total_probability > 1.0 + 1e-9:
            errors.append(
                f"Outgoing routing probabilities from node '{node_id}' sum to {total_probability:.3f}; they must be <= 1.0."
            )
        elif not isclose(total_probability, 1.0, abs_tol=1e-6):
            warnings.append(
                f"Outgoing routing probabilities from node '{node_id}' sum to {total_probability:.3f}; residual flow exits the system."
            )

    for arrival in spec.arrivals:
        if arrival.node not in node_set:
            errors.append(f"Arrival target '{arrival.node}' references an unknown node.")
        if arrival.class_mix:
            class_total = sum(arrival.class_mix.values())
            if not isclose(class_total, 1.0, abs_tol=1e-6):
                errors.append(
                    f"Arrival class_mix for node '{arrival.node}' sums to {class_total:.3f}; it must sum to 1.0."
                )
            unknown_classes = set(arrival.class_mix).difference(class_ids)
            if unknown_classes:
                errors.append(
                    f"Arrival class_mix for node '{arrival.node}' references unknown classes: {sorted(unknown_classes)}."
                )

    for shock in spec.shocks:
        if shock.target and shock.target not in node_set and shock.target not in edge_targets:
            errors.append(
                f"Shock '{shock.id}' targets '{shock.target}', which is neither a node ID nor an edge reference."
            )
        if shock.duration is not None and shock.duration < 0:
            errors.append(f"Shock '{shock.id}' has a negative duration.")

    for policy in spec.policies:
        if policy.target not in node_set and policy.target not in edge_targets:
            errors.append(
                f"Policy '{policy.id}' targets '{policy.target}', which is not a known node or edge."
            )
            continue
        if policy.trigger_node and policy.trigger_node not in node_set:
            errors.append(
                f"Policy '{policy.id}' references unknown trigger_node '{policy.trigger_node}'."
            )
        if policy.target in node_set and policy.action_type not in {"priority_policy_change"}:
            errors.append(
                f"Policy '{policy.id}' uses unsupported node action '{policy.action_type}'."
            )
        if policy.target in edge_targets and policy.action_type not in {"reroute_fraction", "enable_backup_edge"}:
            errors.append(
                f"Policy '{policy.id}' uses unsupported edge action '{policy.action_type}'."
            )
        if policy.mode == "scheduled" and policy.start > spec.clock.end:
            warnings.append(
                f"Policy '{policy.id}' starts after the simulation horizon and will never activate."
            )
        if policy.mode == "threshold" and policy.trigger_threshold is not None and policy.clear_threshold is None:
            warnings.append(
                f"Policy '{policy.id}' omits clear_threshold; a default hysteresis threshold will be used."
            )
        if policy.stages:
            for stage in policy.stages:
                action_type = stage.action_type or policy.action_type
                if policy.target in node_set and action_type not in {"priority_policy_change"}:
                    errors.append(
                        f"Policy '{policy.id}' stage '{stage.id}' uses unsupported node action '{action_type}'."
                    )
                if policy.target in edge_targets and action_type not in {"reroute_fraction", "enable_backup_edge"}:
                    errors.append(
                        f"Policy '{policy.id}' stage '{stage.id}' uses unsupported edge action '{action_type}'."
                    )

    for condition in spec.failure_conditions:
        _validate_failure_condition(condition, node_set, errors)

    intervention_id_set = set(intervention_ids)
    for intervention in spec.interventions:
        if intervention.action_type != "bundle" and intervention.target not in node_set and intervention.target not in edge_targets:
            errors.append(
                f"Intervention '{intervention.id}' targets '{intervention.target}', which is not a known node or edge."
            )
        if intervention.trigger_node and intervention.trigger_node not in node_set:
            errors.append(
                f"Intervention '{intervention.id}' references unknown trigger_node '{intervention.trigger_node}'."
            )
        if intervention.cost < 0:
            errors.append(f"Intervention '{intervention.id}' has a negative cost.")
        if intervention.stages:
            thresholds = [stage.trigger_threshold for stage in intervention.stages]
            if thresholds != sorted(thresholds):
                errors.append(f"Intervention '{intervention.id}' stages must be ordered by trigger_threshold.")
        if intervention.action_type == "bundle":
            if not intervention.bundle_members:
                errors.append(f"Intervention '{intervention.id}' is a bundle but has no bundle_members.")
            for member_id in intervention.bundle_members:
                if member_id == intervention.id:
                    errors.append(f"Intervention '{intervention.id}' cannot reference itself in bundle_members.")
                elif member_id not in intervention_id_set:
                    errors.append(
                        f"Intervention '{intervention.id}' references unknown bundle member '{member_id}'."
                    )

    for dimension in spec.search.search_space:
        if dimension.target not in node_set and dimension.target not in edge_targets:
            errors.append(
                f"Search dimension '{dimension.id}' targets '{dimension.target}', which is not a known node or edge."
            )

    if not spec.nodes:
        errors.append("At least one node is required.")
    if not spec.arrivals:
        warnings.append("No arrivals defined; the simulation will be trivially empty.")
    if not spec.failure_conditions:
        warnings.append("No failure conditions defined; searches will optimize damage without explicit failure thresholds.")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def _validate_failure_condition(condition, node_set: set[str], errors: list[str]) -> None:
    if condition.type in {"any", "all"}:
        if not condition.conditions:
            errors.append(f"Failure condition '{condition.type}' requires nested conditions.")
        for nested in condition.conditions:
            _validate_failure_condition(nested, node_set, errors)
        return
    if condition.node and condition.node not in node_set:
        errors.append(f"Failure condition '{condition.type}' references unknown node '{condition.node}'.")
    if condition.threshold is None and condition.type not in {"buffer_overflow"}:
        errors.append(f"Failure condition '{condition.type}' requires a threshold.")
