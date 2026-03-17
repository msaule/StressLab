"""Typer-powered CLI for StressLab."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated, TypeVar

import pandas as pd
import typer

from stresslab.campaigns import (
    build_artifact_bundle,
    build_casebook,
    build_comparison_artifacts,
    build_doctor_report,
    build_evaluation_study,
    build_run_catalog,
    build_workspace_board,
    build_workspace_status,
    execute_batch_campaign,
    restore_artifact_bundle,
    upsert_registry_entry,
)
from stresslab.config import DEFAULT_OUTPUT_ROOT
from stresslab.des import Simulator
from stresslab.discovery import build_discovery_artifacts
from stresslab.explain import attribute_failure, counterfactuals
from stresslab.generator import (
    SUPPORTED_TOPOLOGIES,
    SyntheticGenerationConfig,
    build_generation_artifacts,
)
from stresslab.models import BenchmarkRecord, BenchmarkSummary
from stresslab.optimize import Optimizer, apply_interventions
from stresslab.optimize.policy_catalog import (
    bundle_hierarchy_rows,
    expand_intervention_catalog,
    intervention_catalog_rows,
)
from stresslab.reports import build_report
from stresslab.research import build_research_artifacts, build_theory_artifacts
from stresslab.search import Searcher
from stresslab.service import serve_workspace_api
from stresslab.systemspec import load_spec, resolve_spec, validate_spec
from stresslab.utils import (
    ensure_directory,
    make_run_dir,
    runtime_metadata,
    write_dataframe,
    write_json,
    write_yaml,
)
from stresslab.viz import create_standard_plots, plot_benchmark_leaderboard, plot_benchmark_tradeoff

app = typer.Typer(help="StressLab: adversarial resilience testing for operational networks.")
T = TypeVar("T")

BUNDLE_OUTPUT_OPTION = typer.Option(
    None,
    help="Directory where the bundle zip should be written. Defaults next to the run directory.",
)
BUNDLE_PATH_OPTION = typer.Option(
    None,
    help="Optional explicit bundle zip path. If omitted, StressLab derives one from the run directory name.",
)
INCLUDE_REGISTRY_OPTION = typer.Option(
    False,
    help="Include workspace registry files alongside the artifact bundle for handoff context.",
)
RESTORE_OUTPUT_OPTION = typer.Option(
    Path("runs"),
    help="Workspace directory where the bundled artifact should be restored.",
)
RESTORE_REGISTRY_OPTION = typer.Option(
    None,
    help="Optional registry root to update after restore. Defaults to the restore output directory.",
)


def _top_n_nodes(spec) -> int:
    return getattr(spec.report, "top_n_nodes", 3)


def _registry_base(*, output_dir: Path | None, registry_root: Path | None) -> Path:
    """Resolve the workspace root used for registry updates."""

    return Path(registry_root or output_dir or DEFAULT_OUTPUT_ROOT)


def _validate_shards(*, shard_count: int, shard_index: int) -> None:
    if shard_count < 1:
        raise typer.BadParameter("shard_count must be at least 1.")
    if shard_index < 0 or shard_index >= shard_count:
        raise typer.BadParameter("shard_index must be between 0 and shard_count - 1.")


def _shard_bounds(total: int, *, shard_count: int, shard_index: int) -> tuple[int, int]:
    base = total // shard_count
    remainder = total % shard_count
    start = shard_index * base + min(shard_index, remainder)
    size = base + (1 if shard_index < remainder else 0)
    return start, size


def _slice_for_shard(items: list[T], *, shard_count: int, shard_index: int) -> list[T]:
    start, size = _shard_bounds(len(items), shard_count=shard_count, shard_index=shard_index)
    return items[start : start + size]


@app.command()
def validate(spec_path: Path) -> None:
    """Validate a SystemSpec YAML file."""

    spec = load_spec(spec_path)
    validation = validate_spec(spec)
    typer.echo(f"Spec: {spec.system.name}")
    typer.echo(f"Nodes: {len(spec.nodes)} | Edges: {len(spec.edges)} | Arrivals: {len(spec.arrivals)}")
    for warning in validation.warnings:
        typer.echo(f"warning: {warning}")
    if not validation.valid:
        for error in validation.errors:
            typer.echo(f"error: {error}")
        raise typer.Exit(code=1)
    typer.echo("Validation passed.")


@app.command()
def generate(
    count: int = typer.Option(24, help="Number of synthetic systems to generate."),
    topology_type: str = typer.Option(
        "mixed",
        help="Topology family: mixed, random_queue, scale_free, small_world, hierarchical_supply, market_microstructure.",
    ),
    min_nodes: int = typer.Option(6, help="Minimum node count per generated system."),
    max_nodes: int = typer.Option(16, help="Maximum node count per generated system."),
    seed: int = typer.Option(7, help="Deterministic base seed for generation."),
    batch_size: int = typer.Option(250, help="Batch size for generation bookkeeping."),
    horizon: float = typer.Option(360.0, help="Simulation horizon in minutes for generated systems."),
    shard_count: int = typer.Option(1, help="Total number of deterministic generation shards."),
    shard_index: int = typer.Option(0, help="Zero-based shard index for this generation run."),
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Generate synthetic queue/flow/dependency networks as valid SystemSpec YAML files."""

    start = time.perf_counter()
    if topology_type not in SUPPORTED_TOPOLOGIES:
        raise typer.BadParameter(f"Unsupported topology_type '{topology_type}'.")
    _validate_shards(shard_count=shard_count, shard_index=shard_index)
    start_index, shard_size = _shard_bounds(count, shard_count=shard_count, shard_index=shard_index)
    run_dir = make_run_dir("synthetic_systems", "generate", root=output_dir)
    summary = build_generation_artifacts(
        run_dir,
        config=SyntheticGenerationConfig(
            count=shard_size,
            topology_type=topology_type,
            min_nodes=min_nodes,
            max_nodes=max_nodes,
            seed=seed,
            batch_size=batch_size,
            horizon=horizon,
            start_index=start_index,
            shard_count=shard_count,
            shard_index=shard_index,
        ),
    )
    write_json(
        run_dir / "metadata.json",
        runtime_metadata(
            command=(
                f"stresslab generate --count {count} --topology-type {topology_type} "
                f"--shard-count {shard_count} --shard-index {shard_index}"
            ),
            system_name=f"synthetic_{topology_type}",
            seed=seed,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), run_dir)
    typer.echo(f"Generation complete: {run_dir}")
    typer.echo(
        f"systems={summary.system_count} topology={summary.topology_type} "
        f"shard={shard_index + 1}/{shard_count}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def discover(
    source_dir: Annotated[
        Path | None,
        typer.Option(
            help="Optional directory of existing SystemSpec YAML files. If omitted, StressLab generates synthetic systems first.",
        ),
    ] = None,
    count: int = typer.Option(24, help="Number of synthetic systems to generate when source_dir is omitted."),
    topology_type: str = typer.Option(
        "mixed",
        help="Topology family for generated discovery systems.",
    ),
    min_nodes: int = typer.Option(6, help="Minimum node count for generated systems."),
    max_nodes: int = typer.Option(16, help="Maximum node count for generated systems."),
    seed: int = typer.Option(7, help="Deterministic base seed for generation and search."),
    batch_size: int = typer.Option(100, help="Batch size for discovery dataset checkpointing."),
    worst_case_budget: float | None = typer.Option(
        None,
        help="Optional fixed budget for worst-case discovery search.",
    ),
    shard_count: int = typer.Option(1, help="Total number of deterministic discovery shards."),
    shard_index: int = typer.Option(0, help="Zero-based shard index for this discovery run."),
    workers: int = typer.Option(1, help="Number of worker processes for per-system discovery execution."),
    resume_run_dir: Annotated[
        Path | None,
        typer.Option(help="Optional existing discovery run directory to resume in place."),
    ] = None,
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Generate systems, run collapse searches, and assemble a discovery dataset."""

    start = time.perf_counter()
    if topology_type not in SUPPORTED_TOPOLOGIES:
        raise typer.BadParameter(f"Unsupported topology_type '{topology_type}'.")
    _validate_shards(shard_count=shard_count, shard_index=shard_index)
    run_dir = ensure_directory(resume_run_dir) if resume_run_dir is not None else make_run_dir("discovery", "discover", root=output_dir)
    spec_paths: list[Path] | None = None
    if source_dir is not None:
        spec_paths = sorted(Path(source_dir).rglob("*.yml"))
        if not spec_paths:
            raise typer.BadParameter(f"No YAML specs found under '{source_dir}'.")
        spec_paths = _slice_for_shard(spec_paths, shard_count=shard_count, shard_index=shard_index)
    summary = build_discovery_artifacts(
        run_dir,
        spec_paths=spec_paths,
        generation_config=(
            None
            if spec_paths is not None
            else SyntheticGenerationConfig(
                count=_shard_bounds(count, shard_count=shard_count, shard_index=shard_index)[1],
                topology_type=topology_type,
                min_nodes=min_nodes,
                max_nodes=max_nodes,
                seed=seed,
                batch_size=batch_size,
                start_index=_shard_bounds(count, shard_count=shard_count, shard_index=shard_index)[0],
                shard_count=shard_count,
                shard_index=shard_index,
            )
        ),
        worst_case_budget=worst_case_budget,
        batch_size=batch_size,
        workers=workers,
        resume=resume_run_dir is not None,
    )
    write_json(
        run_dir / "metadata.json",
        runtime_metadata(
            command=(
                f"stresslab discover --workers {workers} "
                f"--shard-count {shard_count} --shard-index {shard_index}"
            ),
            system_name="discovery_campaign",
            seed=seed,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), run_dir)
    typer.echo(f"Discovery complete: {run_dir}")
    typer.echo(
        f"systems={summary.generated_system_count} rows={summary.dataset_row_count} "
        f"topologies={summary.topology_type_counts} shard={shard_index + 1}/{shard_count}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def theory(
    dataset_source: Path,
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Analyze discovery datasets for collapse laws, thresholds, and warnings."""

    start = time.perf_counter()
    run_dir = make_run_dir("theory", "theory", root=output_dir)
    summary = build_theory_artifacts(dataset_source, output_dir=run_dir)
    write_json(
        run_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab theory {dataset_source}",
            system_name="theory_analysis",
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), run_dir)
    typer.echo(f"Theory complete: {run_dir}")
    typer.echo(
        f"fragility_models={summary.fragility_model_count} law_candidates={summary.law_candidate_count}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def research(
    dataset_source: Path,
    output_dir: Path | None = None,
    theory_dir: Annotated[
        Path | None,
        typer.Option(help="Optional existing theory-analysis directory to reuse."),
    ] = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Produce publication-style research artifacts from discovery datasets."""

    start = time.perf_counter()
    run_dir = make_run_dir("research", "research", root=output_dir)
    summary = build_research_artifacts(dataset_source, output_dir=run_dir, theory_dir=theory_dir)
    write_json(
        run_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab research {dataset_source}",
            system_name="research_report",
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), run_dir)
    typer.echo(f"Research complete: {run_dir}")
    typer.echo(f"figures={summary.figure_count} theory_dir={summary.theory_dir}")
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def run(
    spec_path: Path,
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Run a baseline simulation and build a report."""

    start = time.perf_counter()
    spec = load_spec(spec_path)
    resolved = resolve_spec(spec)
    run_dir = make_run_dir(spec.system.name, "run", root=output_dir)
    simulator = Simulator(resolved, seed=spec.seed)
    result = simulator.run(run_id="baseline", artifacts_dir=run_dir, capture_events=True)
    plots = create_standard_plots(
        resolved_spec=resolved,
        simulator=simulator,
        result=result,
        output_dir=run_dir,
        top_n=_top_n_nodes(spec),
    )
    result = result.model_copy(update={"plots": plots, "artifacts_dir": str(run_dir)})
    attribution = attribute_failure(result)
    write_yaml(run_dir / "spec_resolved.yaml", spec.model_dump(mode="json", by_alias=True))
    write_json(run_dir / "baseline_result.json", result)
    write_json(run_dir / "attribution.json", attribution)
    write_json(
        run_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab run {spec_path}",
            system_name=spec.system.name,
            seed=spec.seed,
            execution_duration=time.perf_counter() - start,
        ),
    )
    report_paths = build_report(run_dir)
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), run_dir)
    typer.echo(f"Run complete: {run_dir}")
    typer.echo(
        f"failure={result.failure_triggered} throughput={result.metrics.get('throughput', 0.0):.3f} "
        f"mean_wait={result.metrics.get('mean_wait', 0.0):.3f}"
    )
    typer.echo(f"Report: {report_paths.html}")


