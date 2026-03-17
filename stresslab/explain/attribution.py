"""Failure attribution heuristics."""

from __future__ import annotations

from stresslab.models import AttributionResult


def attribute_failure(result) -> AttributionResult:
    """Attribute failure to the most burdened nodes."""

    node_metrics = result.node_metrics
    edge_metrics = getattr(result, "edge_metrics", {})
    ranked = sorted(
        node_metrics.items(),
        key=lambda item: (
            item[1].get("queue_integral", 0.0),
            item[1].get("mean_wait", 0.0),
            item[1].get("holding_integral", 0.0),
            item[1].get("overflow_count", 0.0),
        ),
        reverse=True,
    )
    ranked_edges = sorted(
        edge_metrics.items(),
        key=lambda item: (
            item[1].get("blocked_count", 0.0),
            item[1].get("mean_delay", 0.0),
            item[1].get("max_delay", 0.0),
        ),
        reverse=True,
    )
    dominant = [node_id for node_id, _ in ranked[:3]]
    first_bottleneck = dominant[0] if dominant else None
    blockers = [
        node_id
        for node_id, metrics in ranked
        if (
            metrics.get("utilization", 0.0) > 0.9
            or metrics.get("overflow_count", 0.0) > 0
            or metrics.get("holding_integral", 0.0) > 0
        )
    ]
    summary = {
        node_id: metrics.get("queue_integral", 0.0)
        for node_id, metrics in ranked[:5]
    }
    critical_edges = [edge_id for edge_id, _ in ranked_edges[:3] if edge_metrics]
    narrative = "No material bottlenecks were detected."
    if first_bottleneck is not None:
        narrative = (
            f"The dominant bottleneck was '{first_bottleneck}', with the largest backlog integral "
            f"and wait burden in the run."
        )
        if critical_edges:
            narrative += (
                f" The most stressed route was '{critical_edges[0]}', which accumulated the most "
                "blocking or transfer delay."
            )
        fairness_degradation = result.metrics.get("fairness_degradation", 0.0)
        if fairness_degradation > 0.0:
            narrative += (
                f" Class equity also deteriorated by {fairness_degradation:.3f}, indicating the burden "
                "was not shared evenly across flow classes."
            )
    return AttributionResult(
        first_bottleneck=first_bottleneck,
        dominant_bottlenecks=dominant,
        critical_edges=critical_edges,
        recovery_blockers=blockers[:3],
        sensitivity_summary=summary,
        narrative_summary=narrative,
    )
