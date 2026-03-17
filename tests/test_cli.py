from __future__ import annotations

import csv
import zipfile
from pathlib import Path

import yaml
from typer.testing import CliRunner

from stresslab.cli.main import app

runner = CliRunner()


def test_validate_command(toy_spec_path):
    result = runner.invoke(app, ["validate", str(toy_spec_path)])
    assert result.exit_code == 0
    assert "Validation passed" in result.stdout


def test_run_command_builds_artifacts(toy_spec_path, tmp_path: Path):
    output_dir = tmp_path / "runs"
    result = runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(output_dir)])
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    run_dir = created[0]
    assert (run_dir / "baseline_result.json").exists()
    assert (run_dir / "edge_metrics.csv").exists()
    assert (run_dir / "class_metrics.csv").exists()
    assert (run_dir / "class_fairness.png").exists()
    assert (run_dir / "report.html").exists()


def test_optimize_robust_builds_scenario_summary(toy_spec_path, tmp_path: Path):
    output_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "optimize",
            str(toy_spec_path),
            "--robust",
            "--scenario-budget",
            "0.5",
            "--scenario-samples",
            "2",
            "--budget",
            "100",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    run_dir = created[0]
    assert (run_dir / "scenario_summary.csv").exists()
    assert (run_dir / "scenario_clusters.csv").exists()
    assert (run_dir / "cluster_summary.csv").exists()
    assert (run_dir / "intervention_coverage.csv").exists()
    assert (run_dir / "portfolio_candidates.csv").exists()
    assert (run_dir / "portfolio_cluster_coverage.csv").exists()
    assert (run_dir / "cluster_response_plan.csv").exists()
    assert (run_dir / "regime_plan_summary.json").exists()
    assert (run_dir / "regime_detection.csv").exists()
    assert (run_dir / "regime_detection_confusion.csv").exists()
    assert (run_dir / "regime_detection_summary.json").exists()
    assert (run_dir / "online_regime_detection.csv").exists()
    assert (run_dir / "online_regime_horizons.csv").exists()
    assert (run_dir / "online_regime_summary.json").exists()
    assert (run_dir / "response_timing.csv").exists()
    assert (run_dir / "response_timing_summary.json").exists()
    assert (run_dir / "closed_loop_regime.csv").exists()
    assert (run_dir / "closed_loop_regime_summary.json").exists()
    assert (run_dir / "controller_policy_candidates.csv").exists()
    assert (run_dir / "controller_frontier.csv").exists()
    assert (run_dir / "controller_tuning_summary.json").exists()
    assert (run_dir / "pareto_frontier.csv").exists()
    assert (run_dir / "scenario_clusters.png").exists()
    assert (run_dir / "intervention_coverage.png").exists()
    assert (run_dir / "portfolio_tradeoff.png").exists()
    assert (run_dir / "cluster_response_plan.png").exists()
    assert (run_dir / "regime_detection.png").exists()
    assert (run_dir / "online_regime_accuracy.png").exists()
    assert (run_dir / "response_timing.png").exists()
    assert (run_dir / "closed_loop_regime.png").exists()
    assert (run_dir / "controller_tuning.png").exists()
    assert (run_dir / "controller_frontier.png").exists()
    assert (run_dir / "class_metrics.csv").exists()
    assert (run_dir / "class_fairness.png").exists()
    assert (run_dir / "optimization.json").exists()


def test_optimize_without_budget_still_builds_report(toy_spec_path, tmp_path: Path):
    output_dir = tmp_path / "runs"
    result = runner.invoke(app, ["optimize", str(toy_spec_path), "--output-dir", str(output_dir)])
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    run_dir = created[0]
    assert (run_dir / "optimization.json").exists()
    assert (run_dir / "report.html").exists()
    assert (run_dir / "intervention_roi.png").exists()


def test_compare_command_builds_comparison_report(toy_spec_path, tmp_path: Path):
    runs_root = tmp_path / "runs"
    first = runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(runs_root)])
    assert first.exit_code == 0
    second = runner.invoke(
        app,
        ["optimize", str(toy_spec_path), "--budget", "100", "--output-dir", str(runs_root)],
    )
    assert second.exit_code == 0
    run_dirs = sorted(path for path in runs_root.iterdir() if path.is_dir())
    compare_root = tmp_path / "comparisons"
    result = runner.invoke(
        app,
        ["compare", str(run_dirs[0]), str(run_dirs[1]), "--output-dir", str(compare_root)],
    )
    assert result.exit_code == 0
    created = [path for path in compare_root.iterdir() if path.is_dir()]
    assert created
    compare_dir = created[0]
    assert (compare_dir / "comparison_summary.csv").exists()
    assert (compare_dir / "comparison_summary.json").exists()
    assert (compare_dir / "comparison_report.html").exists()
    assert (compare_dir / "comparison_tradeoff.png").exists()
    assert (compare_dir / "comparison_metrics.png").exists()


