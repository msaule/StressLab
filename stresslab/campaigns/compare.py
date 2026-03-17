"""Cross-run comparison utilities for StressLab artifact directories."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import pandas as pd
import seaborn as sns

from stresslab.models import ComparisonRecord, ComparisonSummary
from stresslab.utils import write_dataframe, write_json

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid")


def summarize_run_dir(
    run_dir: Path,
    *,
    label: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> ComparisonRecord:
    """Load one artifact directory and normalize it into a comparable record."""

    run_dir = Path(run_dir)
    metadata = _load_json(run_dir / "metadata.json")
    baseline = _load_json(run_dir / "baseline_result.json")
    scenario = _load_json(run_dir / "scenario_result.json")
    search = _load_json(run_dir / "search_result.json")
    optimization = _load_json(run_dir / "optimization.json")
    evaluation = _load_json(run_dir / "evaluation_summary.json")
    generation = _load_json(run_dir / "generation_summary.json")
    discovery = _load_json(run_dir / "discovery_summary.json")
    theory = _load_json(run_dir / "theory_summary.json")
    research = _load_json(run_dir / "research_summary.json")
    if evaluation:
        metrics_frame = _load_csv(run_dir / "evaluation_metric_summary.csv")
        metric_lookup = (
            metrics_frame.set_index("metric").to_dict(orient="index")
            if not metrics_frame.empty and "metric" in metrics_frame.columns
            else {}
        )
        return ComparisonRecord(
            run_id=run_dir.name,
            label=label or metadata.get("system_name") or run_dir.name,
            run_dir=str(run_dir),
            report_html_path=(
                str(run_dir / "evaluation_report.html")
                if (run_dir / "evaluation_report.html").exists()
                else None
            ),
            system_name=evaluation.get("system_name", metadata.get("system_name", run_dir.name)),
            analysis_type="evaluation",
            command=metadata.get("command", "stresslab evaluate"),
            failure_triggered=bool(evaluation.get("scenario_failure_rate", 0.0) > 0.0),
            throughput=float(metric_lookup.get("throughput", {}).get("scenario_mean", 0.0)),
            mean_wait=float(metric_lookup.get("mean_wait", {}).get("scenario_mean", 0.0)),
            resilience_score=float(metric_lookup.get("resilience_score", {}).get("scenario_mean", 0.0)),
            fairness_score=float(metric_lookup.get("fairness_score", {}).get("scenario_mean", 0.0)),
            blocked_transfers=0.0,
            recovery_time=0.0,
            robust_mode=bool(str(evaluation.get("evaluation_mode", "")).startswith("robust")),
            scenario_count=int(evaluation.get("replicate_count", 1) or 1),
            cluster_count=0,
            best_resilience=float(metric_lookup.get("resilience_score", {}).get("scenario_mean", 0.0)),
            best_shock_budget=None,
            damage_score=None,
            top_intervention_id=(
                str(evaluation.get("selected_intervention_ids", [None])[0])
                if evaluation.get("selected_intervention_ids")
                else None
            ),
            recommended_portfolio_id=None,
            replicate_count=int(evaluation.get("replicate_count", 0) or 0),
            execution_duration=(
                float(metadata["execution_duration"])
                if metadata.get("execution_duration") is not None
                else None
            ),
            tags=list(tags or []),
            notes=notes,
        )
    if generation:
        return ComparisonRecord(
            run_id=run_dir.name,
            label=label or metadata.get("system_name") or run_dir.name,
            run_dir=str(run_dir),
            report_html_path=(
                str(run_dir / "generation_report.html")
                if (run_dir / "generation_report.html").exists()
                else None
            ),
            system_name=metadata.get("system_name", generation.get("title", run_dir.name)),
            analysis_type="generate",
            command=metadata.get("command", "stresslab generate"),
            failure_triggered=False,
            throughput=float(generation.get("system_count", 0.0) or 0.0),
            mean_wait=0.0,
            resilience_score=0.0,
            fairness_score=0.0,
            blocked_transfers=0.0,
            recovery_time=0.0,
            execution_duration=(
                float(metadata["execution_duration"])
                if metadata.get("execution_duration") is not None
                else None
            ),
            tags=list(tags or []),
            notes=notes,
        )
    if discovery:
        dataset_frame = _load_csv(run_dir / "collapse_dataset.csv")
        return ComparisonRecord(
            run_id=run_dir.name,
            label=label or metadata.get("system_name") or run_dir.name,
            run_dir=str(run_dir),
            report_html_path=(
                str(run_dir / "discovery_report.html")
                if (run_dir / "discovery_report.html").exists()
                else None
            ),
            system_name=metadata.get("system_name", discovery.get("title", run_dir.name)),
            analysis_type="discover",
            command=metadata.get("command", "stresslab discover"),
            failure_triggered=bool(dataset_frame.get("collapse_probability", pd.Series(dtype=float)).mean() > 0.5)
            if not dataset_frame.empty
            else False,
            throughput=float(discovery.get("dataset_row_count", 0.0) or 0.0),
            mean_wait=float(dataset_frame.get("failure_shock_budget", pd.Series(dtype=float)).mean())
            if not dataset_frame.empty and "failure_shock_budget" in dataset_frame.columns
            else 0.0,
            resilience_score=float(dataset_frame.get("resilience_score", pd.Series(dtype=float)).mean())
            if not dataset_frame.empty and "resilience_score" in dataset_frame.columns
            else 0.0,
            fairness_score=0.0,
            blocked_transfers=0.0,
            recovery_time=float(dataset_frame.get("recovery_time", pd.Series(dtype=float)).mean())
            if not dataset_frame.empty and "recovery_time" in dataset_frame.columns
            else 0.0,
            execution_duration=(
                float(metadata["execution_duration"])
                if metadata.get("execution_duration") is not None
                else None
            ),
            tags=list(tags or []),
            notes=notes,
        )
    if theory:
        return ComparisonRecord(
            run_id=run_dir.name,
            label=label or metadata.get("system_name") or run_dir.name,
            run_dir=str(run_dir),
            report_html_path=(
                str(run_dir / "theory_report.html")
                if (run_dir / "theory_report.html").exists()
                else None
            ),
            system_name=metadata.get("system_name", theory.get("title", run_dir.name)),
            analysis_type="theory",
            command=metadata.get("command", "stresslab theory"),
            failure_triggered=False,
            throughput=float(theory.get("law_candidate_count", 0.0) or 0.0),
            mean_wait=0.0,
            resilience_score=float(theory.get("symbolic_law_count", 0.0) or 0.0),
            fairness_score=0.0,
            blocked_transfers=0.0,
            recovery_time=0.0,
            execution_duration=(
                float(metadata["execution_duration"])
                if metadata.get("execution_duration") is not None
                else None
            ),
            tags=list(tags or []),
            notes=notes,
        )
    if research:
        return ComparisonRecord(
            run_id=run_dir.name,
            label=label or metadata.get("system_name") or run_dir.name,
            run_dir=str(run_dir),
            report_html_path=(
                str(run_dir / "research_report.html")
                if (run_dir / "research_report.html").exists()
                else None
            ),
            system_name=metadata.get("system_name", research.get("title", run_dir.name)),
            analysis_type="research",
            command=metadata.get("command", "stresslab research"),
            failure_triggered=False,
            throughput=float(research.get("figure_count", 0.0) or 0.0),
            mean_wait=0.0,
            resilience_score=0.0,
            fairness_score=0.0,
            blocked_transfers=0.0,
            recovery_time=0.0,
            execution_duration=(
                float(metadata["execution_duration"])
                if metadata.get("execution_duration") is not None
                else None
            ),
            tags=list(tags or []),
            notes=notes,
        )
    primary = scenario or baseline
    metrics = primary.get("metrics", {})
    ranked_interventions = optimization.get("ranked_interventions", [])
    analysis_type = "optimize" if optimization else ("search" if search else "run")
    report_html = run_dir / "report.html"
    return ComparisonRecord(
        run_id=run_dir.name,
        label=label or metadata.get("system_name") or run_dir.name,
        run_dir=str(run_dir),
        report_html_path=str(report_html) if report_html.exists() else None,
        system_name=metadata.get("system_name", primary.get("run_id", run_dir.name)),
        analysis_type=analysis_type,
        command=metadata.get("command", f"stresslab {analysis_type}"),
        failure_triggered=bool(primary.get("failure_triggered", False)),
        throughput=float(metrics.get("throughput", 0.0)),
        mean_wait=float(metrics.get("mean_wait", 0.0)),
        resilience_score=float(metrics.get("resilience_score", 0.0)),
        fairness_score=float(metrics.get("fairness_score", 0.0)),
        blocked_transfers=float(metrics.get("blocked_transfers", 0.0)),
        recovery_time=float(metrics.get("recovery_time", 0.0)),
        robust_mode=bool(optimization.get("robust_mode", False)),
        scenario_count=int(optimization.get("scenario_count", 1) or 1),
        cluster_count=int(optimization.get("cluster_count", 0) or 0),
        best_resilience=(
            float(optimization["best_resilience"])
            if optimization.get("best_resilience") is not None
            else None
        ),
        best_shock_budget=(
            float(search["best_shock_budget"])
            if search.get("best_shock_budget") is not None
            else None
        ),
        damage_score=float(search.get("damage_score", 0.0)) if search else None,
        top_intervention_id=(
            str(ranked_interventions[0].get("intervention_id"))
            if ranked_interventions
            else None
        ),
        recommended_portfolio_id=optimization.get("recommended_portfolio_id"),
        execution_duration=(
            float(metadata["execution_duration"])
            if metadata.get("execution_duration") is not None
            else None
        ),
        tags=list(tags or []),
        notes=notes,
    )


def build_comparison_artifacts(
    run_dirs: list[Path],
    *,
    output_dir: Path,
    title: str,
    labels_by_dir: dict[str, str] | None = None,
    notes_by_dir: dict[str, str] | None = None,
    tags_by_dir: dict[str, list[str]] | None = None,
) -> ComparisonSummary:
    """Build CSV/JSON/Markdown/HTML comparison artifacts for multiple runs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    labels = labels_by_dir or {}
    notes = notes_by_dir or {}
    tags = tags_by_dir or {}
    records = [
        summarize_run_dir(
            Path(run_dir),
            label=labels.get(str(Path(run_dir).resolve())) or labels.get(str(Path(run_dir))),
            notes=notes.get(str(Path(run_dir).resolve())) or notes.get(str(Path(run_dir))),
            tags=tags.get(str(Path(run_dir).resolve())) or tags.get(str(Path(run_dir))),
        )
        for run_dir in run_dirs
    ]
    frame = pd.DataFrame([record.model_dump(mode="json") for record in records]).sort_values(
        ["resilience_score", "fairness_score", "throughput"],
        ascending=[False, False, False],
    )
    write_dataframe(output_dir / "comparison_summary.csv", frame)
    tradeoff_plot = plot_comparison_tradeoff(frame, output_dir / "comparison_tradeoff.png")
    metrics_plot = plot_comparison_metrics(frame, output_dir / "comparison_metrics.png")
    summary = ComparisonSummary(
        title=title,
        run_count=len(records),
        analysis_types=sorted({record.analysis_type for record in records}),
        best_resilience_run_id=_best_run_id(frame, "resilience_score", higher_is_better=True),
        lowest_wait_run_id=_best_run_id(frame, "mean_wait", higher_is_better=False),
        highest_fairness_run_id=_best_run_id(frame, "fairness_score", higher_is_better=True),
        comparison_summary_path=str(output_dir / "comparison_summary.csv"),
        report_markdown_path=str(output_dir / "comparison_report.md"),
        report_html_path=str(output_dir / "comparison_report.html"),
        tradeoff_plot_path=str(tradeoff_plot),
        metrics_plot_path=str(metrics_plot),
    )
    write_json(output_dir / "comparison_summary.json", summary)
    markdown = _build_markdown(title=title, frame=frame, summary=summary)
    (output_dir / "comparison_report.md").write_text(markdown, encoding="utf-8")
    html = _build_html(title=title, frame=frame, summary=summary)
    (output_dir / "comparison_report.html").write_text(html, encoding="utf-8")
    return summary


