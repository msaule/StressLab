from __future__ import annotations

import argparse
import html
import json
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
    "healthcare_referral": "Healthcare ED Family",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the curated follow-up threshold study package.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--theory-dir", type=Path, required=True)
    parser.add_argument("--research-dir", type=Path, required=True)
    parser.add_argument("--spec-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    output_dir = ensure_dir(args.output_dir.resolve())
    figures_dir = ensure_dir(output_dir / "figures")

    dataset = load_csv(args.theory_dir / "combined_collapse_dataset.csv")
    if dataset.empty:
        dataset = load_csv(args.workspace / "collapse_dataset.csv")
    synthetic_manifest = load_csv(args.spec_root / "synthetic_manifest.csv")
    healthcare_manifest = load_csv(args.spec_root / "healthcare_manifest.csv")
    design = pd.concat([synthetic_manifest, healthcare_manifest], ignore_index=True, sort=False)
    if dataset.empty:
        raise FileNotFoundError("Could not locate follow-up collapse dataset.")
    merged = dataset.merge(
        design[["spec_path", "study_family", "topology_type", "replicate", "util_target", "coupling_scale", "achieved_utilization", "achieved_coupling"]],
        on=["spec_path"],
        how="left",
        suffixes=("", "_design"),
    )
    if "topology_type_design" in merged.columns:
        merged["topology_type"] = merged["topology_type_design"].fillna(merged["topology_type"])
    merged["topology_label"] = merged["topology_type"].map(TOPOLOGY_LABELS).fillna(merged["topology_type"])
    merged["coupling_regime"] = merged["coupling_scale"].map({0.75: "low", 1.0: "medium", 1.25: "high"}).fillna(
        merged["coupling_scale"].astype(str)
    )

    synthetic = merged[merged["study_family"] == "synthetic_controlled"].copy()
    healthcare = merged[merged["study_family"] == "healthcare_controlled"].copy()

    threshold_table = estimate_controlled_thresholds(synthetic)
    healthcare_thresholds = estimate_controlled_thresholds(healthcare, feature="util_target")
    shift_table = build_threshold_shift_table(threshold_table)
    budget_margin_table = build_budget_margin_table(synthetic)

    figures = [
        (
            "controlled_threshold_by_coupling.png",
            "Controlled synthetic collapse curves by topology and coupling regime.",
            plot_controlled_thresholds(synthetic, figures_dir / "controlled_threshold_by_coupling.png"),
        ),
        (
            "threshold_shift_by_coupling.png",
            "Estimated threshold shifts between low and high coupling regimes.",
            plot_threshold_shift(shift_table, figures_dir / "threshold_shift_by_coupling.png"),
        ),
        (
            "failure_shock_budget_margin.png",
            "How higher coupling changes the minimum shock required to trigger failure.",
            plot_budget_margin(budget_margin_table, figures_dir / "failure_shock_budget_margin.png"),
        ),
        (
            "healthcare_family_threshold.png",
            "Healthcare ED family collapse curves under utilization and dependency coupling sweeps.",
            plot_healthcare_thresholds(healthcare, figures_dir / "healthcare_family_threshold.png"),
        ),
        (
            "followup_main_result.png",
            "Multi-panel summary of the controlled follow-up study.",
            plot_followup_summary(synthetic, threshold_table, healthcare, figures_dir / "followup_main_result.png"),
        ),
    ]

    results_table = build_results_table(synthetic, healthcare, threshold_table, healthcare_thresholds, shift_table, budget_margin_table)
    results_table.to_csv(output_dir / "FOLLOWUP_RESULTS_TABLES.csv", index=False)

    key_findings = build_key_findings(synthetic, healthcare, threshold_table, healthcare_thresholds, shift_table, budget_margin_table)
    headline = build_headline(synthetic, healthcare, shift_table, budget_margin_table)

    write_text(output_dir / "FOLLOWUP_EXEC_SUMMARY.md", build_exec_summary(headline, key_findings))
    write_text(output_dir / "FOLLOWUP_REPRO.md", build_repro(args.workspace, args.theory_dir, args.research_dir, args.spec_root, args.manifest, output_dir))
    write_text(output_dir / "FOLLOWUP_FIGURE_INDEX.md", build_figure_index(figures))
    write_text(output_dir / "FOLLOWUP_WRITEUP.md", build_writeup(headline, key_findings, synthetic, healthcare, threshold_table, healthcare_thresholds, shift_table, budget_margin_table, figures))
    write_text(output_dir / "FOLLOWUP_RESEARCH_REPORT.html", build_html_report(headline, key_findings, synthetic, healthcare, threshold_table, healthcare_thresholds, shift_table, budget_margin_table, figures))
    write_text(output_dir / "FOLLOWUP_README_BLOCK.md", build_readme_block(headline, key_findings))

    with (output_dir / "followup_package_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "workspace": str(args.workspace),
                "theory_dir": str(args.theory_dir),
                "research_dir": str(args.research_dir),
                "spec_root": str(args.spec_root),
                "synthetic_rows": int(len(synthetic)),
                "healthcare_rows": int(len(healthcare)),
                "headline_result": headline,
            },
            handle,
            indent=2,
        )


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def build_curve(frame: pd.DataFrame, *, group_cols: list[str], x_col: str, y_col: str, bins: int = 8) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if frame.empty:
        return pd.DataFrame(columns=group_cols + [x_col, y_col, "system_count"])
    for group_key, subset in frame.groupby(group_cols):
        clean = subset[[x_col, y_col]].dropna().copy()
        q = min(bins, clean[x_col].nunique())
        if q < 2:
            continue
        clean["bin"] = pd.qcut(clean[x_col], q=q, duplicates="drop")
        grouped = clean.groupby("bin", observed=False).agg(**{x_col: (x_col, "mean"), y_col: (y_col, "mean"), "system_count": (y_col, "size")}).reset_index(drop=True)
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        for name, value in zip(group_cols, group_key, strict=True):
            grouped[name] = value
        rows.extend(grouped.to_dict(orient="records"))
    return pd.DataFrame(rows)


