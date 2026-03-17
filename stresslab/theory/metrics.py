"""Collapse-oriented metric extraction for discovery campaigns."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from stresslab.models import SearchResult, SimulationResult
from stresslab.systemspec.schema import SystemSpec


def collapse_metrics_from_results(
    *,
    spec: SystemSpec,
    baseline_result: SimulationResult,
    min_search: SearchResult,
    min_result: SimulationResult,
    worst_search: SearchResult,
    worst_result: SimulationResult,
) -> dict[str, float]:
    """Convert baseline and stress-search outputs into collapse metrics."""

    failure_flags = np.asarray(
        [
            float(baseline_result.failure_triggered),
            float(min_result.failure_triggered),
            float(worst_result.failure_triggered),
        ],
        dtype=float,
    )
    cascade_sizes = np.asarray(
        [
            float(baseline_result.metrics.get("cascade_size", 0.0)),
            float(min_result.metrics.get("cascade_size", 0.0)),
            float(worst_result.metrics.get("cascade_size", 0.0)),
        ],
        dtype=float,
    )
    recovery_times = np.asarray(
        [
            float(baseline_result.metrics.get("recovery_time", 0.0)),
            float(min_result.metrics.get("recovery_time", 0.0)),
            float(worst_result.metrics.get("recovery_time", 0.0)),
        ],
        dtype=float,
    )
    throughput_losses = np.asarray(
        [
            float(min_result.metrics.get("throughput_loss", 0.0)),
            float(worst_result.metrics.get("throughput_loss", 0.0)),
        ],
        dtype=float,
    )
    fragility_index = float(
        np.mean(
            [
                float(min_search.damage_score),
                float(worst_search.damage_score),
                float(np.max(throughput_losses)),
                float(np.max(cascade_sizes) / max(len(spec.nodes), 1)),
            ]
        )
    )
    bottleneck_count = float(_bottleneck_count(worst_result.node_metrics))
    cascade_depth = float(_cascade_depth(spec=spec, node_metrics=worst_result.node_metrics))
    cascade_speed = float(np.max(cascade_sizes) / max(np.max(recovery_times), float(worst_result.horizon), 1.0))
    collapse_probability = float(failure_flags.mean())
    resilience_score = float(
        np.mean(
            [
                baseline_result.metrics.get("resilience_score", 0.0),
                min_result.metrics.get("resilience_score", 0.0),
                worst_result.metrics.get("resilience_score", 0.0),
            ]
        )
    )
    return {
        "collapse_probability": collapse_probability,
        "cascade_size": float(np.mean(cascade_sizes)),
        "max_cascade_size": float(np.max(cascade_sizes)),
        "cascade_depth": cascade_depth,
        "recovery_time": float(np.max(recovery_times)),
        "failure_shock_budget": float(min_search.best_shock_budget if min_search.success else worst_search.best_shock_budget),
        "worst_case_budget": float(worst_search.best_shock_budget),
        "resilience_score": resilience_score,
        "fragility_index": fragility_index,
        "bottleneck_count": bottleneck_count,
        "cascade_speed": cascade_speed,
        "throughput_loss": float(np.max(throughput_losses)),
        "min_failure_damage": float(min_search.damage_score),
        "worst_case_damage": float(worst_search.damage_score),
        "baseline_failure": float(baseline_result.failure_triggered),
        "min_failure_triggered": float(min_result.failure_triggered),
        "worst_case_triggered": float(worst_result.failure_triggered),
        "min_failure_cascade_size": float(min_result.metrics.get("cascade_size", 0.0)),
        "worst_case_cascade_size": float(worst_result.metrics.get("cascade_size", 0.0)),
        "baseline_utilization": float(baseline_result.metrics.get("utilization", 0.0)),
        "baseline_mean_wait": float(baseline_result.metrics.get("mean_wait", 0.0)),
        "baseline_throughput": float(baseline_result.metrics.get("throughput", 0.0)),
        "worst_case_mean_wait": float(worst_result.metrics.get("mean_wait", 0.0)),
        "worst_case_throughput": float(worst_result.metrics.get("throughput", 0.0)),
    }


def build_collapse_distribution(
    frame: pd.DataFrame,
    *,
    metric: str = "worst_case_cascade_size",
) -> pd.DataFrame:
    """Build an empirical survival function for cascade sizes."""

    if frame.empty or metric not in frame.columns:
        return pd.DataFrame(columns=["metric", "threshold", "survival_probability"])
    values = frame[metric].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return pd.DataFrame(columns=["metric", "threshold", "survival_probability"])
    thresholds = sorted(set(float(value) for value in values if value > 0))
    rows = [
        {
            "metric": metric,
            "threshold": threshold,
            "survival_probability": float((values >= threshold).mean()),
        }
        for threshold in thresholds
    ]
    return pd.DataFrame(rows)


def load_queue_timeseries(path: Path) -> pd.DataFrame:
    """Load a queue timeseries artifact if present."""

    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame(columns=["node", "time", "queue_length"])
    return pd.read_csv(csv_path)


def _bottleneck_count(node_metrics: dict[str, dict[str, float]]) -> int:
    count = 0
    for metrics in node_metrics.values():
        if (
            metrics.get("max_queue_length", 0.0) > 0
            or metrics.get("overflow_count", 0.0) > 0
            or metrics.get("blocked_routing_count", 0.0) > 0
            or metrics.get("utilization", 0.0) >= 0.9
        ):
            count += 1
    return count


def _cascade_depth(*, spec: SystemSpec, node_metrics: dict[str, dict[str, float]]) -> int:
    degraded_nodes = {
        node_id
        for node_id, metrics in node_metrics.items()
        if (
            metrics.get("max_queue_length", 0.0) > 0
            or metrics.get("overflow_count", 0.0) > 0
            or metrics.get("blocked_routing_count", 0.0) > 0
            or metrics.get("utilization", 0.0) >= 0.9
        )
    }
    if not degraded_nodes:
        return 0
    graph = nx.Graph()
    graph.add_nodes_from(node.id for node in spec.nodes)
    graph.add_edges_from((edge.from_node, edge.to_node) for edge in spec.edges)
    subgraph = graph.subgraph(degraded_nodes).copy()
    if subgraph.number_of_nodes() <= 1:
        return int(subgraph.number_of_nodes())
    depth = 1
    for component in nx.connected_components(subgraph):
        component_graph = subgraph.subgraph(component)
        for source in component_graph.nodes():
            lengths = nx.single_source_shortest_path_length(component_graph, source)
            if lengths:
                depth = max(depth, max(lengths.values()) + 1)
    return depth