def plot_comparison_tradeoff(frame: pd.DataFrame, path: Path) -> Path:
    """Plot resilience versus mean wait for compared runs."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [{"label": "none", "mean_wait": 0.0, "resilience_score": 0.0, "analysis_type": "run"}]
        )
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    sns.scatterplot(
        data=plot_frame,
        x="mean_wait",
        y="resilience_score",
        hue="analysis_type",
        style="failure_triggered",
        size="throughput",
        sizes=(90, 260),
        ax=ax,
    )
    for row in plot_frame.itertuples(index=False):
        ax.annotate(str(row.label), (row.mean_wait, row.resilience_score), xytext=(4, 4), textcoords="offset points", fontsize=8)
    ax.set_title("Run Comparison: Resilience vs Mean Wait")
    ax.set_xlabel("Mean wait")
    ax.set_ylabel("Resilience score")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_comparison_metrics(frame: pd.DataFrame, path: Path) -> Path:
    """Plot core comparable metrics across runs."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [{"label": "none", "throughput": 0.0, "resilience_score": 0.0, "fairness_score": 0.0}]
        )
    melted = plot_frame.melt(
        id_vars="label",
        value_vars=[metric for metric in ["throughput", "resilience_score", "fairness_score"] if metric in plot_frame.columns],
        var_name="metric",
        value_name="value",
    )
    fig, ax = plt.subplots(figsize=(9.5, max(4.2, 0.45 * len(plot_frame) + 2.0)))
    sns.barplot(data=melted, x="value", y="label", hue="metric", ax=ax)
    ax.set_title("Run Comparison: Core Metrics")
    ax.set_xlabel("Value")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _best_run_id(frame: pd.DataFrame, column: str, *, higher_is_better: bool) -> str | None:
    if frame.empty or column not in frame.columns:
        return None
    ordered = frame.sort_values(column, ascending=not higher_is_better)
    if ordered.empty:
        return None
    return str(ordered.iloc[0]["run_id"])