def test_batch_command_executes_manifest(toy_spec_path, tmp_path: Path):
    manifest_path = tmp_path / "campaign.yml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "name": "toy_campaign",
                "description": "Toy batch campaign",
                "jobs": [
                    {
                        "id": "baseline_run",
                        "command": "run",
                        "spec_path": str(toy_spec_path),
                    },
                    {
                        "id": "quick_optimize",
                        "command": "optimize",
                        "spec_path": str(toy_spec_path),
                        "budget": 100,
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "batches"
    result = runner.invoke(app, ["batch", str(manifest_path), "--output-dir", str(output_dir)])
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    batch_dir = created[0]
    assert (batch_dir / "batch_manifest_resolved.yaml").exists()
    assert (batch_dir / "batch_summary.csv").exists()
    assert (batch_dir / "batch_summary.json").exists()
    assert (batch_dir / "batch_report.html").exists()
    assert (batch_dir / "comparison_summary.csv").exists()
    assert (batch_dir / "comparison_report.html").exists()
    assert (batch_dir / "comparison_tradeoff.png").exists()
    assert (batch_dir / "baseline_run").exists()
    assert (batch_dir / "quick_optimize").exists()


def test_batch_command_executes_discovery_pipeline_manifest(tmp_path: Path):
    manifest_path = tmp_path / "discovery_campaign.yml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "name": "universal_fragility_pipeline",
                "description": "Synthetic discovery pipeline",
                "jobs": [
                    {
                        "id": "synthetic_generate",
                        "command": "generate",
                        "count": 2,
                        "topology_type": "mixed",
                        "min_nodes": 5,
                        "max_nodes": 6,
                        "batch_size": 2,
                    },
                    {
                        "id": "fragility_discover",
                        "command": "discover",
                        "source_dir": "{synthetic_generate}/generated",
                        "batch_size": 1,
                        "workers": 1,
                    },
                    {
                        "id": "fragility_theory",
                        "command": "theory",
                        "dataset_source": "{fragility_discover}",
                    },
                    {
                        "id": "fragility_research",
                        "command": "research",
                        "dataset_source": "{fragility_discover}",
                        "theory_dir": "{fragility_theory}",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "discovery_batches"
    result = runner.invoke(app, ["batch", str(manifest_path), "--output-dir", str(output_dir)])
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    batch_dir = created[0]
    assert (batch_dir / "synthetic_generate").exists()
    assert (batch_dir / "fragility_discover").exists()
    assert (batch_dir / "fragility_theory").exists()
    assert (batch_dir / "fragility_research").exists()
    assert list((batch_dir / "synthetic_generate").rglob("generation_summary.json"))
    assert list((batch_dir / "fragility_discover").rglob("discovery_summary.json"))
    assert list((batch_dir / "fragility_theory").rglob("theory_summary.json"))
    assert list((batch_dir / "fragility_research").rglob("research_summary.json"))
    summary_text = (batch_dir / "batch_summary.csv").read_text(encoding="utf-8")
    assert "generate" in summary_text
    assert "discover" in summary_text
    assert "theory" in summary_text
    assert "research" in summary_text


def test_catalog_command_builds_inventory_report(toy_spec_path, tmp_path: Path):
    runs_root = tmp_path / "runs"
    first = runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(runs_root)])
    assert first.exit_code == 0
    second = runner.invoke(
        app,
        ["optimize", str(toy_spec_path), "--budget", "100", "--output-dir", str(runs_root)],
    )
    assert second.exit_code == 0
    run_dirs = sorted(path for path in runs_root.iterdir() if path.is_dir())
    compare = runner.invoke(
        app,
        ["compare", str(run_dirs[0]), str(run_dirs[1]), "--output-dir", str(runs_root)],
    )
    assert compare.exit_code == 0
    catalogs_root = tmp_path / "catalogs"
    result = runner.invoke(
        app,
        ["catalog", str(runs_root), "--output-dir", str(catalogs_root)],
    )
    assert result.exit_code == 0
    created = [path for path in catalogs_root.iterdir() if path.is_dir()]
    assert created
    catalog_dir = created[0]
    assert (catalog_dir / "run_catalog.csv").exists()
    assert (catalog_dir / "run_catalog_summary.json").exists()
    assert (catalog_dir / "run_catalog_report.html").exists()
    assert (catalog_dir / "catalog_types.png").exists()
    assert (catalog_dir / "catalog_systems.png").exists()
    catalog_text = (catalog_dir / "run_catalog.csv").read_text(encoding="utf-8")
    assert "comparison" in catalog_text
    assert "optimize" in catalog_text


def test_status_command_builds_workspace_report(toy_spec_path, tmp_path: Path):
    workspace = tmp_path / "workspace"
    baseline = runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(workspace)])
    assert baseline.exit_code == 0
    optimize_result = runner.invoke(
        app,
        ["optimize", str(toy_spec_path), "--budget", "100", "--output-dir", str(workspace)],
    )
    assert optimize_result.exit_code == 0

    status_root = tmp_path / "status"
    result = runner.invoke(app, ["status", str(workspace), "--output-dir", str(status_root), "--refresh"])
    assert result.exit_code == 0
    created = [path for path in status_root.iterdir() if path.is_dir()]
    assert created
    status_dir = created[0]
    assert (status_dir / "workspace_status.csv").exists()
    assert (status_dir / "workspace_status_summary.json").exists()
    assert (status_dir / "workspace_status_report.html").exists()
    assert (status_dir / "status_analysis_types.png").exists()
    assert (status_dir / "status_systems.png").exists()
    assert (status_dir / "status_timeline.png").exists()
    summary_text = (status_dir / "workspace_status_summary.json").read_text(encoding="utf-8")
    assert '"entry_count"' in summary_text
    assert "optimize" in summary_text