@app.command()
def search(
    spec_path: Path,
    objective: str = typer.Option("min_failure", help="min_failure or worst_case"),
    budget: float | None = typer.Option(None, help="Budget for worst_case search."),
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Run adversarial search and build a report."""

    start = time.perf_counter()
    spec = load_spec(spec_path)
    run_dir = make_run_dir(spec.system.name, objective, root=output_dir)
    searcher = Searcher(spec, objective=objective, seed=spec.seed)
    if objective == "min_failure":
        search_result = searcher.find_min_failure()
    elif objective == "worst_case":
        effective_budget = budget if budget is not None else (spec.search.budget or 1.0)
        search_result = searcher.find_worst_case(effective_budget)
    else:
        raise typer.BadParameter("objective must be 'min_failure' or 'worst_case'")
    scenario_spec, simulator, scenario_result = searcher.replay_best(search_result)
    scenario_result = simulator.run(run_id="scenario", artifacts_dir=run_dir, capture_events=True)
    resolved = resolve_spec(scenario_spec)
    plots = create_standard_plots(
        resolved_spec=resolved,
        simulator=simulator,
        result=scenario_result,
        output_dir=run_dir,
        search_history=searcher.history,
        top_n=_top_n_nodes(spec),
    )
    scenario_result = scenario_result.model_copy(update={"plots": plots, "artifacts_dir": str(run_dir)})
    attribution = attribute_failure(scenario_result)
    write_yaml(run_dir / "spec_resolved.yaml", scenario_spec.model_dump(mode="json", by_alias=True))
    write_json(run_dir / "baseline_result.json", searcher.baseline_result)
    write_json(run_dir / "scenario_result.json", scenario_result)
    search_result = search_result.model_copy(
        update={
            "result_paths": {
                "run_dir": str(run_dir),
                "search_history": str(run_dir / "search_history.csv"),
                "report_html": str(run_dir / "report.html"),
                "report_markdown": str(run_dir / "report.md"),
                "scenario_spec": str(run_dir / "spec_resolved.yaml"),
            }
        }
    )
    write_json(run_dir / "search_result.json", search_result)
    write_json(run_dir / "attribution.json", attribution)
    write_json(
        run_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab search {spec_path} --objective {objective}",
            system_name=spec.system.name,
            seed=spec.seed,
            execution_duration=time.perf_counter() - start,
        ),
    )
    write_dataframe(run_dir / "search_history.csv", pd.DataFrame(searcher.history))
    report_paths = build_report(run_dir)
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), run_dir)
    typer.echo(f"Search complete: {run_dir}")
    typer.echo(
        f"best_budget={search_result.best_shock_budget:.3f} damage={search_result.damage_score:.3f} "
        f"failure={search_result.failure_triggered}"
    )
    typer.echo(f"Report: {report_paths.html}")


@app.command()
def optimize(
    spec_path: Path,
    budget: float | None = None,
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
    robust: bool = typer.Option(False, help="Optimize across a portfolio of stress scenarios."),
    scenario_budget: float | None = typer.Option(
        None,
        help="Budget used to generate robust optimization scenarios.",
    ),
    scenario_samples: int = typer.Option(
        4,
        help="Number of additional random stress scenarios for robust optimization.",
    ),
    fairness_weight: float = typer.Option(
        0.0,
        help="Optional fairness weight for class-equity-aware optimization.",
    ),
    expand_policies: bool = typer.Option(
        False,
        help="Synthesize queue and routing policy candidates and add them to the intervention catalog.",
    ),
    expand_dynamic_policies: bool = typer.Option(
        False,
        help="Synthesize scheduled queue and routing policy candidates anchored to stress windows.",
    ),
    expand_adaptive_policies: bool = typer.Option(
        False,
        help="Synthesize threshold-triggered policy controllers from congestion signals.",
    ),
    expand_controller_bundles: bool = typer.Option(
        False,
        help="Synthesize coordinated controller bundles from adaptive policy candidates.",
    ),
    expand_hierarchical_playbooks: bool = typer.Option(
        False,
        help="Synthesize hierarchical playbooks that nest controller bundles with supporting controllers.",
    ),
    policy_only: bool = typer.Option(
        False,
        help="Optimize only synthesized policy candidates.",
    ),
    dynamic_only: bool = typer.Option(
        False,
        help="Optimize only synthesized dynamic policy candidates.",
    ),
    adaptive_only: bool = typer.Option(
        False,
        help="Optimize only synthesized adaptive policy candidates.",
    ),
    bundle_only: bool = typer.Option(
        False,
        help="Optimize only synthesized controller bundles.",
    ),
    playbook_only: bool = typer.Option(
        False,
        help="Optimize only synthesized hierarchical playbooks.",
    ),
) -> None:
    """Rank interventions and optionally select under budget."""

    start = time.perf_counter()
    original_spec = load_spec(spec_path)
    spec, intervention_catalog = expand_intervention_catalog(
        original_spec,
        expand_policies=expand_policies or policy_only,
        expand_dynamic_policies=expand_dynamic_policies or dynamic_only,
        expand_adaptive_policies=expand_adaptive_policies or adaptive_only,
        expand_controller_bundles=expand_controller_bundles or bundle_only,
        expand_hierarchical_playbooks=expand_hierarchical_playbooks or playbook_only,
        policy_only=policy_only,
        dynamic_only=dynamic_only,
        adaptive_only=adaptive_only,
        bundle_only=bundle_only,
        playbook_only=playbook_only,
    )
    resolved = resolve_spec(spec)
    run_dir = make_run_dir(spec.system.name, "optimize", root=output_dir)
    baseline_simulator = Simulator(resolved, seed=spec.seed)
    baseline_result = baseline_simulator.run(run_id="baseline", artifacts_dir=run_dir, capture_events=True)
    optimizer = Optimizer(spec, baseline_result)
    if robust:
        optimization_result = optimizer.rank_interventions_robust(
            budget=budget,
            scenario_budget=scenario_budget,
            random_samples=scenario_samples,
            fairness_weight=fairness_weight,
        )
    else:
        optimization_result = optimizer.rank_interventions(
            budget=budget,
            fairness_weight=fairness_weight,
        )
    scenario_summary_frame = pd.DataFrame()
    scenario_clusters_frame = pd.DataFrame()
    cluster_summary_frame = pd.DataFrame()
    intervention_coverage_frame = pd.DataFrame()
    portfolio_candidates_frame = pd.DataFrame()
    portfolio_cluster_coverage_frame = pd.DataFrame()
    cluster_response_plan_frame = pd.DataFrame()
    regime_detection_frame = pd.DataFrame()
    regime_detection_confusion_frame = pd.DataFrame()
    online_regime_frame = pd.DataFrame()
    online_regime_horizon_frame = pd.DataFrame()
    response_timing_frame = pd.DataFrame()
    closed_loop_regime_frame = pd.DataFrame()
    controller_policy_frame = pd.DataFrame()
    controller_frontier_frame = pd.DataFrame()
    intervention_catalog_frame = pd.DataFrame(intervention_catalog_rows(intervention_catalog))
    bundle_hierarchy_frame = pd.DataFrame(bundle_hierarchy_rows(intervention_catalog))
    if robust and optimizer.last_scenario_summaries:
        scenario_summary_frame = pd.DataFrame(
            [
                {
                    "scenario_id": summary.scenario_id,
                    "source": summary.source,
                    "shock_budget": summary.shock_budget,
                    "failure_triggered": summary.failure_triggered,
                    "damage_score": summary.damage_score,
                    "resilience_score": summary.metrics.get("resilience_score", 0.0),
                    "throughput": summary.metrics.get("throughput", 0.0),
                    "mean_wait": summary.metrics.get("mean_wait", 0.0),
                    "blocked_transfers": summary.metrics.get("blocked_transfers", 0.0),
                }
                for summary in optimizer.last_scenario_summaries
            ]
        )
    if robust and optimizer.last_scenario_clusters:
        scenario_clusters_frame = pd.DataFrame(
            [assignment.model_dump(mode="json") for assignment in optimizer.last_scenario_clusters]
        ).sort_values(["cluster_id", "damage_score"], ascending=[True, False])
    if robust and optimizer.last_cluster_summaries:
        cluster_summary_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_cluster_summaries]
        ).sort_values("cluster_id")
    if robust and optimizer.last_intervention_coverage:
        intervention_coverage_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_intervention_coverage]
        ).sort_values(["cluster_id", "coverage_score"], ascending=[True, False])
    if robust and optimizer.last_portfolio_candidates:
        portfolio_candidates_frame = pd.DataFrame(
            [candidate.model_dump(mode="json") for candidate in optimizer.last_portfolio_candidates]
        ).sort_values(
            ["objective_score", "cluster_coverage_rate", "failure_prevention_rate"],
            ascending=[False, False, False],
        )
    if robust and optimizer.last_portfolio_cluster_coverage:
        portfolio_cluster_coverage_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_portfolio_cluster_coverage]
        )
        if optimization_result.recommended_portfolio_id:
            portfolio_cluster_coverage_frame = portfolio_cluster_coverage_frame[
                portfolio_cluster_coverage_frame["portfolio_id"] == optimization_result.recommended_portfolio_id
            ].copy()
        portfolio_cluster_coverage_frame = portfolio_cluster_coverage_frame.sort_values(
            ["coverage_score", "cluster_id"],
            ascending=[False, True],
        )
    if robust and optimizer.last_cluster_response_plan:
        cluster_response_plan_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_cluster_response_plan]
        ).sort_values(
            ["covered", "coverage_score", "scenario_count"],
            ascending=[False, False, False],
        )
    if robust and optimizer.last_regime_detection_rows:
        regime_detection_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_regime_detection_rows]
        ).sort_values(
            ["true_cluster_id", "scenario_id"],
            ascending=[True, True],
        )
    if robust and optimizer.last_regime_detection_confusion:
        regime_detection_confusion_frame = pd.DataFrame(
            optimizer.last_regime_detection_confusion
        ).sort_values(
            ["true_cluster_id", "predicted_cluster_id"],
            ascending=[True, True],
        )
    if robust and optimizer.last_online_regime_rows:
        online_regime_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_online_regime_rows]
        ).sort_values(
            ["true_cluster_id", "scenario_id"],
            ascending=[True, True],
        )
    if robust and optimizer.last_online_regime_horizons:
        online_regime_horizon_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_online_regime_horizons]
        ).sort_values("observation_fraction")
    if robust and optimizer.last_response_timing_points:
        response_timing_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_response_timing_points]
        ).sort_values("deployment_fraction")
    if robust and optimizer.last_closed_loop_regime_rows:
        closed_loop_regime_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_closed_loop_regime_rows]
        ).sort_values(["true_cluster_id", "scenario_id"], ascending=[True, True])
    if robust and optimizer.last_controller_policy_candidates:
        controller_policy_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_controller_policy_candidates]
        ).sort_values(["objective_score", "deployment_accuracy"], ascending=[False, False])
    if robust and optimizer.last_controller_frontier:
        controller_frontier_frame = pd.DataFrame(
            [summary.model_dump(mode="json") for summary in optimizer.last_controller_frontier]
        ).sort_values(
            ["expected_resilience", "deployment_accuracy", "monitoring_burden_score"],
            ascending=[False, False, True],
        )

    scenario_spec = spec
    scenario_result = baseline_result
    scenario_simulator = baseline_simulator
    if optimization_result.selected_interventions:
        selected_interventions = [
            next(item for item in spec.interventions if item.id == selected.intervention_id)
            for selected in optimization_result.selected_interventions
        ]
        scenario_spec = apply_interventions(spec, selected_interventions)
        scenario_resolved = resolve_spec(scenario_spec)
        scenario_simulator = Simulator(
            scenario_resolved,
            seed=spec.seed,
            baseline_metrics=baseline_result.metrics,
        )
        scenario_result = scenario_simulator.run(run_id="scenario", artifacts_dir=run_dir, capture_events=True)
    plots = create_standard_plots(
        resolved_spec=resolve_spec(scenario_spec),
        simulator=scenario_simulator,
        result=scenario_result,
        output_dir=run_dir,
        optimization_result=optimization_result,
        scenario_cluster_frame=scenario_clusters_frame,
        intervention_coverage_frame=intervention_coverage_frame,
        portfolio_candidates_frame=portfolio_candidates_frame,
        cluster_response_plan_frame=cluster_response_plan_frame,
        regime_detection_confusion_frame=regime_detection_confusion_frame,
        online_regime_horizon_frame=online_regime_horizon_frame,
        response_timing_frame=response_timing_frame,
        closed_loop_regime_frame=closed_loop_regime_frame,
        controller_policy_frame=controller_policy_frame,
        controller_frontier_frame=controller_frontier_frame,
        top_n=_top_n_nodes(spec),
    )
    scenario_result = scenario_result.model_copy(update={"plots": plots, "artifacts_dir": str(run_dir)})
    attribution = attribute_failure(scenario_result)
    write_yaml(run_dir / "spec_resolved.yaml", scenario_spec.model_dump(mode="json", by_alias=True))
    write_json(run_dir / "baseline_result.json", baseline_result)
    write_json(run_dir / "scenario_result.json", scenario_result)
    write_json(run_dir / "attribution.json", attribution)
    roi_table = pd.DataFrame(
        [
            {
                "intervention_id": item.intervention_id,
                "label": item.label,
                "action_type": item.action_type,
                "target": item.target,
                "source": item.source,
                "generated": item.generated,
                "dynamic": item.dynamic,
                "policy_mode": item.policy_mode,
                "schedule_start": item.schedule_start,
                "schedule_duration": item.schedule_duration,
                "stage_count": item.stage_count,
                "bundle_size": item.bundle_size,
                "bundle_depth": item.bundle_depth,
                "trigger_metric": item.trigger_metric,
                "trigger_node": item.trigger_node,
                "trigger_threshold": item.trigger_threshold,
                "clear_threshold": item.clear_threshold,
                "cost": item.cost,
                "resilience_gain": item.resilience_gain,
                "roi": item.roi,
                "failure_prevented": item.failure_prevented,
                "fairness_gain": item.fairness_gain,
                "expected_resilience": item.expected_resilience,
                "worst_case_resilience": item.worst_case_resilience,
                "expected_fairness_score": item.expected_fairness_score,
                "worst_case_fairness_score": item.worst_case_fairness_score,
                "resilience_std": item.resilience_std,
                "failure_prevention_rate": item.failure_prevention_rate,
                "robust_score": item.robust_score,
                "evaluated_scenarios": item.evaluated_scenarios,
            }
            for item in optimization_result.ranked_interventions
        ]
    )
    write_dataframe(run_dir / "roi_table.csv", roi_table)
    write_dataframe(run_dir / "intervention_catalog.csv", intervention_catalog_frame)
    if not bundle_hierarchy_frame.empty:
        write_dataframe(run_dir / "bundle_hierarchy.csv", bundle_hierarchy_frame)
    if robust and not cluster_response_plan_frame.empty:
        write_dataframe(run_dir / "cluster_response_plan.csv", cluster_response_plan_frame)
        if optimizer.last_regime_plan_summary is not None:
            write_json(run_dir / "regime_plan_summary.json", optimizer.last_regime_plan_summary)
    if robust and not regime_detection_frame.empty:
        write_dataframe(run_dir / "regime_detection.csv", regime_detection_frame)
        write_dataframe(run_dir / "regime_detection_confusion.csv", regime_detection_confusion_frame)
        if optimizer.last_regime_detection_summary is not None:
            write_json(run_dir / "regime_detection_summary.json", optimizer.last_regime_detection_summary)
    if robust and not online_regime_frame.empty:
        write_dataframe(run_dir / "online_regime_detection.csv", online_regime_frame)
        write_dataframe(run_dir / "online_regime_horizons.csv", online_regime_horizon_frame)
        if optimizer.last_online_regime_summary is not None:
            write_json(run_dir / "online_regime_summary.json", optimizer.last_online_regime_summary)
    if robust and not response_timing_frame.empty:
        write_dataframe(run_dir / "response_timing.csv", response_timing_frame)
        if optimizer.last_response_timing_summary is not None:
            write_json(run_dir / "response_timing_summary.json", optimizer.last_response_timing_summary)
    if robust and not closed_loop_regime_frame.empty:
        write_dataframe(run_dir / "closed_loop_regime.csv", closed_loop_regime_frame)
        if optimizer.last_closed_loop_regime_summary is not None:
            write_json(run_dir / "closed_loop_regime_summary.json", optimizer.last_closed_loop_regime_summary)
    if robust and not controller_policy_frame.empty:
        write_dataframe(run_dir / "controller_policy_candidates.csv", controller_policy_frame)
        if optimizer.last_controller_tuning_summary is not None:
            write_json(run_dir / "controller_tuning_summary.json", optimizer.last_controller_tuning_summary)
    if robust and not controller_frontier_frame.empty:
        write_dataframe(run_dir / "controller_frontier.csv", controller_frontier_frame)
    frontier_ids = set(optimization_result.pareto_intervention_ids)
    frontier_frame = roi_table[roi_table["intervention_id"].isin(frontier_ids)].copy()
    write_dataframe(run_dir / "pareto_frontier.csv", frontier_frame)
    optimization_result = optimization_result.model_copy(
        update={
            "roi_table_path": str(run_dir / "roi_table.csv"),
            "intervention_catalog_path": str(run_dir / "intervention_catalog.csv"),
            "bundle_hierarchy_path": (
                str(run_dir / "bundle_hierarchy.csv")
                if not bundle_hierarchy_frame.empty
                else None
            ),
            "cluster_response_plan_path": (
                str(run_dir / "cluster_response_plan.csv")
                if robust and not cluster_response_plan_frame.empty
                else None
            ),
            "regime_plan_summary_path": (
                str(run_dir / "regime_plan_summary.json")
                if robust and optimizer.last_regime_plan_summary is not None
                else None
            ),
            "regime_detection_path": (
                str(run_dir / "regime_detection.csv")
                if robust and not regime_detection_frame.empty
                else None
            ),
            "regime_detection_confusion_path": (
                str(run_dir / "regime_detection_confusion.csv")
                if robust and not regime_detection_confusion_frame.empty
                else None
            ),
            "regime_detection_summary_path": (
                str(run_dir / "regime_detection_summary.json")
                if robust and optimizer.last_regime_detection_summary is not None
                else None
            ),
            "online_regime_detection_path": (
                str(run_dir / "online_regime_detection.csv")
                if robust and not online_regime_frame.empty
                else None
            ),
            "online_regime_horizons_path": (
                str(run_dir / "online_regime_horizons.csv")
                if robust and not online_regime_horizon_frame.empty
                else None
            ),
            "online_regime_summary_path": (
                str(run_dir / "online_regime_summary.json")
                if robust and optimizer.last_online_regime_summary is not None
                else None
            ),
            "response_timing_path": (
                str(run_dir / "response_timing.csv")
                if robust and not response_timing_frame.empty
                else None
            ),
            "response_timing_summary_path": (
                str(run_dir / "response_timing_summary.json")
                if robust and optimizer.last_response_timing_summary is not None
                else None
            ),
            "closed_loop_regime_path": (
                str(run_dir / "closed_loop_regime.csv")
                if robust and not closed_loop_regime_frame.empty
                else None
            ),
            "closed_loop_regime_summary_path": (
                str(run_dir / "closed_loop_regime_summary.json")
                if robust and optimizer.last_closed_loop_regime_summary is not None
                else None
            ),
            "controller_policy_candidates_path": (
                str(run_dir / "controller_policy_candidates.csv")
                if robust and not controller_policy_frame.empty
                else None
            ),
            "controller_frontier_path": (
                str(run_dir / "controller_frontier.csv")
                if robust and not controller_frontier_frame.empty
                else None
            ),
            "controller_tuning_summary_path": (
                str(run_dir / "controller_tuning_summary.json")
                if robust and optimizer.last_controller_tuning_summary is not None
                else None
            ),
            "pareto_frontier_path": str(run_dir / "pareto_frontier.csv"),
            "scenario_summary_path": (
                str(run_dir / "scenario_summary.csv")
                if robust and not scenario_summary_frame.empty
                else None
            ),
            "scenario_clusters_path": (
                str(run_dir / "scenario_clusters.csv")
                if robust and not scenario_clusters_frame.empty
                else None
            ),
            "cluster_summary_path": (
                str(run_dir / "cluster_summary.csv")
                if robust and not cluster_summary_frame.empty
                else None
            ),
            "intervention_coverage_path": (
                str(run_dir / "intervention_coverage.csv")
                if robust and not intervention_coverage_frame.empty
                else None
            ),
            "portfolio_candidates_path": (
                str(run_dir / "portfolio_candidates.csv")
                if robust and not portfolio_candidates_frame.empty
                else None
            ),
            "portfolio_cluster_coverage_path": (
                str(run_dir / "portfolio_cluster_coverage.csv")
                if robust and not portfolio_cluster_coverage_frame.empty
                else None
            ),
        }
    )
    write_json(run_dir / "optimization.json", optimization_result)
    if robust and not scenario_summary_frame.empty:
        write_dataframe(run_dir / "scenario_summary.csv", scenario_summary_frame)
        write_json(run_dir / "scenario_summary.json", optimizer.last_scenario_summaries)
    if robust and not scenario_clusters_frame.empty:
        write_dataframe(run_dir / "scenario_clusters.csv", scenario_clusters_frame)
        write_json(run_dir / "scenario_clusters.json", optimizer.last_scenario_clusters)
    if robust and not cluster_summary_frame.empty:
        write_dataframe(run_dir / "cluster_summary.csv", cluster_summary_frame)
        write_json(run_dir / "cluster_summary.json", optimizer.last_cluster_summaries)
    if robust and not intervention_coverage_frame.empty:
        write_dataframe(run_dir / "intervention_coverage.csv", intervention_coverage_frame)
        write_json(run_dir / "intervention_coverage.json", optimizer.last_intervention_coverage)
    if robust and not portfolio_candidates_frame.empty:
        write_dataframe(run_dir / "portfolio_candidates.csv", portfolio_candidates_frame)
        write_json(run_dir / "portfolio_candidates.json", optimizer.last_portfolio_candidates)
    if robust and not portfolio_cluster_coverage_frame.empty:
        write_dataframe(run_dir / "portfolio_cluster_coverage.csv", portfolio_cluster_coverage_frame)
        write_json(run_dir / "portfolio_cluster_coverage.json", portfolio_cluster_coverage_frame.to_dict("records"))
    write_json(
        run_dir / "counterfactuals.json",
        counterfactuals(baseline_result, optimization_result.ranked_interventions[:5]),
    )
    write_json(
        run_dir / "metadata.json",
        runtime_metadata(
            command=_optimize_command(
                spec_path,
                robust=robust,
                budget=budget,
                scenario_budget=scenario_budget,
                scenario_samples=scenario_samples,
                fairness_weight=fairness_weight,
                expand_policies=expand_policies,
                expand_dynamic_policies=expand_dynamic_policies,
                expand_adaptive_policies=expand_adaptive_policies,
                expand_controller_bundles=expand_controller_bundles,
                expand_hierarchical_playbooks=expand_hierarchical_playbooks,
                policy_only=policy_only,
                dynamic_only=dynamic_only,
                adaptive_only=adaptive_only,
                bundle_only=bundle_only,
                playbook_only=playbook_only,
            ),
            system_name=spec.system.name,
            seed=spec.seed,
            execution_duration=time.perf_counter() - start,
        ),
    )
    report_paths = build_report(run_dir)
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), run_dir)
    typer.echo(f"Optimization complete: {run_dir}")
    if optimization_result.ranked_interventions:
        best = optimization_result.ranked_interventions[0]
        typer.echo(
            f"top_intervention={best.intervention_id} roi={best.roi:.4f} "
            f"gain={best.resilience_gain:.4f}"
        )
        if robust:
            typer.echo(
                f"robust_expected={best.expected_resilience:.4f} "
                f"worst_case={best.worst_case_resilience:.4f} "
                f"scenarios={optimization_result.scenario_count}"
            )
            typer.echo(
                f"fairness={best.expected_fairness_score:.4f} "
                f"fairness_weight={optimization_result.fairness_weight:.2f}"
            )
            typer.echo(
                f"scenario_clusters={optimization_result.cluster_count} "
                f"coverage_rows={len(optimizer.last_intervention_coverage)}"
            )
            if optimization_result.recommended_portfolio_id:
                typer.echo(
                    f"portfolio={optimization_result.recommended_portfolio_id} "
                    f"portfolio_method={optimization_result.portfolio_method} "
                    f"cluster_coverage={optimization_result.portfolio_cluster_coverage_rate:.3f}"
                )
            if optimization_result.regime_plan_method:
                typer.echo(
                    f"regime_plan={optimization_result.regime_plan_method} "
                    f"standby_cost={optimization_result.regime_plan_standby_cost:.3f} "
                    f"regime_coverage={optimization_result.regime_plan_cluster_coverage_rate:.3f}"
                )
            if optimization_result.regime_detection_method:
                typer.echo(
                    f"regime_detection={optimization_result.regime_detection_method} "
                    f"accuracy={optimization_result.regime_detection_accuracy:.3f} "
                    f"regret={optimization_result.regime_detection_resilience_regret:.4f}"
                )
            if optimization_result.online_regime_detection_method:
                typer.echo(
                    f"online_regime={optimization_result.online_regime_detection_method} "
                    f"accuracy={optimization_result.online_regime_detection_accuracy:.3f} "
                    f"pre_degradation={optimization_result.online_regime_pre_degradation_rate:.3f}"
                )
            if optimization_result.response_timing_method:
                typer.echo(
                    f"response_timing={optimization_result.response_timing_method} "
                    f"best_fraction={optimization_result.response_timing_best_fraction:.2f} "
                    f"response_window={optimization_result.response_timing_latest_high_value_fraction:.2f} "
                    f"decay={optimization_result.response_timing_value_decay:.4f}"
                )
            if optimization_result.closed_loop_regime_method:
                typer.echo(
                    f"closed_loop={optimization_result.closed_loop_regime_method} "
                    f"deploy_accuracy={optimization_result.closed_loop_regime_deployment_accuracy:.3f} "
                    f"pre_degradation={optimization_result.closed_loop_regime_pre_degradation_rate:.3f} "
                    f"retarget_rate={optimization_result.closed_loop_regime_retarget_rate:.3f}"
                )
            if optimization_result.controller_tuning_method:
                typer.echo(
                    f"controller_tuning={optimization_result.controller_tuning_method} "
                    f"policy={optimization_result.controller_policy_id} "
                    f"schedule={optimization_result.controller_schedule_id} "
                    f"threshold={optimization_result.controller_confidence_threshold:.2f} "
                    f"confirm={optimization_result.controller_confirmation_count} "
                    f"start={optimization_result.controller_schedule_start_fraction:.2f} "
                    f"step={optimization_result.controller_schedule_interval_fraction:.2f} "
                    f"frontier={optimization_result.controller_frontier_count} "
                    f"burden={optimization_result.controller_monitoring_burden_score:.2f}"
                )
    if (
        expand_policies
        or policy_only
        or expand_dynamic_policies
        or dynamic_only
        or expand_adaptive_policies
        or adaptive_only
        or expand_controller_bundles
        or bundle_only
        or expand_hierarchical_playbooks
        or playbook_only
    ):
        typer.echo(
            f"candidate_count={optimization_result.candidate_count} "
            f"generated_policies={optimization_result.generated_policy_count} "
            f"dynamic_policies={optimization_result.dynamic_policy_count} "
            f"adaptive_policies={optimization_result.adaptive_policy_count} "
            f"bundles={optimization_result.bundle_candidate_count} "
            f"playbooks={optimization_result.hierarchical_playbook_count}"
        )
    typer.echo(f"Report: {report_paths.html}")


@app.command()
def report(run_dir: Path) -> None:
    """Rebuild markdown and HTML reports from artifacts."""

    report_paths = build_report(run_dir)
    typer.echo(f"Markdown: {report_paths.markdown}")
    typer.echo(f"HTML: {report_paths.html}")


@app.command()
def compare(
    run_dirs: list[Path],
    output_dir: Path | None = None,
    title: str = typer.Option("StressLab Comparison", help="Title used for the comparison report."),
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Compare multiple StressLab run directories and build a decision report."""

    start = time.perf_counter()
    if len(run_dirs) < 2:
        raise typer.BadParameter("compare requires at least two run directories.")
    compare_dir = make_run_dir("comparison", "compare", root=output_dir)
    summary = build_comparison_artifacts(run_dirs, output_dir=compare_dir, title=title)
    write_json(
        compare_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab compare {' '.join(str(run_dir) for run_dir in run_dirs)}",
            system_name=title,
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), compare_dir)
    typer.echo(f"Comparison complete: {compare_dir}")
    typer.echo(
        f"runs={summary.run_count} best_resilience={summary.best_resilience_run_id} "
        f"lowest_wait={summary.lowest_wait_run_id} highest_fairness={summary.highest_fairness_run_id}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def batch(
    manifest_path: Path,
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Execute a batch manifest and build campaign-level comparison artifacts."""

    start = time.perf_counter()
    batch_dir, summary = execute_batch_campaign(
        manifest_path,
        output_dir=output_dir,
        registry_root=_registry_base(output_dir=output_dir, registry_root=registry_root),
        runners={
            "run": run,
            "search": search,
            "optimize": optimize,
            "generate": generate,
            "discover": discover,
            "theory": theory,
            "research": research,
        },
    )
    write_json(
        batch_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab batch {manifest_path}",
            system_name=summary.campaign_name,
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), batch_dir)
    typer.echo(f"Batch complete: {batch_dir}")
    typer.echo(
        f"jobs={summary.total_jobs} completed={summary.completed_jobs} failed={summary.failed_jobs}"
    )
    if summary.comparison_report_html_path:
        typer.echo(f"Comparison report: {summary.comparison_report_html_path}")
    typer.echo(f"Batch report: {batch_dir / 'batch_report.html'}")


@app.command()
def catalog(
    root: Annotated[
        Path,
        typer.Argument(help="Workspace root to scan for StressLab artifacts."),
    ] = Path("runs"),
    output_dir: Path | None = None,
    title: str = typer.Option("StressLab Run Catalog", help="Title used for the catalog report."),
    analysis_type: str | None = typer.Option(None, help="Optional analysis type filter."),
    system_name: str | None = typer.Option(None, help="Optional system-name substring filter."),
    limit: int | None = typer.Option(None, help="Optional maximum number of entries to keep in the report."),
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Scan a workspace and build a catalog of discovered StressLab artifacts."""

    start = time.perf_counter()
    catalog_dir = make_run_dir("catalog", "catalog", root=output_dir)
    summary = build_run_catalog(
        root,
        output_dir=catalog_dir,
        title=title,
        analysis_type=analysis_type,
        system_name=system_name,
        limit=limit,
    )
    write_json(
        catalog_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab catalog {root}",
            system_name=title,
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), catalog_dir)
    typer.echo(f"Catalog complete: {catalog_dir}")
    typer.echo(
        f"entries={summary.entry_count} analysis_types={summary.analysis_type_counts} "
        f"systems={summary.system_counts}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def status(
    root: Annotated[
        Path,
        typer.Argument(help="Workspace root that stores StressLab artifacts."),
    ] = Path("runs"),
    output_dir: Path | None = None,
    title: str = typer.Option("StressLab Workspace Status", help="Title used for the workspace status report."),
    refresh: bool = typer.Option(
        False,
        help="Refresh the registry from disk before building the status snapshot.",
    ),
    limit: int | None = typer.Option(25, help="Maximum recent registry rows to include in the exported table."),
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Build a workspace status snapshot from the persistent registry."""

    start = time.perf_counter()
    status_dir = make_run_dir("workspace", "status", root=output_dir)
    summary = build_workspace_status(
        root,
        output_dir=status_dir,
        title=title,
        refresh=refresh,
        limit=limit,
    )
    write_json(
        status_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab status {root}",
            system_name=title,
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), status_dir)
    typer.echo(f"Status complete: {status_dir}")
    typer.echo(
        f"entries={summary.entry_count} unique_systems={summary.unique_system_count} "
        f"latest_type={summary.latest_analysis_type}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def board(
    root: Annotated[
        Path,
        typer.Argument(help="Workspace root that stores StressLab artifacts."),
    ] = Path("runs"),
    output_dir: Path | None = None,
    title: str = typer.Option("StressLab Workspace Board", help="Title used for the workspace board report."),
    refresh: bool = typer.Option(
        False,
        help="Refresh the registry from disk before building the board.",
    ),
    recent_limit: int = typer.Option(20, help="Number of recent entries to include."),
    watch_limit: int = typer.Option(12, help="Maximum number of entries on the failure watchlist."),
    plan_limit: int = typer.Option(12, help="Maximum number of optimize plans to show."),
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Build a decision dashboard from the workspace registry."""

    start = time.perf_counter()
    board_dir = make_run_dir("workspace", "board", root=output_dir)
    summary = build_workspace_board(
        root,
        output_dir=board_dir,
        title=title,
        refresh=refresh,
        recent_limit=recent_limit,
        watch_limit=watch_limit,
        plan_limit=plan_limit,
    )
    write_json(
        board_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab board {root}",
            system_name=title,
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), board_dir)
    typer.echo(f"Board complete: {board_dir}")
    typer.echo(
        f"entries={summary.entry_count} leaders={summary.system_leader_count} "
        f"watchlist={summary.failure_watch_count} plans={summary.optimize_plan_count}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def serve(
    root: Annotated[
        Path,
        typer.Argument(help="Workspace root that stores StressLab artifacts."),
    ] = Path("runs"),
    host: str = typer.Option("127.0.0.1", help="Host interface to bind."),
    port: int = typer.Option(8765, help="TCP port to bind. Use 0 for an ephemeral port."),
    refresh: bool = typer.Option(
        False,
        help="Refresh the workspace registry from disk before serving requests.",
    ),
    duration_seconds: float | None = typer.Option(
        None,
        help="Optional maximum runtime for smoke tests or scheduled sessions.",
    ),
    api_token: str | None = typer.Option(
        None,
        help="Optional bearer token required for non-public API endpoints.",
    ),
    quiet: bool = typer.Option(False, help="Suppress HTTP request logs."),
) -> None:
    """Serve a lightweight HTTP API over the workspace registry and artifacts."""

    if duration_seconds is not None and duration_seconds <= 0:
        raise typer.BadParameter("duration_seconds must be positive when provided.")
    start = time.perf_counter()
    typer.echo(f"Starting StressLab API for {root} on {host}:{port}...")
    base_url = serve_workspace_api(
        root,
        host=host,
        port=port,
        refresh=refresh,
        quiet=quiet,
        duration_seconds=duration_seconds,
        api_token=api_token,
    )
    typer.echo(f"Serving StressLab API at {base_url}")
    if duration_seconds is not None:
        typer.echo(f"Server stopped after {duration_seconds:.2f}s.")
    typer.echo(f"elapsed={time.perf_counter() - start:.3f}s")


