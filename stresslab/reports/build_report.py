"""Markdown and HTML report generation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stresslab.models import ReportPaths


def build_report(run_artifact_dir: Path) -> ReportPaths:
    """Build markdown and HTML reports from artifact files."""

    run_dir = Path(run_artifact_dir)
    baseline = _load_json(run_dir / "baseline_result.json")
    scenario = _load_json(run_dir / "scenario_result.json")
    primary = scenario or baseline
    search = _load_json(run_dir / "search_result.json")
    optimization = _load_json(run_dir / "optimization.json")
    attribution = _load_json(run_dir / "attribution.json")
    counterfactuals = _load_json(run_dir / "counterfactuals.json")
    regime_plan_summary = _load_json(run_dir / "regime_plan_summary.json")
    regime_detection_summary = _load_json(run_dir / "regime_detection_summary.json")
    online_regime_summary = _load_json(run_dir / "online_regime_summary.json")
    response_timing_summary = _load_json(run_dir / "response_timing_summary.json")
    closed_loop_regime_summary = _load_json(run_dir / "closed_loop_regime_summary.json")
    controller_tuning_summary = _load_json(run_dir / "controller_tuning_summary.json")
    metadata = _load_json(run_dir / "metadata.json")
    metrics_frame = _load_csv(run_dir / "metrics.csv")
    node_metrics_frame = _load_csv(run_dir / "node_metrics.csv")
    edge_metrics_frame = _load_csv(run_dir / "edge_metrics.csv")
    class_metrics_frame = _load_csv(run_dir / "class_metrics.csv")
    policy_schedule_frame = _load_csv(run_dir / "policy_schedule.csv")
    intervention_catalog_frame = _load_csv(run_dir / "intervention_catalog.csv")
    bundle_hierarchy_frame = _load_csv(run_dir / "bundle_hierarchy.csv")
    cluster_response_plan_frame = _load_csv(run_dir / "cluster_response_plan.csv")
    regime_detection_frame = _load_csv(run_dir / "regime_detection.csv")
    regime_detection_confusion_frame = _load_csv(run_dir / "regime_detection_confusion.csv")
    online_regime_frame = _load_csv(run_dir / "online_regime_detection.csv")
    online_regime_horizon_frame = _load_csv(run_dir / "online_regime_horizons.csv")
    response_timing_frame = _load_csv(run_dir / "response_timing.csv")
    closed_loop_regime_frame = _load_csv(run_dir / "closed_loop_regime.csv")
    controller_policy_frame = _load_csv(run_dir / "controller_policy_candidates.csv")
    controller_frontier_frame = _load_csv(run_dir / "controller_frontier.csv")
    scenario_summary_frame = _load_csv(run_dir / "scenario_summary.csv")
    scenario_clusters_frame = _load_csv(run_dir / "scenario_clusters.csv")
    cluster_summary_frame = _load_csv(run_dir / "cluster_summary.csv")
    intervention_coverage_frame = _load_csv(run_dir / "intervention_coverage.csv")
    portfolio_candidates_frame = _load_csv(run_dir / "portfolio_candidates.csv")
    portfolio_cluster_coverage_frame = _load_csv(run_dir / "portfolio_cluster_coverage.csv")
    pareto_frontier_frame = _load_csv(run_dir / "pareto_frontier.csv")
    comparison_frame = _comparison_frame(baseline, primary)
    plots = {
        path.stem: str(path)
        for path in sorted(run_dir.glob("*.png"))
    }
    markdown = _build_markdown(
        baseline=baseline,
        primary=primary,
        search=search,
        optimization=optimization,
        attribution=attribution,
        counterfactuals=counterfactuals,
        regime_plan_summary=regime_plan_summary,
        regime_detection_summary=regime_detection_summary,
        online_regime_summary=online_regime_summary,
        response_timing_summary=response_timing_summary,
        closed_loop_regime_summary=closed_loop_regime_summary,
        controller_tuning_summary=controller_tuning_summary,
        metadata=metadata,
        metrics_frame=metrics_frame,
        node_metrics_frame=node_metrics_frame,
        edge_metrics_frame=edge_metrics_frame,
        class_metrics_frame=class_metrics_frame,
        policy_schedule_frame=policy_schedule_frame,
        intervention_catalog_frame=intervention_catalog_frame,
        bundle_hierarchy_frame=bundle_hierarchy_frame,
        cluster_response_plan_frame=cluster_response_plan_frame,
        regime_detection_frame=regime_detection_frame,
        regime_detection_confusion_frame=regime_detection_confusion_frame,
        online_regime_frame=online_regime_frame,
        online_regime_horizon_frame=online_regime_horizon_frame,
        response_timing_frame=response_timing_frame,
        closed_loop_regime_frame=closed_loop_regime_frame,
        controller_policy_frame=controller_policy_frame,
        controller_frontier_frame=controller_frontier_frame,
        scenario_summary_frame=scenario_summary_frame,
        scenario_clusters_frame=scenario_clusters_frame,
        cluster_summary_frame=cluster_summary_frame,
        intervention_coverage_frame=intervention_coverage_frame,
        portfolio_candidates_frame=portfolio_candidates_frame,
        portfolio_cluster_coverage_frame=portfolio_cluster_coverage_frame,
        pareto_frontier_frame=pareto_frontier_frame,
        comparison_frame=comparison_frame,
        plots=plots,
    )
    markdown_path = run_dir / "report.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path = run_dir / "report.html"
    html_path.write_text(
        _build_html(
            run_dir=run_dir,
            baseline=baseline,
            primary=primary,
            search=search,
            optimization=optimization,
            attribution=attribution,
            counterfactuals=counterfactuals,
            regime_plan_summary=regime_plan_summary,
            regime_detection_summary=regime_detection_summary,
            online_regime_summary=online_regime_summary,
            response_timing_summary=response_timing_summary,
            closed_loop_regime_summary=closed_loop_regime_summary,
            controller_tuning_summary=controller_tuning_summary,
            metadata=metadata,
            metrics_frame=metrics_frame,
            node_metrics_frame=node_metrics_frame,
            edge_metrics_frame=edge_metrics_frame,
            class_metrics_frame=class_metrics_frame,
            policy_schedule_frame=policy_schedule_frame,
            intervention_catalog_frame=intervention_catalog_frame,
            bundle_hierarchy_frame=bundle_hierarchy_frame,
            cluster_response_plan_frame=cluster_response_plan_frame,
            regime_detection_frame=regime_detection_frame,
            regime_detection_confusion_frame=regime_detection_confusion_frame,
            online_regime_frame=online_regime_frame,
            online_regime_horizon_frame=online_regime_horizon_frame,
            response_timing_frame=response_timing_frame,
            closed_loop_regime_frame=closed_loop_regime_frame,
            controller_policy_frame=controller_policy_frame,
            controller_frontier_frame=controller_frontier_frame,
            scenario_summary_frame=scenario_summary_frame,
            scenario_clusters_frame=scenario_clusters_frame,
            cluster_summary_frame=cluster_summary_frame,
            intervention_coverage_frame=intervention_coverage_frame,
            portfolio_candidates_frame=portfolio_candidates_frame,
            portfolio_cluster_coverage_frame=portfolio_cluster_coverage_frame,
            pareto_frontier_frame=pareto_frontier_frame,
            comparison_frame=comparison_frame,
            plots=plots,
        ),
        encoding="utf-8",
    )
    return ReportPaths(markdown=str(markdown_path), html=str(html_path), plots=plots)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _build_markdown(
    *,
    baseline: dict,
    primary: dict,
    search: dict,
    optimization: dict,
    attribution: dict,
    counterfactuals: list[dict],
    regime_plan_summary: dict,
    regime_detection_summary: dict,
    online_regime_summary: dict,
    response_timing_summary: dict,
    closed_loop_regime_summary: dict,
    controller_tuning_summary: dict,
    metadata: dict,
    metrics_frame: pd.DataFrame,
    node_metrics_frame: pd.DataFrame,
    edge_metrics_frame: pd.DataFrame,
    class_metrics_frame: pd.DataFrame,
    policy_schedule_frame: pd.DataFrame,
    intervention_catalog_frame: pd.DataFrame,
    bundle_hierarchy_frame: pd.DataFrame,
    cluster_response_plan_frame: pd.DataFrame,
    regime_detection_frame: pd.DataFrame,
    regime_detection_confusion_frame: pd.DataFrame,
    online_regime_frame: pd.DataFrame,
    online_regime_horizon_frame: pd.DataFrame,
    response_timing_frame: pd.DataFrame,
    closed_loop_regime_frame: pd.DataFrame,
    controller_policy_frame: pd.DataFrame,
    controller_frontier_frame: pd.DataFrame,
    scenario_summary_frame: pd.DataFrame,
    scenario_clusters_frame: pd.DataFrame,
    cluster_summary_frame: pd.DataFrame,
    intervention_coverage_frame: pd.DataFrame,
    portfolio_candidates_frame: pd.DataFrame,
    portfolio_cluster_coverage_frame: pd.DataFrame,
    pareto_frontier_frame: pd.DataFrame,
    comparison_frame: pd.DataFrame,
    plots: dict[str, str],
) -> str:
    lines = [
        f"# StressLab Report: {metadata.get('system_name', baseline.get('run_id', 'run'))}",
        "",
        "## Run Summary",
        "",
        f"- Timestamp: {metadata.get('timestamp', 'unknown')}",
        f"- Seed: {metadata.get('seed', primary.get('seed', baseline.get('seed', 'unknown')))}",
        f"- Command: `{metadata.get('command', 'stresslab run')}`",
        f"- Failure triggered: `{primary.get('failure_triggered', False)}`",
        "",
        "## Core Metrics",
        "",
        _frame_to_markdown(metrics_frame) if not metrics_frame.empty else "_No metrics available._",
        "",
    ]
    if not node_metrics_frame.empty:
        lines.extend(
            [
                "## Node Metrics",
                "",
                _frame_to_markdown(node_metrics_frame),
                "",
            ]
        )
    if not edge_metrics_frame.empty:
        lines.extend(
            [
                "## Edge Metrics",
                "",
                _frame_to_markdown(edge_metrics_frame),
                "",
            ]
        )
    if not class_metrics_frame.empty:
        lines.extend(
            [
                "## Class Metrics",
                "",
                _frame_to_markdown(class_metrics_frame),
                "",
            ]
        )
    if not policy_schedule_frame.empty:
        lines.extend(
            [
                "## Policy Schedule",
                "",
                _frame_to_markdown(policy_schedule_frame),
                "",
            ]
        )
    if not intervention_catalog_frame.empty:
        lines.extend(
            [
                "## Intervention Catalog",
                "",
                _frame_to_markdown(intervention_catalog_frame),
                "",
            ]
        )
    if not bundle_hierarchy_frame.empty:
        lines.extend(
            [
                "## Bundle Hierarchy",
                "",
                _frame_to_markdown(bundle_hierarchy_frame),
                "",
            ]
        )
    if not cluster_response_plan_frame.empty:
        lines.extend(
            [
                "## Cluster Response Plan",
                "",
                _frame_to_markdown(cluster_response_plan_frame),
                "",
            ]
        )
    if not regime_detection_frame.empty:
        lines.extend(
            [
                "## Regime Detection Outcomes",
                "",
                _frame_to_markdown(regime_detection_frame),
                "",
            ]
        )
    if not regime_detection_confusion_frame.empty:
        lines.extend(
            [
                "## Regime Detection Confusion",
                "",
                _frame_to_markdown(regime_detection_confusion_frame),
                "",
            ]
        )
    if not online_regime_frame.empty:
        lines.extend(
            [
                "## Online Regime Decisions",
                "",
                _frame_to_markdown(online_regime_frame),
                "",
            ]
        )
    if not online_regime_horizon_frame.empty:
        lines.extend(
            [
                "## Online Regime Horizons",
                "",
                _frame_to_markdown(online_regime_horizon_frame),
                "",
            ]
        )
    if not response_timing_frame.empty:
        lines.extend(
            [
                "## Response Timing",
                "",
                _frame_to_markdown(response_timing_frame),
                "",
            ]
        )
    if not closed_loop_regime_frame.empty:
        lines.extend(
            [
                "## Closed-Loop Regime Control",
                "",
                _frame_to_markdown(closed_loop_regime_frame),
                "",
            ]
        )
    if not controller_policy_frame.empty:
        lines.extend(
            [
                "## Controller Policy Candidates",
                "",
                _frame_to_markdown(controller_policy_frame),
                "",
            ]
        )
    if not controller_frontier_frame.empty:
        lines.extend(
            [
                "## Controller Frontier",
                "",
                _frame_to_markdown(controller_frontier_frame),
                "",
            ]
        )
    if not comparison_frame.empty:
        lines.extend(
            [
                "## Baseline vs Scenario",
                "",
                _frame_to_markdown(comparison_frame),
                "",
            ]
        )
    if not scenario_summary_frame.empty:
        lines.extend(
            [
                "## Robust Scenario Portfolio",
                "",
                _frame_to_markdown(scenario_summary_frame),
                "",
            ]
        )
    if not cluster_summary_frame.empty:
        lines.extend(
            [
                "## Scenario Families",
                "",
                _frame_to_markdown(cluster_summary_frame),
                "",
            ]
        )
    if not scenario_clusters_frame.empty:
        lines.extend(
            [
                "## Scenario Cluster Assignments",
                "",
                _frame_to_markdown(scenario_clusters_frame),
                "",
            ]
        )
    if not intervention_coverage_frame.empty:
        lines.extend(
            [
                "## Intervention Coverage",
                "",
                _frame_to_markdown(intervention_coverage_frame),
                "",
            ]
        )
    if not portfolio_candidates_frame.empty:
        lines.extend(
            [
                "## Portfolio Candidates",
                "",
                _frame_to_markdown(portfolio_candidates_frame),
                "",
            ]
        )
    if not portfolio_cluster_coverage_frame.empty:
        lines.extend(
            [
                "## Selected Portfolio Coverage",
                "",
                _frame_to_markdown(portfolio_cluster_coverage_frame),
                "",
            ]
        )
    if not pareto_frontier_frame.empty:
        lines.extend(
            [
                "## Pareto Frontier",
                "",
                _frame_to_markdown(pareto_frontier_frame),
                "",
            ]
        )
    if attribution:
        lines.extend(
            [
                "## Attribution",
                "",
                f"- First bottleneck: `{attribution.get('first_bottleneck')}`",
                f"- Dominant bottlenecks: {', '.join(attribution.get('dominant_bottlenecks', [])) or 'none'}",
                f"- Critical edges: {', '.join(attribution.get('critical_edges', [])) or 'none'}",
                f"- Recovery blockers: {', '.join(attribution.get('recovery_blockers', [])) or 'none'}",
                "",
                attribution.get("narrative_summary", ""),
                "",
            ]
        )
    if search:
        lines.extend(
            [
                "## Search",
                "",
                f"- Objective: `{search.get('objective')}`",
                f"- Best budget: `{search.get('best_shock_budget')}`",
                f"- Damage score: `{search.get('damage_score')}`",
                f"- Failure triggered: `{search.get('failure_triggered')}`",
                "",
                "Best shock vector:",
                "",
                "```yaml",
                json.dumps(search.get("best_shock_vector", {}), indent=2),
                "```",
                "",
            ]
        )
    if optimization:
        lines.extend(
            [
                "## Optimization",
                "",
                f"- Baseline resilience: `{optimization.get('baseline_resilience')}`",
                f"- Best resilience: `{optimization.get('best_resilience')}`",
                f"- Robust mode: `{optimization.get('robust_mode', False)}`",
                f"- Scenario count: `{optimization.get('scenario_count', 1)}`",
                f"- Cluster count: `{optimization.get('cluster_count', 0)}`",
                f"- Candidate count: `{optimization.get('candidate_count', 0)}`",
                f"- Generated policy count: `{optimization.get('generated_policy_count', 0)}`",
                f"- Dynamic policy count: `{optimization.get('dynamic_policy_count', 0)}`",
                f"- Adaptive policy count: `{optimization.get('adaptive_policy_count', 0)}`",
                f"- Bundle candidate count: `{optimization.get('bundle_candidate_count', 0)}`",
                f"- Hierarchical playbook count: `{optimization.get('hierarchical_playbook_count', 0)}`",
                f"- Fairness weight: `{optimization.get('fairness_weight', 0.0)}`",
                f"- Recommended portfolio: `{optimization.get('recommended_portfolio_id')}`",
                f"- Portfolio method: `{optimization.get('portfolio_method')}`",
                f"- Portfolio objective: `{optimization.get('portfolio_objective_score')}`",
                f"- Portfolio cluster coverage: `{optimization.get('portfolio_cluster_coverage_rate')}`",
                f"- Regime plan method: `{optimization.get('regime_plan_method')}`",
                f"- Regime plan standby cost: `{optimization.get('regime_plan_standby_cost')}`",
                f"- Regime plan coverage: `{optimization.get('regime_plan_cluster_coverage_rate')}`",
                f"- Regime plan expected resilience: `{optimization.get('regime_plan_expected_resilience')}`",
                f"- Regime detection method: `{optimization.get('regime_detection_method')}`",
                f"- Regime detection accuracy: `{optimization.get('regime_detection_accuracy')}`",
                f"- Regime detection expected resilience: `{optimization.get('regime_detection_expected_resilience')}`",
                f"- Regime detection resilience regret: `{optimization.get('regime_detection_resilience_regret')}`",
                f"- Online regime method: `{optimization.get('online_regime_detection_method')}`",
                f"- Online regime accuracy: `{optimization.get('online_regime_detection_accuracy')}`",
                f"- Online regime expected resilience: `{optimization.get('online_regime_expected_resilience')}`",
                f"- Online regime resilience regret: `{optimization.get('online_regime_resilience_regret')}`",
                f"- Online pre-degradation rate: `{optimization.get('online_regime_pre_degradation_rate')}`",
                f"- Response timing method: `{optimization.get('response_timing_method')}`",
                f"- Response timing best fraction: `{optimization.get('response_timing_best_fraction')}`",
                f"- Response timing response window: `{optimization.get('response_timing_latest_high_value_fraction')}`",
                f"- Response timing half-life: `{optimization.get('response_timing_half_life_fraction')}`",
                f"- Response timing value decay: `{optimization.get('response_timing_value_decay')}`",
                f"- Closed-loop regime method: `{optimization.get('closed_loop_regime_method')}`",
                f"- Closed-loop deployment accuracy: `{optimization.get('closed_loop_regime_deployment_accuracy')}`",
                f"- Closed-loop expected resilience: `{optimization.get('closed_loop_regime_expected_resilience')}`",
                f"- Closed-loop pre-degradation rate: `{optimization.get('closed_loop_regime_pre_degradation_rate')}`",
                f"- Closed-loop retarget rate: `{optimization.get('closed_loop_regime_retarget_rate')}`",
                f"- Closed-loop resilience regret: `{optimization.get('closed_loop_regime_resilience_regret')}`",
                f"- Controller tuning method: `{optimization.get('controller_tuning_method')}`",
                f"- Controller policy id: `{optimization.get('controller_policy_id')}`",
                f"- Controller schedule id: `{optimization.get('controller_schedule_id')}`",
                f"- Controller confidence threshold: `{optimization.get('controller_confidence_threshold')}`",
                f"- Controller confirmation count: `{optimization.get('controller_confirmation_count')}`",
                f"- Controller schedule start: `{optimization.get('controller_schedule_start_fraction')}`",
                f"- Controller schedule interval: `{optimization.get('controller_schedule_interval_fraction')}`",
                f"- Controller schedule growth: `{optimization.get('controller_schedule_growth')}`",
                f"- Controller observation limit: `{optimization.get('controller_schedule_observation_limit')}`",
                f"- Controller mean observations: `{optimization.get('controller_mean_observation_count')}`",
                f"- Controller mean deployments: `{optimization.get('controller_mean_deployment_count')}`",
                f"- Controller monitoring burden: `{optimization.get('controller_monitoring_burden_score')}`",
                f"- Controller allow retargeting: `{optimization.get('controller_allow_retargeting')}`",
                f"- Controller frontier count: `{optimization.get('controller_frontier_count')}`",
                f"- Controller search rounds: `{optimization.get('controller_search_rounds')}`",
                f"- Controller candidate count: `{optimization.get('controller_candidate_count')}`",
                "",
            ]
        )
        ranked = pd.DataFrame(optimization.get("ranked_interventions", []))
        if not ranked.empty:
            columns = [
                "intervention_id",
                "label",
                "action_type",
                "target",
                "source",
                "generated",
                "dynamic",
                "policy_mode",
                "schedule_start",
                "schedule_duration",
                "stage_count",
                "bundle_size",
                "bundle_depth",
                "trigger_metric",
                "trigger_node",
                "trigger_threshold",
                "clear_threshold",
                "cost",
                "resilience_gain",
                "roi",
                "failure_prevented",
            ]
            if optimization.get("robust_mode", False):
                columns.extend(
                    [
                        "expected_resilience",
                        "worst_case_resilience",
                        "fairness_gain",
                        "expected_fairness_score",
                        "worst_case_fairness_score",
                        "resilience_std",
                        "failure_prevention_rate",
                        "robust_score",
                        "evaluated_scenarios",
                    ]
                )
            columns = [column for column in columns if column in ranked.columns]
            lines.extend(
                [
                    _frame_to_markdown(ranked[columns]),
                    "",
                ]
            )
    if regime_plan_summary:
        regime_frame = pd.DataFrame([regime_plan_summary])
        lines.extend(
            [
                "## Regime Plan Summary",
                "",
                _frame_to_markdown(regime_frame),
                "",
            ]
        )
    if regime_detection_summary:
        detection_frame = pd.DataFrame([regime_detection_summary])
        lines.extend(
            [
                "## Regime Detection Summary",
                "",
                _frame_to_markdown(detection_frame),
                "",
            ]
        )
    if online_regime_summary:
        online_frame = pd.DataFrame([online_regime_summary])
        lines.extend(
            [
                "## Online Regime Summary",
                "",
                _frame_to_markdown(online_frame),
                "",
            ]
        )
    if response_timing_summary:
        timing_frame = pd.DataFrame([response_timing_summary])
        lines.extend(
            [
                "## Response Timing Summary",
                "",
                _frame_to_markdown(timing_frame),
                "",
            ]
        )
    if closed_loop_regime_summary:
        closed_loop_frame = pd.DataFrame([closed_loop_regime_summary])
        lines.extend(
            [
                "## Closed-Loop Regime Summary",
                "",
                _frame_to_markdown(closed_loop_frame),
                "",
            ]
        )
    if controller_tuning_summary:
        tuning_frame = pd.DataFrame([controller_tuning_summary])
        lines.extend(
            [
                "## Controller Tuning Summary",
                "",
                _frame_to_markdown(tuning_frame),
                "",
            ]
        )
    if counterfactuals:
        counterfactual_frame = pd.DataFrame(counterfactuals)
        if not counterfactual_frame.empty:
            lines.extend(
                [
                    "## Counterfactuals",
                    "",
                    _frame_to_markdown(counterfactual_frame),
                    "",
                ]
            )
    if plots:
        lines.append("## Plots")
        lines.append("")
        for label, plot_path in plots.items():
            lines.append(f"### {label.replace('_', ' ').title()}")
            lines.append("")
            lines.append(f"![{label}]({Path(plot_path).name})")
            lines.append("")
    return "\n".join(lines)


def _build_html(
    *,
    run_dir: Path,
    baseline: dict,
    primary: dict,
    search: dict,
    optimization: dict,
    attribution: dict,
    counterfactuals: list[dict],
    regime_plan_summary: dict,
    regime_detection_summary: dict,
    online_regime_summary: dict,
    response_timing_summary: dict,
    closed_loop_regime_summary: dict,
    controller_tuning_summary: dict,
    metadata: dict,
    metrics_frame: pd.DataFrame,
    node_metrics_frame: pd.DataFrame,
    edge_metrics_frame: pd.DataFrame,
    class_metrics_frame: pd.DataFrame,
    policy_schedule_frame: pd.DataFrame,
    intervention_catalog_frame: pd.DataFrame,
    bundle_hierarchy_frame: pd.DataFrame,
    cluster_response_plan_frame: pd.DataFrame,
    regime_detection_frame: pd.DataFrame,
    regime_detection_confusion_frame: pd.DataFrame,
    online_regime_frame: pd.DataFrame,
    online_regime_horizon_frame: pd.DataFrame,
    response_timing_frame: pd.DataFrame,
    closed_loop_regime_frame: pd.DataFrame,
    controller_policy_frame: pd.DataFrame,
    controller_frontier_frame: pd.DataFrame,
    scenario_summary_frame: pd.DataFrame,
    scenario_clusters_frame: pd.DataFrame,
    cluster_summary_frame: pd.DataFrame,
    intervention_coverage_frame: pd.DataFrame,
    portfolio_candidates_frame: pd.DataFrame,
    portfolio_cluster_coverage_frame: pd.DataFrame,
    pareto_frontier_frame: pd.DataFrame,
    comparison_frame: pd.DataFrame,
    plots: dict[str, str],
) -> str:
    parts = [
        "<html>",
        "<head>",
        "<meta charset='utf-8'>",
        "<title>StressLab Report</title>",
        "<style>",
        "body { font-family: Georgia, serif; margin: 2rem auto; max-width: 1100px; color: #182026; }",
        "table { border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }",
        "td, th { border: 1px solid #d6dde2; padding: 0.45rem 0.6rem; text-align: left; }",
        "img { max-width: 100%; border: 1px solid #d6dde2; margin-bottom: 1.5rem; }",
        "code { background: #f4f6f8; padding: 0.1rem 0.3rem; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>StressLab Report: {metadata.get('system_name', baseline.get('run_id', 'run'))}</h1>",
        "<h2>Run Summary</h2>",
        "<ul>",
        f"<li>Timestamp: {metadata.get('timestamp', 'unknown')}</li>",
        f"<li>Seed: {metadata.get('seed', primary.get('seed', baseline.get('seed', 'unknown')))}</li>",
        f"<li>Command: <code>{metadata.get('command', 'stresslab run')}</code></li>",
        f"<li>Failure triggered: <code>{primary.get('failure_triggered', False)}</code></li>",
        "</ul>",
        "<h2>Core Metrics</h2>",
        metrics_frame.to_html(index=False, border=0) if not metrics_frame.empty else "<p>No metrics available.</p>",
    ]
    if not node_metrics_frame.empty:
        parts.extend(["<h2>Node Metrics</h2>", node_metrics_frame.to_html(index=False, border=0)])
    if not edge_metrics_frame.empty:
        parts.extend(["<h2>Edge Metrics</h2>", edge_metrics_frame.to_html(index=False, border=0)])
    if not class_metrics_frame.empty:
        parts.extend(["<h2>Class Metrics</h2>", class_metrics_frame.to_html(index=False, border=0)])
    if not policy_schedule_frame.empty:
        parts.extend(["<h2>Policy Schedule</h2>", policy_schedule_frame.to_html(index=False, border=0)])
    if not intervention_catalog_frame.empty:
        parts.extend(
            ["<h2>Intervention Catalog</h2>", intervention_catalog_frame.to_html(index=False, border=0)]
        )
    if not bundle_hierarchy_frame.empty:
        parts.extend(["<h2>Bundle Hierarchy</h2>", bundle_hierarchy_frame.to_html(index=False, border=0)])
    if not cluster_response_plan_frame.empty:
        parts.extend(["<h2>Cluster Response Plan</h2>", cluster_response_plan_frame.to_html(index=False, border=0)])
    if not regime_detection_frame.empty:
        parts.extend(["<h2>Regime Detection Outcomes</h2>", regime_detection_frame.to_html(index=False, border=0)])
    if not regime_detection_confusion_frame.empty:
        parts.extend(
            ["<h2>Regime Detection Confusion</h2>", regime_detection_confusion_frame.to_html(index=False, border=0)]
        )
    if not online_regime_frame.empty:
        parts.extend(["<h2>Online Regime Decisions</h2>", online_regime_frame.to_html(index=False, border=0)])
    if not online_regime_horizon_frame.empty:
        parts.extend(["<h2>Online Regime Horizons</h2>", online_regime_horizon_frame.to_html(index=False, border=0)])
    if not response_timing_frame.empty:
        parts.extend(["<h2>Response Timing</h2>", response_timing_frame.to_html(index=False, border=0)])
    if not closed_loop_regime_frame.empty:
        parts.extend(["<h2>Closed-Loop Regime Control</h2>", closed_loop_regime_frame.to_html(index=False, border=0)])
    if not controller_policy_frame.empty:
        parts.extend(["<h2>Controller Policy Candidates</h2>", controller_policy_frame.to_html(index=False, border=0)])
    if not controller_frontier_frame.empty:
        parts.extend(["<h2>Controller Frontier</h2>", controller_frontier_frame.to_html(index=False, border=0)])
    if not comparison_frame.empty:
        parts.extend(["<h2>Baseline vs Scenario</h2>", comparison_frame.to_html(index=False, border=0)])
    if not scenario_summary_frame.empty:
        parts.extend(["<h2>Robust Scenario Portfolio</h2>", scenario_summary_frame.to_html(index=False, border=0)])
    if not cluster_summary_frame.empty:
        parts.extend(["<h2>Scenario Families</h2>", cluster_summary_frame.to_html(index=False, border=0)])
    if not scenario_clusters_frame.empty:
        parts.extend(
            ["<h2>Scenario Cluster Assignments</h2>", scenario_clusters_frame.to_html(index=False, border=0)]
        )
    if not intervention_coverage_frame.empty:
        parts.extend(
            ["<h2>Intervention Coverage</h2>", intervention_coverage_frame.to_html(index=False, border=0)]
        )
    if not portfolio_candidates_frame.empty:
        parts.extend(
            ["<h2>Portfolio Candidates</h2>", portfolio_candidates_frame.to_html(index=False, border=0)]
        )
    if not portfolio_cluster_coverage_frame.empty:
        parts.extend(
            [
                "<h2>Selected Portfolio Coverage</h2>",
                portfolio_cluster_coverage_frame.to_html(index=False, border=0),
            ]
        )
    if not pareto_frontier_frame.empty:
        parts.extend(["<h2>Pareto Frontier</h2>", pareto_frontier_frame.to_html(index=False, border=0)])
    if attribution:
        parts.extend(
            [
                "<h2>Attribution</h2>",
                f"<p>{attribution.get('narrative_summary', '')}</p>",
                "<ul>",
                f"<li>First bottleneck: <code>{attribution.get('first_bottleneck')}</code></li>",
                f"<li>Dominant bottlenecks: {', '.join(attribution.get('dominant_bottlenecks', [])) or 'none'}</li>",
                f"<li>Critical edges: {', '.join(attribution.get('critical_edges', [])) or 'none'}</li>",
                f"<li>Recovery blockers: {', '.join(attribution.get('recovery_blockers', [])) or 'none'}</li>",
                "</ul>",
            ]
        )
    if search:
        parts.extend(
            [
                "<h2>Search</h2>",
                "<ul>",
                f"<li>Objective: <code>{search.get('objective')}</code></li>",
                f"<li>Best budget: <code>{search.get('best_shock_budget')}</code></li>",
                f"<li>Damage score: <code>{search.get('damage_score')}</code></li>",
                f"<li>Failure triggered: <code>{search.get('failure_triggered')}</code></li>",
                "</ul>",
                f"<pre>{json.dumps(search.get('best_shock_vector', {}), indent=2)}</pre>",
            ]
        )
    if optimization:
        parts.extend(
            [
                "<h2>Optimization</h2>",
                "<ul>",
                f"<li>Baseline resilience: <code>{optimization.get('baseline_resilience')}</code></li>",
                f"<li>Best resilience: <code>{optimization.get('best_resilience')}</code></li>",
                f"<li>Robust mode: <code>{optimization.get('robust_mode', False)}</code></li>",
                f"<li>Scenario count: <code>{optimization.get('scenario_count', 1)}</code></li>",
                f"<li>Cluster count: <code>{optimization.get('cluster_count', 0)}</code></li>",
                f"<li>Candidate count: <code>{optimization.get('candidate_count', 0)}</code></li>",
                f"<li>Generated policy count: <code>{optimization.get('generated_policy_count', 0)}</code></li>",
                f"<li>Dynamic policy count: <code>{optimization.get('dynamic_policy_count', 0)}</code></li>",
                f"<li>Adaptive policy count: <code>{optimization.get('adaptive_policy_count', 0)}</code></li>",
                f"<li>Bundle candidate count: <code>{optimization.get('bundle_candidate_count', 0)}</code></li>",
                f"<li>Hierarchical playbook count: <code>{optimization.get('hierarchical_playbook_count', 0)}</code></li>",
                f"<li>Fairness weight: <code>{optimization.get('fairness_weight', 0.0)}</code></li>",
                f"<li>Recommended portfolio: <code>{optimization.get('recommended_portfolio_id')}</code></li>",
                f"<li>Portfolio method: <code>{optimization.get('portfolio_method')}</code></li>",
                f"<li>Portfolio objective: <code>{optimization.get('portfolio_objective_score')}</code></li>",
                f"<li>Portfolio cluster coverage: <code>{optimization.get('portfolio_cluster_coverage_rate')}</code></li>",
                f"<li>Regime plan method: <code>{optimization.get('regime_plan_method')}</code></li>",
                f"<li>Regime plan standby cost: <code>{optimization.get('regime_plan_standby_cost')}</code></li>",
                f"<li>Regime plan coverage: <code>{optimization.get('regime_plan_cluster_coverage_rate')}</code></li>",
                f"<li>Regime plan expected resilience: <code>{optimization.get('regime_plan_expected_resilience')}</code></li>",
                f"<li>Regime detection method: <code>{optimization.get('regime_detection_method')}</code></li>",
                f"<li>Regime detection accuracy: <code>{optimization.get('regime_detection_accuracy')}</code></li>",
                f"<li>Regime detection expected resilience: <code>{optimization.get('regime_detection_expected_resilience')}</code></li>",
                f"<li>Regime detection resilience regret: <code>{optimization.get('regime_detection_resilience_regret')}</code></li>",
                f"<li>Online regime method: <code>{optimization.get('online_regime_detection_method')}</code></li>",
                f"<li>Online regime accuracy: <code>{optimization.get('online_regime_detection_accuracy')}</code></li>",
                f"<li>Online regime expected resilience: <code>{optimization.get('online_regime_expected_resilience')}</code></li>",
                f"<li>Online regime resilience regret: <code>{optimization.get('online_regime_resilience_regret')}</code></li>",
                f"<li>Online pre-degradation rate: <code>{optimization.get('online_regime_pre_degradation_rate')}</code></li>",
                f"<li>Response timing method: <code>{optimization.get('response_timing_method')}</code></li>",
                f"<li>Response timing best fraction: <code>{optimization.get('response_timing_best_fraction')}</code></li>",
                f"<li>Response timing response window: <code>{optimization.get('response_timing_latest_high_value_fraction')}</code></li>",
                f"<li>Response timing half-life: <code>{optimization.get('response_timing_half_life_fraction')}</code></li>",
                f"<li>Response timing value decay: <code>{optimization.get('response_timing_value_decay')}</code></li>",
                f"<li>Closed-loop regime method: <code>{optimization.get('closed_loop_regime_method')}</code></li>",
                f"<li>Closed-loop deployment accuracy: <code>{optimization.get('closed_loop_regime_deployment_accuracy')}</code></li>",
                f"<li>Closed-loop expected resilience: <code>{optimization.get('closed_loop_regime_expected_resilience')}</code></li>",
                f"<li>Closed-loop pre-degradation rate: <code>{optimization.get('closed_loop_regime_pre_degradation_rate')}</code></li>",
                f"<li>Closed-loop retarget rate: <code>{optimization.get('closed_loop_regime_retarget_rate')}</code></li>",
                f"<li>Closed-loop resilience regret: <code>{optimization.get('closed_loop_regime_resilience_regret')}</code></li>",
                f"<li>Controller tuning method: <code>{optimization.get('controller_tuning_method')}</code></li>",
                f"<li>Controller policy id: <code>{optimization.get('controller_policy_id')}</code></li>",
                f"<li>Controller schedule id: <code>{optimization.get('controller_schedule_id')}</code></li>",
                f"<li>Controller confidence threshold: <code>{optimization.get('controller_confidence_threshold')}</code></li>",
                f"<li>Controller confirmation count: <code>{optimization.get('controller_confirmation_count')}</code></li>",
                f"<li>Controller schedule start: <code>{optimization.get('controller_schedule_start_fraction')}</code></li>",
                f"<li>Controller schedule interval: <code>{optimization.get('controller_schedule_interval_fraction')}</code></li>",
                f"<li>Controller schedule growth: <code>{optimization.get('controller_schedule_growth')}</code></li>",
                f"<li>Controller observation limit: <code>{optimization.get('controller_schedule_observation_limit')}</code></li>",
                f"<li>Controller mean observations: <code>{optimization.get('controller_mean_observation_count')}</code></li>",
                f"<li>Controller mean deployments: <code>{optimization.get('controller_mean_deployment_count')}</code></li>",
                f"<li>Controller monitoring burden: <code>{optimization.get('controller_monitoring_burden_score')}</code></li>",
                f"<li>Controller allow retargeting: <code>{optimization.get('controller_allow_retargeting')}</code></li>",
                f"<li>Controller frontier count: <code>{optimization.get('controller_frontier_count')}</code></li>",
                f"<li>Controller search rounds: <code>{optimization.get('controller_search_rounds')}</code></li>",
                f"<li>Controller candidate count: <code>{optimization.get('controller_candidate_count')}</code></li>",
                "</ul>",
            ]
        )
        ranked = pd.DataFrame(optimization.get("ranked_interventions", []))
        if not ranked.empty:
            columns = [
                "intervention_id",
                "label",
                "action_type",
                "target",
                "source",
                "generated",
                "dynamic",
                "policy_mode",
                "schedule_start",
                "schedule_duration",
                "stage_count",
                "bundle_size",
                "bundle_depth",
                "trigger_metric",
                "trigger_node",
                "trigger_threshold",
                "clear_threshold",
                "cost",
                "resilience_gain",
                "roi",
                "failure_prevented",
            ]
            if optimization.get("robust_mode", False):
                columns.extend(
                    [
                        "expected_resilience",
                        "worst_case_resilience",
                        "fairness_gain",
                        "expected_fairness_score",
                        "worst_case_fairness_score",
                        "resilience_std",
                        "failure_prevention_rate",
                        "robust_score",
                        "evaluated_scenarios",
                    ]
                )
            columns = [column for column in columns if column in ranked.columns]
            parts.append(
                ranked[columns].to_html(index=False, border=0)
            )
    if regime_plan_summary:
        parts.extend(
            ["<h2>Regime Plan Summary</h2>", pd.DataFrame([regime_plan_summary]).to_html(index=False, border=0)]
        )
    if regime_detection_summary:
        parts.extend(
            [
                "<h2>Regime Detection Summary</h2>",
                pd.DataFrame([regime_detection_summary]).to_html(index=False, border=0),
            ]
        )
    if online_regime_summary:
        parts.extend(
            ["<h2>Online Regime Summary</h2>", pd.DataFrame([online_regime_summary]).to_html(index=False, border=0)]
        )
    if response_timing_summary:
        parts.extend(
            ["<h2>Response Timing Summary</h2>", pd.DataFrame([response_timing_summary]).to_html(index=False, border=0)]
        )
    if closed_loop_regime_summary:
        parts.extend(
            ["<h2>Closed-Loop Regime Summary</h2>", pd.DataFrame([closed_loop_regime_summary]).to_html(index=False, border=0)]
        )
    if controller_tuning_summary:
        parts.extend(
            ["<h2>Controller Tuning Summary</h2>", pd.DataFrame([controller_tuning_summary]).to_html(index=False, border=0)]
        )
    if counterfactuals:
        counterfactual_frame = pd.DataFrame(counterfactuals)
        if not counterfactual_frame.empty:
            parts.extend(["<h2>Counterfactuals</h2>", counterfactual_frame.to_html(index=False, border=0)])
    if plots:
        parts.append("<h2>Plots</h2>")
        for label, plot_path in plots.items():
            relative = Path(plot_path).name
            parts.extend([f"<h3>{label.replace('_', ' ').title()}</h3>", f"<img src='{relative}' alt='{label}'>"])
    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def _comparison_frame(baseline: dict, primary: dict) -> pd.DataFrame:
    baseline_metrics = baseline.get("metrics", {})
    primary_metrics = primary.get("metrics", {})
    if not baseline_metrics or not primary_metrics or baseline_metrics == primary_metrics:
        return pd.DataFrame()
    selected_metrics = [
        "throughput",
        "throughput_efficiency",
        "throughput_loss",
        "mean_wait",
        "p95_wait",
        "queue_integral",
        "holding_integral",
        "recovery_time",
        "cascade_norm",
        "blocked_transfers",
        "mean_edge_delay",
        "fairness_score",
        "fairness_degradation",
        "wait_inequity",
        "throughput_inequity",
        "drop_inequity",
        "policy_schedule_count",
        "policy_activation_count",
        "adaptive_policy_activation_count",
        "policy_stage_change_count",
        "policy_active_time",
        "deployment_count",
        "first_deployment_time",
        "resilience_score",
    ]
    rows = []
    for metric in selected_metrics:
        if metric not in baseline_metrics and metric not in primary_metrics:
            continue
        baseline_value = baseline_metrics.get(metric, 0.0)
        primary_value = primary_metrics.get(metric, 0.0)
        rows.append(
            {
                "metric": metric,
                "baseline": baseline_value,
                "scenario": primary_value,
                "delta": primary_value - baseline_value,
            }
        )
    return pd.DataFrame(rows)