def _build_markdown(*, title: str, frame: pd.DataFrame, summary: ComparisonSummary) -> str:
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        f"- Run count: `{summary.run_count}`",
        f"- Analysis types: {', '.join(summary.analysis_types) or 'none'}",
        f"- Best resilience run: `{summary.best_resilience_run_id}`",
        f"- Lowest wait run: `{summary.lowest_wait_run_id}`",
        f"- Highest fairness run: `{summary.highest_fairness_run_id}`",
        "",
        "## Compared Runs",
        "",
        _frame_to_markdown(frame),
        "",
        "## Plots",
        "",
        "![comparison_tradeoff](comparison_tradeoff.png)",
        "",
        "![comparison_metrics](comparison_metrics.png)",
        "",
    ]
    return "\n".join(lines)


def _build_html(*, title: str, frame: pd.DataFrame, summary: ComparisonSummary) -> str:
    return "\n".join(
        [
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            f"<title>{title}</title>",
            "<style>",
            "body { font-family: Georgia, serif; margin: 2rem auto; max-width: 1100px; color: #182026; }",
            "table { border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }",
            "td, th { border: 1px solid #d6dde2; padding: 0.45rem 0.6rem; text-align: left; }",
            "img { max-width: 100%; border: 1px solid #d6dde2; margin-bottom: 1.5rem; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{title}</h1>",
            "<h2>Summary</h2>",
            "<ul>",
            f"<li>Run count: <code>{summary.run_count}</code></li>",
            f"<li>Analysis types: {', '.join(summary.analysis_types) or 'none'}</li>",
            f"<li>Best resilience run: <code>{summary.best_resilience_run_id}</code></li>",
            f"<li>Lowest wait run: <code>{summary.lowest_wait_run_id}</code></li>",
            f"<li>Highest fairness run: <code>{summary.highest_fairness_run_id}</code></li>",
            "</ul>",
            "<h2>Compared Runs</h2>",
            frame.to_html(index=False, border=0),
            "<h2>Plots</h2>",
            "<h3>Tradeoff</h3>",
            "<img src='comparison_tradeoff.png' alt='comparison_tradeoff'>",
            "<h3>Metrics</h3>",
            "<img src='comparison_metrics.png' alt='comparison_metrics'>",
            "</body>",
            "</html>",
        ]
    )


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No comparison data available._"
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])
