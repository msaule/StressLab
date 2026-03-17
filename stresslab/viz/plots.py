"""Plot generation for StressLab artifacts."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import networkx as nx
import pandas as pd
import seaborn as sns

from stresslab.config import DEFAULT_TOP_N_NODES

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid")


def create_standard_plots(
    *,
    resolved_spec,
    simulator,
    result,
    output_dir: Path,
    search_history: list[dict[str, float | bool]] | None = None,
    optimization_result=None,
    scenario_cluster_frame: pd.DataFrame | None = None,
    intervention_coverage_frame: pd.DataFrame | None = None,
    portfolio_candidates_frame: pd.DataFrame | None = None,
    cluster_response_plan_frame: pd.DataFrame | None = None,
    regime_detection_confusion_frame: pd.DataFrame | None = None,
    online_regime_horizon_frame: pd.DataFrame | None = None,
    response_timing_frame: pd.DataFrame | None = None,
    closed_loop_regime_frame: pd.DataFrame | None = None,
    controller_policy_frame: pd.DataFrame | None = None,
    controller_frontier_frame: pd.DataFrame | None = None,
    top_n: int = DEFAULT_TOP_N_NODES,
) -> dict[str, str]:
    """Create the core plot set for a run."""

    output_dir.mkdir(parents=True, exist_ok=True)
    plots = {
        "queue_lengths": str(plot_queue_lengths(simulator, result, output_dir / "queue_lengths.png", top_n=top_n)),
        "utilization": str(plot_utilization(simulator, result, output_dir / "utilization.png", top_n=top_n)),
        "wait_histogram": str(plot_wait_histogram(simulator, output_dir / "wait_histogram.png")),
        "class_fairness": str(plot_class_fairness(result, output_dir / "class_fairness.png")),
        "heatmap": str(plot_node_damage_heatmap(result, output_dir / "bottleneck_heatmap.png")),
        "system_graph": str(plot_system_graph(resolved_spec, result, output_dir / "system_graph.png")),
    }
    if getattr(simulator.spec.spec, "policies", []):
        plots["policy_schedule"] = str(
            plot_policy_schedule(simulator, output_dir / "policy_schedule.png")
        )
    if search_history:
        plots["fragility_curve"] = str(
            plot_fragility_curve(search_history, output_dir / "fragility_curve.png")
        )
        failure_surface_path = output_dir / "failure_surface.png"
        surface = plot_failure_surface(search_history, failure_surface_path)
        if surface is not None:
            plots["failure_surface"] = str(surface)
    if optimization_result is not None:
        plots["intervention_roi"] = str(
            plot_intervention_roi(optimization_result, output_dir / "intervention_roi.png")
        )
        plots["pareto_frontier"] = str(
            plot_pareto_frontier(optimization_result, output_dir / "pareto_frontier.png")
        )
    if scenario_cluster_frame is not None and not scenario_cluster_frame.empty:
        plots["scenario_clusters"] = str(
            plot_scenario_clusters(scenario_cluster_frame, output_dir / "scenario_clusters.png")
        )
    if intervention_coverage_frame is not None and not intervention_coverage_frame.empty:
        plots["intervention_coverage"] = str(
            plot_intervention_coverage_heatmap(
                intervention_coverage_frame,
                output_dir / "intervention_coverage.png",
            )
        )
    if portfolio_candidates_frame is not None and not portfolio_candidates_frame.empty:
        plots["portfolio_tradeoff"] = str(
            plot_portfolio_tradeoff(
                portfolio_candidates_frame,
                output_dir / "portfolio_tradeoff.png",
            )
        )
    if cluster_response_plan_frame is not None and not cluster_response_plan_frame.empty:
        plots["cluster_response_plan"] = str(
            plot_cluster_response_plan(
                cluster_response_plan_frame,
                output_dir / "cluster_response_plan.png",
            )
        )
    if regime_detection_confusion_frame is not None and not regime_detection_confusion_frame.empty:
        plots["regime_detection"] = str(
            plot_regime_detection_confusion(
                regime_detection_confusion_frame,
                output_dir / "regime_detection.png",
            )
        )
    if online_regime_horizon_frame is not None and not online_regime_horizon_frame.empty:
        plots["online_regime_accuracy"] = str(
            plot_online_regime_accuracy(
                online_regime_horizon_frame,
                output_dir / "online_regime_accuracy.png",
            )
        )
    if response_timing_frame is not None and not response_timing_frame.empty:
        plots["response_timing"] = str(
            plot_response_timing_curve(
                response_timing_frame,
                output_dir / "response_timing.png",
            )
        )
    if closed_loop_regime_frame is not None and not closed_loop_regime_frame.empty:
        plots["closed_loop_regime"] = str(
            plot_closed_loop_regime(
                closed_loop_regime_frame,
                output_dir / "closed_loop_regime.png",
            )
        )
    if controller_policy_frame is not None and not controller_policy_frame.empty:
        plots["controller_tuning"] = str(
            plot_controller_tuning(
                controller_policy_frame,
                output_dir / "controller_tuning.png",
            )
        )
    if controller_frontier_frame is not None and not controller_frontier_frame.empty:
        plots["controller_frontier"] = str(
            plot_controller_frontier(
                controller_frontier_frame,
                output_dir / "controller_frontier.png",
            )
        )
    return plots


def plot_queue_lengths(simulator, result, path: Path, *, top_n: int) -> Path:
    ranked = sorted(
        result.node_metrics.items(),
        key=lambda item: item[1].get("queue_integral", 0.0),
        reverse=True,
    )[:top_n]
    fig, ax = plt.subplots(figsize=(9, 5))
    for node_id, _ in ranked:
        state = simulator.node_states[node_id]
        ax.step(state.queue_times, state.queue_lengths, where="post", label=node_id)
    ax.set_title("Queue Lengths Over Time")
    ax.set_xlabel("Time")
    ax.set_ylabel("Queue length")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_utilization(simulator, result, path: Path, *, top_n: int) -> Path:
    ranked = sorted(
        result.node_metrics.items(),
        key=lambda item: item[1].get("utilization", 0.0),
        reverse=True,
    )[:top_n]
    fig, ax = plt.subplots(figsize=(9, 5))
    for node_id, _ in ranked:
        state = simulator.node_states[node_id]
        ax.step(state.utilization_times, state.utilization_values, where="post", label=node_id)
    ax.set_title("Utilization Over Time")
    ax.set_xlabel("Time")
    ax.set_ylabel("Utilization")
    ax.set_ylim(0, 1.05)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_wait_histogram(simulator, path: Path) -> Path:
    waits = []
    for state in simulator.node_states.values():
        waits.extend(state.wait_times)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(waits or [0.0], bins=20, color="#2f6c80", alpha=0.9)
    ax.set_title("Wait Time Distribution")
    ax.set_xlabel("Wait time")
    ax.set_ylabel("Count")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_class_fairness(result, path: Path) -> Path:
    frame = pd.DataFrame.from_dict(getattr(result, "class_metrics", {}), orient="index")
    if frame.empty:
        frame = pd.DataFrame(
            {
                "mean_wait": [0.0],
                "throughput_efficiency": [0.0],
                "drop_rate": [0.0],
            },
            index=["default"],
        )
    frame = frame.reset_index(names="class_id")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    sns.barplot(data=frame, x="mean_wait", y="class_id", ax=axes[0], color="#8c5e3c")
    axes[0].set_title("Mean Wait by Class")
    axes[0].set_xlabel("Mean wait")
    axes[0].set_ylabel("")
    comparison = frame.melt(
        id_vars="class_id",
        value_vars=["throughput_efficiency", "drop_rate"],
        var_name="metric",
        value_name="value",
    )
    sns.barplot(data=comparison, x="value", y="class_id", hue="metric", ax=axes[1])
    axes[1].set_title("Class Service Equity")
    axes[1].set_xlabel("Rate")
    axes[1].set_ylabel("")
    axes[1].legend(title="")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_policy_schedule(simulator, path: Path) -> Path:
    policies = list(getattr(simulator.spec.spec, "policies", []))
    if not policies:
        fig, ax = plt.subplots(figsize=(8, 1.8))
        ax.text(0.5, 0.5, "No scheduled policies", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(path, dpi=160)
        plt.close(fig)
        return path
    horizon_end = simulator.spec.spec.clock.end
    frame = pd.DataFrame(
        [
            {
                "policy_id": policy.id,
                "label": policy.label or policy.id,
                "mode": policy.mode,
                "fallback_start": policy.start,
                "fallback_end": policy.end_time() if policy.end_time() is not None else horizon_end,
                "source": (policy.applicability_constraints or {}).get("source", "authored"),
            }
            for policy in policies
        ]
    ).sort_values(["fallback_start", "label"])
    fig, ax = plt.subplots(figsize=(10, max(2.6, 0.55 * len(frame) + 1.5)))
    palette = {"authored": "#355070", "generated_policy": "#bc6c25", "generated_dynamic_policy": "#b22222"}
    for index, row in enumerate(frame.itertuples(index=False)):
        intervals = simulator._policy_intervals(str(row.policy_id), horizon_end)
        if intervals:
            ax.broken_barh(
                [(start, max(0.0, end - start)) for start, end in intervals],
                (index - 0.35, 0.7),
                facecolors=palette.get(str(row.source), "#6c757d"),
            )
        elif str(row.mode) == "scheduled":
            start = float(row.fallback_start)
            width = max(0.0, float(row.fallback_end) - start)
            ax.broken_barh(
                [(start, max(width, 1e-6))],
                (index - 0.35, 0.7),
                facecolors="#c9d5df",
                alpha=0.45,
            )
        else:
            ax.scatter([0.0], [index], marker="x", color="#6c757d", s=40)
    ax.set_yticks(range(len(frame)))
    ax.set_yticklabels([f"{label} [{mode}]" for label, mode in zip(frame["label"], frame["mode"], strict=True)])
    ax.set_xlabel("Time")
    ax.set_title("Policy Activation Timeline")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_fragility_curve(search_history: list[dict[str, float | bool]], path: Path) -> Path:
    frame = pd.DataFrame(search_history)
    if frame.empty:
        frame = pd.DataFrame([{"budget": 0.0, "damage": 0.0, "failure": False}])
    frame = frame.sort_values("budget")
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.lineplot(data=frame, x="budget", y="damage", ax=ax, marker="o")
    if "failure" in frame:
        failed = frame[frame["failure"] == True]  # noqa: E712
        ax.scatter(failed["budget"], failed["damage"], color="#b22222", label="Failure")
        if not failed.empty:
            ax.legend()
    ax.set_title("Fragility Curve")
    ax.set_xlabel("Shock budget")
    ax.set_ylabel("Damage score")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_intervention_roi(optimization_result, path: Path) -> Path:
    frame = pd.DataFrame(
        [
            {
                "intervention_id": item.intervention_id,
                "roi": item.roi,
                "resilience_gain": item.resilience_gain,
            }
            for item in optimization_result.ranked_interventions
        ]
    )
    if frame.empty:
        frame = pd.DataFrame([{"intervention_id": "none", "roi": 0.0}])
    fig, ax = plt.subplots(figsize=(8.5, max(5.0, 0.42 * len(frame) + 1.8)))
    sns.barplot(data=frame, x="roi", y="intervention_id", ax=ax, color="#40798c")
    ax.set_title("Intervention ROI")
    ax.set_xlabel("ROI")
    ax.set_ylabel("")
    fig.subplots_adjust(left=0.34, right=0.97, top=0.90, bottom=0.10)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_pareto_frontier(optimization_result, path: Path) -> Path:
    frame = pd.DataFrame(
        [
            {
                "intervention_id": item.intervention_id,
                "cost": item.cost,
                "resilience_gain": item.resilience_gain,
                "expected_resilience": item.expected_resilience,
                "worst_case_resilience": item.worst_case_resilience,
                "on_frontier": item.intervention_id in optimization_result.pareto_intervention_ids,
            }
            for item in optimization_result.ranked_interventions
        ]
    )
    if frame.empty:
        frame = pd.DataFrame(
            [{"intervention_id": "none", "cost": 0.0, "resilience_gain": 0.0, "on_frontier": True}]
        )
    y_col = "expected_resilience" if optimization_result.robust_mode else "resilience_gain"
    if y_col not in frame or frame[y_col].isna().all():
        y_col = "resilience_gain"
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.scatterplot(
        data=frame,
        x="cost",
        y=y_col,
        hue="on_frontier",
        palette={True: "#b22222", False: "#9eb3c2"},
        s=90,
        ax=ax,
    )
    frontier = frame[frame["on_frontier"] == True].sort_values("cost")  # noqa: E712
    if len(frontier) >= 2:
        ax.plot(frontier["cost"], frontier[y_col], color="#b22222", linewidth=1.5)
    for row in frontier.itertuples(index=False):
        ax.annotate(
            row.intervention_id,
            (row.cost, getattr(row, y_col)),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_title("Pareto Frontier")
    ax.set_xlabel("Cost")
    ax.set_ylabel(y_col.replace("_", " ").title())
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_scenario_clusters(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "scenario_id": "configured",
                    "cluster_label": "Single cluster",
                    "failure_triggered": False,
                    "damage_score": 0.0,
                    "resilience_score": 0.0,
                    "shock_budget": 0.0,
                }
            ]
        )
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    sns.scatterplot(
        data=plot_frame,
        x="damage_score",
        y="resilience_score",
        hue="cluster_label",
        style="failure_triggered",
        size="shock_budget",
        sizes=(90, 240),
        ax=ax,
    )
    for row in plot_frame.itertuples(index=False):
        ax.annotate(
            row.scenario_id,
            (row.damage_score, row.resilience_score),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_title("Scenario Families")
    ax.set_xlabel("Damage score")
    ax.set_ylabel("Resilience score")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_intervention_coverage_heatmap(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [{"intervention_id": "none", "cluster_id": "cluster_01", "coverage_score": 0.0}]
        )
    ordered_interventions = (
        plot_frame.groupby("intervention_id")["coverage_score"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )
    ordered_clusters = (
        plot_frame.groupby("cluster_id")["coverage_score"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )
    matrix = (
        plot_frame.pivot_table(
            index="intervention_id",
            columns="cluster_id",
            values="coverage_score",
            aggfunc="max",
            fill_value=0.0,
        )
        .reindex(index=ordered_interventions, columns=ordered_clusters)
        .head(10)
    )
    fig, ax = plt.subplots(figsize=(8.5, max(3.5, 0.55 * len(matrix.index) + 1.5)))
    sns.heatmap(matrix, annot=True, fmt=".2f", cmap="crest", ax=ax, vmin=0.0)
    ax.set_title("Intervention Coverage by Scenario Family")
    ax.set_xlabel("Scenario cluster")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_portfolio_tradeoff(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "portfolio_id": "portfolio__baseline",
                    "total_cost": 0.0,
                    "cluster_coverage_rate": 0.0,
                    "expected_resilience": 0.0,
                    "objective_score": 0.0,
                }
            ]
        )
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    sns.scatterplot(
        data=plot_frame,
        x="total_cost",
        y="cluster_coverage_rate",
        hue="objective_score",
        size="expected_resilience",
        sizes=(90, 260),
        palette="YlOrRd",
        ax=ax,
    )
    for row in plot_frame.head(8).itertuples(index=False):
        ax.annotate(
            str(row.portfolio_id).replace("portfolio__", ""),
            (row.total_cost, row.cluster_coverage_rate),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_title("Portfolio Cost vs Scenario-Family Coverage")
    ax.set_xlabel("Portfolio cost")
    ax.set_ylabel("Cluster coverage rate")
    ax.set_ylim(0, 1.05)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_cluster_response_plan(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "cluster_label": "Single cluster",
                    "scenario_count": 1,
                    "coverage_score": 0.0,
                    "selected_intervention_id": "baseline",
                    "marginal_cost": 0.0,
                    "covered": False,
                    "reused_intervention": False,
                }
            ]
        )
    plot_frame["cluster_display"] = [
        f"{label} ({count})"
        for label, count in zip(plot_frame["cluster_label"], plot_frame["scenario_count"], strict=False)
    ]
    plot_frame = plot_frame.sort_values(
        ["coverage_score", "scenario_count", "cluster_label"],
        ascending=[False, False, True],
    )
    fig, ax = plt.subplots(figsize=(10, max(4.0, 0.7 * len(plot_frame) + 1.4)))
    colors = ["#2f6c80" if bool(value) else "#c97b63" for value in plot_frame["covered"]]
    y_positions = list(range(len(plot_frame)))
    ax.barh(y_positions, plot_frame["coverage_score"], color=colors)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(plot_frame["cluster_display"])
    ax.invert_yaxis()
    for index, row in enumerate(plot_frame.itertuples(index=False)):
        label = str(row.selected_intervention_id or "unassigned")
        if getattr(row, "reused_intervention", False):
            label += " [reuse]"
        ax.annotate(
            label,
            (float(row.coverage_score), index),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
        )
    ax.set_title("Regime Response Map")
    ax.set_xlabel("Coverage score")
    ax.set_ylabel("")
    ax.set_xlim(0.0, max(1.05, float(plot_frame["coverage_score"].max()) + 0.05))
    fig.subplots_adjust(left=0.34, right=0.98, top=0.90, bottom=0.12)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_regime_detection_confusion(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "true_cluster_label": "Single cluster",
                    "predicted_cluster_label": "Single cluster",
                    "row_rate": 1.0,
                }
            ]
        )
    matrix = plot_frame.pivot_table(
        index="true_cluster_label",
        columns="predicted_cluster_label",
        values="row_rate",
        aggfunc="mean",
        fill_value=0.0,
    )
    fig, ax = plt.subplots(
        figsize=(max(5.5, 1.2 * len(matrix.columns) + 2.5), max(4.5, 0.8 * len(matrix.index) + 2.0))
    )
    sns.heatmap(matrix, annot=True, fmt=".2f", cmap="mako", vmin=0.0, vmax=1.0, ax=ax)
    ax.set_title("Regime Detection Confusion")
    ax.set_xlabel("Predicted cluster")
    ax.set_ylabel("True cluster")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_online_regime_accuracy(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "observation_fraction": 1.0,
                    "detection_accuracy": 0.0,
                    "mean_confidence": 0.0,
                }
            ]
        )
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    sns.lineplot(
        data=plot_frame,
        x="observation_fraction",
        y="detection_accuracy",
        marker="o",
        label="accuracy",
        ax=ax,
    )
    if "mean_confidence" in plot_frame.columns:
        sns.lineplot(
            data=plot_frame,
            x="observation_fraction",
            y="mean_confidence",
            marker="o",
            label="confidence",
            ax=ax,
        )
    ax.set_title("Online Regime Detection Over Time")
    ax.set_xlabel("Observed fraction of horizon")
    ax.set_ylabel("Score")
    ax.set_ylim(0.0, 1.05)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_response_timing_curve(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "deployment_fraction": 0.0,
                    "expected_resilience": 0.0,
                    "failure_prevention_rate": 0.0,
                    "pre_degradation_deployment_rate": 0.0,
                }
            ]
        )
    metrics = [
        "expected_resilience",
        "failure_prevention_rate",
        "pre_degradation_deployment_rate",
    ]
    melted = plot_frame.melt(
        id_vars="deployment_fraction",
        value_vars=[metric for metric in metrics if metric in plot_frame.columns],
        var_name="metric",
        value_name="value",
    )
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    sns.lineplot(
        data=melted,
        x="deployment_fraction",
        y="value",
        hue="metric",
        marker="o",
        ax=ax,
    )
    ax.set_title("Response Value vs Deployment Delay")
    ax.set_xlabel("Deployment fraction of horizon")
    ax.set_ylabel("Score")
    ax.set_ylim(0.0, 1.05)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_closed_loop_regime(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "scenario_id": "scenario_00",
                    "first_deployment_time": 0.0,
                    "final_resilience": 0.0,
                    "deployment_correct": False,
                    "retargeted": False,
                    "deployment_count": 0,
                }
            ]
        )
    if "first_deployment_time" not in plot_frame.columns:
        plot_frame["first_deployment_time"] = 0.0
    fallback_time = float(plot_frame["first_deployment_time"].dropna().max() if not plot_frame["first_deployment_time"].dropna().empty else 0.0)
    plot_frame["deployment_time_plot"] = plot_frame["first_deployment_time"].fillna(fallback_time + 1.0)
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    sns.scatterplot(
        data=plot_frame,
        x="deployment_time_plot",
        y="final_resilience",
        hue="deployment_correct",
        style="retargeted" if "retargeted" in plot_frame.columns else None,
        size="deployment_count" if "deployment_count" in plot_frame.columns else None,
        sizes=(80, 220),
        ax=ax,
    )
    for row in plot_frame.itertuples(index=False):
        ax.annotate(
            str(row.scenario_id),
            (row.deployment_time_plot, row.final_resilience),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_title("Closed-Loop Regime Control")
    ax.set_xlabel("First deployment time")
    ax.set_ylabel("Final resilience")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_controller_tuning(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "policy_id": "controller__baseline",
                    "objective_score": 0.0,
                    "monitoring_burden_score": 0.0,
                    "expected_resilience": 0.0,
                    "schedule_id": "balanced",
                    "generation": 0,
                }
            ]
        )
    x_column = "monitoring_burden_score" if "monitoring_burden_score" in plot_frame.columns else "deployment_accuracy"
    y_column = "objective_score" if "objective_score" in plot_frame.columns else "expected_resilience"
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    sns.scatterplot(
        data=plot_frame,
        x=x_column,
        y=y_column,
        hue="generation" if "generation" in plot_frame.columns else "schedule_id",
        style="search_method" if "search_method" in plot_frame.columns else None,
        size="deployment_accuracy" if "deployment_accuracy" in plot_frame.columns else None,
        sizes=(80, 220),
        ax=ax,
    )
    label_frame = plot_frame.sort_values(y_column, ascending=False).head(10)
    for row in label_frame.itertuples(index=False):
        ax.annotate(
            str(row.policy_id).replace("controller__", ""),
            (getattr(row, x_column), getattr(row, y_column)),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_title("Closed-Loop Controller Tuning")
    ax.set_xlabel(x_column.replace("_", " ").title())
    ax.set_ylabel(y_column.replace("_", " ").title())
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_controller_frontier(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "policy_id": "controller__baseline",
                    "monitoring_burden_score": 0.0,
                    "expected_resilience": 0.0,
                    "deployment_accuracy": 0.0,
                    "pre_degradation_rate": 0.0,
                }
            ]
        )
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    sns.scatterplot(
        data=plot_frame,
        x="monitoring_burden_score",
        y="expected_resilience",
        hue="deployment_accuracy" if "deployment_accuracy" in plot_frame.columns else None,
        size="pre_degradation_rate" if "pre_degradation_rate" in plot_frame.columns else None,
        palette="YlOrRd",
        sizes=(90, 240),
        ax=ax,
    )
    for row in plot_frame.itertuples(index=False):
        ax.annotate(
            str(row.policy_id).replace("controller__", ""),
            (row.monitoring_burden_score, row.expected_resilience),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_title("Controller Frontier")
    ax.set_xlabel("Monitoring burden score")
    ax.set_ylabel("Expected resilience")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_node_damage_heatmap(result, path: Path) -> Path:
    frame = pd.DataFrame.from_dict(result.node_metrics, orient="index")
    if frame.empty:
        frame = pd.DataFrame(
            {
                "queue_integral": [0.0],
                "mean_wait": [0.0],
                "utilization": [0.0],
            },
            index=["none"],
        )
    selected = ["queue_integral", "mean_wait", "utilization"]
    if "holding_integral" in frame.columns:
        selected.append("holding_integral")
    frame = frame[selected]
    fig, ax = plt.subplots(figsize=(7, max(3, 0.5 * len(frame.index) + 1)))
    sns.heatmap(frame, annot=True, fmt=".2f", cmap="YlOrRd", ax=ax)
    ax.set_title("Node Damage Heatmap")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_system_graph(resolved_spec, result, path: Path) -> Path:
    graph = nx.DiGraph()
    for node in resolved_spec.spec.nodes:
        graph.add_node(node.id)
    for edge in resolved_spec.spec.edges:
        graph.add_edge(edge.from_node, edge.to_node)
    pos = nx.spring_layout(graph, seed=42)
    queue_integrals = {node_id: metrics.get("queue_integral", 0.0) for node_id, metrics in result.node_metrics.items()}
    max_damage = max(queue_integrals.values(), default=1.0)
    colors = [
        plt.cm.YlOrRd(min(1.0, queue_integrals.get(node, 0.0) / max(max_damage, 1e-9)))
        for node in graph.nodes
    ]
    fig, ax = plt.subplots(figsize=(7, 5))
    nx.draw_networkx(graph, pos=pos, ax=ax, node_color=colors, arrows=True, with_labels=True)
    ax.set_title("System Graph")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_failure_surface(
    search_history: list[dict[str, float | bool]],
    path: Path,
) -> Path | None:
    frame = pd.DataFrame(search_history)
    reserved = {"budget", "damage", "failure", "cached"}
    dimensions = [column for column in frame.columns if column not in reserved]
    if len(dimensions) != 2 or frame.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 6))
    scatter = ax.scatter(
        frame[dimensions[0]],
        frame[dimensions[1]],
        c=frame["damage"],
        cmap="YlOrRd",
        s=65,
        edgecolor="black",
        linewidth=0.3,
    )
    failed = frame[frame["failure"] == True]  # noqa: E712
    if not failed.empty:
        ax.scatter(
            failed[dimensions[0]],
            failed[dimensions[1]],
            facecolors="none",
            edgecolors="#7a0018",
            s=120,
            linewidth=1.5,
            label="Failure",
        )
        ax.legend()
    ax.set_title("Failure Surface")
    ax.set_xlabel(dimensions[0])
    ax.set_ylabel(dimensions[1])
    fig.colorbar(scatter, ax=ax, label="Damage")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_benchmark_leaderboard(frame: pd.DataFrame, path: Path) -> Path:
    ordered = frame.sort_values("benchmark_score", ascending=False)
    fig, ax = plt.subplots(figsize=(9, max(4, 0.7 * len(ordered))))
    sns.barplot(data=ordered, x="benchmark_score", y="scenario_id", ax=ax, color="#2f6c80")
    ax.set_title("Benchmark Leaderboard")
    ax.set_xlabel("Benchmark score")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_benchmark_tradeoff(frame: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.scatterplot(
        data=frame,
        x="min_failure_budget",
        y="resilience_score",
        size="top_intervention_expected_resilience",
        hue="benchmark_score",
        palette="YlOrRd",
        sizes=(80, 260),
        ax=ax,
    )
    for row in frame.itertuples(index=False):
        ax.annotate(row.scenario_id.split("/")[-1], (row.min_failure_budget, row.resilience_score), fontsize=8)
    ax.set_title("Fragility vs Resilience")
    ax.set_xlabel("Min-failure budget")
    ax.set_ylabel("Baseline resilience")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
