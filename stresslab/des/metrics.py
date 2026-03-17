"""Metric summarization and failure evaluation."""

from __future__ import annotations

from math import isfinite

import numpy as np

from stresslab.des.node import EdgeState, NodeState
from stresslab.systemspec.schema import FailureConditionSpec, ResolvedSystemSpec


def summarize_metrics(
    spec: ResolvedSystemSpec,
    node_states: dict[str, NodeState],
    edge_states: dict[str, EdgeState],
    *,
    event_count: int,
    horizon: float,
    departed_jobs: int,
    external_arrivals: int,
    external_arrival_class_counts: dict[str, int],
    departed_class_counts: dict[str, int],
    baseline_metrics: dict[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """Build per-node and system metrics."""

    baseline = baseline_metrics or {}
    node_metrics: dict[str, dict[str, float]] = {}
    degraded_nodes = 0
    first_degraded: float | None = None
    last_degraded: float | None = None
    total_dropped = 0
    total_waits: list[float] = []
    total_queue_integral = 0.0
    total_holding_integral = 0.0
    class_wait_times: dict[str, list[float]] = {}
    class_drop_counts: dict[str, int] = {}
    observed_classes = set(spec.class_priorities)
    observed_classes.update(external_arrival_class_counts)
    observed_classes.update(departed_class_counts)

    for node_id, state in node_states.items():
        waits = np.array(state.wait_times, dtype=float) if state.wait_times else np.array([], dtype=float)
        mean_wait = float(waits.mean()) if waits.size else 0.0
        p95_wait = float(np.percentile(waits, 95)) if waits.size else 0.0
        effective_capacity = max(state.effective_servers, 1)
        utilization = state.utilization_integral / max(horizon, 1e-9)
        throughput = state.completion_count / max(horizon, 1e-9)
        degraded = bool(
            state.overflow_count
            or state.max_queue_length > 0
            or state.routed_hold_count > 0
            or utilization > 0.95
        )
        if degraded:
            degraded_nodes += 1
            if state.first_degraded_time is not None:
                first_degraded = (
                    state.first_degraded_time
                    if first_degraded is None
                    else min(first_degraded, state.first_degraded_time)
                )
            if state.last_degraded_time is not None:
                last_degraded = (
                    state.last_degraded_time
                    if last_degraded is None
                    else max(last_degraded, state.last_degraded_time)
                )
        node_metrics[node_id] = {
            "mean_wait": mean_wait,
            "p95_wait": p95_wait,
            "queue_integral": state.queue_integral,
            "holding_integral": state.holding_integral,
            "utilization": utilization,
            "throughput": throughput,
            "completed": float(state.completion_count),
            "arrivals": float(state.arrival_count),
            "dropped": float(state.dropped_count),
            "overflow_count": float(state.overflow_count),
            "max_queue_length": float(state.max_queue_length),
            "blocked_routing_count": float(state.blocked_routing_count),
            "servers_total": float(max(effective_capacity, 0)),
        }
        total_dropped += state.dropped_count
        total_waits.extend(state.wait_times)
        total_queue_integral += state.queue_integral
        total_holding_integral += state.holding_integral
        observed_classes.update(state.class_arrival_counts)
        observed_classes.update(state.class_completion_counts)
        observed_classes.update(state.class_dropped_counts)
        observed_classes.update(state.class_wait_times)
        for class_id, waits_for_class in state.class_wait_times.items():
            class_wait_times.setdefault(class_id, []).extend(waits_for_class)
        for class_id, drop_count in state.class_dropped_counts.items():
            class_drop_counts[class_id] = class_drop_counts.get(class_id, 0) + drop_count

    edge_metrics: dict[str, dict[str, float]] = {}
    edge_degraded_count = 0
    total_edge_delay = 0.0
    total_transfers = 0
    total_blocked = 0.0
    for edge_id, edge_state in edge_states.items():
        mean_delay = edge_state.total_delay / max(edge_state.transferred_count, 1)
        degraded = bool(edge_state.blocked_count or not edge_state.enabled)
        edge_metrics[edge_id] = {
            "enabled": float(1.0 if edge_state.enabled else 0.0),
            "travel_time": edge_state.travel_time,
            "transfer_capacity": float(edge_state.transfer_capacity or 0.0),
            "transferred_count": float(edge_state.transferred_count),
            "blocked_count": float(edge_state.blocked_count),
            "mean_delay": mean_delay,
            "max_delay": edge_state.max_delay,
            "degraded": float(1.0 if degraded else 0.0),
        }
        total_edge_delay += edge_state.total_delay
        total_transfers += edge_state.transferred_count
        total_blocked += edge_state.blocked_count
        if degraded:
            edge_degraded_count += 1

    total_waits_array = np.array(total_waits, dtype=float) if total_waits else np.array([], dtype=float)
    throughput = departed_jobs / max(horizon, 1e-9)
    throughput_efficiency = departed_jobs / max(external_arrivals, 1)
    mean_wait = float(total_waits_array.mean()) if total_waits_array.size else 0.0
    p95_wait = float(np.percentile(total_waits_array, 95)) if total_waits_array.size else 0.0
    baseline_throughput = baseline.get("throughput", throughput)
    throughput_loss = 0.0
    if baseline_throughput > 0:
        throughput_loss = max(0.0, (baseline_throughput - throughput) / baseline_throughput)
    recovery_time = 0.0
    if first_degraded is not None and last_degraded is not None:
        recovery_time = max(0.0, last_degraded - first_degraded)
    cascade_norm = degraded_nodes / max(len(node_states), 1)
    backlog_norm = total_queue_integral / max(horizon, 1.0)
    class_metrics = _summarize_class_metrics(
        observed_classes=observed_classes,
        class_wait_times=class_wait_times,
        external_arrival_class_counts=external_arrival_class_counts,
        departed_class_counts=departed_class_counts,
        class_drop_counts=class_drop_counts,
        horizon=horizon,
    )
    fairness_metrics = _fairness_metrics(
        class_metrics,
        class_priorities=spec.class_priorities,
        baseline_metrics=baseline,
    )
    metrics = {
        "throughput": throughput,
        "throughput_efficiency": throughput_efficiency,
        "throughput_loss": throughput_loss,
        "mean_wait": mean_wait,
        "p95_wait": p95_wait,
        "backlog_integral": total_queue_integral,
        "queue_integral": total_queue_integral,
        "holding_integral": total_holding_integral,
        "utilization": float(
            np.mean([node_metric["utilization"] for node_metric in node_metrics.values()])
        ) if node_metrics else 0.0,
        "recovery_time": recovery_time,
        "cascade_size": float(degraded_nodes),
        "cascade_norm": cascade_norm,
        "degraded_nodes": float(degraded_nodes),
        "degraded_edges": float(edge_degraded_count),
        "edge_cascade_norm": edge_degraded_count / max(len(edge_states), 1),
        "event_count": float(event_count),
        "dropped_jobs": float(total_dropped),
        "blocked_transfers": total_blocked,
        "mean_edge_delay": total_edge_delay / max(total_transfers, 1),
        "arrival_count": float(external_arrivals),
        "completed_jobs": float(departed_jobs),
        "fragility_score": 0.0,
        "recovery_score": 1.0 / (1.0 + recovery_time),
        **fairness_metrics,
    }
    metrics["resilience_score"] = _resilience_score(metrics)
    metrics["backlog_norm"] = backlog_norm
    metrics["holding_norm"] = _normalize(
        total_holding_integral,
        baseline.get("holding_integral", max(total_holding_integral, 1.0)),
    )
    metrics["mean_wait_norm"] = _normalize(mean_wait, baseline.get("mean_wait", max(mean_wait, 1.0)))
    metrics["p95_wait_norm"] = _normalize(p95_wait, baseline.get("p95_wait", max(p95_wait, 1.0)))
    metrics["recovery_norm"] = _normalize(
        recovery_time,
        baseline.get("recovery_time", max(recovery_time, 1.0)),
    )
    metrics["__edge_metrics__"] = edge_metrics
    return metrics, node_metrics, class_metrics


def evaluate_failure_conditions(
    conditions: list[FailureConditionSpec],
    metrics: dict[str, float],
    node_metrics: dict[str, dict[str, float]],
) -> list[str]:
    """Return textual failure reasons for all triggered conditions."""

    reasons: list[str] = []
    for condition in conditions:
        triggered, reason = _evaluate_condition(condition, metrics, node_metrics)
        if triggered:
            reasons.append(reason)
    return reasons


def _evaluate_condition(
    condition: FailureConditionSpec,
    metrics: dict[str, float],
    node_metrics: dict[str, dict[str, float]],
) -> tuple[bool, str]:
    condition_type = condition.type
    if condition_type == "any":
        nested_reasons = []
        for nested in condition.conditions:
            triggered, reason = _evaluate_condition(nested, metrics, node_metrics)
            if triggered:
                nested_reasons.append(reason)
        return (bool(nested_reasons), " OR ".join(nested_reasons) if nested_reasons else "any")
    if condition_type == "all":
        nested_reasons = []
        for nested in condition.conditions:
            triggered, reason = _evaluate_condition(nested, metrics, node_metrics)
            if not triggered:
                return False, "all"
            nested_reasons.append(reason)
        return True, " AND ".join(nested_reasons)

    actual = _metric_value(condition, metrics, node_metrics)
    threshold = condition.threshold if condition.threshold is not None else float("inf")
    triggered = actual > threshold
    reason = f"{condition_type}={actual:.3f} > {threshold:.3f}"
    if condition.node:
        reason = f"{condition.node}:{reason}"
    return triggered, reason


def _metric_value(
    condition: FailureConditionSpec,
    metrics: dict[str, float],
    node_metrics: dict[str, dict[str, float]],
) -> float:
    if condition.type == "throughput_loss":
        return metrics.get("throughput_loss", 0.0)
    if condition.type == "recovery_time":
        return metrics.get("recovery_time", 0.0)
    if condition.type == "cascade_norm":
        return metrics.get("cascade_norm", 0.0)
    if condition.type == "edge_cascade_norm":
        return metrics.get("edge_cascade_norm", 0.0)
    if condition.type == "blocked_transfers":
        return metrics.get("blocked_transfers", 0.0)
    if condition.type == "fairness_degradation":
        return metrics.get("fairness_degradation", 0.0)
    if condition.type == "fairness_score":
        return metrics.get("fairness_score", 0.0)
    if condition.type == "buffer_overflow":
        return node_metrics.get(condition.node or "", {}).get("overflow_count", 0.0)
    metric_name = {
        "mean_wait": "mean_wait",
        "mean_wait_time": "mean_wait",
        "p95_wait": "p95_wait",
        "queue_integral": "queue_integral",
        "backlog_integral": "queue_integral",
        "utilization": "utilization",
    }.get(condition.type, condition.type)
    if condition.node:
        return node_metrics.get(condition.node, {}).get(metric_name, 0.0)
    return metrics.get(metric_name, 0.0)


def _normalize(value: float, baseline: float) -> float:
    denominator = baseline if isfinite(baseline) and abs(baseline) > 1e-9 else 1.0
    return value / denominator


def _resilience_score(metrics: dict[str, float]) -> float:
    throughput_term = metrics.get("throughput_efficiency", 1.0 - metrics.get("throughput_loss", 0.0))
    return (
        0.35 * (1.0 / (1.0 + metrics.get("recovery_time", 0.0)))
        + 0.4 * throughput_term
        + 0.25 * (1.0 - metrics.get("cascade_norm", 0.0))
    )


def _summarize_class_metrics(
    *,
    observed_classes: set[str],
    class_wait_times: dict[str, list[float]],
    external_arrival_class_counts: dict[str, int],
    departed_class_counts: dict[str, int],
    class_drop_counts: dict[str, int],
    horizon: float,
) -> dict[str, dict[str, float]]:
    class_metrics: dict[str, dict[str, float]] = {}
    for class_id in sorted(observed_classes):
        waits = np.array(class_wait_times.get(class_id, []), dtype=float)
        arrivals = float(external_arrival_class_counts.get(class_id, 0))
        completed = float(departed_class_counts.get(class_id, 0))
        dropped = float(class_drop_counts.get(class_id, 0))
        if arrivals <= 0 and completed <= 0 and dropped <= 0 and not waits.size:
            continue
        throughput_efficiency = completed / max(arrivals, 1.0)
        drop_rate = dropped / max(arrivals, 1.0)
        class_metrics[class_id] = {
            "arrivals": arrivals,
            "completed_jobs": completed,
            "dropped_jobs": dropped,
            "mean_wait": float(waits.mean()) if waits.size else 0.0,
            "p95_wait": float(np.percentile(waits, 95)) if waits.size else 0.0,
            "throughput": completed / max(horizon, 1e-9),
            "throughput_efficiency": throughput_efficiency,
            "drop_rate": drop_rate,
        }
    return class_metrics


def _fairness_metrics(
    class_metrics: dict[str, dict[str, float]],
    *,
    class_priorities: dict[str, int],
    baseline_metrics: dict[str, float],
) -> dict[str, float]:
    if len(class_metrics) <= 1:
        fairness_score = 1.0 if class_metrics else 0.0
        baseline_score = baseline_metrics.get("fairness_score")
        degradation = (
            max(0.0, baseline_score - fairness_score)
            if baseline_score is not None
            else 0.0
        )
        return {
            "fairness_score": fairness_score,
            "fairness_degradation": degradation,
            "wait_inequity": 0.0,
            "throughput_inequity": 0.0,
            "drop_inequity": 0.0,
            "priority_wait_gradient": 0.0,
        }

    wait_values = np.array([metrics["mean_wait"] for metrics in class_metrics.values()], dtype=float)
    throughput_values = np.array(
        [metrics["throughput_efficiency"] for metrics in class_metrics.values()],
        dtype=float,
    )
    drop_values = np.array([metrics["drop_rate"] for metrics in class_metrics.values()], dtype=float)
    wait_inequity = _normalized_gap(wait_values)
    throughput_inequity = _normalized_gap(throughput_values)
    drop_inequity = float(drop_values.max() - drop_values.min()) if drop_values.size else 0.0
    priority_wait_gradient = _priority_wait_gradient(class_metrics, class_priorities)
    fairness_score = max(
        0.0,
        1.0
        - (
            0.45 * wait_inequity
            + 0.35 * throughput_inequity
            + 0.20 * min(drop_inequity, 1.0)
        ),
    )
    baseline_score = baseline_metrics.get("fairness_score")
    degradation = max(0.0, baseline_score - fairness_score) if baseline_score is not None else 0.0
    return {
        "fairness_score": fairness_score,
        "fairness_degradation": degradation,
        "wait_inequity": wait_inequity,
        "throughput_inequity": throughput_inequity,
        "drop_inequity": float(min(drop_inequity, 1.0)),
        "priority_wait_gradient": priority_wait_gradient,
    }


def _normalized_gap(values: np.ndarray) -> float:
    if values.size <= 1:
        return 0.0
    maximum = float(values.max())
    minimum = float(values.min())
    return max(0.0, (maximum - minimum) / max(maximum, 1.0))


def _priority_wait_gradient(
    class_metrics: dict[str, dict[str, float]],
    class_priorities: dict[str, int],
) -> float:
    ranked = [
        (class_priorities.get(class_id, 999), metrics["mean_wait"])
        for class_id, metrics in class_metrics.items()
        if class_id in class_priorities
    ]
    if len(ranked) <= 1:
        return 0.0
    ranked.sort(key=lambda item: item[0])
    first_wait = float(ranked[0][1])
    last_wait = float(ranked[-1][1])
    max_wait = max(wait for _, wait in ranked)
    return max(0.0, (last_wait - first_wait) / max(max_wait, 1.0))