def test_board_command_builds_workspace_dashboard(toy_spec_path, tmp_path: Path):
    workspace = tmp_path / "workspace"
    baseline = runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(workspace)])
    assert baseline.exit_code == 0
    optimize_result = runner.invoke(
        app,
        ["optimize", str(toy_spec_path), "--budget", "100", "--output-dir", str(workspace)],
    )
    assert optimize_result.exit_code == 0

    board_root = tmp_path / "boards"
    result = runner.invoke(app, ["board", str(workspace), "--output-dir", str(board_root), "--refresh"])
    assert result.exit_code == 0
    created = [path for path in board_root.iterdir() if path.is_dir()]
    assert created
    board_dir = created[0]
    assert (board_dir / "workspace_board_recent.csv").exists()
    assert (board_dir / "workspace_board_leaders.csv").exists()
    assert (board_dir / "workspace_board_failure_watchlist.csv").exists()
    assert (board_dir / "workspace_board_plans.csv").exists()
    assert (board_dir / "workspace_board_summary.json").exists()
    assert (board_dir / "workspace_board_report.html").exists()
    assert (board_dir / "board_analysis_mix.png").exists()
    assert (board_dir / "board_system_resilience.png").exists()
    assert (board_dir / "board_failure_watchlist.png").exists()
    assert (board_dir / "board_plan_tradeoff.png").exists()
    summary_text = (board_dir / "workspace_board_summary.json").read_text(encoding="utf-8")
    assert '"optimize_plan_count"' in summary_text
    plans_text = (board_dir / "workspace_board_plans.csv").read_text(encoding="utf-8")
    assert "optimize" in plans_text