@app.command()
def doctor(
    root: Annotated[
        Path,
        typer.Argument(help="Workspace root to inspect for deployment readiness."),
    ] = Path("runs"),
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Inspect local deployment readiness and write a doctor report artifact."""

    start = time.perf_counter()
    doctor_dir = make_run_dir("workspace", "doctor", root=output_dir)
    summary = build_doctor_report(root, output_dir=doctor_dir)
    write_json(
        doctor_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab doctor {root}",
            system_name="workspace_doctor",
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), doctor_dir)
    typer.echo(f"Doctor complete: {doctor_dir}")
    typer.echo(
        f"ready_for_container_build={summary.ready_for_container_build} "
        f"required_pass={summary.passing_required_checks} required_fail={summary.failing_required_checks}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def evaluate(
    spec_path: Path,
    replicates: Annotated[int, typer.Option(help="Number of paired baseline/scenario seed replications.")] = 8,
    seed_step: Annotated[int, typer.Option(help="Increment between replicate seeds.")] = 1,
    budget: float | None = None,
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
    robust: Annotated[bool, typer.Option(help="Select the treatment plan using robust optimization.")] = False,
    scenario_budget: Annotated[
        float | None,
        typer.Option(help="Budget used to generate robust optimization scenarios during plan selection."),
    ] = None,
    scenario_samples: Annotated[
        int,
        typer.Option(help="Number of additional random stress scenarios during robust plan selection."),
    ] = 4,
    fairness_weight: Annotated[
        float,
        typer.Option(help="Fairness weight applied during treatment-plan selection."),
    ] = 0.0,
    intervention_ids: Annotated[
        list[str] | None,
        typer.Option("--intervention-id", help="Explicit intervention ids to evaluate instead of selecting a plan."),
    ] = None,
    expand_policies: Annotated[
        bool,
        typer.Option(help="Synthesize queue and routing policy candidates before selecting a plan."),
    ] = False,
    expand_dynamic_policies: Annotated[
        bool,
        typer.Option(help="Synthesize scheduled policy candidates before selecting a plan."),
    ] = False,
    expand_adaptive_policies: Annotated[
        bool,
        typer.Option(help="Synthesize threshold-triggered policy candidates before selecting a plan."),
    ] = False,
    expand_controller_bundles: Annotated[
        bool,
        typer.Option(help="Synthesize controller bundles before selecting a plan."),
    ] = False,
    expand_hierarchical_playbooks: Annotated[
        bool,
        typer.Option(help="Synthesize hierarchical playbooks before selecting a plan."),
    ] = False,
    policy_only: Annotated[bool, typer.Option(help="Select plans only from synthesized policy candidates.")] = False,
    dynamic_only: Annotated[bool, typer.Option(help="Select plans only from synthesized dynamic policy candidates.")] = False,
    adaptive_only: Annotated[bool, typer.Option(help="Select plans only from synthesized adaptive policy candidates.")] = False,
    bundle_only: Annotated[bool, typer.Option(help="Select plans only from synthesized controller bundles.")] = False,
    playbook_only: Annotated[bool, typer.Option(help="Select plans only from synthesized hierarchical playbooks.")] = False,
) -> None:
    """Run a multi-seed evaluation study for a baseline/treatment pair."""

    start = time.perf_counter()
    spec = load_spec(spec_path)
    run_dir = make_run_dir(spec.system.name, "evaluate", root=output_dir)
    summary = build_evaluation_study(
        spec_path,
        output_dir=run_dir,
        replicates=replicates,
        seed_step=seed_step,
        budget=budget,
        robust=robust,
        scenario_budget=scenario_budget,
        scenario_samples=scenario_samples,
        fairness_weight=fairness_weight,
        intervention_ids=intervention_ids,
        expand_policies=expand_policies or policy_only,
        expand_dynamic_policies=expand_dynamic_policies or dynamic_only,
        expand_adaptive_policies=expand_adaptive_policies or adaptive_only,
        expand_controller_bundles=expand_controller_bundles or bundle_only,
        expand_hierarchical_playbooks=expand_hierarchical_playbooks or playbook_only,
        policy_only=policy_only,
        dynamic_only=dynamic_only,
        adaptive_only=adaptive_only,
        bundle_only=bundle_only,
        playbook_only=playbook_only,
    )
    write_json(
        run_dir / "metadata.json",
        runtime_metadata(
            command=_evaluate_command(
                spec_path,
                replicates=replicates,
                seed_step=seed_step,
                budget=budget,
                robust=robust,
                scenario_budget=scenario_budget,
                scenario_samples=scenario_samples,
                fairness_weight=fairness_weight,
                intervention_ids=intervention_ids or [],
                expand_policies=expand_policies,
                expand_dynamic_policies=expand_dynamic_policies,
                expand_adaptive_policies=expand_adaptive_policies,
                expand_controller_bundles=expand_controller_bundles,
                expand_hierarchical_playbooks=expand_hierarchical_playbooks,
                policy_only=policy_only,
                dynamic_only=dynamic_only,
                adaptive_only=adaptive_only,
                bundle_only=bundle_only,
                playbook_only=playbook_only,
            ),
            system_name=summary.system_name,
            seed=spec.seed,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), run_dir)
    typer.echo(f"Evaluation complete: {run_dir}")
    typer.echo(
        f"replicates={summary.replicate_count} baseline_failure={summary.baseline_failure_rate:.3f} "
        f"scenario_failure={summary.scenario_failure_rate:.3f}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def casebook(
    spec_paths: Annotated[
        list[Path] | None,
        typer.Argument(help="Optional spec paths to include in the casebook."),
    ] = None,
    suite: Annotated[str | None, typer.Option(help="Optional named suite such as 'starter'.")] = None,
    replicates: Annotated[int, typer.Option(help="Number of replications per study.")] = 4,
    seed_step: Annotated[int, typer.Option(help="Increment between replicate seeds.")] = 1,
    budget: float | None = None,
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
    robust: Annotated[bool, typer.Option(help="Select plans using robust optimization.")] = True,
    scenario_budget: Annotated[
        float | None,
        typer.Option(help="Budget used to generate robust optimization scenarios during plan selection."),
    ] = None,
    scenario_samples: Annotated[
        int,
        typer.Option(help="Number of additional random stress scenarios during robust plan selection."),
    ] = 4,
    fairness_weight: Annotated[float, typer.Option(help="Fairness weight used during plan selection.")] = 0.25,
    title: Annotated[str, typer.Option(help="Title used for the casebook report.")] = "StressLab Evidence Casebook",
) -> None:
    """Build an evidence casebook across multiple evaluation studies."""

    if suite is None and not spec_paths:
        raise typer.BadParameter("Provide at least one spec path or use --suite starter.")
    if suite is not None and suite != "starter":
        raise typer.BadParameter("Only the 'starter' suite is currently supported.")
    selected_paths = list(spec_paths or [])
    if suite == "starter":
        selected_paths.extend(
            [
                Path("examples/healthcare/ed_basic.yml"),
                Path("examples/supply_chain/two_supplier_port.yml"),
                Path("examples/markets/liquidity_withdrawal.yml"),
            ]
        )
    seen = set()
    ordered_paths: list[Path] = []
    for path in selected_paths:
        resolved = Path(path)
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            ordered_paths.append(resolved)

    start = time.perf_counter()
    casebook_dir = make_run_dir("casebook", suite or "custom", root=output_dir)
    summary = build_casebook(
        ordered_paths,
        output_dir=casebook_dir,
        title=title,
        suite=suite,
        replicates=replicates,
        seed_step=seed_step,
        budget=budget,
        robust=robust,
        scenario_budget=scenario_budget,
        scenario_samples=scenario_samples,
        fairness_weight=fairness_weight,
    )
    write_json(
        casebook_dir / "metadata.json",
        runtime_metadata(
            command=f"stresslab casebook {' '.join(str(path) for path in ordered_paths)}",
            system_name=title,
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), casebook_dir)
    typer.echo(f"Casebook complete: {casebook_dir}")
    typer.echo(
        f"records={summary.record_count} replicates={summary.replicate_count} suite={summary.suite or 'custom'}"
    )
    typer.echo(f"Report: {summary.report_html_path}")


@app.command()
def bundle(
    run_dir: Path,
    output_dir: Path | None = BUNDLE_OUTPUT_OPTION,
    bundle_path: Path | None = BUNDLE_PATH_OPTION,
    include_registry: bool = INCLUDE_REGISTRY_OPTION,
) -> None:
    """Package one StressLab artifact directory into a portable bundle zip."""

    summary = build_artifact_bundle(
        run_dir,
        output_dir=output_dir,
        bundle_path=bundle_path,
        include_registry=include_registry,
    )
    typer.echo(f"Bundle created: {summary.bundle_path}")
    typer.echo(
        f"run_id={summary.run_id} analysis_type={summary.analysis_type} "
        f"files={summary.file_count} include_registry={include_registry}"
    )


@app.command(name="restore")
def restore_bundle(
    bundle_path: Path,
    output_dir: Path = RESTORE_OUTPUT_OPTION,
    registry_root: Path | None = RESTORE_REGISTRY_OPTION,
) -> None:
    """Restore a portable StressLab bundle into a workspace and re-register it."""

    summary = restore_artifact_bundle(
        bundle_path,
        output_dir=output_dir,
        registry_root=registry_root,
    )
    typer.echo(f"Bundle restored: {summary.restored_run_dir}")
    typer.echo(
        f"source_run_id={summary.source_run_id} files={summary.restored_file_count} "
        f"collision_resolved={summary.collision_resolved}"
    )


@app.command()
def benchmark(
    suite: str = typer.Option("starter"),
    output_dir: Path | None = None,
    registry_root: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Run the starter benchmark suite."""

    if suite != "starter":
        raise typer.BadParameter("Only the 'starter' benchmark suite is available in v0.1.")
    start = time.perf_counter()
    example_paths = [
        Path("examples/healthcare/ed_basic.yml"),
        Path("examples/supply_chain/two_supplier_port.yml"),
        Path("examples/markets/liquidity_withdrawal.yml"),
    ]
    run_dir = make_run_dir("benchmarks", suite, root=output_dir)
    records: list[BenchmarkRecord] = []
    for path in example_paths:
        spec = load_spec(path)
        resolved = resolve_spec(spec)
        simulator = Simulator(resolved, seed=spec.seed)
        result = simulator.run(run_id=path.stem)
        search_result = Searcher(spec, objective="min_failure", seed=spec.seed).find_min_failure()
        optimizer = Optimizer(spec, result)
        benchmark_budget = sum(sorted(intervention.cost for intervention in spec.interventions)[:2]) if spec.interventions else 0.0
        optimization_result = optimizer.rank_interventions_robust(
            budget=benchmark_budget,
            scenario_budget=spec.search.budget,
            random_samples=3,
            fairness_weight=0.25,
        )
        records.append(
            BenchmarkRecord(
                scenario_id=path.as_posix(),
                metrics={
                    **result.metrics,
                    "min_failure_budget": search_result.best_shock_budget
                    if search_result.success
                    else float("inf"),
                    "search_damage_score": search_result.damage_score,
                    "robust_scenario_count": float(optimization_result.scenario_count),
                    "robust_cluster_count": float(optimization_result.cluster_count),
                    "portfolio_cluster_coverage_rate": optimization_result.portfolio_cluster_coverage_rate or 0.0,
                    "portfolio_intervention_count": float(len(optimization_result.selected_interventions)),
                    "regime_plan_standby_cost": optimization_result.regime_plan_standby_cost or 0.0,
                    "regime_plan_cluster_coverage_rate": optimization_result.regime_plan_cluster_coverage_rate or 0.0,
                    "regime_plan_expected_resilience": optimization_result.regime_plan_expected_resilience or 0.0,
                    "regime_detection_accuracy": optimization_result.regime_detection_accuracy or 0.0,
                    "regime_detection_resilience_regret": optimization_result.regime_detection_resilience_regret or 0.0,
                    "regime_detection_expected_resilience": (
                        optimization_result.regime_detection_expected_resilience or 0.0
                    ),
                    "online_regime_detection_accuracy": optimization_result.online_regime_detection_accuracy or 0.0,
                    "online_regime_resilience_regret": optimization_result.online_regime_resilience_regret or 0.0,
                    "online_regime_expected_resilience": optimization_result.online_regime_expected_resilience or 0.0,
                    "online_regime_pre_degradation_rate": (
                        optimization_result.online_regime_pre_degradation_rate or 0.0
                    ),
                    "response_timing_best_fraction": optimization_result.response_timing_best_fraction or 0.0,
                    "response_timing_latest_high_value_fraction": (
                        optimization_result.response_timing_latest_high_value_fraction or 0.0
                    ),
                    "response_timing_half_life_fraction": (
                        optimization_result.response_timing_half_life_fraction or 0.0
                    ),
                    "response_timing_best_resilience": (
                        optimization_result.response_timing_best_resilience or 0.0
                    ),
                    "response_timing_value_decay": optimization_result.response_timing_value_decay or 0.0,
                    "closed_loop_regime_prediction_accuracy": (
                        optimization_result.closed_loop_regime_prediction_accuracy or 0.0
                    ),
                    "closed_loop_regime_deployment_accuracy": (
                        optimization_result.closed_loop_regime_deployment_accuracy or 0.0
                    ),
                    "closed_loop_regime_expected_resilience": (
                        optimization_result.closed_loop_regime_expected_resilience or 0.0
                    ),
                    "closed_loop_regime_pre_degradation_rate": (
                        optimization_result.closed_loop_regime_pre_degradation_rate or 0.0
                    ),
                    "closed_loop_regime_retarget_rate": (
                        optimization_result.closed_loop_regime_retarget_rate or 0.0
                    ),
                    "closed_loop_regime_resilience_regret": (
                        optimization_result.closed_loop_regime_resilience_regret or 0.0
                    ),
                    "controller_candidate_count": float(optimization_result.controller_candidate_count),
                    "controller_tuning_scenario_count": float(optimization_result.controller_tuning_scenario_count),
                    "controller_confidence_threshold": (
                        optimization_result.controller_confidence_threshold or 0.0
                    ),
                    "controller_confirmation_count": float(
                        optimization_result.controller_confirmation_count or 0
                    ),
                    "controller_schedule_start_fraction": (
                        optimization_result.controller_schedule_start_fraction or 0.0
                    ),
                    "controller_schedule_interval_fraction": (
                        optimization_result.controller_schedule_interval_fraction or 0.0
                    ),
                    "controller_schedule_growth": optimization_result.controller_schedule_growth or 0.0,
                    "controller_schedule_observation_limit": float(
                        optimization_result.controller_schedule_observation_limit or 0
                    ),
                    "controller_mean_observation_count": (
                        optimization_result.controller_mean_observation_count or 0.0
                    ),
                    "controller_mean_deployment_count": (
                        optimization_result.controller_mean_deployment_count or 0.0
                    ),
                    "controller_monitoring_burden_score": (
                        optimization_result.controller_monitoring_burden_score or 0.0
                    ),
                    "controller_frontier_count": float(optimization_result.controller_frontier_count),
                    "controller_search_rounds": float(optimization_result.controller_search_rounds),
                    "top_intervention_expected_fairness": (
                        optimization_result.ranked_interventions[0].expected_fairness_score or 0.0
                        if optimization_result.ranked_interventions
                        else 0.0
                    ),
                    "top_intervention_expected_resilience": (
                        optimization_result.ranked_interventions[0].expected_resilience or 0.0
                        if optimization_result.ranked_interventions
                        else 0.0
                    ),
                    "top_cluster_coverage_score": max(
                        (
                            item.coverage_score
                            for item in optimizer.last_intervention_coverage
                        ),
                        default=0.0,
                    ),
                },
                status=result.status,
                artifacts_dir=str(run_dir),
            )
        )
    summary = BenchmarkSummary(suite=suite, records=records, summary_table_path=str(run_dir / "benchmark_summary.csv"))
    frame = pd.DataFrame(
        [
            {
                "scenario_id": record.scenario_id,
                "status": record.status,
                "throughput": record.metrics.get("throughput", 0.0),
                "mean_wait": record.metrics.get("mean_wait", 0.0),
                "recovery_time": record.metrics.get("recovery_time", 0.0),
                "blocked_transfers": record.metrics.get("blocked_transfers", 0.0),
                "min_failure_budget": record.metrics.get("min_failure_budget", 0.0),
                "search_damage_score": record.metrics.get("search_damage_score", 0.0),
                "robust_scenario_count": record.metrics.get("robust_scenario_count", 0.0),
                "robust_cluster_count": record.metrics.get("robust_cluster_count", 0.0),
                "portfolio_cluster_coverage_rate": record.metrics.get("portfolio_cluster_coverage_rate", 0.0),
                "portfolio_intervention_count": record.metrics.get("portfolio_intervention_count", 0.0),
                "regime_plan_standby_cost": record.metrics.get("regime_plan_standby_cost", 0.0),
                "regime_plan_cluster_coverage_rate": record.metrics.get("regime_plan_cluster_coverage_rate", 0.0),
                "regime_plan_expected_resilience": record.metrics.get("regime_plan_expected_resilience", 0.0),
                "regime_detection_accuracy": record.metrics.get("regime_detection_accuracy", 0.0),
                "regime_detection_resilience_regret": record.metrics.get("regime_detection_resilience_regret", 0.0),
                "regime_detection_expected_resilience": record.metrics.get(
                    "regime_detection_expected_resilience",
                    0.0,
                ),
                "online_regime_detection_accuracy": record.metrics.get("online_regime_detection_accuracy", 0.0),
                "online_regime_resilience_regret": record.metrics.get("online_regime_resilience_regret", 0.0),
                "online_regime_expected_resilience": record.metrics.get("online_regime_expected_resilience", 0.0),
                "online_regime_pre_degradation_rate": record.metrics.get(
                    "online_regime_pre_degradation_rate",
                    0.0,
                ),
                "response_timing_best_fraction": record.metrics.get("response_timing_best_fraction", 0.0),
                "response_timing_latest_high_value_fraction": record.metrics.get(
                    "response_timing_latest_high_value_fraction",
                    0.0,
                ),
                "response_timing_half_life_fraction": record.metrics.get(
                    "response_timing_half_life_fraction",
                    0.0,
                ),
                "response_timing_best_resilience": record.metrics.get("response_timing_best_resilience", 0.0),
                "response_timing_value_decay": record.metrics.get("response_timing_value_decay", 0.0),
                "closed_loop_regime_prediction_accuracy": record.metrics.get(
                    "closed_loop_regime_prediction_accuracy",
                    0.0,
                ),
                "closed_loop_regime_deployment_accuracy": record.metrics.get(
                    "closed_loop_regime_deployment_accuracy",
                    0.0,
                ),
                "closed_loop_regime_expected_resilience": record.metrics.get(
                    "closed_loop_regime_expected_resilience",
                    0.0,
                ),
                "closed_loop_regime_pre_degradation_rate": record.metrics.get(
                    "closed_loop_regime_pre_degradation_rate",
                    0.0,
                ),
                "closed_loop_regime_retarget_rate": record.metrics.get(
                    "closed_loop_regime_retarget_rate",
                    0.0,
                ),
                "closed_loop_regime_resilience_regret": record.metrics.get(
                    "closed_loop_regime_resilience_regret",
                    0.0,
                ),
                "controller_candidate_count": record.metrics.get("controller_candidate_count", 0.0),
                "controller_tuning_scenario_count": record.metrics.get("controller_tuning_scenario_count", 0.0),
                "controller_confidence_threshold": record.metrics.get("controller_confidence_threshold", 0.0),
                "controller_confirmation_count": record.metrics.get("controller_confirmation_count", 0.0),
                "controller_schedule_start_fraction": record.metrics.get("controller_schedule_start_fraction", 0.0),
                "controller_schedule_interval_fraction": record.metrics.get("controller_schedule_interval_fraction", 0.0),
                "controller_schedule_growth": record.metrics.get("controller_schedule_growth", 0.0),
                "controller_schedule_observation_limit": record.metrics.get("controller_schedule_observation_limit", 0.0),
                "controller_mean_observation_count": record.metrics.get("controller_mean_observation_count", 0.0),
                "controller_mean_deployment_count": record.metrics.get("controller_mean_deployment_count", 0.0),
                "controller_monitoring_burden_score": record.metrics.get(
                    "controller_monitoring_burden_score",
                    0.0,
                ),
                "controller_frontier_count": record.metrics.get("controller_frontier_count", 0.0),
                "controller_search_rounds": record.metrics.get("controller_search_rounds", 0.0),
                "fairness_score": record.metrics.get("fairness_score", 0.0),
                "top_intervention_expected_fairness": record.metrics.get(
                    "top_intervention_expected_fairness",
                    0.0,
                ),
                "top_intervention_expected_resilience": record.metrics.get(
                    "top_intervention_expected_resilience",
                    0.0,
                ),
                "top_cluster_coverage_score": record.metrics.get("top_cluster_coverage_score", 0.0),
                "resilience_score": record.metrics.get("resilience_score", 0.0),
            }
            for record in records
        ]
    )
    frame["benchmark_score"] = _benchmark_score(frame)
    frame["fragility_rank"] = frame["min_failure_budget"].rank(method="min", ascending=False)
    frame["resilience_rank"] = frame["resilience_score"].rank(method="min", ascending=False)
    frame["intervention_rank"] = frame["top_intervention_expected_resilience"].rank(
        method="min",
        ascending=False,
    )
    write_dataframe(run_dir / "benchmark_summary.csv", frame)
    write_json(run_dir / "benchmark_summary.json", summary)
    plot_benchmark_leaderboard(frame, run_dir / "benchmark_leaderboard.png")
    plot_benchmark_tradeoff(frame, run_dir / "benchmark_tradeoff.png")
    _write_benchmark_report(run_dir, frame)
    write_json(
        run_dir / "metadata.json",
        runtime_metadata(
            command="stresslab benchmark --suite starter",
            system_name="benchmark_suite",
            seed=0,
            execution_duration=time.perf_counter() - start,
        ),
    )
    upsert_registry_entry(_registry_base(output_dir=output_dir, registry_root=registry_root), run_dir)
    typer.echo(f"Benchmark complete: {run_dir}")
    typer.echo(frame.to_string(index=False))


def _write_benchmark_report(run_dir: Path, frame: pd.DataFrame) -> None:
    ordered = frame.sort_values("benchmark_score", ascending=False)
    markdown_lines = [
        "# StressLab Benchmark Suite",
        "",
        _frame_to_markdown(ordered),
        "",
        "![Benchmark Leaderboard](benchmark_leaderboard.png)",
        "",
        "![Benchmark Tradeoff](benchmark_tradeoff.png)",
        "",
    ]
    (run_dir / "benchmark_report.md").write_text("\n".join(markdown_lines), encoding="utf-8")
    html = [
        "<html><body><h1>StressLab Benchmark Suite</h1>",
        ordered.to_html(index=False, border=0),
        "<h2>Leaderboard</h2><img src='benchmark_leaderboard.png' style='max-width: 100%;'>",
        "<h2>Tradeoff</h2><img src='benchmark_tradeoff.png' style='max-width: 100%;'>",
        "</body></html>",
    ]
    (run_dir / "benchmark_report.html").write_text("\n".join(html), encoding="utf-8")


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def _optimize_command(
    spec_path: Path,
    *,
    robust: bool,
    budget: float | None,
    scenario_budget: float | None,
    scenario_samples: int,
    fairness_weight: float,
    expand_policies: bool,
    expand_dynamic_policies: bool,
    expand_adaptive_policies: bool,
    expand_controller_bundles: bool,
    expand_hierarchical_playbooks: bool,
    policy_only: bool,
    dynamic_only: bool,
    adaptive_only: bool,
    bundle_only: bool,
    playbook_only: bool,
) -> str:
    parts = ["stresslab", "optimize", str(spec_path)]
    if robust:
        parts.append("--robust")
        if scenario_budget is not None:
            parts.extend(["--scenario-budget", str(scenario_budget)])
        parts.extend(["--scenario-samples", str(scenario_samples)])
    if budget is not None:
        parts.extend(["--budget", str(budget)])
    if fairness_weight:
        parts.extend(["--fairness-weight", str(fairness_weight)])
    if expand_policies:
        parts.append("--expand-policies")
    if expand_dynamic_policies:
        parts.append("--expand-dynamic-policies")
    if expand_adaptive_policies:
        parts.append("--expand-adaptive-policies")
    if expand_controller_bundles:
        parts.append("--expand-controller-bundles")
    if expand_hierarchical_playbooks:
        parts.append("--expand-hierarchical-playbooks")
    if policy_only:
        parts.append("--policy-only")
    if dynamic_only:
        parts.append("--dynamic-only")
    if adaptive_only:
        parts.append("--adaptive-only")
    if bundle_only:
        parts.append("--bundle-only")
    if playbook_only:
        parts.append("--playbook-only")
    return " ".join(parts)


def _evaluate_command(
    spec_path: Path,
    *,
    replicates: int,
    seed_step: int,
    budget: float | None,
    robust: bool,
    scenario_budget: float | None,
    scenario_samples: int,
    fairness_weight: float,
    intervention_ids: list[str],
    expand_policies: bool,
    expand_dynamic_policies: bool,
    expand_adaptive_policies: bool,
    expand_controller_bundles: bool,
    expand_hierarchical_playbooks: bool,
    policy_only: bool,
    dynamic_only: bool,
    adaptive_only: bool,
    bundle_only: bool,
    playbook_only: bool,
) -> str:
    parts = ["stresslab", "evaluate", str(spec_path), "--replicates", str(replicates), "--seed-step", str(seed_step)]
    if budget is not None:
        parts.extend(["--budget", str(budget)])
    if robust:
        parts.append("--robust")
    if scenario_budget is not None:
        parts.extend(["--scenario-budget", str(scenario_budget)])
    if scenario_samples != 4:
        parts.extend(["--scenario-samples", str(scenario_samples)])
    if fairness_weight:
        parts.extend(["--fairness-weight", str(fairness_weight)])
    for intervention_id in intervention_ids:
        parts.extend(["--intervention-id", intervention_id])
    if expand_policies:
        parts.append("--expand-policies")
    if expand_dynamic_policies:
        parts.append("--expand-dynamic-policies")
    if expand_adaptive_policies:
        parts.append("--expand-adaptive-policies")
    if expand_controller_bundles:
        parts.append("--expand-controller-bundles")
    if expand_hierarchical_playbooks:
        parts.append("--expand-hierarchical-playbooks")
    if policy_only:
        parts.append("--policy-only")
    if dynamic_only:
        parts.append("--dynamic-only")
    if adaptive_only:
        parts.append("--adaptive-only")
    if bundle_only:
        parts.append("--bundle-only")
    if playbook_only:
        parts.append("--playbook-only")
    return " ".join(parts)


def _benchmark_score(frame: pd.DataFrame) -> pd.Series:
    def normalize(series: pd.Series, *, higher_is_better: bool) -> pd.Series:
        values = series.astype(float)
        minimum = values.min()
        maximum = values.max()
        if abs(maximum - minimum) <= 1e-9:
            return pd.Series([1.0] * len(values), index=values.index)
        normalized = (values - minimum) / (maximum - minimum)
        return normalized if higher_is_better else 1.0 - normalized

    fragility = normalize(frame["min_failure_budget"], higher_is_better=True)
    resilience = normalize(frame["resilience_score"], higher_is_better=True)
    wait = normalize(frame["mean_wait"], higher_is_better=False)
    fairness = normalize(frame["fairness_score"], higher_is_better=True)
    intervention = normalize(frame["top_intervention_expected_resilience"], higher_is_better=True)
    detection = normalize(
        frame.get("regime_detection_accuracy", pd.Series([0.0] * len(frame))),
        higher_is_better=True,
    )
    detection_regret = normalize(
        frame.get("regime_detection_resilience_regret", pd.Series([0.0] * len(frame))),
        higher_is_better=False,
    )
    online_detection = normalize(
        frame.get("online_regime_detection_accuracy", pd.Series([0.0] * len(frame))),
        higher_is_better=True,
    )
    online_regret = normalize(
        frame.get("online_regime_resilience_regret", pd.Series([0.0] * len(frame))),
        higher_is_better=False,
    )
    pre_degradation = normalize(
        frame.get("online_regime_pre_degradation_rate", pd.Series([0.0] * len(frame))),
        higher_is_better=True,
    )
    response_window = normalize(
        frame.get("response_timing_latest_high_value_fraction", pd.Series([0.0] * len(frame))),
        higher_is_better=True,
    )
    response_decay = normalize(
        frame.get("response_timing_value_decay", pd.Series([0.0] * len(frame))),
        higher_is_better=False,
    )
    closed_loop_deploy = normalize(
        frame.get("closed_loop_regime_deployment_accuracy", pd.Series([0.0] * len(frame))),
        higher_is_better=True,
    )
    closed_loop_regret = normalize(
        frame.get("closed_loop_regime_resilience_regret", pd.Series([0.0] * len(frame))),
        higher_is_better=False,
    )
    closed_loop_pre = normalize(
        frame.get("closed_loop_regime_pre_degradation_rate", pd.Series([0.0] * len(frame))),
        higher_is_better=True,
    )
    coverage_signal = (
        frame["top_cluster_coverage_score"].astype(float)
        + frame.get("portfolio_cluster_coverage_rate", pd.Series([0.0] * len(frame))).astype(float)
        + frame.get("regime_plan_cluster_coverage_rate", pd.Series([0.0] * len(frame))).astype(float)
    ) / 3.0
    coverage = normalize(coverage_signal, higher_is_better=True)
    return (
        0.20 * fragility
        + 0.20 * resilience
        + 0.10 * wait
        + 0.15 * fairness
        + 0.12 * intervention
        + 0.14 * coverage
        + 0.06 * detection
        + 0.03 * detection_regret
        + 0.05 * online_detection
        + 0.03 * online_regret
        + 0.02 * pre_degradation
        + 0.03 * response_window
        + 0.03 * response_decay
        + 0.03 * closed_loop_deploy
        + 0.02 * closed_loop_regret
        + 0.02 * closed_loop_pre
    )


if __name__ == "__main__":  # pragma: no cover
    app()
