"""Structural feature extraction for synthetic and authored systems."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

from stresslab.systemspec import load_spec
from stresslab.systemspec.schema import SystemSpec


def extract_system_features(spec_or_path: SystemSpec | str | Path, baseline_result: object | None = None) -> dict[str, Any]:
    """Extract graph and capacity features for fragility analysis."""

    spec = _coerce_spec(spec_or_path)
    graph = nx.DiGraph()
    graph.add_nodes_from(node.id for node in spec.nodes)
    graph.add_edges_from((edge.from_node, edge.to_node) for edge in spec.edges)
    undirected = graph.to_undirected()
    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()
    average_degree = (2.0 * edge_count / max(node_count, 1)) if node_count else 0.0
    clustering = float(nx.average_clustering(undirected)) if node_count > 1 else 0.0
    largest_component = _largest_component_graph(undirected)
    average_path_length = _average_path_length(largest_component)
    graph_diameter = _graph_diameter(largest_component)
    redundancy_index = _redundancy_index(node_count=node_count, edge_count=edge_count)
    coupling_strength = _coupling_strength(spec)
    utilization = _estimated_utilization(spec, baseline_result=baseline_result)
    capacity_slack = max(0.0, 1.0 - utilization)
    routing_entropy = _routing_entropy(spec)
    centralization_index = _centralization_index(graph)
    buffer_ratio = _buffer_ratio(spec)
    betweenness = nx.betweenness_centrality(undirected) if node_count > 1 else {}
    eigenvector = _eigenvector_centrality(undirected)
    k_core = nx.core_number(undirected) if undirected.number_of_edges() else {node: 0 for node in undirected.nodes()}
    component_sizes = sorted((len(component) for component in nx.connected_components(undirected)), reverse=True) if node_count else []
    feature_row: dict[str, Any] = {
        "system_name": spec.system.name,
        "domain": spec.system.domain or "unknown",
        "topology_type": getattr(spec.system, "topology_type", _infer_topology_type(spec)),
        "node_count": float(node_count),
        "edge_count": float(edge_count),
        "average_degree": float(average_degree),
        "clustering_coefficient": float(clustering),
        "average_path_length": float(average_path_length),
        "graph_diameter": float(graph_diameter),
        "redundancy_index": float(redundancy_index),
        "coupling_strength": float(coupling_strength),
        "utilization": float(utilization),
        "capacity_slack": float(capacity_slack),
        "routing_entropy": float(routing_entropy),
        "centralization_index": float(centralization_index),
        "buffer_ratio": float(buffer_ratio),
        "mean_betweenness": float(np.mean(list(betweenness.values()))) if betweenness else 0.0,
        "max_betweenness": float(max(betweenness.values())) if betweenness else 0.0,
        "mean_eigenvector": float(np.mean(list(eigenvector.values()))) if eigenvector else 0.0,
        "max_eigenvector": float(max(eigenvector.values())) if eigenvector else 0.0,
        "max_k_core": float(max(k_core.values())) if k_core else 0.0,
        "largest_component_size": float(component_sizes[0]) if component_sizes else float(node_count),
        "largest_component_fraction": float(component_sizes[0] / max(node_count, 1)) if component_sizes else 1.0,
        "component_count": float(len(component_sizes) if component_sizes else (1 if node_count else 0)),
        "source_count": float(sum(1 for node in graph.nodes() if graph.in_degree(node) == 0)),
        "sink_count": float(sum(1 for node in graph.nodes() if graph.out_degree(node) == 0)),
    }
    if baseline_result is not None and hasattr(baseline_result, "metrics"):
        metrics = baseline_result.metrics
        feature_row["baseline_resilience_score"] = float(metrics.get("resilience_score", 0.0))
        feature_row["baseline_throughput"] = float(metrics.get("throughput", 0.0))
        feature_row["baseline_mean_wait"] = float(metrics.get("mean_wait", 0.0))
    return feature_row


def _coerce_spec(spec_or_path: SystemSpec | str | Path) -> SystemSpec:
    if isinstance(spec_or_path, SystemSpec):
        return spec_or_path
    return load_spec(Path(spec_or_path))


def _largest_component_graph(graph: nx.Graph) -> nx.Graph:
    if graph.number_of_nodes() <= 1:
        return graph
    components = list(nx.connected_components(graph))
    if not components:
        return graph
    largest = max(components, key=len)
    return graph.subgraph(largest).copy()


def _average_path_length(graph: nx.Graph) -> float:
    if graph.number_of_nodes() <= 1:
        return 0.0
    try:
        return float(nx.average_shortest_path_length(graph))
    except (nx.NetworkXError, ZeroDivisionError):
        return 0.0


def _graph_diameter(graph: nx.Graph) -> float:
    if graph.number_of_nodes() <= 1:
        return 0.0
    try:
        return float(nx.diameter(graph))
    except nx.NetworkXError:
        return 0.0


def _redundancy_index(*, node_count: int, edge_count: int) -> float:
    if node_count <= 1:
        return 0.0
    spanning_edges = node_count - 1
    max_edges = node_count * (node_count - 1)
    numerator = max(0, edge_count - spanning_edges)
    denominator = max(1, max_edges - spanning_edges)
    return numerator / denominator


def _coupling_strength(spec: SystemSpec) -> float:
    probabilities = [edge.routing.probability for edge in spec.edges]
    transfer_capacities = [edge.transfer_capacity or 0.0 for edge in spec.edges]
    if not probabilities:
        return 0.0
    base = float(np.mean(probabilities))
    cap_term = float(np.mean(transfer_capacities)) if transfer_capacities else 0.0
    return min(1.0, base * 0.7 + cap_term * 0.3)


def _estimated_utilization(spec: SystemSpec, baseline_result: object | None) -> float:
    if baseline_result is not None and hasattr(baseline_result, "metrics"):
        metrics = baseline_result.metrics
        if "utilization" in metrics:
            return float(metrics.get("utilization", 0.0))
    arrival_rate = 0.0
    for arrival in spec.arrivals:
        process = arrival.process
        arrival_rate += float(process.base_rate if process.base_rate is not None else process.rate or 0.0)
    service_capacity = 0.0
    for node in spec.nodes:
        service = node.service_time
        if service.distribution == "deterministic":
            mean = float(service.value or 1.0)
        elif service.mean is not None:
            mean = float(service.mean)
        elif service.rate is not None and service.rate > 0:
            mean = 1.0 / float(service.rate)
        elif service.scale is not None and service.shape is not None:
            mean = float(service.shape * service.scale)
        else:
            mean = math.exp(float(service.mu or 0.0) + 0.5 * float(service.sigma or 0.0) ** 2)
        service_capacity += node.servers / max(mean, 1e-9)
    if service_capacity <= 0:
        return 0.0
    return min(1.5, arrival_rate / service_capacity)


def _routing_entropy(spec: SystemSpec) -> float:
    probabilities_by_node: dict[str, list[float]] = {}
    for edge in spec.edges:
        probabilities_by_node.setdefault(edge.from_node, []).append(float(edge.routing.probability))
    entropies = []
    for probabilities in probabilities_by_node.values():
        values = np.asarray(probabilities, dtype=float)
        total = values.sum()
        if total <= 0:
            continue
        normalized = values / total
        entropy = -np.sum(normalized * np.log2(np.clip(normalized, 1e-12, None)))
        if len(normalized) > 1:
            entropy = entropy / np.log2(len(normalized))
        entropies.append(float(entropy))
    return float(np.mean(entropies)) if entropies else 0.0


def _centralization_index(graph: nx.DiGraph) -> float:
    node_count = graph.number_of_nodes()
    if node_count <= 2:
        return 0.0
    degrees = np.asarray([graph.degree(node) for node in graph.nodes()], dtype=float)
    max_degree = float(degrees.max()) if degrees.size else 0.0
    numerator = float(np.sum(max_degree - degrees))
    denominator = float((node_count - 1) * (node_count - 2))
    return numerator / max(denominator, 1.0)


def _buffer_ratio(spec: SystemSpec) -> float:
    total_buffer = float(sum(node.buffer_capacity or 0 for node in spec.nodes))
    total_servers = float(sum(node.servers for node in spec.nodes))
    return total_buffer / max(total_servers, 1.0)


def _eigenvector_centrality(graph: nx.Graph) -> dict[str, float]:
    if graph.number_of_nodes() <= 1:
        return {node: 0.0 for node in graph.nodes()}
    try:
        values = nx.eigenvector_centrality_numpy(graph)
        return {str(key): float(value) for key, value in values.items()}
    except (nx.NetworkXException, ValueError):
        return {str(node): 0.0 for node in graph.nodes()}


def _infer_topology_type(spec: SystemSpec) -> str:
    domain = (spec.system.domain or "").lower()
    if "supply" in domain:
        return "hierarchical_supply"
    if "market" in domain:
        return "market_microstructure"
    return "authored"
