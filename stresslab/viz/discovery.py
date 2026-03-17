"""Discovery and theory plotting helpers."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
import seaborn as sns

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid")


def plot_generation_mix(frame: pd.DataFrame, path: Path) -> Path:
    """Plot generated systems by topology type."""

    plot_frame = frame.copy()
    if plot_frame.empty or "topology_type" not in plot_frame.columns:
        plot_frame = pd.DataFrame([{"topology_type": "none", "count": 0}])
    else:
        plot_frame = (
            plot_frame["topology_type"].value_counts().rename_axis("topology_type").reset_index(name="count")
        )
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    sns.barplot(data=plot_frame, x="count", y="topology_type", ax=ax, color="#2f6c80")
    ax.set_title("Generated Systems by Topology")
    ax.set_xlabel("Count")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_generation_topologies(frame: pd.DataFrame, path: Path) -> Path:
    """Plot node count vs average degree for generated systems."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame([{"node_count": 0.0, "average_degree": 0.0, "topology_type": "none"}])
    fig, ax = plt.subplots(figsize=(8.5, 5.4))
    sns.scatterplot(data=plot_frame, x="node_count", y="average_degree", hue="topology_type", s=90, ax=ax)
    ax.set_title("Synthetic System Feature Space")
    ax.set_xlabel("Node count")
    ax.set_ylabel("Average degree")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_fragility_curves(frame: pd.DataFrame, path: Path) -> Path:
    """Plot collapse probability against utilization by topology."""

    plot_frame = frame.copy()
    required = {"baseline_utilization", "collapse_probability"}
    if plot_frame.empty or not required.issubset(plot_frame.columns):
        plot_frame = pd.DataFrame([{"baseline_utilization": 0.0, "collapse_probability": 0.0, "topology_type": "none"}])
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    sns.scatterplot(
        data=plot_frame,
        x="baseline_utilization",
        y="collapse_probability",
        hue="topology_type" if "topology_type" in plot_frame.columns else None,
        alpha=0.8,
        ax=ax,
    )
    sns.regplot(
        data=plot_frame,
        x="baseline_utilization",
        y="collapse_probability",
        scatter=False,
        color="#222222",
        line_kws={"linewidth": 1.6},
        ax=ax,
    )
    ax.set_title("Fragility Curve: Collapse Probability vs Utilization")
    ax.set_xlabel("Baseline utilization")
    ax.set_ylabel("Collapse probability")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_cascade_distribution(frame: pd.DataFrame, path: Path) -> Path:
    """Plot the empirical cascade survival function."""

    plot_frame = frame.copy()
    if plot_frame.empty or "threshold" not in plot_frame.columns or "survival_probability" not in plot_frame.columns:
        plot_frame = pd.DataFrame([{"threshold": 1.0, "survival_probability": 0.0}])
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    sns.lineplot(data=plot_frame, x="threshold", y="survival_probability", marker="o", ax=ax)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title("Cascade Distribution (CCDF)")
    ax.set_xlabel("Cascade size threshold")
    ax.set_ylabel("P(size >= x)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_phase_transition(frame: pd.DataFrame, path: Path, *, feature: str, outcome: str) -> Path:
    """Plot a binned phase-transition curve."""

    plot_frame = frame.copy()
    if plot_frame.empty or feature not in plot_frame.columns or outcome not in plot_frame.columns:
        plot_frame = pd.DataFrame([{feature: 0.0, outcome: 0.0, "system_count": 0}])
    fig, ax = plt.subplots(figsize=(8.6, 5.3))
    sns.lineplot(data=plot_frame, x=feature, y=outcome, marker="o", ax=ax)
    ax.set_title(f"Phase Transition: {outcome} vs {feature}")
    ax.set_xlabel(feature.replace("_", " ").title())
    ax.set_ylabel(outcome.replace("_", " ").title())
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_feature_importance(frame: pd.DataFrame, path: Path) -> Path:
    """Plot ranked feature importance or correlations."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame([{"feature": "none", "score": 0.0}])
    fig, ax = plt.subplots(figsize=(8.8, max(4.5, 0.4 * len(plot_frame) + 1.6)))
    sns.barplot(data=plot_frame, x="score", y="feature", ax=ax, color="#a85d34")
    ax.set_title("Feature Importance for Collapse")
    ax.set_xlabel("Importance score")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_law_candidates(frame: pd.DataFrame, path: Path) -> Path:
    """Plot top candidate laws by fit quality."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame([{"formula": "none", "r2": 0.0}])
    display = plot_frame.head(12).copy()
    display["formula"] = display["formula"].astype(str).map(_short_label)
    fig, ax = plt.subplots(figsize=(9.6, max(4.8, 0.42 * len(display) + 1.5)))
    sns.barplot(data=display, x="r2", y="formula", ax=ax, color="#48736e")
    ax.set_title("Candidate Collapse Laws")
    ax.set_xlabel("R^2")
    ax.set_ylabel("")
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_collapse_heatmap(frame: pd.DataFrame, path: Path) -> Path:
    """Plot collapse probability by topology and utilization band."""

    plot_frame = frame.copy()
    required = {"topology_type", "baseline_utilization", "collapse_probability"}
    if plot_frame.empty or not required.issubset(plot_frame.columns):
        plot_frame = pd.DataFrame([{"topology_type": "none", "utilization_band": "0.0-0.1", "collapse_probability": 0.0}])
    else:
        plot_frame["utilization_band"] = pd.cut(
            plot_frame["baseline_utilization"].astype(float),
            bins=[0.0, 0.25, 0.5, 0.75, 1.0, float("inf")],
            labels=["0.0-0.25", "0.25-0.5", "0.5-0.75", "0.75-1.0", "1.0+"],
            include_lowest=True,
        ).astype(str)
        plot_frame = plot_frame.groupby(["topology_type", "utilization_band"], observed=False)["collapse_probability"].mean().reset_index()
    pivot = plot_frame.pivot(index="topology_type", columns="utilization_band", values="collapse_probability").fillna(0.0)
    fig, ax = plt.subplots(figsize=(9.0, max(4.8, 0.6 * len(pivot.index) + 2.0)))
    sns.heatmap(pivot, annot=True, cmap="mako", fmt=".2f", ax=ax)
    ax.set_title("Collapse Probability Heatmap")
    ax.set_xlabel("Baseline utilization band")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _short_label(value: str, *, width: int = 78) -> str:
    text = str(value)
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."
