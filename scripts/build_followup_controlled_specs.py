from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from stresslab.generator import generate_system_spec
from stresslab.systemspec import load_spec
from stresslab.systemspec.schema import SystemSpec
from stresslab.theory.features import extract_system_features
from stresslab.utils import ensure_directory, write_dataframe, write_yaml

TOPOLOGIES = [
    "random_queue",
    "scale_free",
    "small_world",
    "hierarchical_supply",
    "market_microstructure",
]

UTILIZATION_TARGETS = [0.06, 0.10, 0.14, 0.18, 0.22, 0.26]
COUPLING_SCALES = [0.75, 1.0, 1.25]
HEALTHCARE_UTILIZATION_MULTIPLIERS = [0.75, 0.9, 1.05, 1.2, 1.35, 1.5]
HEALTHCARE_COUPLING_MODES = {
    "low": {"triage_imaging": 0.30, "triage_ward": 0.60, "imaging_ward": 0.60, "transfer_capacity": 0.18},
    "medium": {"triage_imaging": 0.45, "triage_ward": 0.45, "imaging_ward": 0.80, "transfer_capacity": 0.28},
    "high": {"triage_imaging": 0.60, "triage_ward": 0.30, "imaging_ward": 0.95, "transfer_capacity": 0.40},
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build controlled specs for the follow-up threshold study.")
    parser.add_argument("--output-root", type=Path, default=Path("generated/followup_controlled_threshold_study"))
    parser.add_argument("--replicates", type=int, default=30)
    parser.add_argument("--node-count", type=int, default=16)
    parser.add_argument("--base-seed", type=int, default=900)
    parser.add_argument("--healthcare-replicates", type=int, default=8)
    parser.add_argument("--healthcare-spec", type=Path, default=Path("examples/healthcare/ed_basic.yml"))
    args = parser.parse_args()

    output_root = ensure_directory(args.output_root.resolve())
    synthetic_dir = ensure_directory(output_root / "synthetic_specs")
    healthcare_dir = ensure_directory(output_root / "healthcare_specs")

    synthetic_rows = build_synthetic_specs(
        output_dir=synthetic_dir,
        replicates=args.replicates,
        node_count=args.node_count,
        base_seed=args.base_seed,
    )
    healthcare_rows = build_healthcare_specs(
        output_dir=healthcare_dir,
        spec_path=args.healthcare_spec.resolve(),
        replicates=args.healthcare_replicates,
    )

    write_dataframe(output_root / "synthetic_manifest.csv", pd.DataFrame(synthetic_rows))
    write_dataframe(output_root / "healthcare_manifest.csv", pd.DataFrame(healthcare_rows))


def build_synthetic_specs(*, output_dir: Path, replicates: int, node_count: int, base_seed: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for topology_index, topology in enumerate(TOPOLOGIES):
        for replicate in range(replicates):
            base_spec = generate_system_spec(
                topology_type=topology,
                index=replicate,
                base_seed=base_seed + topology_index * 1000,
                min_nodes=node_count,
                max_nodes=node_count,
                horizon=360.0,
                system_prefix="followup",
            )
            for util_target in UTILIZATION_TARGETS:
                for coupling_scale in COUPLING_SCALES:
                    spec = SystemSpec.model_validate(base_spec.model_dump(mode="json", by_alias=True))
                    tune_synthetic_spec(spec, util_target=util_target, coupling_scale=coupling_scale)
                    spec.seed = int(base_seed + topology_index * 100_000 + replicate * 100 + round(util_target * 1000) + int(coupling_scale * 10))
                    spec.system.name = (
                        f"followup_{topology}_r{replicate:03d}_u{int(util_target * 1000):03d}_c{int(coupling_scale * 100):03d}"
                    )
                    spec.system.description = "Controlled utilization/coupling follow-up study spec."
                    spec_path = output_dir / f"{spec.system.name}.yml"
                    write_yaml(spec_path, spec.model_dump(mode="json", by_alias=True))
                    features = extract_system_features(spec)
                    rows.append(
                        {
                            "study_family": "synthetic_controlled",
                            "topology_type": topology,
                            "replicate": replicate,
                            "util_target": util_target,
                            "coupling_scale": coupling_scale,
                            "system_name": spec.system.name,
                            "spec_path": str(spec_path),
                            "achieved_utilization": float(features.get("utilization", 0.0)),
                            "achieved_coupling": float(features.get("coupling_strength", 0.0)),
                            "routing_entropy": float(features.get("routing_entropy", 0.0)),
                            "node_count": int(features.get("node_count", node_count)),
                        }
                    )
    return rows


def build_healthcare_specs(*, output_dir: Path, spec_path: Path, replicates: int) -> list[dict[str, object]]:
    base_spec = load_spec(spec_path)
    rows: list[dict[str, object]] = []
    for replicate in range(replicates):
        for util_multiplier in HEALTHCARE_UTILIZATION_MULTIPLIERS:
            for coupling_mode, payload in HEALTHCARE_COUPLING_MODES.items():
                spec = SystemSpec.model_validate(base_spec.model_dump(mode="json", by_alias=True))
                tune_healthcare_spec(spec, util_multiplier=util_multiplier, coupling_payload=payload)
                spec.seed = int(40_000 + replicate * 100 + round(util_multiplier * 100) + len(coupling_mode))
                spec.system.name = f"followup_healthcare_r{replicate:03d}_u{int(util_multiplier * 100):03d}_{coupling_mode}"
                spec.system.description = "Healthcare overload follow-up family spec."
                spec.system.topology_type = "healthcare_referral"
                spec_path_out = output_dir / f"{spec.system.name}.yml"
                write_yaml(spec_path_out, spec.model_dump(mode="json", by_alias=True))
                features = extract_system_features(spec)
                rows.append(
                    {
                        "study_family": "healthcare_controlled",
                        "topology_type": "healthcare_referral",
                        "replicate": replicate,
                        "util_target": util_multiplier,
                        "coupling_scale": coupling_mode,
                        "system_name": spec.system.name,
                        "spec_path": str(spec_path_out),
                        "achieved_utilization": float(features.get("utilization", 0.0)),
                        "achieved_coupling": float(features.get("coupling_strength", 0.0)),
                        "routing_entropy": float(features.get("routing_entropy", 0.0)),
                        "node_count": int(features.get("node_count", len(spec.nodes))),
                    }
                )
    return rows


def tune_synthetic_spec(spec: SystemSpec, *, util_target: float, coupling_scale: float) -> None:
    features = extract_system_features(spec)
    current_util = max(float(features.get("utilization", 0.0)), 1e-6)
    rate_scale = util_target / current_util
    for arrival in spec.arrivals:
        process = arrival.process
        if process.base_rate is not None:
            process.base_rate = max(1e-4, float(process.base_rate) * rate_scale)
        elif process.rate is not None:
            process.rate = max(1e-4, float(process.rate) * rate_scale)
    for edge in spec.edges:
        current_capacity = float(edge.transfer_capacity or 0.25)
        edge.transfer_capacity = min(0.95, max(0.05, current_capacity * coupling_scale))


def tune_healthcare_spec(spec: SystemSpec, *, util_multiplier: float, coupling_payload: dict[str, float]) -> None:
    for arrival in spec.arrivals:
        process = arrival.process
        if process.base_rate is not None:
            process.base_rate = max(1e-4, float(process.base_rate) * util_multiplier)
    for edge in spec.edges:
        if edge.from_node == "triage" and edge.to_node == "imaging":
            edge.routing.probability = float(coupling_payload["triage_imaging"])
            edge.transfer_capacity = float(coupling_payload["transfer_capacity"])
        elif edge.from_node == "triage" and edge.to_node == "ward":
            edge.routing.probability = float(coupling_payload["triage_ward"])
            edge.transfer_capacity = float(coupling_payload["transfer_capacity"])
        elif edge.from_node == "imaging" and edge.to_node == "ward":
            edge.routing.probability = float(coupling_payload["imaging_ward"])
            edge.transfer_capacity = float(coupling_payload["transfer_capacity"])


if __name__ == "__main__":
    main()
