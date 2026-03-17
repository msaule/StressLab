from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from stresslab.cli.main import app
from stresslab.discovery.engine import compute_feature_importance, discover_candidate_laws
from stresslab.generator import (
    SyntheticGenerationConfig,
    build_generation_artifacts,
    generate_system_spec,
)
from stresslab.systemspec.validators import validate_spec
from stresslab.theory.features import extract_system_features

runner = CliRunner()


def test_generate_system_spec_is_valid():
    spec = generate_system_spec(
        topology_type="random_queue",
        index=0,
        base_seed=11,
        min_nodes=6,
        max_nodes=8,
        horizon=180.0,
        system_prefix="test",
    )
    validation = validate_spec(spec)
    assert validation.valid, validation.errors
    assert spec.system.topology_type == "random_queue"
    assert spec.search.search_space


def test_generation_artifacts_and_features(tmp_path: Path):
    output_dir = tmp_path / "generation"
    summary = build_generation_artifacts(
        output_dir,
        config=SyntheticGenerationConfig(count=3, topology_type="mixed", min_nodes=5, max_nodes=7, seed=5),
    )
    assert summary.system_count == 3
    assert (output_dir / "generation_summary.csv").exists()
    assert (output_dir / "generation_report.html").exists()
    frame = pd.read_csv(output_dir / "generation_summary.csv")
    assert set(frame["topology_type"]) <= {
        "random_queue",
        "scale_free",
        "small_world",
        "hierarchical_supply",
        "market_microstructure",
    }
    features = extract_system_features(Path(frame.iloc[0]["spec_path"]))
    assert "redundancy_index" in features
    assert "coupling_strength" in features
    assert features["node_count"] >= 5


def test_candidate_law_discovery_returns_ranked_outputs():
    frame = pd.DataFrame(
        {
            "utilization": [0.2, 0.3, 0.4, 0.55, 0.7, 0.85],
            "redundancy_index": [0.5, 0.42, 0.35, 0.28, 0.18, 0.1],
            "coupling_strength": [0.2, 0.24, 0.29, 0.34, 0.39, 0.44],
            "collapse_probability": [0.05, 0.08, 0.14, 0.31, 0.62, 0.88],
            "fragility_index": [0.1, 0.12, 0.2, 0.36, 0.71, 0.95],
            "throughput_loss": [0.01, 0.02, 0.05, 0.1, 0.2, 0.33],
            "max_cascade_size": [1, 1, 2, 3, 5, 7],
            "failure_shock_budget": [1.8, 1.5, 1.3, 1.0, 0.8, 0.5],
        }
    )
    importance = compute_feature_importance(frame, target="collapse_probability")
    laws = discover_candidate_laws(frame, target="collapse_probability")
    assert not importance.empty
    assert not laws.empty
    assert "formula" in laws.columns
    assert laws.iloc[0]["r2"] >= 0.0


