"""Synthetic SystemSpec generation for discovery-scale experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from stresslab.models import GenerationRecord, GenerationSummary
from stresslab.systemspec.schema import SystemSpec
from stresslab.theory.features import extract_system_features
from stresslab.utils import ensure_directory, write_dataframe, write_json, write_yaml
from stresslab.viz.discovery import plot_generation_mix, plot_generation_topologies

SUPPORTED_TOPOLOGIES = {
    "mixed",
    "random_queue",
    "scale_free",
    "small_world",
    "hierarchical_supply",
    "market_microstructure",
}


@dataclass(slots=True)
class SyntheticGenerationConfig:
    """Configuration for synthetic-system generation."""

    count: int = 24
    topology_type: str = "mixed"
    min_nodes: int = 6
    max_nodes: int = 16
    seed: int = 7
    batch_size: int = 250
    horizon: float = 360.0
    system_prefix: str = "synthetic"
    start_index: int = 0
    shard_count: int = 1
    shard_index: int = 0


def build_generation_artifacts(
    output_dir: Path,
    *,
    config: SyntheticGenerationConfig,
) -> GenerationSummary:
    """Generate YAML SystemSpecs plus summary/report artifacts."""

    output_dir = ensure_directory(Path(output_dir))
    generated_dir = ensure_directory(output_dir / "generated")
    records = generate_spec_records(generated_dir, config=config)
    frame = pd.DataFrame([record.model_dump(mode="json") for record in records])
    write_dataframe(output_dir / "generation_summary.csv", frame)
    plot_generation_mix(frame, output_dir / "generation_topology_mix.png")
    plot_generation_topologies(frame, output_dir / "generation_size_degree.png")
    summary = GenerationSummary(
        title=f"Synthetic Generation: {config.topology_type}",
        topology_type=config.topology_type,
        generation_dir=str(output_dir),
        system_count=len(records),
        shard_count=max(1, config.shard_count),
        shard_index=max(0, config.shard_index),
        summary_csv_path=str(output_dir / "generation_summary.csv"),
        summary_json_path=str(output_dir / "generation_summary.json"),
        report_markdown_path=str(output_dir / "generation_report.md"),
        report_html_path=str(output_dir / "generation_report.html"),
        records=records,
    )
    write_json(output_dir / "generation_summary.json", summary)
    markdown = _build_generation_markdown(summary, frame)
    (output_dir / "generation_report.md").write_text(markdown, encoding="utf-8")
    html = _build_generation_html(summary, frame)
    (output_dir / "generation_report.html").write_text(html, encoding="utf-8")
    return summary


def generate_spec_records(
    generated_dir: Path,
    *,
    config: SyntheticGenerationConfig,
) -> list[GenerationRecord]:
    """Generate a family of synthetic specs and return summary records."""

    generated_dir = ensure_directory(generated_dir)
    records: list[GenerationRecord] = []
    for offset in range(config.count):
        index = config.start_index + offset
        topology_type = _select_topology(config.topology_type, index=index)
        spec = generate_system_spec(
            topology_type=topology_type,
            index=index,
            base_seed=config.seed,
            min_nodes=config.min_nodes,
            max_nodes=config.max_nodes,
            horizon=config.horizon,
            system_prefix=config.system_prefix,
        )
        system_id = f"{config.system_prefix}_{index:06d}"
        spec_path = generated_dir / f"{system_id}.yml"
        write_yaml(spec_path, spec.model_dump(mode="json", by_alias=True))
        features = extract_system_features(spec)
        records.append(
            GenerationRecord(
                system_id=system_id,
                topology_type=topology_type,
                domain=str(spec.system.domain or "synthetic"),
                spec_path=str(spec_path),
                seed=spec.seed,
                node_count=int(features.get("node_count", len(spec.nodes))),
                edge_count=int(features.get("edge_count", len(spec.edges))),
                average_degree=float(features.get("average_degree", 0.0)),
                redundancy_score=float(features.get("redundancy_index", 0.0)),
                coupling_score=float(features.get("coupling_strength", 0.0)),
            )
        )
    return records


def generate_system_spec(
    *,
    topology_type: str,
    index: int,
    base_seed: int,
    min_nodes: int,
    max_nodes: int,
    horizon: float,
    system_prefix: str,
) -> SystemSpec:
    """Generate one valid SystemSpec for a supported synthetic topology."""

    if topology_type not in SUPPORTED_TOPOLOGIES - {"mixed"}:
        raise ValueError(f"Unsupported topology_type '{topology_type}'.")
    seed = int(base_seed + index)
    rng = np.random.default_rng(seed)
    node_count = int(rng.integers(min_nodes, max_nodes + 1))
    graph, domain = _build_topology_graph(topology_type, node_count=node_count, rng=rng)
    node_order = list(graph.nodes())
    degrees = dict(graph.degree())
    centrality = nx.betweenness_centrality(graph.to_undirected()) if graph.number_of_edges() else {
        node_id: 0.0 for node_id in node_order
    }
    source_nodes = [node_id for node_id in node_order if graph.in_degree(node_id) == 0]
    if not source_nodes:
        source_nodes = [node_order[0]]
    max_degree = max((degrees.get(node_id, 0) for node_id in node_order), default=1)
    nodes = []
    for node_id in node_order:
        service_mean = float(rng.uniform(4.5, 11.5) * (1.0 + 0.35 * centrality.get(node_id, 0.0)))
        servers = int(max(1, round(1 + (degrees.get(node_id, 0) / max(max_degree, 1)) * 2 + rng.uniform(0, 1))))
        buffer_capacity = int(rng.integers(10, 36))
        queue_policy = "priority" if centrality.get(node_id, 0.0) > 0.22 and rng.random() < 0.45 else "fifo"
        node_payload = {
            "id": node_id,
            "type": "queue_server",
            "servers": servers,
            "buffer_capacity": buffer_capacity,
            "queue_policy": queue_policy,
            "service_time": {
                "distribution": "exponential",
                "mean": round(service_mean, 4),
            },
        }
        if queue_policy == "priority":
            node_payload["priority_classes"] = ["urgent", "standard"]
        nodes.append(node_payload)

    edges = []
    for source in node_order:
        outgoing = list(graph.successors(source))
        if not outgoing:
            continue
        probabilities = _routing_probabilities(len(outgoing), rng)
        for target, probability in zip(outgoing, probabilities, strict=True):
            edges.append(
                {
                    "from": source,
                    "to": target,
                    "routing": {
                        "type": "probabilistic",
                        "probability": round(float(probability), 6),
                    },
                    "travel_time": round(float(rng.uniform(0.0, 4.0)), 4),
                    "transfer_capacity": round(float(rng.uniform(0.1, 0.45)), 4),
                }
            )

    arrivals = []
    for source in source_nodes[: max(1, len(source_nodes))]:
        base_rate = float(rng.uniform(0.03, 0.09))
        arrivals.append(
            {
                "node": source,
                "process": {
                    "type": "nonhomogeneous_poisson",
                    "base_rate": round(base_rate, 6),
                    "seasonality": {
                        "period": "daily",
                        "amplitude": round(float(rng.uniform(0.0, 0.2)), 4),
                    },
                },
                "class_mix": {
                    "standard": 0.78,
                    "urgent": 0.22,
                },
            }
        )

    hub_nodes = sorted(node_order, key=lambda item: (centrality.get(item, 0.0), degrees.get(item, 0)), reverse=True)
    primary_hub = hub_nodes[0]
    interventions = [
        {
            "id": f"add_staff__{primary_hub}",
            "label": f"Add capacity at {primary_hub}",
            "target": primary_hub,
            "action_type": "add_servers",
            "delta": 1,
            "cost": 250,
        },
        {
            "id": f"add_buffer__{primary_hub}",
            "label": f"Increase buffer at {primary_hub}",
            "target": primary_hub,
            "action_type": "increase_buffer_capacity",
            "delta": 8,
            "cost": 180,
        },
        {
            "id": f"speed_up__{primary_hub}",
            "label": f"Reduce service time at {primary_hub}",
            "target": primary_hub,
            "action_type": "reduce_service_time_factor",
            "delta": 0.18,
            "cost": 320,
        },
    ]
    if edges:
        preferred_edge = max(edges, key=lambda edge: edge["routing"]["probability"])
        interventions.append(
            {
                "id": f"reroute__{preferred_edge['from']}__{preferred_edge['to']}",
                "label": f"Reroute around {preferred_edge['from']}->{preferred_edge['to']}",
                "target": f"{preferred_edge['from']}->{preferred_edge['to']}",
                "action_type": "reroute_fraction",
                "delta": 0.15,
                "cost": 210,
            }
        )

    search_space = []
    for source in source_nodes[: min(2, len(source_nodes))]:
        search_space.append(
            {
                "id": f"demand__{source}",
                "kind": "demand_multiplier",
                "target": source,
                "min": 1.0,
                "max": 2.8,
                "cost_weight": 1.0,
                "start": 0.0,
                "duration": horizon,
            }
        )
    search_space.append(
        {
            "id": f"capacity__{primary_hub}",
            "kind": "capacity_fraction",
            "target": primary_hub,
            "min": 0.0,
            "max": 0.75,
            "cost_weight": 1.3,
            "start": horizon * 0.1,
            "duration": horizon * 0.8,
        }
    )
    if edges:
        weakest_edge = min(edges, key=lambda edge: edge["transfer_capacity"])
        search_space.append(
            {
                "id": f"edge_cap__{weakest_edge['from']}__{weakest_edge['to']}",
                "kind": "transfer_capacity_fraction",
                "target": f"{weakest_edge['from']}->{weakest_edge['to']}",
                "min": 0.0,
                "max": 0.8,
                "cost_weight": 0.9,
                "start": horizon * 0.15,
                "duration": horizon * 0.7,
            }
        )

    spec_payload = {
        "system": {
            "name": f"{system_prefix}_{topology_type}_{index:06d}",
            "domain": domain,
            "description": f"Synthetic {topology_type} network generated by StressLab.",
        },
        "clock": {"type": "continuous", "start": 0.0, "end": float(horizon)},
        "classes": [
            {"id": "standard", "priority": 0},
            {"id": "urgent", "priority": 1},
        ],
        "nodes": nodes,
        "edges": edges,
        "arrivals": arrivals,
        "failure_conditions": [
            {
                "type": "any",
                "conditions": [
                    {"type": "mean_wait", "node": primary_hub, "threshold": 14.0},
                    {"type": "throughput_loss", "threshold": 0.3},
                    {"type": "cascade_norm", "threshold": 0.45},
                ],
            }
        ],
        "interventions": interventions,
        "search": {
            "objective": "min_failure",
            "max_iterations": 10,
            "direction_samples": 6,
            "budget": 1.6,
            "search_space": search_space,
        },
        "report": {"top_n_nodes": 3},
        "seed": seed,
    }
    spec = SystemSpec.model_validate(spec_payload)
    spec.system.topology_type = topology_type
    features = extract_system_features(spec)
    spec.system.node_count = features.get("node_count")
    spec.system.average_degree = features.get("average_degree")
    spec.system.redundancy_index = features.get("redundancy_index")
    spec.system.coupling_strength = features.get("coupling_strength")
    spec.system.centralization_index = features.get("centralization_index")
    spec.system.routing_entropy = features.get("routing_entropy")
    spec.system.redundancy_score = features.get("redundancy_index")
    spec.system.coupling_score = features.get("coupling_strength")
    return spec


def _select_topology(topology_type: str, *, index: int) -> str:
    if topology_type != "mixed":
        return topology_type
    ordered = [
        "random_queue",
        "scale_free",
        "small_world",
        "hierarchical_supply",
        "market_microstructure",
    ]
    return ordered[index % len(ordered)]


def _build_topology_graph(
    topology_type: str,
    *,
    node_count: int,
    rng: np.random.Generator,
) -> tuple[nx.DiGraph, str]:
    if topology_type == "random_queue":
        graph = _random_queue_graph(node_count=node_count, rng=rng)
        return graph, "synthetic_queue"
    if topology_type == "scale_free":
        graph = _scale_free_graph(node_count=node_count, rng=rng)
        return graph, "synthetic_infrastructure"
    if topology_type == "small_world":
        graph = _small_world_graph(node_count=node_count, rng=rng)
        return graph, "synthetic_referral"
    if topology_type == "hierarchical_supply":
        graph = _hierarchical_supply_graph(node_count=node_count, rng=rng)
        return graph, "synthetic_supply_chain"
    graph = _market_microstructure_graph(node_count=node_count, rng=rng)
    return graph, "synthetic_market"


def _random_queue_graph(*, node_count: int, rng: np.random.Generator) -> nx.DiGraph:
    graph = nx.DiGraph()
    node_ids = [f"n{index:02d}" for index in range(node_count)]
    graph.add_nodes_from(node_ids)
    for index in range(node_count - 1):
        graph.add_edge(node_ids[index], node_ids[index + 1])
    extra_probability = min(0.28, 2.6 / max(node_count, 1))
    for source_index in range(node_count):
        candidate_targets = [
            target_index for target_index in range(source_index + 1, node_count)
            if target_index != source_index + 1
        ]
        rng.shuffle(candidate_targets)
        added = 0
        for target_index in candidate_targets:
            if added >= 2:
                break
            if rng.random() <= extra_probability:
                graph.add_edge(node_ids[source_index], node_ids[target_index])
                added += 1
    return graph


def _scale_free_graph(*, node_count: int, rng: np.random.Generator) -> nx.DiGraph:
    attachment = max(1, min(3, node_count - 1))
    undirected = nx.barabasi_albert_graph(node_count, attachment, seed=int(rng.integers(0, 10_000_000)))
    return _orient_graph_with_back_edges(undirected, rng=rng, back_edge_probability=0.12)


def _small_world_graph(*, node_count: int, rng: np.random.Generator) -> nx.DiGraph:
    degree = max(2, min(4, node_count - 1))
    if degree % 2 == 1:
        degree += 1
    degree = max(2, min(degree, node_count - 1))
    undirected = nx.watts_strogatz_graph(
        node_count,
        degree,
        0.22,
        seed=int(rng.integers(0, 10_000_000)),
    )
    return _orient_graph_with_back_edges(undirected, rng=rng, back_edge_probability=0.18)


def _hierarchical_supply_graph(*, node_count: int, rng: np.random.Generator) -> nx.DiGraph:
    graph = nx.DiGraph()
    supplier_count = max(2, node_count // 4)
    plant_count = max(2, node_count // 4)
    distribution_count = max(2, node_count // 4)
    retail_count = max(2, node_count - supplier_count - plant_count - distribution_count)
    tiers = {
        "supplier": [f"s{index:02d}" for index in range(supplier_count)],
        "plant": [f"p{index:02d}" for index in range(plant_count)],
        "distribution": [f"d{index:02d}" for index in range(distribution_count)],
        "retail": [f"r{index:02d}" for index in range(retail_count)],
    }
    for tier_nodes in tiers.values():
        graph.add_nodes_from(tier_nodes)
    tier_names = list(tiers)
    for tier_index in range(len(tier_names) - 1):
        source_tier = tiers[tier_names[tier_index]]
        target_tier = tiers[tier_names[tier_index + 1]]
        for source in source_tier:
            choices = list(target_tier)
            rng.shuffle(choices)
            for target in choices[: max(1, min(3, len(choices)))]:
                graph.add_edge(source, target)
    return graph


def _market_microstructure_graph(*, node_count: int, rng: np.random.Generator) -> nx.DiGraph:
    graph = nx.DiGraph()
    provider_count = max(2, node_count // 3)
    venue_count = max(2, node_count // 3)
    settlement_count = max(2, node_count - provider_count - venue_count)
    providers = [f"lp{index:02d}" for index in range(provider_count)]
    venues = [f"vx{index:02d}" for index in range(venue_count)]
    settlements = [f"st{index:02d}" for index in range(settlement_count)]
    graph.add_nodes_from([*providers, *venues, *settlements])
    for provider in providers:
        choices = list(venues)
        rng.shuffle(choices)
        for venue in choices[: max(1, min(3, len(choices)))]:
            graph.add_edge(provider, venue)
    for venue in venues:
        sibling_choices = [candidate for candidate in venues if candidate != venue]
        rng.shuffle(sibling_choices)
        for sibling in sibling_choices[:1]:
            if rng.random() < 0.35:
                graph.add_edge(venue, sibling)
        settlement_choices = list(settlements)
        rng.shuffle(settlement_choices)
        for settlement in settlement_choices[: max(1, min(2, len(settlement_choices)))]:
            graph.add_edge(venue, settlement)
    return graph


def _orient_graph_with_back_edges(
    graph: nx.Graph,
    *,
    rng: np.random.Generator,
    back_edge_probability: float,
) -> nx.DiGraph:
    directed = nx.DiGraph()
    node_ids = [f"n{index:02d}" for index in range(graph.number_of_nodes())]
    index_map = {index: node_id for index, node_id in enumerate(node_ids)}
    directed.add_nodes_from(node_ids)
    for left, right in graph.edges():
        source = index_map[min(left, right)]
        target = index_map[max(left, right)]
        directed.add_edge(source, target)
        if rng.random() < back_edge_probability:
            directed.add_edge(target, source)
    if not nx.is_weakly_connected(directed):
        ordered = list(node_ids)
        for index in range(len(ordered) - 1):
            directed.add_edge(ordered[index], ordered[index + 1])
    return directed


def _routing_probabilities(count: int, rng: np.random.Generator) -> list[float]:
    raw = rng.uniform(0.25, 1.0, size=count)
    probabilities = 0.98 * (raw / raw.sum())
    return [float(value) for value in probabilities]


def _build_generation_markdown(summary: GenerationSummary, frame: pd.DataFrame) -> str:
    lines = [
        f"# {summary.title}",
        "",
        f"- Generated systems: `{summary.system_count}`",
        f"- Topology mode: `{summary.topology_type}`",
        "",
        "## Records",
        "",
        _frame_to_markdown(frame.head(25)),
        "",
        "![Topology Mix](generation_topology_mix.png)",
        "",
        "![Size vs Degree](generation_size_degree.png)",
        "",
    ]
    return "\n".join(lines)


def _build_generation_html(summary: GenerationSummary, frame: pd.DataFrame) -> str:
    return "\n".join(
        [
            "<html><body>",
            f"<h1>{summary.title}</h1>",
            f"<p>Generated systems: <strong>{summary.system_count}</strong></p>",
            frame.head(50).to_html(index=False, border=0),
            "<h2>Topology Mix</h2><img src='generation_topology_mix.png' style='max-width: 100%;'>",
            "<h2>Size vs Degree</h2><img src='generation_size_degree.png' style='max-width: 100%;'>",
            "</body></html>",
        ]
    )


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No records_"
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])
