"""Evidence casebooks built from multi-seed evaluation studies."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
import seaborn as sns

from stresslab.campaigns.evaluation import build_evaluation_study
from stresslab.models import CasebookRecord, CasebookSummary
from stresslab.systemspec import load_spec
from stresslab.utils import slugify, write_dataframe, write_json

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid")


def build_casebook(
    spec_paths: list[Path],
    *,
    output_dir: Path,
    title: str,
    suite: str | None,
    replicates: int,
    seed_step: int,
    budget: float | None,
    robust: bool,
    scenario_budget: float | None,
    scenario_samples: int,
    fairness_weight: float,
) -> CasebookSummary:
    """Run evaluation studies across multiple systems and aggregate the evidence."""

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[CasebookRecord] = []
    for spec_path in spec_paths:
        spec = load_spec(spec_path)
        derived_budget = budget if budget is not None else _default_budget(spec)
        study_dir = output_dir / slugify(Path(spec_path).stem)
        study_dir.mkdir(parents=True, exist_ok=True)
        summary = build_evaluation_study(
            spec_path,
            output_dir=study_dir,
            replicates=replicates,
            seed_step=seed_step,
            budget=derived_budget,
            robust=robust,
            scenario_budget=scenario_budget,
            scenario_samples=scenario_samples,
            fairness_weight=fairness_weight,
            intervention_ids=None,
            expand_policies=False,
            expand_dynamic_policies=False,
            expand_adaptive_policies=False,
            expand_controller_bundles=False,
            expand_hierarchical_playbooks=False,
            policy_only=False,
            dynamic_only=False,
            adaptive_only=False,
            bundle_only=False,
            playbook_only=False,
        )
        metric_frame = pd.read_csv(study_dir / "evaluation_metric_summary.csv")
        metric_lookup = metric_frame.set_index("metric").to_dict(orient="index")
        records.append(
            CasebookRecord(
                system_name=summary.system_name,
                spec_path=str(Path(spec_path).resolve()),
                evaluation_dir=str(study_dir),
                selected_intervention_ids=summary.selected_intervention_ids,
                replicate_count=summary.replicate_count,
                baseline_failure_rate=summary.baseline_failure_rate,
                scenario_failure_rate=summary.scenario_failure_rate,
                failure_rate_delta=summary.failure_rate_delta,
                throughput_delta=float(metric_lookup.get("throughput", {}).get("delta_mean", 0.0)),
                mean_wait_delta=float(metric_lookup.get("mean_wait", {}).get("delta_mean", 0.0)),
                resilience_delta=float(metric_lookup.get("resilience_score", {}).get("delta_mean", 0.0)),
                fairness_delta=float(metric_lookup.get("fairness_score", {}).get("delta_mean", 0.0)),
                report_html_path=summary.report_html_path,
            )
        )
    frame = pd.DataFrame([record.model_dump(mode="json") for record in records]).sort_values(
        ["resilience_delta", "fairness_delta", "failure_rate_delta"],
        ascending=[False, False, True],
    )
    summary = CasebookSummary(
        title=title,
        suite=suite,
        record_count=len(records),
        replicate_count=replicates,
        casebook_dir=str(output_dir),
        summary_csv_path=str(output_dir / "casebook_summary.csv"),
        summary_json_path=str(output_dir / "casebook_summary.json"),
        report_markdown_path=str(output_dir / "casebook_report.md"),
        report_html_path=str(output_dir / "casebook_report.html"),
        records=records,
    )
    write_dataframe(output_dir / "casebook_summary.csv", frame)
    write_json(output_dir / "casebook_summary.json", summary)
    plot_casebook_resilience(frame, output_dir / "casebook_resilience.png")
    plot_casebook_failure_reduction(frame, output_dir / "casebook_failure_reduction.png")
    _write_casebook_report(output_dir, title=title, frame=frame, summary=summary)
    return summary


def plot_casebook_resilience(frame: pd.DataFrame, path: Path) -> Path:
    """Plot resilience deltas across casebook systems."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame([{"system_name": "none", "resilience_delta": 0.0}])
    fig, ax = plt.subplots(figsize=(9.0, max(4.8, 0.45 * len(plot_frame) + 1.5)))
    sns.barplot(data=plot_frame, x="resilience_delta", y="system_name", ax=ax, color="#2a9d8f")
    ax.set_title("Casebook: Resilience Delta by System")
    ax.set_xlabel("Scenario - Baseline resilience")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_casebook_failure_reduction(frame: pd.DataFrame, path: Path) -> Path:
    """Plot failure-rate deltas across casebook systems."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame([{"system_name": "none", "failure_rate_delta": 0.0}])
    fig, ax = plt.subplots(figsize=(9.0, max(4.8, 0.45 * len(plot_frame) + 1.5)))
    sns.barplot(data=plot_frame, x="failure_rate_delta", y="system_name", ax=ax, color="#e76f51")
    ax.set_title("Casebook: Failure Rate Delta by System")
    ax.set_xlabel("Scenario - Baseline failure rate")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _write_casebook_report(output_dir: Path, *, title: str, frame: pd.DataFrame, summary: CasebookSummary) -> None:
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        f"- Record count: `{summary.record_count}`",
        f"- Replicates per study: `{summary.replicate_count}`",
        f"- Suite: `{summary.suite}`",
        "",
        "## Evidence",
        "",
        _frame_to_markdown(frame),
        "",
        "## Plots",
        "",
        "![casebook_resilience](casebook_resilience.png)",
        "",
        "![casebook_failure_reduction](casebook_failure_reduction.png)",
        "",
    ]
    (output_dir / "casebook_report.md").write_text("\n".join(lines), encoding="utf-8")
    html = [
        "<html><body>",
        f"<h1>{title}</h1>",
        "<ul>",
        f"<li>Record count: <code>{summary.record_count}</code></li>",
        f"<li>Replicates per study: <code>{summary.replicate_count}</code></li>",
        f"<li>Suite: <code>{summary.suite}</code></li>",
        "</ul>",
        frame.to_html(index=False, border=0),
        "<img src='casebook_resilience.png' style='max-width: 100%;'>",
        "<img src='casebook_failure_reduction.png' style='max-width: 100%;'>",
        "</body></html>",
    ]
    (output_dir / "casebook_report.html").write_text("\n".join(html), encoding="utf-8")


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No evidence records._"
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def _default_budget(spec) -> float | None:
    costs = sorted(intervention.cost for intervention in spec.interventions if intervention.cost is not None)
    if not costs:
        return None
    return float(sum(costs[: min(2, len(costs))]))