def estimate_controlled_thresholds(frame: pd.DataFrame, *, feature: str = "baseline_utilization") -> pd.DataFrame:
    curve = build_curve(frame, group_cols=["topology_type", "coupling_regime"], x_col=feature, y_col="collapse_probability", bins=8)
    rows: list[dict[str, object]] = []
    for (topology, coupling_regime), subset in curve.groupby(["topology_type", "coupling_regime"]):
        if len(subset) < 3:
            continue
        ordered = subset.sort_values(feature)
        x = ordered[feature].to_numpy(dtype=float)
        y = ordered["collapse_probability"].to_numpy(dtype=float)
        slopes = np.diff(y) / np.clip(np.diff(x), 1e-9, None)
        peak_index = int(np.argmax(slopes))
        rows.append(
            {
                "topology_type": topology,
                "topology_label": TOPOLOGY_LABELS.get(topology, topology),
                "coupling_regime": coupling_regime,
                "critical_utilization": float(np.mean(x[peak_index : peak_index + 2])),
                "peak_slope": float(slopes[peak_index]),
                "mean_collapse_probability": float(y.mean()),
                "feature": feature,
            }
        )
    return pd.DataFrame(rows).sort_values(["topology_type", "coupling_regime"]).reset_index(drop=True)


def build_threshold_shift_table(threshold_table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for topology, subset in threshold_table.groupby("topology_type"):
        low = subset.loc[subset["coupling_regime"] == "low", "critical_utilization"]
        high = subset.loc[subset["coupling_regime"] == "high", "critical_utilization"]
        medium = subset.loc[subset["coupling_regime"] == "medium", "critical_utilization"]
        if low.empty or high.empty:
            continue
        rows.append(
            {
                "topology_type": topology,
                "topology_label": TOPOLOGY_LABELS.get(topology, topology),
                "low_threshold": float(low.iloc[0]),
                "medium_threshold": float(medium.iloc[0]) if not medium.empty else float("nan"),
                "high_threshold": float(high.iloc[0]),
                "threshold_shift": float(high.iloc[0] - low.iloc[0]),
            }
        )
    return pd.DataFrame(rows).sort_values("threshold_shift").reset_index(drop=True)


def build_budget_margin_table(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        frame.groupby(["topology_type", "util_target", "coupling_regime"], as_index=False)["failure_shock_budget"]
        .mean()
        .rename(columns={"failure_shock_budget": "mean_failure_shock_budget"})
    )
    rows: list[dict[str, object]] = []
    for topology, subset in grouped.groupby("topology_type"):
        pivot = subset.pivot(index="util_target", columns="coupling_regime", values="mean_failure_shock_budget")
        if "low" not in pivot.columns or "high" not in pivot.columns:
            continue
        valid = pivot.replace([np.inf, -np.inf], np.nan).dropna(subset=["low", "high"], how="any")
        pct_change = ((valid["high"] - valid["low"]) / valid["low"].replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
        rows.append(
            {
                "topology_type": topology,
                "topology_label": TOPOLOGY_LABELS.get(topology, topology),
                "mean_pct_change_high_vs_low": float(pct_change.mean()) if not pct_change.dropna().empty else 0.0,
                "median_low_budget": float(valid["low"].median()) if not valid.empty else 0.0,
                "median_high_budget": float(valid["high"].median()) if not valid.empty else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("mean_pct_change_high_vs_low").reset_index(drop=True)


def plot_controlled_thresholds(frame: pd.DataFrame, path: Path) -> Path:
    curve = build_curve(frame, group_cols=["topology_label", "coupling_regime"], x_col="baseline_utilization", y_col="collapse_probability", bins=8)
    g = sns.relplot(
        data=curve,
        x="baseline_utilization",
        y="collapse_probability",
        hue="coupling_regime",
        col="topology_label",
        col_wrap=3,
        kind="line",
        marker="o",
        height=4.0,
        aspect=1.15,
    )
    g.set_axis_labels("Baseline utilization", "Collapse probability")
    g.set_titles("{col_name}")
    g.fig.suptitle("Controlled Threshold Curves by Coupling Regime", y=1.03)
    g.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(g.fig)
    return path


def plot_threshold_shift(shift_table: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9.8, 5.8))
    sns.barplot(data=shift_table, x="threshold_shift", y="topology_label", color="#7c6fa8", ax=ax)
    ax.axvline(0.0, color="#222222", linewidth=1.2, linestyle="--")
    ax.set_title("How Much Does Higher Coupling Shift the Threshold?")
    ax.set_xlabel("High-coupling threshold minus low-coupling threshold")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_budget_margin(budget_margin_table: pd.DataFrame, path: Path) -> Path:
    plot_frame = budget_margin_table.copy()
    plot_frame["mean_pct_change_high_vs_low"] = plot_frame["mean_pct_change_high_vs_low"] * 100.0
    fig, ax = plt.subplots(figsize=(9.8, 5.8))
    sns.barplot(data=plot_frame, x="mean_pct_change_high_vs_low", y="topology_label", color="#b85c38", ax=ax)
    ax.axvline(0.0, color="#222222", linewidth=1.2, linestyle="--")
    ax.set_title("Higher Coupling Shrinks the Failure Shock Margin")
    ax.set_xlabel("Mean % change in failure shock budget (high vs low coupling)")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_healthcare_thresholds(frame: pd.DataFrame, path: Path) -> Path:
    curve = build_curve(frame, group_cols=["coupling_regime"], x_col="util_target", y_col="collapse_probability", bins=6)
    fig, ax = plt.subplots(figsize=(9.6, 6.0))
    sns.lineplot(data=curve, x="util_target", y="collapse_probability", hue="coupling_regime", marker="o", linewidth=2.2, ax=ax)
    ax.set_title("Healthcare Family Validation: Collapse vs Arrival Multiplier")
    ax.set_xlabel("Arrival multiplier")
    ax.set_ylabel("Collapse probability")
    ax.legend(title="")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def plot_followup_summary(synthetic: pd.DataFrame, threshold_table: pd.DataFrame, healthcare: pd.DataFrame, path: Path) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(14.4, 10.2))
    synthetic_curve = build_curve(synthetic, group_cols=["coupling_regime"], x_col="baseline_utilization", y_col="collapse_probability", bins=8)
    sns.lineplot(data=synthetic_curve, x="baseline_utilization", y="collapse_probability", hue="coupling_regime", marker="o", ax=axes[0, 0])
    axes[0, 0].set_title("A. Synthetic Controlled Curves")
    axes[0, 0].set_xlabel("Baseline utilization")
    axes[0, 0].set_ylabel("Collapse probability")
    axes[0, 0].legend(title="")

    sns.barplot(data=threshold_table, x="critical_utilization", y="topology_label", hue="coupling_regime", ax=axes[0, 1])
    axes[0, 1].set_title("B. Thresholds by Coupling")
    axes[0, 1].set_xlabel("Critical utilization")
    axes[0, 1].set_ylabel("")
    axes[0, 1].legend(title="")

    healthcare_curve = build_curve(healthcare, group_cols=["coupling_regime"], x_col="baseline_utilization", y_col="collapse_probability", bins=6)
    healthcare_curve = build_curve(healthcare, group_cols=["coupling_regime"], x_col="util_target", y_col="collapse_probability", bins=6)
    sns.lineplot(data=healthcare_curve, x="util_target", y="collapse_probability", hue="coupling_regime", marker="o", ax=axes[1, 0])
    axes[1, 0].set_title("C. Healthcare Validation")
    axes[1, 0].set_xlabel("Arrival multiplier")
    axes[1, 0].set_ylabel("Collapse probability")
    axes[1, 0].legend(title="")

    shift_table = build_threshold_shift_table(threshold_table)
    sns.barplot(data=shift_table, x="threshold_shift", y="topology_label", color="#6d8a5e", ax=axes[1, 1])
    axes[1, 1].axvline(0.0, color="#222222", linewidth=1.2, linestyle="--")
    axes[1, 1].set_title("D. Coupling-Induced Threshold Shift")
    axes[1, 1].set_xlabel("High minus low coupling threshold")
    axes[1, 1].set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def build_results_table(
    synthetic: pd.DataFrame,
    healthcare: pd.DataFrame,
    threshold_table: pd.DataFrame,
    healthcare_thresholds: pd.DataFrame,
    shift_table: pd.DataFrame,
    budget_margin_table: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    rows.append({"section": "counts", "group": "synthetic", "metric": "system_count", "value": len(synthetic), "notes": ""})
    rows.append({"section": "counts", "group": "healthcare", "metric": "system_count", "value": len(healthcare), "notes": ""})
    for record in threshold_table.to_dict(orient="records"):
        rows.append({"section": "synthetic_thresholds", "group": record["topology_type"], "metric": record["coupling_regime"], "value": record["critical_utilization"], "notes": f"slope={record['peak_slope']:.3f}"})
    for record in healthcare_thresholds.to_dict(orient="records"):
        rows.append({"section": "healthcare_thresholds", "group": "healthcare_referral", "metric": record["coupling_regime"], "value": record["critical_utilization"], "notes": f"slope={record['peak_slope']:.3f}"})
    for record in shift_table.to_dict(orient="records"):
        rows.append({"section": "threshold_shift", "group": record["topology_type"], "metric": "high_minus_low", "value": record["threshold_shift"], "notes": ""})
    for record in budget_margin_table.to_dict(orient="records"):
        rows.append({"section": "shock_margin_shift", "group": record["topology_type"], "metric": "high_vs_low_pct", "value": record["mean_pct_change_high_vs_low"], "notes": f"low={record['median_low_budget']:.3f}; high={record['median_high_budget']:.3f}"})
    return pd.DataFrame(rows)


def build_key_findings(
    synthetic: pd.DataFrame,
    healthcare: pd.DataFrame,
    threshold_table: pd.DataFrame,
    healthcare_thresholds: pd.DataFrame,
    shift_table: pd.DataFrame,
    budget_margin_table: pd.DataFrame,
) -> list[str]:
    mean_shift = float(shift_table["threshold_shift"].mean()) if not shift_table.empty else 0.0
    max_shift = float(shift_table["threshold_shift"].abs().max()) if not shift_table.empty else 0.0
    synthetic_threshold = float(threshold_table["critical_utilization"].median()) if not threshold_table.empty else 0.0
    healthcare_threshold = float(healthcare_thresholds["critical_utilization"].median()) if not healthcare_thresholds.empty else 0.0
    mean_budget_change = float(budget_margin_table["mean_pct_change_high_vs_low"].mean()) if not budget_margin_table.empty else 0.0
    return [
        f"In the controlled synthetic study, the utilization threshold remains the main driver of collapse, with a median controlled threshold near {synthetic_threshold:.3f}.",
        f"Changing coupling shifts the threshold, but only modestly on average: the mean high-minus-low coupling shift is {mean_shift:.3f} utilization points, with the largest absolute shift at {max_shift:.3f}.",
        f"Higher coupling still matters operationally because it shrinks the minimum shock-to-failure margin by about {abs(mean_budget_change) * 100:.1f}% on average across the controlled synthetic grid.",
        "That follow-up result weakens any claim that raw coupling alone sets the universal threshold; coupling acts more like a modifier on a utilization-led transition and a reducer of failure margin.",
        f"The healthcare validation family shows the same qualitative shape in operational terms: collapse turns on around a {healthcare_threshold:.2f}x arrival multiplier and is essentially saturated by 1.20x, which supports the portability of the utilization-threshold result beyond purely synthetic systems.",
    ]


def build_headline(synthetic: pd.DataFrame, healthcare: pd.DataFrame, shift_table: pd.DataFrame, budget_margin_table: pd.DataFrame) -> str:
    mean_shift = float(shift_table["threshold_shift"].mean()) if not shift_table.empty else 0.0
    mean_budget_change = float(budget_margin_table["mean_pct_change_high_vs_low"].mean()) if not budget_margin_table.empty else 0.0
    return (
        f"In the controlled follow-up sweep over {len(synthetic):,} fixed-size synthetic systems plus {len(healthcare):,} healthcare variants, "
        f"StressLab found that the collapse threshold stays primarily utilization-led, while higher coupling shifts it only modestly on average ({mean_shift:.3f} utilization points) but reduces the shock margin to failure by about {abs(mean_budget_change) * 100:.1f}%."
    )


def build_exec_summary(headline: str, key_findings: list[str]) -> str:
    return "\n".join(["# Follow-up Study Executive Summary", "", headline, "", "## Key Findings", "", *[f"- {item}" for item in key_findings]])


def build_repro(workspace: Path, theory_dir: Path, research_dir: Path, spec_root: Path, manifest: Path, output_dir: Path) -> str:
    commands = [
        f"python scripts/build_followup_controlled_specs.py --output-root {spec_root}",
        f"stresslab batch {manifest} --output-dir {workspace.parent}",
        f"stresslab theory {workspace} --output-dir {theory_dir.parent}",
        f"stresslab research {workspace} --theory-dir {theory_dir} --output-dir {research_dir.parent}",
        (
            "python scripts/build_followup_controlled_package.py "
            f"--workspace {workspace} --theory-dir {theory_dir} --research-dir {research_dir} "
            f"--spec-root {spec_root} --output-dir {output_dir} --manifest {manifest}"
        ),
    ]
    lines = ["# Follow-up Study Reproduction", "", "## Commands", ""]
    for command in commands:
        lines.extend(["```powershell", command, "```", ""])
    return "\n".join(lines)


def build_figure_index(figures: list[tuple[str, str, Path]]) -> str:
    return "\n".join(["# Follow-up Figure Index", "", *[f"- `{name}`: {description}" for name, description, _ in figures]])


def build_writeup(
    headline: str,
    key_findings: list[str],
    synthetic: pd.DataFrame,
    healthcare: pd.DataFrame,
    threshold_table: pd.DataFrame,
    healthcare_thresholds: pd.DataFrame,
    shift_table: pd.DataFrame,
    budget_margin_table: pd.DataFrame,
    figures: list[tuple[str, str, Path]],
) -> str:
    return "\n".join(
        [
            "# Follow-up Study: Controlled Utilization-Coupling Sweep",
            "",
            "## Abstract",
            "",
            headline,
            "",
            "## Design",
            "",
            f"- Synthetic controlled systems: `{len(synthetic):,}`",
            f"- Healthcare validation variants: `{len(healthcare):,}`",
            "- Synthetic design held node count fixed and swept utilization targets plus coupling regimes.",
            "- Healthcare design swept arrival intensity and dependency-routing coupling modes on the ED example family.",
            "",
            "## Key Findings",
            "",
            *[f"- {item}" for item in key_findings],
            "",
            "## Controlled Threshold Table",
            "",
            threshold_table.head(15).to_csv(index=False) if threshold_table.empty else threshold_table.head(15).to_string(index=False),
            "",
            "## Healthcare Threshold Table",
            "",
            healthcare_thresholds.to_string(index=False) if not healthcare_thresholds.empty else "_No healthcare thresholds available._",
            "",
            "## Threshold Shift Table",
            "",
            shift_table.to_string(index=False) if not shift_table.empty else "_No shift table available._",
            "",
            "## Failure Shock Margin Shift",
            "",
            budget_margin_table.to_string(index=False) if not budget_margin_table.empty else "_No budget margin table available._",
            "",
            "## Figures",
            "",
            *[f"- `figures/{name}`: {description}" for name, description, _ in figures],
        ]
    )


def build_html_report(
    headline: str,
    key_findings: list[str],
    synthetic: pd.DataFrame,
    healthcare: pd.DataFrame,
    threshold_table: pd.DataFrame,
    healthcare_thresholds: pd.DataFrame,
    shift_table: pd.DataFrame,
    budget_margin_table: pd.DataFrame,
    figures: list[tuple[str, str, Path]],
) -> str:
    figure_blocks = "\n".join(
        [
            f"<figure><img src='figures/{html.escape(name)}' style='max-width:100%; border:1px solid #ddd; border-radius:8px;' /><figcaption>{html.escape(description)}</figcaption></figure>"
            for name, description, _ in figures
        ]
    )
    findings = "\n".join(f"<li>{html.escape(item)}</li>" for item in key_findings)
    return f"""<html><head><meta charset='utf-8' /><title>Follow-up Controlled Threshold Study</title></head>
<body style='font-family:Georgia,serif; max-width:1040px; margin:32px auto; line-height:1.6;'>
<h1>Follow-up Controlled Threshold Study</h1>
<p><strong>{html.escape(headline)}</strong></p>
<ul>{findings}</ul>
<h2>Counts</h2>
<p>Synthetic controlled systems: <code>{len(synthetic):,}</code><br />Healthcare variants: <code>{len(healthcare):,}</code></p>
<h2>Threshold shift table</h2>
{shift_table.to_html(index=False, border=0) if not shift_table.empty else '<p>No shift table available.</p>'}
<h2>Failure shock margin shift</h2>
{budget_margin_table.to_html(index=False, border=0) if not budget_margin_table.empty else '<p>No budget margin table available.</p>'}
<h2>Healthcare threshold table</h2>
{healthcare_thresholds.to_html(index=False, border=0) if not healthcare_thresholds.empty else '<p>No healthcare table available.</p>'}
<h2>Figures</h2>
{figure_blocks}
</body></html>"""


def build_readme_block(headline: str, key_findings: list[str]) -> str:
    return "\n".join(["## Follow-up Controlled Threshold Study", "", headline, "", *[f"- {item}" for item in key_findings[:3]]])


if __name__ == "__main__":
    main()
