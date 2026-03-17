"""Replication-based evaluation studies for StressLab plans."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import seaborn as sns

from stresslab.des import Simulator
from stresslab.models import EvaluationMetricSummary, EvaluationSummary
from stresslab.optimize import Optimizer, apply_interventions
from stresslab.optimize.policy_catalog import expand_intervention_catalog
from stresslab.systemspec import load_spec, resolve_spec
from stresslab.utils import write_dataframe, write_json, write_yaml

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid")

METRIC_DIRECTIONS = {
    "throughput": "higher_is_better",
    "mean_wait": "lower_is_better",
    "resilience_score": "higher_is_better",
    "fairness_score": "higher_is_better",
}


def build_evaluation_study(
    spec_path: Path,
    *,
    output_dir: Path,
    replicates: int,
    seed_step: int,
    budget: float | None,
    robust: bool,
    scenario_budget: float | None,
    scenario_samples: int,
    fairness_weight: float,
    intervention_ids: list[str] | None,
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
) -> EvaluationSummary:
    """Run a multi-seed evaluation study for a planned intervention set."""

    if replicates <= 0:
        raise ValueError("replicates must be positive.")
    if seed_step <= 0:
        raise ValueError("seed_step must be positive.")

    original_spec = load_spec(spec_path)
    spec, _ = expand_intervention_catalog(
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
    base_seed = int(spec.seed)
    baseline_selection = Simulator(resolve_spec(spec), seed=base_seed).run(run_id="selection_baseline")
    selected_interventions, selection_mode = _choose_interventions(
        spec=spec,
        baseline_result=baseline_selection,
        budget=budget,
        robust=robust,
        scenario_budget=scenario_budget,
        scenario_samples=scenario_samples,
        fairness_weight=fairness_weight,
        intervention_ids=intervention_ids or [],
    )
    scenario_spec = apply_interventions(spec, selected_interventions) if selected_interventions else spec.model_copy(deep=True)

    seeds = [base_seed + (index * seed_step) for index in range(replicates)]
    records: list[dict[str, object]] = []
    delta_rows: list[dict[str, object]] = []
    for replicate_index, seed in enumerate(seeds, start=1):
        baseline_spec = spec.model_copy(update={"seed": seed}, deep=True)
        treated_spec = scenario_spec.model_copy(update={"seed": seed}, deep=True)
        baseline_result = Simulator(resolve_spec(baseline_spec), seed=seed).run(
            run_id=f"baseline_rep_{replicate_index}"
        )
        treated_result = Simulator(
            resolve_spec(treated_spec),
            seed=seed,
            baseline_metrics=baseline_result.metrics,
        ).run(run_id=f"scenario_rep_{replicate_index}")
        records.extend(
            [
                _replicate_record(
                    variant="baseline",
                    replicate_index=replicate_index,
                    seed=seed,
                    result=baseline_result,
                ),
                _replicate_record(
                    variant="scenario",
                    replicate_index=replicate_index,
                    seed=seed,
                    result=treated_result,
                ),
            ]
        )
        delta_rows.append(
            _paired_delta_row(
                replicate_index=replicate_index,
                seed=seed,
                baseline_result=baseline_result,
                scenario_result=treated_result,
            )
        )

    replicate_frame = pd.DataFrame(records)
    delta_frame = pd.DataFrame(delta_rows)
    summary_rows = [_metric_summary_row(delta_frame, metric) for metric in METRIC_DIRECTIONS]
    summary_rows.append(_failure_summary_row(replicate_frame))
    metric_summary_frame = pd.DataFrame([row.model_dump(mode="json") for row in summary_rows])
    evaluation_summary = EvaluationSummary(
        evaluation_mode="robust_optimize" if robust else "optimize" if selected_interventions else "baseline",
        selection_mode=selection_mode,
        system_name=spec.system.name,
        replicate_count=replicates,
        seeds=seeds,
        selected_intervention_ids=[item.id for item in selected_interventions],
        selected_intervention_labels=[item.label or item.id for item in selected_interventions],
        baseline_failure_rate=float(
            replicate_frame[replicate_frame["variant"] == "baseline"]["failure_triggered"].astype(float).mean()
        ),
        scenario_failure_rate=float(
            replicate_frame[replicate_frame["variant"] == "scenario"]["failure_triggered"].astype(float).mean()
        ),
        failure_rate_delta=float(
            replicate_frame[replicate_frame["variant"] == "scenario"]["failure_triggered"].astype(float).mean()
            - replicate_frame[replicate_frame["variant"] == "baseline"]["failure_triggered"].astype(float).mean()
        ),
        replicate_metrics_path=str(output_dir / "replicate_metrics.csv"),
        paired_deltas_path=str(output_dir / "paired_deltas.csv"),
        metric_summary_path=str(output_dir / "evaluation_metric_summary.csv"),
        treatment_plan_path=str(output_dir / "treatment_plan.json"),
        report_markdown_path=str(output_dir / "evaluation_report.md"),
        report_html_path=str(output_dir / "evaluation_report.html"),
        metric_summaries=summary_rows,
    )

    write_dataframe(output_dir / "replicate_metrics.csv", replicate_frame)
    write_dataframe(output_dir / "paired_deltas.csv", delta_frame)
    write_dataframe(output_dir / "evaluation_metric_summary.csv", metric_summary_frame)
    write_json(
        output_dir / "treatment_plan.json",
        {
            "selection_mode": selection_mode,
            "selected_interventions": [
                {
                    "intervention_id": item.id,
                    "label": item.label,
                    "action_type": item.action_type,
                    "target": item.target,
                    "cost": item.cost,
                }
                for item in selected_interventions
            ],
        },
    )
    write_yaml(output_dir / "spec_resolved_baseline.yaml", spec.model_dump(mode="json", by_alias=True))
    write_yaml(output_dir / "spec_resolved_scenario.yaml", scenario_spec.model_dump(mode="json", by_alias=True))
    write_json(output_dir / "evaluation_summary.json", evaluation_summary)
    plot_replicate_distributions(replicate_frame, output_dir / "evaluation_distributions.png")
    plot_delta_summary(metric_summary_frame, output_dir / "evaluation_deltas.png")
    plot_failure_rates(evaluation_summary, output_dir / "evaluation_failures.png")
    _write_evaluation_report(output_dir, evaluation_summary, metric_summary_frame, replicate_frame)
    return evaluation_summary


def plot_replicate_distributions(frame: pd.DataFrame, path: Path) -> Path:
    """Plot per-metric replicate distributions for baseline vs scenario."""

    metrics = [metric for metric in METRIC_DIRECTIONS if metric in frame.columns]
    melted = frame.melt(
        id_vars=["variant", "replicate_index"],
        value_vars=metrics,
        var_name="metric",
        value_name="value",
    )
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 8.0))
    for metric, ax in zip(metrics, axes.flatten(), strict=False):
        metric_frame = melted[melted["metric"] == metric]
        sns.boxplot(
            data=metric_frame,
            x="variant",
            y="value",
            hue="variant",
            legend=False,
            ax=ax,
            palette="Set2",
        )
        sns.stripplot(data=metric_frame, x="variant", y="value", ax=ax, color="#264653", alpha=0.55)
        ax.set_title(metric.replace("_", " ").title())
        ax.set_xlabel("")
        ax.set_ylabel("value")
    for ax in axes.flatten()[len(metrics):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_delta_summary(frame: pd.DataFrame, path: Path) -> Path:
    """Plot mean paired deltas with confidence intervals."""

    plot_frame = frame[frame["metric"] != "failure_rate"].copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [{"metric": "none", "delta_mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}]
        )
    plot_frame["ci_left"] = plot_frame["delta_mean"] - plot_frame["ci_low"]
    plot_frame["ci_right"] = plot_frame["ci_high"] - plot_frame["delta_mean"]
    fig, ax = plt.subplots(figsize=(9.5, max(4.5, 0.55 * len(plot_frame) + 1.5)))
    ax.errorbar(
        plot_frame["delta_mean"],
        plot_frame["metric"],
        xerr=[plot_frame["ci_left"], plot_frame["ci_right"]],
        fmt="o",
        color="#1d3557",
        ecolor="#457b9d",
        capsize=4,
    )
    ax.axvline(0.0, color="#d62828", linestyle="--", linewidth=1)
    ax.set_title("Evaluation: Mean Paired Deltas")
    ax.set_xlabel("Scenario - Baseline")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_failure_rates(summary: EvaluationSummary, path: Path) -> Path:
    """Plot baseline vs scenario failure rates from the evaluation study."""

    plot_frame = pd.DataFrame(
        [
            {"variant": "baseline", "failure_rate": summary.baseline_failure_rate},
            {"variant": "scenario", "failure_rate": summary.scenario_failure_rate},
        ]
    )
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    sns.barplot(
        data=plot_frame,
        x="variant",
        y="failure_rate",
        hue="variant",
        legend=False,
        palette="Set2",
        ax=ax,
    )
    ax.set_ylim(0.0, max(1.0, plot_frame["failure_rate"].max() * 1.1))
    ax.set_title("Evaluation: Failure Rate Comparison")
    ax.set_xlabel("")
    ax.set_ylabel("Failure rate")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _choose_interventions(
    *,
    spec,
    baseline_result,
    budget: float | None,
    robust: bool,
    scenario_budget: float | None,
    scenario_samples: int,
    fairness_weight: float,
    intervention_ids: list[str],
):
    if intervention_ids:
        lookup = {item.id: item for item in spec.interventions}
        selected = []
        for intervention_id in intervention_ids:
            item = lookup.get(intervention_id)
            if item is None:
                raise ValueError(f"Unknown intervention id '{intervention_id}' for evaluation.")
            selected.append(item)
        return selected, "manual"

    optimizer = Optimizer(spec, baseline_result)
    result = (
        optimizer.rank_interventions_robust(
            budget=budget,
            scenario_budget=scenario_budget,
            random_samples=scenario_samples,
            fairness_weight=fairness_weight,
        )
        if robust
        else optimizer.rank_interventions(
            budget=budget,
            fairness_weight=fairness_weight,
        )
    )
    chosen_ids = (
        [item.intervention_id for item in result.selected_interventions]
        if result.selected_interventions
        else [result.ranked_interventions[0].intervention_id] if result.ranked_interventions else []
    )
    lookup = {item.id: item for item in spec.interventions}
    return [lookup[item_id] for item_id in chosen_ids if item_id in lookup], "optimized"


def _replicate_record(*, variant: str, replicate_index: int, seed: int, result) -> dict[str, object]:
    metrics = result.metrics
    return {
        "variant": variant,
        "replicate_index": replicate_index,
        "seed": seed,
        "failure_triggered": result.failure_triggered,
        "throughput": metrics.get("throughput", 0.0),
        "mean_wait": metrics.get("mean_wait", 0.0),
        "resilience_score": metrics.get("resilience_score", 0.0),
        "fairness_score": metrics.get("fairness_score", 0.0),
    }


def _paired_delta_row(*, replicate_index: int, seed: int, baseline_result, scenario_result) -> dict[str, object]:
    return {
        "replicate_index": replicate_index,
        "seed": seed,
        "baseline_throughput": baseline_result.metrics.get("throughput", 0.0),
        "scenario_throughput": scenario_result.metrics.get("throughput", 0.0),
        "throughput": scenario_result.metrics.get("throughput", 0.0) - baseline_result.metrics.get("throughput", 0.0),
        "baseline_mean_wait": baseline_result.metrics.get("mean_wait", 0.0),
        "scenario_mean_wait": scenario_result.metrics.get("mean_wait", 0.0),
        "mean_wait": scenario_result.metrics.get("mean_wait", 0.0) - baseline_result.metrics.get("mean_wait", 0.0),
        "baseline_resilience_score": baseline_result.metrics.get("resilience_score", 0.0),
        "scenario_resilience_score": scenario_result.metrics.get("resilience_score", 0.0),
        "resilience_score": scenario_result.metrics.get("resilience_score", 0.0)
        - baseline_result.metrics.get("resilience_score", 0.0),
        "baseline_fairness_score": baseline_result.metrics.get("fairness_score", 0.0),
        "scenario_fairness_score": scenario_result.metrics.get("fairness_score", 0.0),
        "fairness_score": scenario_result.metrics.get("fairness_score", 0.0)
        - baseline_result.metrics.get("fairness_score", 0.0),
        "failure_rate": float(scenario_result.failure_triggered) - float(baseline_result.failure_triggered),
    }


def _metric_summary_row(frame: pd.DataFrame, metric: str) -> EvaluationMetricSummary:
    values = frame[metric].astype(float)
    mean = float(values.mean()) if not values.empty else 0.0
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    sem = std / math.sqrt(len(values)) if len(values) > 0 else 0.0
    margin = 1.96 * sem
    direction = METRIC_DIRECTIONS[metric]
    baseline_mean = float(frame[f"baseline_{metric}"].mean()) if f"baseline_{metric}" in frame.columns else 0.0
    scenario_mean = float(frame[f"scenario_{metric}"].mean()) if f"scenario_{metric}" in frame.columns else baseline_mean + mean
    if direction == "lower_is_better":
        improvement_rate = float((values < 0).mean()) if len(values) > 0 else 0.0
    else:
        improvement_rate = float((values > 0).mean()) if len(values) > 0 else 0.0
    return EvaluationMetricSummary(
        metric=metric,
        direction=direction,
        baseline_mean=baseline_mean,
        scenario_mean=scenario_mean,
        delta_mean=mean,
        delta_std=std,
        ci_low=mean - margin,
        ci_high=mean + margin,
        improvement_rate=improvement_rate,
    )


def _failure_summary_row(replicate_frame: pd.DataFrame) -> EvaluationMetricSummary:
    baseline = replicate_frame[replicate_frame["variant"] == "baseline"]["failure_triggered"].astype(float)
    scenario = replicate_frame[replicate_frame["variant"] == "scenario"]["failure_triggered"].astype(float)
    delta = scenario.values - baseline.values
    mean = float(delta.mean()) if len(delta) else 0.0
    std = float(np.std(delta, ddof=1)) if len(delta) > 1 else 0.0
    sem = std / math.sqrt(len(delta)) if len(delta) else 0.0
    margin = 1.96 * sem
    return EvaluationMetricSummary(
        metric="failure_rate",
        direction="lower_is_better",
        baseline_mean=float(baseline.mean()) if len(baseline) else 0.0,
        scenario_mean=float(scenario.mean()) if len(scenario) else 0.0,
        delta_mean=mean,
        delta_std=std,
        ci_low=mean - margin,
        ci_high=mean + margin,
        improvement_rate=float((delta < 0).mean()) if len(delta) else 0.0,
    )


def _write_evaluation_report(
    output_dir: Path,
    summary: EvaluationSummary,
    metric_summary_frame: pd.DataFrame,
    replicate_frame: pd.DataFrame,
) -> None:
    report_lines = [
        f"# Evaluation Study: {summary.system_name}",
        "",
        "## Summary",
        "",
        f"- Mode: `{summary.evaluation_mode}`",
        f"- Selection mode: `{summary.selection_mode}`",
        f"- Replicates: `{summary.replicate_count}`",
        f"- Seeds: `{summary.seeds}`",
        f"- Selected interventions: `{summary.selected_intervention_ids}`",
        f"- Baseline failure rate: `{summary.baseline_failure_rate:.3f}`",
        f"- Scenario failure rate: `{summary.scenario_failure_rate:.3f}`",
        f"- Failure rate delta: `{summary.failure_rate_delta:.3f}`",
        "",
        "## Metric Summary",
        "",
        _frame_to_markdown(metric_summary_frame),
        "",
        "## Replicates",
        "",
        _frame_to_markdown(replicate_frame),
        "",
        "## Plots",
        "",
        "![evaluation_distributions](evaluation_distributions.png)",
        "",
        "![evaluation_deltas](evaluation_deltas.png)",
        "",
        "![evaluation_failures](evaluation_failures.png)",
        "",
    ]
    (output_dir / "evaluation_report.md").write_text("\n".join(report_lines), encoding="utf-8")
    html = [
        "<html><body>",
        f"<h1>Evaluation Study: {summary.system_name}</h1>",
        "<ul>",
        f"<li>Mode: <code>{summary.evaluation_mode}</code></li>",
        f"<li>Selection mode: <code>{summary.selection_mode}</code></li>",
        f"<li>Replicates: <code>{summary.replicate_count}</code></li>",
        f"<li>Seeds: <code>{summary.seeds}</code></li>",
        f"<li>Selected interventions: <code>{summary.selected_intervention_ids}</code></li>",
        f"<li>Baseline failure rate: <code>{summary.baseline_failure_rate:.3f}</code></li>",
        f"<li>Scenario failure rate: <code>{summary.scenario_failure_rate:.3f}</code></li>",
        f"<li>Failure rate delta: <code>{summary.failure_rate_delta:.3f}</code></li>",
        "</ul>",
        "<h2>Metric Summary</h2>",
        metric_summary_frame.to_html(index=False, border=0),
        "<h2>Replicates</h2>",
        replicate_frame.to_html(index=False, border=0),
        "<h2>Plots</h2>",
        "<img src='evaluation_distributions.png' style='max-width: 100%;'>",
        "<img src='evaluation_deltas.png' style='max-width: 100%;'>",
        "<img src='evaluation_failures.png' style='max-width: 100%;'>",
        "</body></html>",
    ]
    (output_dir / "evaluation_report.html").write_text("\n".join(html), encoding="utf-8")


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No data available._"
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])