def test_generate_discover_theory_research_cli(tmp_path: Path):
    output_dir = tmp_path / "runs"
    generate_result = runner.invoke(
        app,
        [
            "generate",
            "--count",
            "2",
            "--topology-type",
            "mixed",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert generate_result.exit_code == 0

    discover_result = runner.invoke(
        app,
        [
            "discover",
            "--count",
            "2",
            "--topology-type",
            "mixed",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert discover_result.exit_code == 0
    discover_dirs = [path for path in output_dir.iterdir() if path.is_dir() and path.name.endswith("_discover")]
    assert discover_dirs
    discover_dir = sorted(discover_dirs)[-1]
    assert (discover_dir / "collapse_dataset.csv").exists()
    assert (discover_dir / "discovery_report.html").exists()
    assert (discover_dir / "symbolic_laws.csv").exists()

    theory_result = runner.invoke(
        app,
        ["theory", str(discover_dir), "--output-dir", str(output_dir)],
    )
    assert theory_result.exit_code == 0
    theory_dirs = [path for path in output_dir.iterdir() if path.is_dir() and path.name.endswith("_theory")]
    assert theory_dirs
    theory_dir = sorted(theory_dirs)[-1]
    assert (theory_dir / "theory_summary.json").exists()
    assert (theory_dir / "theory_report.html").exists()
    assert (theory_dir / "symbolic_laws.csv").exists()
    assert (theory_dir / "phase_transition_bootstrap.csv").exists()
    assert (theory_dir / "tail_model_comparison.csv").exists()
    assert (theory_dir / "early_warning_trends.csv").exists()

    research_result = runner.invoke(
        app,
        ["research", str(discover_dir), "--output-dir", str(output_dir)],
    )
    assert research_result.exit_code == 0
    research_dirs = [path for path in output_dir.iterdir() if path.is_dir() and path.name.endswith("_research")]
    assert research_dirs
    research_dir = sorted(research_dirs)[-1]
    assert (research_dir / "research_summary.json").exists()
    assert (research_dir / "research_report.html").exists()
    assert (research_dir / "figure_index.csv").exists()
    assert (research_dir / "figures").exists()

    catalog_result = runner.invoke(app, ["catalog", str(output_dir), "--output-dir", str(output_dir)])
    assert catalog_result.exit_code == 0
    catalog_dirs = [path for path in output_dir.iterdir() if path.is_dir() and path.name.endswith("_catalog")]
    assert catalog_dirs
    catalog_dir = sorted(catalog_dirs)[-1]
    catalog_text = (catalog_dir / "run_catalog.csv").read_text(encoding="utf-8")
    assert "generate" in catalog_text
    assert "discover" in catalog_text
    assert "theory" in catalog_text
    assert "research" in catalog_text


def test_generate_and_discover_support_deterministic_shards(tmp_path: Path):
    output_dir = tmp_path / "shards"
    generate_result = runner.invoke(
        app,
        [
            "generate",
            "--count",
            "5",
            "--topology-type",
            "mixed",
            "--shard-count",
            "2",
            "--shard-index",
            "1",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert generate_result.exit_code == 0
    generate_dir = sorted(path for path in output_dir.iterdir() if path.is_dir() and path.name.endswith("_generate"))[-1]
    generation_frame = pd.read_csv(generate_dir / "generation_summary.csv")
    assert len(generation_frame) == 2
    assert generation_frame.iloc[0]["system_id"].endswith("000003")

    discover_result = runner.invoke(
        app,
        [
            "discover",
            "--count",
            "5",
            "--topology-type",
            "mixed",
            "--shard-count",
            "2",
            "--shard-index",
            "1",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert discover_result.exit_code == 0
    discover_dir = sorted(path for path in output_dir.iterdir() if path.is_dir() and path.name.endswith("_discover"))[-1]
    discovery_frame = pd.read_csv(discover_dir / "collapse_dataset.csv")
    summary_text = (discover_dir / "discovery_summary.json").read_text(encoding="utf-8")
    assert len(discovery_frame) == 2
    assert '"shard_count": 2' in summary_text
    assert '"shard_index": 1' in summary_text


def test_theory_can_merge_multiple_discovery_runs(tmp_path: Path):
    workspace = tmp_path / "workspace"
    for shard_index in [0, 1]:
        result = runner.invoke(
            app,
            [
                "discover",
                "--count",
                "4",
                "--topology-type",
                "mixed",
                "--shard-count",
                "2",
                "--shard-index",
                str(shard_index),
                "--output-dir",
                str(workspace),
            ],
        )
        assert result.exit_code == 0

    theory_root = tmp_path / "theory"
    theory_result = runner.invoke(app, ["theory", str(workspace), "--output-dir", str(theory_root)])
    assert theory_result.exit_code == 0
    theory_dir = sorted(path for path in theory_root.iterdir() if path.is_dir() and path.name.endswith("_theory"))[-1]
    combined = pd.read_csv(theory_dir / "combined_collapse_dataset.csv")
    source_index = pd.read_csv(theory_dir / "source_dataset_index.csv")
    summary_text = (theory_dir / "theory_summary.json").read_text(encoding="utf-8")
    assert len(combined) == 4
    assert len(source_index) == 2
    assert '"source_dataset_count": 2' in summary_text