def test_serve_command_smoke(toy_spec_path, tmp_path: Path):
    workspace = tmp_path / "workspace"
    baseline = runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(workspace)])
    assert baseline.exit_code == 0
    result = runner.invoke(
        app,
        [
            "serve",
            str(workspace),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--refresh",
            "--duration-seconds",
            "0.1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert "Serving StressLab API at http://127.0.0.1:" in result.stdout


def test_doctor_command_builds_preflight_report(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "doctor"
    result = runner.invoke(app, ["doctor", str(workspace), "--output-dir", str(output_dir)])
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    doctor_dir = created[0]
    assert (doctor_dir / "doctor_checks.csv").exists()
    assert (doctor_dir / "doctor_summary.json").exists()
    assert (doctor_dir / "doctor_report.html").exists()
    summary_text = (doctor_dir / "doctor_summary.json").read_text(encoding="utf-8")
    assert '"ready_for_container_build"' in summary_text
    assert '"checks"' in summary_text


def test_evaluate_command_builds_replication_study(toy_spec_path, tmp_path: Path):
    output_dir = tmp_path / "evaluations"
    result = runner.invoke(
        app,
        [
            "evaluate",
            str(toy_spec_path),
            "--replicates",
            "3",
            "--intervention-id",
            "add_capacity",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    eval_dir = created[0]
    assert (eval_dir / "replicate_metrics.csv").exists()
    assert (eval_dir / "paired_deltas.csv").exists()
    assert (eval_dir / "evaluation_metric_summary.csv").exists()
    assert (eval_dir / "evaluation_summary.json").exists()
    assert (eval_dir / "treatment_plan.json").exists()
    assert (eval_dir / "evaluation_distributions.png").exists()
    assert (eval_dir / "evaluation_deltas.png").exists()
    assert (eval_dir / "evaluation_failures.png").exists()
    assert (eval_dir / "evaluation_report.html").exists()
    summary_text = (eval_dir / "evaluation_summary.json").read_text(encoding="utf-8")
    assert '"replicate_count": 3' in summary_text
    assert "add_capacity" in summary_text


def test_casebook_command_builds_evidence_report(toy_spec_path, tmp_path: Path):
    output_dir = tmp_path / "casebooks"
    result = runner.invoke(
        app,
        [
            "casebook",
            str(toy_spec_path),
            "--replicates",
            "2",
            "--budget",
            "100",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    casebook_dir = created[0]
    assert (casebook_dir / "casebook_summary.csv").exists()
    assert (casebook_dir / "casebook_summary.json").exists()
    assert (casebook_dir / "casebook_report.html").exists()
    assert (casebook_dir / "casebook_resilience.png").exists()
    assert (casebook_dir / "casebook_failure_reduction.png").exists()
    assert any(path.is_dir() for path in casebook_dir.iterdir())


def test_bundle_and_restore_commands_round_trip(toy_spec_path, tmp_path: Path):
    workspace = tmp_path / "workspace"
    baseline = runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(workspace)])
    assert baseline.exit_code == 0
    run_dir = next(path for path in workspace.iterdir() if path.is_dir())

    bundles_root = tmp_path / "bundles"
    bundle_result = runner.invoke(
        app,
        [
            "bundle",
            str(run_dir),
            "--output-dir",
            str(bundles_root),
            "--include-registry",
        ],
    )
    assert bundle_result.exit_code == 0
    bundle_paths = list(bundles_root.glob("*.zip"))
    assert bundle_paths
    bundle_path = bundle_paths[0]
    with zipfile.ZipFile(bundle_path) as archive:
        members = set(archive.namelist())
    assert "bundle_manifest.json" in members
    assert "artifact/baseline_result.json" in members
    assert "registry/.stresslab_registry.csv" in members

    restored_root = tmp_path / "restored"
    restore_result = runner.invoke(
        app,
        ["restore", str(bundle_path), "--output-dir", str(restored_root)],
    )
    assert restore_result.exit_code == 0
    restored_dirs = [path for path in restored_root.iterdir() if path.is_dir()]
    assert restored_dirs
    restored_dir = restored_dirs[0]
    assert (restored_dir / "baseline_result.json").exists()
    assert (restored_dir / "report.html").exists()
    assert (restored_dir / "bundle_restore.json").exists()
    assert (restored_root / ".stresslab_registry.csv").exists()


def test_workspace_registry_tracks_shared_artifacts(toy_spec_path, tmp_path: Path):
    workspace = tmp_path / "workspace"
    baseline = runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(workspace)])
    assert baseline.exit_code == 0
    optimize_result = runner.invoke(
        app,
        ["optimize", str(toy_spec_path), "--budget", "100", "--output-dir", str(workspace)],
    )
    assert optimize_result.exit_code == 0
    run_dirs = sorted(path for path in workspace.iterdir() if path.is_dir())
    compare_result = runner.invoke(
        app,
        ["compare", str(run_dirs[0]), str(run_dirs[1]), "--output-dir", str(workspace)],
    )
    assert compare_result.exit_code == 0

    manifest_path = tmp_path / "registry_campaign.yml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "name": "registry_campaign",
                "jobs": [
                    {
                        "id": "batch_run",
                        "command": "run",
                        "spec_path": str(toy_spec_path),
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    batch_result = runner.invoke(app, ["batch", str(manifest_path), "--output-dir", str(workspace)])
    assert batch_result.exit_code == 0

    registry_csv = workspace / ".stresslab_registry.csv"
    registry_json = workspace / ".stresslab_registry.json"
    assert registry_csv.exists()
    assert registry_json.exists()
    with registry_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    analysis_types = {row["analysis_type"] for row in rows}
    assert {"run", "optimize", "comparison", "batch"}.issubset(analysis_types)


def test_optimize_can_expand_generated_policies(tmp_path: Path):
    output_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "optimize",
            "examples/markets/liquidity_withdrawal.yml",
            "--expand-policies",
            "--policy-only",
            "--budget",
            "300",
            "--fairness-weight",
            "0.5",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    run_dir = created[0]
    assert (run_dir / "intervention_catalog.csv").exists()
    catalog_text = (run_dir / "intervention_catalog.csv").read_text(encoding="utf-8")
    assert "generated_policy" in catalog_text
    assert "policy_fifo__order_gateway" in catalog_text


def test_optimize_can_select_dynamic_policy_candidates(tmp_path: Path):
    output_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "optimize",
            "examples/healthcare/ed_basic.yml",
            "--expand-dynamic-policies",
            "--dynamic-only",
            "--budget",
            "400",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    run_dir = created[0]
    assert (run_dir / "intervention_catalog.csv").exists()
    assert (run_dir / "policy_schedule.csv").exists()
    assert (run_dir / "policy_schedule.png").exists()
    catalog_text = (run_dir / "intervention_catalog.csv").read_text(encoding="utf-8")
    schedule_text = (run_dir / "policy_schedule.csv").read_text(encoding="utf-8")
    assert "generated_dynamic_policy" in catalog_text
    assert "timed_" in catalog_text
    assert "generated_dynamic_policy" in schedule_text


def test_optimize_can_select_adaptive_policy_candidates(tmp_path: Path):
    output_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "optimize",
            "examples/healthcare/ed_basic.yml",
            "--expand-adaptive-policies",
            "--adaptive-only",
            "--budget",
            "500",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    run_dir = created[0]
    assert (run_dir / "intervention_catalog.csv").exists()
    assert (run_dir / "policy_schedule.csv").exists()
    catalog_text = (run_dir / "intervention_catalog.csv").read_text(encoding="utf-8")
    schedule_text = (run_dir / "policy_schedule.csv").read_text(encoding="utf-8")
    assert "generated_adaptive_policy" in catalog_text
    assert "threshold_" in catalog_text
    assert "routing_bias_ladder" in catalog_text
    assert "threshold" in schedule_text


def test_optimize_can_select_controller_bundles(tmp_path: Path):
    output_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "optimize",
            "examples/healthcare/ed_basic.yml",
            "--expand-adaptive-policies",
            "--expand-controller-bundles",
            "--bundle-only",
            "--budget",
            "900",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    run_dir = created[0]
    catalog_text = (run_dir / "intervention_catalog.csv").read_text(encoding="utf-8")
    assert "generated_bundle" in catalog_text
    assert "controller_bundle__" in catalog_text
    assert "bundle_members" in catalog_text


def test_optimize_can_select_hierarchical_playbooks(tmp_path: Path):
    output_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "optimize",
            "examples/healthcare/ed_basic.yml",
            "--expand-adaptive-policies",
            "--expand-controller-bundles",
            "--expand-hierarchical-playbooks",
            "--playbook-only",
            "--budget",
            "1200",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    run_dir = created[0]
    assert (run_dir / "bundle_hierarchy.csv").exists()
    catalog_text = (run_dir / "intervention_catalog.csv").read_text(encoding="utf-8")
    hierarchy_text = (run_dir / "bundle_hierarchy.csv").read_text(encoding="utf-8")
    optimization_text = (run_dir / "optimization.json").read_text(encoding="utf-8")
    assert "generated_playbook" in catalog_text
    assert "hierarchical_playbook__" in catalog_text
    assert "bundle_depth" in catalog_text
    assert "root_bundle_id" in hierarchy_text
    assert "hierarchical_playbook_count" in optimization_text


def test_benchmark_command_builds_leaderboard_artifacts(tmp_path: Path):
    output_dir = tmp_path / "runs"
    result = runner.invoke(app, ["benchmark", "--suite", "starter", "--output-dir", str(output_dir)])
    assert result.exit_code == 0
    created = [path for path in output_dir.iterdir() if path.is_dir()]
    assert created
    run_dir = created[0]
    assert (run_dir / "benchmark_summary.csv").exists()
    assert (run_dir / "benchmark_leaderboard.png").exists()
    assert (run_dir / "benchmark_tradeoff.png").exists()
    summary_text = (run_dir / "benchmark_summary.csv").read_text(encoding="utf-8")
    assert "regime_plan_cluster_coverage_rate" in summary_text
    assert "regime_detection_accuracy" in summary_text
    assert "online_regime_detection_accuracy" in summary_text
    assert "response_timing_latest_high_value_fraction" in summary_text
    assert "closed_loop_regime_deployment_accuracy" in summary_text
    assert "controller_candidate_count" in summary_text
    assert "controller_frontier_count" in summary_text
    assert "controller_monitoring_burden_score" in summary_text
