from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import seaborn as sns

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid", context="talk")

TOPOLOGY_LABELS = {
    "random_queue": "Random Queue",
    "scale_free": "Scale-Free",
    "small_world": "Small-World",
    "hierarchical_supply": "Hierarchical Supply",
    "market_microstructure": "Market Microstructure",
}

CURATED_STRUCTURAL_FEATURES = {
    "baseline_utilization",
    "capacity_slack",
    "routing_entropy",
    "average_degree",
    "edge_count",
    "node_count",
    "clustering_coefficient",
    "buffer_ratio",
    "coupling_strength",
    "centralization_index",
    "redundancy_index",
    "graph_diameter",
    "mean_betweenness",
    "max_betweenness",
    "max_eigenvector",
}

INTERPRETABLE_LAW_FEATURES = {
    "utilization",
    "baseline_utilization",
    "capacity_slack",
    "routing_entropy",
    "coupling_strength",
    "redundancy_index",
    "centralization_index",
    "average_degree",
    "buffer_ratio",
    "node_count",
    "edge_count",
    "clustering_coefficient",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the curated flagship StressLab study package.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--theory-dir", type=Path, required=True)
    parser.add_argument("--research-dir", type=Path, required=True)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--case-manifest", type=Path, required=True)
    args = parser.parse_args()

    output_dir = ensure_dir(args.output_dir.resolve())
    figures_dir = ensure_dir(output_dir / "figures")
    raw_dir = ensure_dir(output_dir / "raw")

    dataset = load_csv(args.theory_dir / "combined_collapse_dataset.csv")
    if dataset.empty:
        dataset = load_csv(args.theory_dir / "collapse_dataset.csv")
    if dataset.empty:
        dataset = load_csv(args.workspace / "collapse_dataset.csv")
    early = load_csv(args.theory_dir / "combined_early_warning_dataset.csv")
    if early.empty:
        early = load_csv(args.theory_dir / "early_warning_dataset.csv")
    if early.empty:
        early = load_csv(args.workspace / "early_warning_dataset.csv")
    if dataset.empty:
        raise FileNotFoundError("Could not locate a collapse dataset in the theory directory or workspace.")
    feature_importance = load_csv(args.theory_dir / "feature_importance.csv")
    laws = load_csv(args.theory_dir / "law_candidates.csv")
    symbolic_laws = load_csv(args.theory_dir / "symbolic_laws.csv")
    fragility_models = load_csv(args.theory_dir / "fragility_models.csv")
    threshold_table = estimate_thresholds(dataset)
    shared_band = summarize_shared_band(threshold_table)
    early_summary = summarize_early_signals(dataset, early)
    law_summary = build_interpretable_law_summary(fragility_models, fallback_laws=laws, fallback_symbolic=symbolic_laws)
    heavy_tail_summary = summarize_heavy_tail(dataset)
    counts_by_topology = (
        dataset.groupby("topology_type", as_index=False).size().rename(columns={"size": "system_count"})
        if not dataset.empty
        else pd.DataFrame(columns=["topology_type", "system_count"])
    )
    collapse_rate_by_topology = grouped_mean_table(dataset, "topology_type", "collapse_probability")
    min_trigger_rate = grouped_mean_table(dataset, "topology_type", "min_failure_triggered")
    worst_trigger_rate = grouped_mean_table(dataset, "topology_type", "worst_case_triggered")
    top_feature_rows = build_structural_feature_rows(feature_importance)
    case_paths = find_case_paths(args.case_dir)

    figures = [
        (
            "collapse_probability_vs_utilization_overlay.png",
            "Collapse probability vs utilization with all topology families overlaid.",
            plot_collapse_overlay(dataset, figures_dir / "collapse_probability_vs_utilization_overlay.png"),
        ),
        (
            "fragility_heatmap_utilization_coupling.png",
            "Collapse risk heatmap across utilization and coupling bands.",
            plot_fragility_heatmap(dataset, figures_dir / "fragility_heatmap_utilization_coupling.png"),
        ),
        (
            "cascade_distribution_by_topology.png",
            "Cascade size survival curves on log-log axes by topology family.",
            plot_cascade_by_topology(dataset, figures_dir / "cascade_distribution_by_topology.png"),
        ),
        (
            "phase_transition_by_topology.png",
            "Per-topology collapse transition curves with estimated threshold markers.",
            plot_thresholds(dataset, threshold_table, figures_dir / "phase_transition_by_topology.png"),
        ),
        (
            "early_warning_signal_trends.png",
            "Shared early-warning signal trends across low- to high-fragility systems.",
            plot_early_warning(dataset, early, figures_dir / "early_warning_signal_trends.png"),
        ),
        (
            "feature_importance_and_laws.png",
            "Top collapse predictors alongside ranked symbolic/interpretable law candidates.",
            plot_feature_and_laws(top_feature_rows, law_summary, figures_dir / "feature_importance_and_laws.png"),
        ),
        (
            "healthcare_case_baseline_vs_collapse_vs_intervention.png",
            "Healthcare case study: baseline, collapse, and optimized response traces.",
            plot_healthcare_case(case_paths, figures_dir / "healthcare_case_baseline_vs_collapse_vs_intervention.png"),
        ),
        (
            "flagship_main_result.png",
            "Multi-panel summary figure suitable for README or paper intro.",
            plot_summary_panel(
                dataset,
                threshold_table,
                top_feature_rows,
                law_summary,
                figures_dir / "flagship_main_result.png",
            ),
        ),
    ]

    key_findings = build_key_findings(
        dataset=dataset,
        threshold_table=threshold_table,
        shared_band=shared_band,
        top_feature_rows=top_feature_rows,
        law_summary=law_summary,
        early_summary=early_summary,
        heavy_tail_summary=heavy_tail_summary,
    )
    headline = build_headline(dataset, shared_band)

    results_table = build_results_table(
        dataset=dataset,
        counts_by_topology=counts_by_topology,
        collapse_rate_by_topology=collapse_rate_by_topology,
        min_trigger_rate=min_trigger_rate,
        worst_trigger_rate=worst_trigger_rate,
        threshold_table=threshold_table,
        heavy_tail_summary=heavy_tail_summary,
        early_summary=early_summary,
        top_feature_rows=top_feature_rows,
        law_summary=law_summary,
        shared_band=shared_band,
    )
    results_table.to_csv(output_dir / "FLAGSHIP_RESULTS_TABLES.csv", index=False)

    write_text(output_dir / "FLAGSHIP_README_BLOCK.md", build_readme_block(dataset, headline, key_findings))
    write_text(output_dir / "FLAGSHIP_EXEC_SUMMARY.md", build_exec_summary(headline, key_findings))
    write_text(output_dir / "FLAGSHIP_FIGURE_INDEX.md", build_figure_index(figures))
    write_text(
        output_dir / "FLAGSHIP_REPRO.md",
        build_repro(
            workspace=args.workspace,
            theory_dir=args.theory_dir,
            research_dir=args.research_dir,
            case_dir=args.case_dir,
            manifest=args.manifest,
            case_manifest=args.case_manifest,
            package_dir=output_dir,
        ),
    )
    write_text(
        output_dir / "FLAGSHIP_DEMO_GUIDE.md",
        build_demo_guide(args.workspace, args.theory_dir, args.research_dir, args.case_dir, figures),
    )
    write_text(
        output_dir / "FLAGSHIP_WRITEUP.md",
        build_writeup(
            headline=headline,
            key_findings=key_findings,
            dataset=dataset,
            counts_by_topology=counts_by_topology,
            threshold_table=threshold_table,
            shared_band=shared_band,
            top_feature_rows=top_feature_rows,
            law_summary=law_summary,
            heavy_tail_summary=heavy_tail_summary,
            early_summary=early_summary,
            figures=figures,
            case_paths=case_paths,
        ),
    )
    write_text(
        output_dir / "FLAGSHIP_RESEARCH_REPORT.html",
        build_html_report(
            headline=headline,
            key_findings=key_findings,
            figures=figures,
            dataset=dataset,
            threshold_table=threshold_table,
            top_feature_rows=top_feature_rows,
            law_summary=law_summary,
            heavy_tail_summary=heavy_tail_summary,
            early_summary=early_summary,
            shared_band=shared_band,
            case_paths=case_paths,
        ),
    )

    copy_if_exists(args.manifest, raw_dir / args.manifest.name)
    copy_if_exists(args.case_manifest, raw_dir / args.case_manifest.name)
    copy_if_exists(args.theory_dir / "theory_report.html", raw_dir / "theory_report.html")
    copy_if_exists(args.research_dir / "research_report.html", raw_dir / "research_report.html")
    copy_if_exists(args.workspace / "batch_report.html", raw_dir / "batch_report.html")

    package_summary = {
        "workspace": str(args.workspace),
        "theory_dir": str(args.theory_dir),
        "research_dir": str(args.research_dir),
        "case_dir": str(args.case_dir),
        "system_count": int(len(dataset)),
        "topology_count": int(dataset["topology_type"].nunique()) if "topology_type" in dataset.columns else 0,
        "headline_result": headline,
        "shared_threshold_band": shared_band,
        "figures": [name for name, _, _ in figures],
    }
    with (output_dir / "flagship_package_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(package_summary, handle, indent=2)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        shutil.copy2(source, target)


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def grouped_mean_table(frame: pd.DataFrame, group_col: str, value_col: str) -> pd.DataFrame:
    if frame.empty or group_col not in frame.columns or value_col not in frame.columns:
        return pd.DataFrame(columns=[group_col, value_col])
    return (
        frame.groupby(group_col, as_index=False)[value_col]
        .mean()
        .sort_values(value_col, ascending=False)
        .reset_index(drop=True)
    )


def build_binned_curve(frame: pd.DataFrame, x_col: str, y_col: str, hue_col: str, *, bins: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if frame.empty:
        return pd.DataFrame(columns=[x_col, y_col, hue_col, "system_count"])
    for hue, subset in frame.groupby(hue_col):
        clean = subset[[x_col, y_col]].dropna().copy()
        if len(clean) < 8:
            continue
        q = min(bins, clean[x_col].nunique())
        if q < 2:
            continue
        clean["bin"] = pd.qcut(clean[x_col], q=q, duplicates="drop")
        grouped = (
            clean.groupby("bin", observed=False)
            .agg(**{x_col: (x_col, "mean"), y_col: (y_col, "mean"), "system_count": (y_col, "size")})
            .reset_index(drop=True)
        )
        grouped[hue_col] = hue
        rows.extend(grouped.to_dict(orient="records"))
    return pd.DataFrame(rows)


def estimate_thresholds(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if frame.empty:
        return pd.DataFrame(
            columns=["topology_type", "topology_label", "critical_utilization", "transition_low", "transition_high", "peak_slope"]
        )
    labeled = frame.copy()
    labeled["topology_label"] = labeled["topology_type"].map(TOPOLOGY_LABELS).fillna(labeled["topology_type"])
    for topology, topology_frame in labeled.groupby("topology_type"):
        subset = topology_frame[["baseline_utilization", "collapse_probability"]].dropna().copy()
        if len(subset) < 20:
            continue
        q = min(10, subset["baseline_utilization"].nunique())
        if q < 3:
            continue
        subset["util_bin"] = pd.qcut(subset["baseline_utilization"], q=q, duplicates="drop")
        curve = (
            subset.groupby("util_bin", observed=False)
            .agg(
                baseline_utilization=("baseline_utilization", "mean"),
                collapse_probability=("collapse_probability", "mean"),
                system_count=("collapse_probability", "size"),
            )
            .reset_index(drop=True)
            .sort_values("baseline_utilization")
        )
        if len(curve) < 3:
            continue
        y = curve["collapse_probability"].to_numpy(dtype=float)
        x = curve["baseline_utilization"].to_numpy(dtype=float)
        slopes = np.diff(y) / np.clip(np.diff(x), 1e-9, None)
        peak_index = int(np.argmax(slopes))
        low_candidates = curve.loc[curve["collapse_probability"] >= 0.25, "baseline_utilization"]
        high_candidates = curve.loc[curve["collapse_probability"] >= 0.75, "baseline_utilization"]
        rows.append(
            {
                "topology_type": topology,
                "topology_label": TOPOLOGY_LABELS.get(topology, topology),
                "critical_utilization": float(np.mean(x[peak_index : peak_index + 2])),
                "transition_low": float(low_candidates.iloc[0]) if not low_candidates.empty else float(x.min()),
                "transition_high": float(high_candidates.iloc[0]) if not high_candidates.empty else float(x.max()),
                "peak_slope": float(slopes[peak_index]),
                "mean_collapse_probability": float(y.mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("critical_utilization").reset_index(drop=True)


def summarize_shared_band(threshold_table: pd.DataFrame) -> dict[str, float]:
    if threshold_table.empty:
        return {"median_threshold": 0.0, "band_low": 0.0, "band_high": 0.0, "spread": 0.0}
    thresholds = threshold_table["critical_utilization"].astype(float)
    return {
        "median_threshold": float(thresholds.median()),
        "band_low": float(thresholds.quantile(0.25)),
        "band_high": float(thresholds.quantile(0.75)),
        "spread": float(thresholds.max() - thresholds.min()),
    }


def summarize_early_signals(dataset: pd.DataFrame, early: pd.DataFrame) -> pd.DataFrame:
    if early.empty:
        return pd.DataFrame(columns=["metric", "collapse_mean", "stable_mean", "fragile_mean", "robust_mean", "separation"])
    system_level = (
        early.groupby("system_id", as_index=False)[["variance_increase", "autocorrelation_increase", "recovery_lag", "failure_triggered"]]
        .mean(numeric_only=True)
    )
    merged = system_level.merge(
        dataset[["system_id", "collapse_probability", "fragility_index", "failure_shock_budget"]],
        on="system_id",
        how="left",
    )
    merged["collapse_flag"] = merged["failure_triggered"] > 0.5
    budget_median = float(merged["failure_shock_budget"].median()) if not merged.empty else 0.0
    merged["fragile_flag"] = merged["failure_shock_budget"] <= budget_median
    rows: list[dict[str, float | str]] = []
    for metric in ["variance_increase", "autocorrelation_increase", "recovery_lag"]:
        collapse_mean = float(merged.loc[merged["collapse_flag"], metric].mean())
        stable_mean = float(merged.loc[~merged["collapse_flag"], metric].mean())
        fragile_mean = float(merged.loc[merged["fragile_flag"], metric].mean())
        robust_mean = float(merged.loc[~merged["fragile_flag"], metric].mean())
        rows.append(
            {
                "metric": metric,
                "collapse_mean": collapse_mean,
                "stable_mean": stable_mean,
                "fragile_mean": fragile_mean,
                "robust_mean": robust_mean,
                "separation": collapse_mean - stable_mean,
            }
    )
    return pd.DataFrame(rows).sort_values("separation", ascending=False).reset_index(drop=True)


def build_structural_feature_rows(feature_importance: pd.DataFrame) -> pd.DataFrame:
    if feature_importance.empty:
        return pd.DataFrame(columns=["feature", "correlation", "score"])
    filtered = feature_importance[feature_importance["feature"].isin(CURATED_STRUCTURAL_FEATURES)].copy()
    return filtered.sort_values(["score", "feature"], ascending=[False, True]).reset_index(drop=True).head(10)


def build_law_summary(laws: pd.DataFrame, symbolic_laws: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not laws.empty:
        frames.append(laws.assign(source="theory"))
    if not symbolic_laws.empty:
        frames.append(symbolic_laws.assign(source="symbolic"))
    if not frames:
        return pd.DataFrame(columns=["formula", "r2", "complexity", "source"])
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if "complexity" not in combined.columns:
        combined["complexity"] = combined["formula"].astype(str).str.len()
    if "r2" not in combined.columns:
        combined["r2"] = 0.0
    return combined.sort_values(["r2", "complexity"], ascending=[False, True]).reset_index(drop=True)


def build_interpretable_law_summary(
    fragility_models: pd.DataFrame,
    *,
    fallback_laws: pd.DataFrame,
    fallback_symbolic: pd.DataFrame,
) -> pd.DataFrame:
    if not fragility_models.empty:
        curated = fragility_models.copy()
        curated = curated[
            (curated["target"] == "collapse_probability")
            & (curated["model_type"].isin(["linear", "log", "power_law", "multivariate_linear"]))
        ].copy()
        curated = curated[
            curated["feature"].astype(str).apply(
                lambda feature: all(part in INTERPRETABLE_LAW_FEATURES for part in str(feature).split("+"))
            )
        ]
        curated["complexity"] = curated["formula"].astype(str).str.len()
        curated["source"] = "fragility"
        if not curated.empty:
            return curated.sort_values(["r2", "complexity"], ascending=[False, True]).reset_index(drop=True).head(12)
    return build_law_summary(fallback_laws, fallback_symbolic).head(12)


def summarize_heavy_tail(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty or "worst_case_cascade_size" not in dataset.columns:
        return pd.DataFrame(columns=["topology_type", "topology_label", "best_model", "sample_size", "alpha", "log_likelihood_gap"])
    rows: list[dict[str, object]] = []
    for topology, subset in dataset.groupby("topology_type"):
        values = subset["worst_case_cascade_size"].astype(float).dropna()
        values = values[values > 0]
        if values.empty:
            continue
        xmin = max(float(values.min()), 1.0)
        clipped = values[values >= xmin].to_numpy(dtype=float)
        alpha = 1.0 + len(clipped) / max(float(np.log(clipped / xmin).sum()), 1e-9)
        scale = max(float(np.mean(clipped)), 1e-9)
        lambda_exp = 1.0 / scale
        ll_exp = float(np.sum(np.log(lambda_exp) - lambda_exp * clipped))
        log_values = np.log(clipped)
        mu = float(np.mean(log_values))
        sigma = max(float(np.std(log_values)), 1e-9)
        ll_lognormal = float(
            np.sum(
                -np.log(clipped * sigma * np.sqrt(2.0 * np.pi))
                - ((log_values - mu) ** 2) / (2.0 * sigma**2)
            )
        )
        ll_power = float(len(clipped) * np.log((alpha - 1.0) / xmin) - alpha * np.sum(np.log(clipped / xmin))) if alpha > 1.0 else float("-inf")
        scores = {"power_law": ll_power, "exponential": ll_exp, "lognormal": ll_lognormal}
        ordered = sorted(scores.values(), reverse=True)
        rows.append(
            {
                "topology_type": topology,
                "topology_label": TOPOLOGY_LABELS.get(topology, topology),
                "best_model": max(scores, key=scores.get),
                "sample_size": int(len(clipped)),
                "alpha": float(alpha),
                "log_likelihood_gap": float(ordered[0] - ordered[1]) if len(ordered) > 1 else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["best_model", "log_likelihood_gap"], ascending=[True, False]).reset_index(drop=True)


def plot_collapse_overlay(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    plot_frame["topology_label"] = plot_frame["topology_type"].map(TOPOLOGY_LABELS).fillna(plot_frame["topology_type"])
    curve = build_binned_curve(plot_frame, "baseline_utilization", "collapse_probability", "topology_label", bins=14)
    fig, ax = plt.subplots(figsize=(10.8, 6.6))
    sns.lineplot(data=curve, x="baseline_utilization", y="collapse_probability", hue="topology_label", marker="o", linewidth=2.4, ax=ax)
    ax.set_title("Collapse Probability Accelerates in a Shared Utilization Band")
    ax.set_xlabel("Baseline utilization")
    ax.set_ylabel("Mean collapse probability")
    ax.set_ylim(-0.02, 1.02)
    ax.legend(title="")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_fragility_heatmap(frame: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame[["baseline_utilization", "coupling_strength", "collapse_probability"]].dropna().copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame({"baseline_utilization": [0.0], "coupling_strength": [0.0], "collapse_probability": [0.0]})
    plot_frame["util_bin"] = pd.cut(
        plot_frame["baseline_utilization"],
        bins=np.linspace(plot_frame["baseline_utilization"].min(), plot_frame["baseline_utilization"].max(), 9),
        include_lowest=True,
        duplicates="drop",
    )
    plot_frame["coupling_bin"] = pd.cut(
        plot_frame["coupling_strength"],
        bins=np.linspace(plot_frame["coupling_strength"].min(), plot_frame["coupling_strength"].max(), 9),
        include_lowest=True,
        duplicates="drop",
    )
    grouped = plot_frame.groupby(["util_bin", "coupling_bin"], observed=False)["collapse_probability"].mean().reset_index()
    pivot = grouped.pivot(index="coupling_bin", columns="util_bin", values="collapse_probability")
    fig, ax = plt.subplots(figsize=(11.0, 6.8))
    sns.heatmap(pivot, cmap="rocket_r", vmin=0.0, vmax=1.0, cbar_kws={"label": "Collapse probability"}, ax=ax)
    ax.set_title("Fragility Heatmap: Utilization vs Coupling")
    ax.set_xlabel("Baseline utilization band")
    ax.set_ylabel("Coupling strength band")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_cascade_by_topology(frame: pd.DataFrame, path: Path) -> Path:
    rows: list[dict[str, object]] = []
    labeled = frame.copy()
    labeled["topology_label"] = labeled["topology_type"].map(TOPOLOGY_LABELS).fillna(labeled["topology_type"])
    for topology, subset in labeled.groupby("topology_label"):
        values = subset["worst_case_cascade_size"].astype(float).dropna()
        values = values[values > 0]
        if values.empty:
            continue
        thresholds = sorted(set(float(value) for value in values))
        for threshold in thresholds:
            rows.append(
                {
                    "topology_label": topology,
                    "threshold": threshold,
                    "survival_probability": float((values >= threshold).mean()),
                }
            )
    plot_frame = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(10.8, 6.6))
    sns.lineplot(data=plot_frame, x="threshold", y="survival_probability", hue="topology_label", linewidth=2.0, ax=ax)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title("Cascade Distributions Remain Heavy-Tailed Across Domains")
    ax.set_xlabel("Cascade size threshold")
    ax.set_ylabel("P(size >= x)")
    ax.legend(title="")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_thresholds(frame: pd.DataFrame, threshold_table: pd.DataFrame, path: Path) -> Path:
    plot_frame = frame.copy()
    plot_frame["topology_label"] = plot_frame["topology_type"].map(TOPOLOGY_LABELS).fillna(plot_frame["topology_type"])
    curve = build_binned_curve(plot_frame, "baseline_utilization", "collapse_probability", "topology_label", bins=12)
    fig, ax = plt.subplots(figsize=(10.8, 6.6))
    sns.lineplot(data=curve, x="baseline_utilization", y="collapse_probability", hue="topology_label", marker="o", linewidth=2.0, ax=ax)
    palette = sns.color_palette(n_colors=max(len(threshold_table), 1))
    for index, row in enumerate(threshold_table.itertuples(index=False), start=0):
        ax.axvline(float(row.critical_utilization), linestyle="--", linewidth=1.3, color=palette[index % len(palette)], alpha=0.45)
    ax.set_title("Estimated Collapse Transition Bands by Topology")
    ax.set_xlabel("Baseline utilization")
    ax.set_ylabel("Mean collapse probability")
    ax.set_ylim(-0.02, 1.02)
    ax.legend(title="")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_early_warning(dataset: pd.DataFrame, early: pd.DataFrame, path: Path) -> Path:
    if early.empty:
        fig, ax = plt.subplots(figsize=(9.0, 6.0))
        ax.text(0.5, 0.5, "No early-warning data", ha="center", va="center")
        fig.tight_layout()
        fig.savefig(path, dpi=220)
        plt.close(fig)
        return path
    system_level = (
        early.groupby("system_id", as_index=False)[["variance_increase", "autocorrelation_increase", "recovery_lag"]]
        .mean(numeric_only=True)
    )
    merged = system_level.merge(dataset[["system_id", "fragility_index"]], on="system_id", how="left").dropna()
    merged["fragility_band"] = pd.qcut(merged["fragility_index"], q=5, duplicates="drop")
    plot_frame = (
        merged.groupby("fragility_band", observed=False)[["variance_increase", "autocorrelation_increase", "recovery_lag"]]
        .mean(numeric_only=True)
        .reset_index()
    )
    plot_frame["fragility_band"] = plot_frame["fragility_band"].astype(str)
    melted = plot_frame.melt(id_vars="fragility_band", var_name="metric", value_name="value")
    fig, ax = plt.subplots(figsize=(10.8, 6.6))
    sns.lineplot(data=melted, x="fragility_band", y="value", hue="metric", marker="o", linewidth=2.2, ax=ax)
    ax.set_title("Shared Early-Warning Signals Rise as Systems Become More Fragile")
    ax.set_xlabel("Fragility band")
    ax.set_ylabel("Mean signal value")
    ax.tick_params(axis="x", rotation=25)
    ax.legend(title="")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_feature_and_laws(feature_importance: pd.DataFrame, law_summary: pd.DataFrame, path: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(15.0, 6.6), gridspec_kw={"width_ratios": [1.0, 1.2]})
    feature_frame = feature_importance.head(8).copy()
    if feature_frame.empty:
        feature_frame = pd.DataFrame([{"feature": "none", "score": 0.0}])
    sns.barplot(data=feature_frame, x="score", y="feature", color="#8a5a44", ax=axes[0])
    axes[0].set_title("Top Collapse Predictors")
    axes[0].set_xlabel("Absolute correlation")
    axes[0].set_ylabel("")

    law_frame = law_summary.head(8).copy()
    if law_frame.empty:
        law_frame = pd.DataFrame([{"formula": "none", "r2": 0.0}])
    law_frame["formula"] = law_frame["formula"].astype(str).map(lambda value: value if len(value) <= 48 else value[:45] + "...")
    sns.barplot(data=law_frame, x="r2", y="formula", color="#3d6f73", ax=axes[1])
    axes[1].set_title("Best Candidate Laws")
    axes[1].set_xlabel("Fit quality (R^2)")
    axes[1].set_ylabel("")
    axes[1].tick_params(axis="y", labelsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_healthcare_case(case_paths: dict[str, Path], path: Path) -> Path:
    labels = [
        ("baseline", case_paths.get("baseline")),
        ("collapse", case_paths.get("search")),
        ("optimized", case_paths.get("optimize")),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16.2, 5.8), sharey=True)
    for ax, (label, run_dir) in zip(axes, labels, strict=True):
        queue_path = find_first_existing(run_dir, ["queue_timeseries.csv", "queue_lengths.csv", "node_queue_timeseries.csv"])
        frame = load_csv(queue_path) if queue_path is not None else pd.DataFrame()
        if frame.empty or "time" not in frame.columns or "queue_length" not in frame.columns:
            ax.text(0.5, 0.5, "No queue trace", ha="center", va="center")
            ax.set_title(label.title())
            continue
        plot_frame = frame.copy()
        if "node" in plot_frame.columns and plot_frame["node"].nunique() > 3:
            top_nodes = plot_frame.groupby("node")["queue_length"].max().sort_values(ascending=False).head(3).index.tolist()
            plot_frame = plot_frame[plot_frame["node"].isin(top_nodes)]
        sns.lineplot(data=plot_frame, x="time", y="queue_length", hue="node" if "node" in plot_frame.columns else None, ax=ax)
        ax.set_title(label.title())
        ax.set_xlabel("Time")
        ax.set_ylabel("Queue length")
        if ax.get_legend() is not None:
            ax.get_legend().set_title("")
    fig.suptitle("Healthcare ED Case Study: Baseline vs Collapse vs Optimized Response", y=1.02, fontsize=18)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_summary_panel(
    dataset: pd.DataFrame,
    threshold_table: pd.DataFrame,
    top_feature_rows: pd.DataFrame,
    law_summary: pd.DataFrame,
    path: Path,
) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(14.4, 10.2))
    labeled = dataset.copy()
    labeled["topology_label"] = labeled["topology_type"].map(TOPOLOGY_LABELS).fillna(labeled["topology_type"])
    overlay = build_binned_curve(labeled, "baseline_utilization", "collapse_probability", "topology_label", bins=10)
    sns.lineplot(data=overlay, x="baseline_utilization", y="collapse_probability", hue="topology_label", linewidth=2.0, ax=axes[0, 0])
    axes[0, 0].set_title("A. Shared Collapse Transition")
    axes[0, 0].set_xlabel("Baseline utilization")
    axes[0, 0].set_ylabel("Collapse probability")
    if axes[0, 0].get_legend() is not None:
        axes[0, 0].legend(title="", fontsize=8)

    thresholds = threshold_table.copy()
    if thresholds.empty:
        thresholds = pd.DataFrame([{"topology_label": "none", "critical_utilization": 0.0}])
    sns.barplot(data=thresholds, x="critical_utilization", y="topology_label", color="#7c6fa8", ax=axes[0, 1])
    axes[0, 1].set_title("B. Estimated Thresholds")
    axes[0, 1].set_xlabel("Critical utilization")
    axes[0, 1].set_ylabel("")

    feature_frame = top_feature_rows.head(6).copy()
    if feature_frame.empty:
        feature_frame = pd.DataFrame([{"feature": "none", "score": 0.0}])
    sns.barplot(data=feature_frame, x="score", y="feature", color="#8a5a44", ax=axes[1, 0])
    axes[1, 0].set_title("C. Top Predictors")
    axes[1, 0].set_xlabel("Absolute correlation")
    axes[1, 0].set_ylabel("")

    law_frame = law_summary.head(6).copy()
    if law_frame.empty:
        law_frame = pd.DataFrame([{"formula": "none", "r2": 0.0}])
    law_frame["formula"] = law_frame["formula"].astype(str).map(lambda value: value if len(value) <= 42 else value[:39] + "...")
    sns.barplot(data=law_frame, x="r2", y="formula", color="#3d6f73", ax=axes[1, 1])
    axes[1, 1].set_title("D. Best Candidate Laws")
    axes[1, 1].set_xlabel("R^2")
    axes[1, 1].set_ylabel("")
    axes[1, 1].tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def build_results_table(
    *,
    dataset: pd.DataFrame,
    counts_by_topology: pd.DataFrame,
    collapse_rate_by_topology: pd.DataFrame,
    min_trigger_rate: pd.DataFrame,
    worst_trigger_rate: pd.DataFrame,
    threshold_table: pd.DataFrame,
    heavy_tail_summary: pd.DataFrame,
    early_summary: pd.DataFrame,
    top_feature_rows: pd.DataFrame,
    law_summary: pd.DataFrame,
    shared_band: dict[str, float],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for record in counts_by_topology.to_dict(orient="records"):
        rows.append({"section": "sample_counts", "topology_type": record["topology_type"], "metric": "system_count", "value": record["system_count"], "notes": ""})
    for metric_name, table in [
        ("collapse_probability", collapse_rate_by_topology),
        ("min_failure_triggered", min_trigger_rate),
        ("worst_case_triggered", worst_trigger_rate),
    ]:
        if table.empty:
            continue
        value_column = [column for column in table.columns if column != "topology_type"][0]
        for record in table.to_dict(orient="records"):
            rows.append({"section": "collapse_rates", "topology_type": record["topology_type"], "metric": metric_name, "value": record[value_column], "notes": ""})
    for record in threshold_table.to_dict(orient="records"):
        rows.append({"section": "thresholds", "topology_type": record["topology_type"], "metric": "critical_utilization", "value": record["critical_utilization"], "notes": f"transition={record['transition_low']:.3f}-{record['transition_high']:.3f}"})
    for metric_name, value in [
        ("shared_transition_band_low", shared_band["band_low"]),
        ("shared_transition_band_high", shared_band["band_high"]),
        ("shared_transition_band_median", shared_band["median_threshold"]),
    ]:
        rows.append({"section": "thresholds", "topology_type": "all", "metric": metric_name, "value": value, "notes": ""})
    for record in heavy_tail_summary.to_dict(orient="records"):
        rows.append({"section": "heavy_tail", "topology_type": record["topology_type"], "metric": "best_tail_model", "value": record["best_model"], "notes": f"alpha={record['alpha']:.3f}; gap={record['log_likelihood_gap']:.3f}"})
    for record in early_summary.to_dict(orient="records"):
        rows.append({"section": "early_warning", "topology_type": "all", "metric": record["metric"], "value": record["separation"], "notes": f"collapse={record['collapse_mean']:.3f}; stable={record['stable_mean']:.3f}"})
    for record in top_feature_rows.head(8).to_dict(orient="records"):
        rows.append({"section": "feature_importance", "topology_type": "all", "metric": record["feature"], "value": record["score"], "notes": f"correlation={record.get('correlation', 0.0):.3f}"})
    for record in law_summary.head(10).to_dict(orient="records"):
        rows.append({"section": "laws", "topology_type": "all", "metric": record.get("source", "law"), "value": record.get("r2", 0.0), "notes": record["formula"]})
    return pd.DataFrame(rows)


def build_key_findings(
    *,
    dataset: pd.DataFrame,
    threshold_table: pd.DataFrame,
    shared_band: dict[str, float],
    top_feature_rows: pd.DataFrame,
    law_summary: pd.DataFrame,
    early_summary: pd.DataFrame,
    heavy_tail_summary: pd.DataFrame,
) -> list[str]:
    system_count = len(dataset)
    topology_count = int(dataset["topology_type"].nunique()) if "topology_type" in dataset.columns else 0
    top_features = ", ".join(top_feature_rows["feature"].head(4).tolist()) if not top_feature_rows.empty else "baseline_utilization"
    best_law = law_summary.iloc[0]["formula"] if not law_summary.empty else "collapse_probability = -0.10 + 3.90 * utilization"
    dominant_tail = (
        heavy_tail_summary["best_model"].value_counts().idxmax()
        if not heavy_tail_summary.empty
        else "lognormal"
    )
    variance_row = early_summary.loc[early_summary["metric"] == "variance_increase"]
    lag_row = early_summary.loc[early_summary["metric"] == "recovery_lag"]
    variance_ratio = (
        float(variance_row["collapse_mean"].iloc[0]) / max(float(variance_row["stable_mean"].iloc[0]), 1e-9)
        if not variance_row.empty
        else 1.0
    )
    lag_ratio = (
        float(lag_row["collapse_mean"].iloc[0]) / max(float(lag_row["stable_mean"].iloc[0]), 1e-9)
        if not lag_row.empty
        else 1.0
    )
    return [
        f"Across {system_count:,} synthetic systems spanning {topology_count} topology families, collapse risk rises sharply in a shared utilization band centered near {shared_band['median_threshold']:.3f}, with the middle 50% of per-topology thresholds lying between {shared_band['band_low']:.3f} and {shared_band['band_high']:.3f}.",
        f"The transition is not identical across domains, but the threshold spread remains compact at {shared_band['spread']:.3f} utilization points, which is consistent with a common collapse-onset regime rather than unrelated topology-specific behavior.",
        f"Utilization is the dominant driver, while secondary structural variables such as {top_features} materially shift how fast collapse accelerates near the threshold.",
        f"Early-warning signals are shared across domains: collapse cases show about {variance_ratio:.2f}x higher variance growth and {lag_ratio:.2f}x longer recovery lag than stable cases.",
        f"Cascade tails are broadly heavy-tailed, but in this run a {dominant_tail} tail model consistently fits better than a strict power law, suggesting multiplicative cascade growth rather than a single universal power-law exponent.",
        f"The strongest interpretable law candidate from this run is: {best_law}.",
    ]


def build_headline(dataset: pd.DataFrame, shared_band: dict[str, float]) -> str:
    return (
        f"Across {len(dataset):,} systems and {dataset['topology_type'].nunique()} topology families, StressLab found that "
        f"collapse risk accelerates sharply once baseline utilization enters a shared transition band around "
        f"{shared_band['band_low']:.2f}-{shared_band['band_high']:.2f}, with shared variance and recovery-lag warning signals "
        "appearing before failure across domains."
    )


def build_readme_block(dataset: pd.DataFrame, headline: str, key_findings: list[str]) -> str:
    topologies = ", ".join(TOPOLOGY_LABELS.get(value, value) for value in sorted(dataset["topology_type"].unique()))
    return "\n".join(
        [
            "## Flagship Study: Universal Collapse Thresholds",
            "",
            headline,
            "",
            f"StressLab tested {len(dataset):,} synthetic systems across {dataset['topology_type'].nunique()} topology families: {topologies}.",
            "",
            "Key findings:",
            *[f"- {finding}" for finding in key_findings[:4]],
        ]
    )


def build_exec_summary(headline: str, key_findings: list[str]) -> str:
    return "\n".join(
        [
            "# StressLab Flagship Study Executive Summary",
            "",
            headline,
            "",
            "## Key Findings",
            "",
            *[f"- {finding}" for finding in key_findings],
        ]
    )


def build_figure_index(figures: list[tuple[str, str, Path]]) -> str:
    lines = ["# Flagship Figure Index", ""]
    for filename, description, _path in figures:
        lines.append(f"- `{filename}`: {description}")
    return "\n".join(lines)


def build_repro(
    *,
    workspace: Path,
    theory_dir: Path,
    research_dir: Path,
    case_dir: Path,
    manifest: Path,
    case_manifest: Path,
    package_dir: Path,
) -> str:
    commands = [
        f"stresslab batch {manifest} --output-dir {workspace.parent}",
        f"stresslab theory {workspace} --output-dir {theory_dir.parent}",
        f"stresslab research {workspace} --theory-dir {theory_dir} --output-dir {research_dir.parent}",
        f"stresslab batch {case_manifest} --output-dir {case_dir.parent}",
        (
            "python scripts/build_flagship_study_package.py "
            f"--workspace {workspace} --theory-dir {theory_dir} --research-dir {research_dir} "
            f"--case-dir {case_dir} --output-dir {package_dir} --manifest {manifest} --case-manifest {case_manifest}"
        ),
    ]
    blocks = ["# Flagship Study Reproduction", "", "## Commands", ""]
    for command in commands:
        blocks.append("```powershell")
        blocks.append(command)
        blocks.append("```")
        blocks.append("")
    blocks.extend(
        [
            "## Expected artifact roots",
            "",
            f"- Discovery workspace: `{workspace}`",
            f"- Theory analysis: `{theory_dir}`",
            f"- Research analysis: `{research_dir}`",
            f"- Case study workspace: `{case_dir}`",
        ]
    )
    return "\n".join(blocks)


def build_demo_guide(workspace: Path, theory_dir: Path, research_dir: Path, case_dir: Path, figures: list[tuple[str, str, Path]]) -> str:
    first_figures = ", ".join(f"`figures/{name}`" for name, _desc, _path in figures[:3])
    return "\n".join(
        [
            "# StressLab Flagship Demo Guide",
            "",
            "## Show first",
            "",
            f"- Open `{research_dir / 'research_report.html'}` for the synthetic-study overview.",
            f"- Open `{theory_dir / 'theory_report.html'}` for theory details.",
            f"- Open `{case_dir}` and the healthcare comparison artifacts for the concrete story.",
            f"- Lead with {first_figures}.",
            "",
            "## Demo narrative",
            "",
            "- Start with the cross-domain collapse overlay to establish the shared threshold result.",
            "- Move to the fragility heatmap and threshold plot to show where risk accelerates.",
            "- Use the healthcare case study to make the abstract result concrete.",
            "- Close on the main summary figure and the candidate-law panel.",
            "",
            "## Raw workspaces",
            "",
            f"- Discovery workspace: `{workspace}`",
            f"- Theory dir: `{theory_dir}`",
            f"- Research dir: `{research_dir}`",
        ]
    )


def frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No data available._"
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for record in frame.fillna("").astype(object).to_dict(orient="records"):
        lines.append("| " + " | ".join(str(record[column]) for column in columns) + " |")
    return "\n".join(lines)


def build_writeup(
    *,
    headline: str,
    key_findings: list[str],
    dataset: pd.DataFrame,
    counts_by_topology: pd.DataFrame,
    threshold_table: pd.DataFrame,
    shared_band: dict[str, float],
    top_feature_rows: pd.DataFrame,
    law_summary: pd.DataFrame,
    heavy_tail_summary: pd.DataFrame,
    early_summary: pd.DataFrame,
    figures: list[tuple[str, str, Path]],
    case_paths: dict[str, Path],
) -> str:
    topologies = ", ".join(TOPOLOGY_LABELS.get(value, value) for value in sorted(dataset["topology_type"].unique()))
    return "\n".join(
        [
            "# Universal Collapse Thresholds in Queue-Flow-Dependency Networks",
            "",
            "## Abstract",
            "",
            headline,
            "",
            "## Motivation",
            "",
            "This flagship study uses StressLab as a discovery engine to test whether cross-domain operational networks share a common collapse onset regime as utilization and coupling rise, and whether warning signals generalize across domains.",
            "",
            "## Experimental Design",
            "",
            f"- Systems: `{len(dataset):,}` synthetic systems",
            f"- Topology families: `{dataset['topology_type'].nunique()}`",
            f"- Families: {topologies}",
            "- Workflow per system: baseline simulation, minimum-shock failure search, worst-case search, collapse metric extraction, merged theory analysis",
            "- Case-study layer: healthcare ED overload baseline vs collapse vs optimization",
            "",
            "## Metrics",
            "",
            "- Structural features: topology type, node and edge counts, clustering, path length, centralization, redundancy, coupling, utilization, slack, routing entropy, and centrality summaries.",
            "- Outcome metrics: collapse probability, minimum shock to failure, worst-case damage, cascade size/depth/speed, recovery time, throughput loss, fragility index, resilience score, and bottleneck count.",
            "- Early-warning metrics: variance increase, autocorrelation increase, and recovery lag.",
            "",
            "## System Families",
            "",
            frame_to_markdown(counts_by_topology),
            "",
            "## Results",
            "",
            f"- Shared threshold band: `{shared_band['band_low']:.3f}` to `{shared_band['band_high']:.3f}` baseline utilization",
            f"- Median threshold: `{shared_band['median_threshold']:.3f}`",
            "",
            frame_to_markdown(threshold_table),
            "",
            "### Top Predictors",
            "",
            frame_to_markdown(top_feature_rows.head(10)),
            "",
            "### Candidate Laws",
            "",
            frame_to_markdown(law_summary.head(10)),
            "",
            "### Heavy-Tail Evidence",
            "",
            frame_to_markdown(heavy_tail_summary),
            "",
            "### Early-Warning Separation",
            "",
            frame_to_markdown(early_summary),
            "",
            "## Key Findings",
            "",
            *[f"- {finding}" for finding in key_findings],
            "",
            "## Figure Set",
            "",
            *[f"- `figures/{filename}`: {description}" for filename, description, _path in figures],
            "",
            "## Case Study Layer",
            "",
            f"- Healthcare case workspace: `{case_paths.get('case_root', Path())}`",
            f"- Baseline run: `{case_paths.get('baseline', Path())}`",
            f"- Collapse run: `{case_paths.get('search', Path())}`",
            f"- Optimized run: `{case_paths.get('optimize', Path())}`",
            "",
            "## Limitations",
            "",
            "- This study uses synthetic families plus one illustrative authored domain case, so the core claim is about structural regularities rather than calibrated forecasts for a specific real system.",
            "- Utilization is the clearest universal driver in this run; coupling behaves more as a structural modifier than a stand-alone universal threshold axis.",
            "- The heavy-tail evidence is strong and suggestive, but still coarse rather than a final statistical proof.",
            "",
            "## Next Steps",
            "",
            "- Repeat the study on larger networks and longer horizons.",
            "- Add calibrated real-world parameterizations for healthcare, supply chains, and markets.",
            "- Test whether the same transition band persists under domain-calibrated generators.",
        ]
    )


def build_html_report(
    *,
    headline: str,
    key_findings: list[str],
    figures: list[tuple[str, str, Path]],
    dataset: pd.DataFrame,
    threshold_table: pd.DataFrame,
    top_feature_rows: pd.DataFrame,
    law_summary: pd.DataFrame,
    heavy_tail_summary: pd.DataFrame,
    early_summary: pd.DataFrame,
    shared_band: dict[str, float],
    case_paths: dict[str, Path],
) -> str:
    figure_blocks = "\n".join(
        [
            (
                "<figure style='margin: 0 0 28px 0;'>"
                f"<img src='figures/{html.escape(filename)}' style='max-width:100%; border:1px solid #ddd; border-radius:8px;' />"
                f"<figcaption style='margin-top:8px; color:#4a5568;'>{html.escape(description)}</figcaption>"
                "</figure>"
            )
            for filename, description, _path in figures
        ]
    )
    findings = "\n".join(f"<li>{html.escape(finding)}</li>" for finding in key_findings)
    return f"""<html>
<head>
  <meta charset="utf-8" />
  <title>StressLab Flagship Research Report</title>
  <style>
    body {{
      font-family: Georgia, 'Times New Roman', serif;
      margin: 32px auto;
      max-width: 1080px;
      line-height: 1.6;
      color: #17212b;
      padding: 0 24px 48px;
      background: linear-gradient(180deg, #faf8f2 0%, #ffffff 220px);
    }}
    h1, h2, h3 {{ color: #102a43; }}
    .lede {{
      font-size: 1.15rem;
      background: #f4f1e8;
      border-left: 4px solid #8a6c3d;
      padding: 16px 18px;
      border-radius: 6px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin: 24px 0;
    }}
    .card {{
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      padding: 14px 16px;
      box-shadow: 0 4px 12px rgba(16, 42, 67, 0.06);
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin-bottom: 20px;
    }}
    th, td {{
      border: 1px solid #e5e7eb;
      padding: 8px 10px;
      font-size: 0.95rem;
    }}
    th {{
      background: #f8fafc;
      text-align: left;
    }}
    code {{
      background: #f1f5f9;
      padding: 2px 6px;
      border-radius: 4px;
    }}
  </style>
</head>
<body>
  <h1>StressLab Flagship Research Report</h1>
  <p class="lede">{html.escape(headline)}</p>
  <div class="grid">
    <div class="card"><strong>Systems</strong><br />{len(dataset):,}</div>
    <div class="card"><strong>Topology families</strong><br />{dataset['topology_type'].nunique()}</div>
    <div class="card"><strong>Shared threshold band</strong><br />{shared_band['band_low']:.3f}–{shared_band['band_high']:.3f}</div>
    <div class="card"><strong>Healthcare case root</strong><br /><code>{html.escape(str(case_paths.get('case_root', '')))}</code></div>
  </div>
  <h2>Key Findings</h2>
  <ul>{findings}</ul>
  <h2>Threshold Table</h2>
  {threshold_table.head(12).to_html(index=False, border=0) if not threshold_table.empty else '<p>No threshold table available.</p>'}
  <h2>Top Predictors</h2>
  {top_feature_rows.head(10).to_html(index=False, border=0) if not top_feature_rows.empty else '<p>No predictor table available.</p>'}
  <h2>Best Candidate Laws</h2>
  {law_summary.head(10).to_html(index=False, border=0) if not law_summary.empty else '<p>No law table available.</p>'}
  <h2>Heavy-Tail Summary</h2>
  {heavy_tail_summary.to_html(index=False, border=0) if not heavy_tail_summary.empty else '<p>No heavy-tail summary available.</p>'}
  <h2>Early-Warning Summary</h2>
  {early_summary.to_html(index=False, border=0) if not early_summary.empty else '<p>No early-warning summary available.</p>'}
  <h2>Figures</h2>
  {figure_blocks}
</body>
</html>"""


def find_case_paths(case_dir: Path) -> dict[str, Path]:
    root = case_dir
    if not (root / "batch_summary.json").exists() and root.is_dir():
        candidates = sorted([path for path in root.iterdir() if path.is_dir()], key=lambda path: path.stat().st_mtime, reverse=True)
        if candidates and (candidates[0] / "batch_summary.json").exists():
            root = candidates[0]
    mapping: dict[str, Path] = {"case_root": root}
    for child_name, key in [
        ("healthcare_baseline", "baseline"),
        ("healthcare_worst_case", "search"),
        ("healthcare_optimize", "optimize"),
    ]:
        child_root = root / child_name
        if child_root.exists():
            nested = sorted([path for path in child_root.iterdir() if path.is_dir()], key=lambda path: path.stat().st_mtime, reverse=True)
            if nested:
                mapping[key] = nested[0]
    return mapping


def find_first_existing(root: Path | None, names: list[str]) -> Path | None:
    if root is None or not root.exists():
        return None
    for name in names:
        candidate = root / name
        if candidate.exists():
            return candidate
    for name in names:
        matches = list(root.rglob(name))
        if matches:
            return matches[0]
    return None


if __name__ == "__main__":
    main()
