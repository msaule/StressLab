"""Workspace run-catalog utilities for StressLab artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import pandas as pd
import seaborn as sns

from stresslab.campaigns.compare import summarize_run_dir
from stresslab.models import RunCatalogEntry, RunCatalogSummary
from stresslab.utils import write_dataframe, write_json

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid")


def build_run_catalog(
    root: Path,
    *,
    output_dir: Path,
    title: str,
    analysis_type: str | None = None,
    system_name: str | None = None,
    limit: int | None = None,
) -> RunCatalogSummary:
    """Scan a workspace root and build a reportable catalog of discovered artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    entries = discover_catalog_entries(root)
    if analysis_type is not None:
        entries = [entry for entry in entries if entry.analysis_type == analysis_type]
    if system_name is not None:
        lowered = system_name.lower()
        entries = [entry for entry in entries if lowered in entry.system_name.lower()]
    frame = pd.DataFrame([entry.model_dump(mode="json") for entry in entries])
    if not frame.empty:
        frame = frame.sort_values("timestamp", ascending=False)
        if limit is not None:
            frame = frame.head(limit)
    write_dataframe(output_dir / "run_catalog.csv", frame)
    plot_catalog_types(frame, output_dir / "catalog_types.png")
    plot_catalog_systems(frame, output_dir / "catalog_systems.png")
    summary = RunCatalogSummary(
        title=title,
        root=str(Path(root).resolve()),
        entry_count=len(frame),
        analysis_type_counts=(
            frame["analysis_type"].value_counts().to_dict()
            if not frame.empty and "analysis_type" in frame.columns
            else {}
        ),
        system_counts=(
            frame["system_name"].value_counts().head(10).to_dict()
            if not frame.empty and "system_name" in frame.columns
            else {}
        ),
        catalog_csv_path=str(output_dir / "run_catalog.csv"),
        report_markdown_path=str(output_dir / "run_catalog_report.md"),
        report_html_path=str(output_dir / "run_catalog_report.html"),
    )
    write_json(output_dir / "run_catalog_summary.json", summary)
    markdown = _build_markdown(title=title, frame=frame, summary=summary)
    (output_dir / "run_catalog_report.md").write_text(markdown, encoding="utf-8")
    html = _build_html(title=title, frame=frame, summary=summary)
    (output_dir / "run_catalog_report.html").write_text(html, encoding="utf-8")
    return summary


def discover_catalog_entries(root: Path) -> list[RunCatalogEntry]:
    """Discover artifact directories under a root by scanning for metadata.json."""

    root = Path(root)
    entries: list[RunCatalogEntry] = []
    for metadata_path in sorted(root.rglob("metadata.json")):
        run_dir = metadata_path.parent
        entry = catalog_entry_from_dir(run_dir)
        if entry is not None:
            entries.append(entry)
    return entries


def catalog_entry_from_dir(run_dir: Path) -> RunCatalogEntry | None:
    """Build a catalog entry from one artifact directory."""

    metadata = _load_json(run_dir / "metadata.json")
    if not metadata:
        return None
    if (run_dir / "batch_summary.json").exists():
        summary = _load_json(run_dir / "batch_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "batch_campaign"),
            analysis_type="batch",
            command=metadata.get("command", "stresslab batch"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=str(run_dir / "batch_report.html") if (run_dir / "batch_report.html").exists() else None,
            batch_job_count=summary.get("total_jobs"),
            failed_job_count=summary.get("failed_jobs"),
        )
    if (run_dir / "comparison_summary.json").exists():
        summary = _load_json(run_dir / "comparison_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "comparison"),
            analysis_type="comparison",
            command=metadata.get("command", "stresslab compare"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=str(run_dir / "comparison_report.html") if (run_dir / "comparison_report.html").exists() else None,
            compared_run_count=summary.get("run_count"),
        )
    if (run_dir / "run_catalog_summary.json").exists():
        summary = _load_json(run_dir / "run_catalog_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "run_catalog"),
            analysis_type="catalog",
            command=metadata.get("command", "stresslab catalog"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=str(run_dir / "run_catalog_report.html") if (run_dir / "run_catalog_report.html").exists() else None,
            catalog_entry_count=summary.get("entry_count"),
        )
    if (run_dir / "workspace_board_summary.json").exists():
        summary = _load_json(run_dir / "workspace_board_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "workspace_board"),
            analysis_type="board",
            command=metadata.get("command", "stresslab board"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=(
                str(run_dir / "workspace_board_report.html")
                if (run_dir / "workspace_board_report.html").exists()
                else None
            ),
            tracked_entry_count=summary.get("entry_count"),
        )
    if (run_dir / "workspace_status_summary.json").exists():
        summary = _load_json(run_dir / "workspace_status_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "workspace_status"),
            analysis_type="status",
            command=metadata.get("command", "stresslab status"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=(
                str(run_dir / "workspace_status_report.html")
                if (run_dir / "workspace_status_report.html").exists()
                else None
            ),
            tracked_entry_count=summary.get("entry_count"),
        )
    if (run_dir / "doctor_summary.json").exists():
        summary = _load_json(run_dir / "doctor_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "workspace_doctor"),
            analysis_type="doctor",
            command=metadata.get("command", "stresslab doctor"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=(
                str(run_dir / "doctor_report.html")
                if (run_dir / "doctor_report.html").exists()
                else None
            ),
            container_build_ready=summary.get("ready_for_container_build"),
        )
    if (run_dir / "generation_summary.json").exists():
        summary = _load_json(run_dir / "generation_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "synthetic_generation"),
            analysis_type="generate",
            command=metadata.get("command", "stresslab generate"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=(
                str(run_dir / "generation_report.html")
                if (run_dir / "generation_report.html").exists()
                else None
            ),
            generated_system_count=summary.get("system_count"),
            shard_count=summary.get("shard_count"),
            shard_index=summary.get("shard_index"),
        )
    if (run_dir / "discovery_summary.json").exists():
        summary = _load_json(run_dir / "discovery_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "discovery_campaign"),
            analysis_type="discover",
            command=metadata.get("command", "stresslab discover"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=(
                str(run_dir / "discovery_report.html")
                if (run_dir / "discovery_report.html").exists()
                else None
            ),
            generated_system_count=summary.get("generated_system_count"),
            dataset_row_count=summary.get("dataset_row_count"),
            shard_count=summary.get("shard_count"),
            shard_index=summary.get("shard_index"),
            worker_count=summary.get("worker_count"),
            resumed_system_count=summary.get("resumed_system_count"),
        )
    if (run_dir / "theory_summary.json").exists():
        summary = _load_json(run_dir / "theory_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "theory_analysis"),
            analysis_type="theory",
            command=metadata.get("command", "stresslab theory"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=(
                str(run_dir / "theory_report.html")
                if (run_dir / "theory_report.html").exists()
                else None
            ),
            dataset_row_count=_load_csv(Path(summary.get("dataset_path", ""))).shape[0]
            if summary.get("dataset_path")
            else None,
            law_candidate_count=summary.get("law_candidate_count"),
            symbolic_law_count=summary.get("symbolic_law_count"),
        )
    if (run_dir / "research_summary.json").exists():
        summary = _load_json(run_dir / "research_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "research_report"),
            analysis_type="research",
            command=metadata.get("command", "stresslab research"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=(
                str(run_dir / "research_report.html")
                if (run_dir / "research_report.html").exists()
                else None
            ),
            law_candidate_count=_load_csv(Path(summary.get("theory_dir", "")) / "law_candidates.csv").shape[0]
            if summary.get("theory_dir")
            else None,
        )
    if (run_dir / "casebook_summary.json").exists():
        summary = _load_json(run_dir / "casebook_summary.json")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "casebook"),
            analysis_type="casebook",
            command=metadata.get("command", "stresslab casebook"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=(
                str(run_dir / "casebook_report.html")
                if (run_dir / "casebook_report.html").exists()
                else None
            ),
            casebook_record_count=summary.get("record_count"),
        )
    if (run_dir / "evaluation_summary.json").exists():
        summary = _load_json(run_dir / "evaluation_summary.json")
        metric_rows = _load_csv(run_dir / "evaluation_metric_summary.csv")
        def metric_value(metric: str, column: str) -> float | None:
            if metric_rows.empty or "metric" not in metric_rows.columns or column not in metric_rows.columns:
                return None
            matches = metric_rows[metric_rows["metric"] == metric]
            if matches.empty:
                return None
            value = matches.iloc[0][column]
            return float(value) if pd.notna(value) else None
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=summary.get("system_name", metadata.get("system_name", "evaluation")),
            analysis_type="evaluation",
            command=metadata.get("command", "stresslab evaluate"),
            status="completed",
            failure_triggered=bool(summary.get("scenario_failure_rate", 0.0) > 0.0),
            throughput=metric_value("throughput", "scenario_mean"),
            mean_wait=metric_value("mean_wait", "scenario_mean"),
            resilience_score=metric_value("resilience_score", "scenario_mean"),
            fairness_score=metric_value("fairness_score", "scenario_mean"),
            execution_duration=metadata.get("execution_duration"),
            report_html_path=(
                str(run_dir / "evaluation_report.html")
                if (run_dir / "evaluation_report.html").exists()
                else None
            ),
            top_intervention_id=(
                summary.get("selected_intervention_ids", [None])[0]
                if summary.get("selected_intervention_ids")
                else None
            ),
            replicate_count=summary.get("replicate_count"),
        )
    if (run_dir / "benchmark_summary.json").exists():
        frame = _load_csv(run_dir / "benchmark_summary.csv")
        return RunCatalogEntry(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            timestamp=metadata.get("timestamp"),
            system_name=metadata.get("system_name", "benchmark_suite"),
            analysis_type="benchmark",
            command=metadata.get("command", "stresslab benchmark"),
            status="completed",
            execution_duration=metadata.get("execution_duration"),
            report_html_path=str(run_dir / "benchmark_report.html") if (run_dir / "benchmark_report.html").exists() else None,
            benchmark_record_count=len(frame),
        )
    comparison = summarize_run_dir(run_dir)
    return RunCatalogEntry(
        run_id=comparison.run_id,
        run_dir=comparison.run_dir,
        timestamp=metadata.get("timestamp"),
        system_name=comparison.system_name,
        analysis_type=comparison.analysis_type,
        command=comparison.command,
        status="completed",
        failure_triggered=comparison.failure_triggered,
        robust_mode=comparison.robust_mode,
        scenario_count=comparison.scenario_count,
        cluster_count=comparison.cluster_count,
        throughput=comparison.throughput,
        mean_wait=comparison.mean_wait,
        resilience_score=comparison.resilience_score,
        fairness_score=comparison.fairness_score,
        best_resilience=comparison.best_resilience,
        best_shock_budget=comparison.best_shock_budget,
        damage_score=comparison.damage_score,
        top_intervention_id=comparison.top_intervention_id,
        recommended_portfolio_id=comparison.recommended_portfolio_id,
        execution_duration=comparison.execution_duration,
        report_html_path=comparison.report_html_path,
    )


def plot_catalog_types(frame: pd.DataFrame, path: Path) -> Path:
    """Plot discovered entries by analysis type."""

    plot_frame = frame.copy()
    if plot_frame.empty or "analysis_type" not in plot_frame.columns:
        plot_frame = pd.DataFrame([{"analysis_type": "none", "count": 0}])
    else:
        plot_frame = (
            plot_frame["analysis_type"]
            .value_counts()
            .rename_axis("analysis_type")
            .reset_index(name="count")
        )
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    sns.barplot(data=plot_frame, x="count", y="analysis_type", ax=ax, color="#2f6c80")
    ax.set_title("Catalog Entries by Analysis Type")
    ax.set_xlabel("Count")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_catalog_systems(frame: pd.DataFrame, path: Path) -> Path:
    """Plot the most common systems in the discovered catalog."""

    plot_frame = frame.copy()
    if plot_frame.empty or "system_name" not in plot_frame.columns:
        plot_frame = pd.DataFrame([{"system_name": "none", "count": 0}])
    else:
        plot_frame = (
            plot_frame["system_name"]
            .value_counts()
            .head(10)
            .rename_axis("system_name")
            .reset_index(name="count")
        )
    fig, ax = plt.subplots(figsize=(9.0, max(4.6, 0.45 * len(plot_frame) + 1.8)))
    sns.barplot(data=plot_frame, x="count", y="system_name", ax=ax, color="#8c5e3c")
    ax.set_title("Catalog Entries by System")
    ax.set_xlabel("Count")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _build_markdown(*, title: str, frame: pd.DataFrame, summary: RunCatalogSummary) -> str:
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        f"- Root: `{summary.root}`",
        f"- Entry count: `{summary.entry_count}`",
        f"- Analysis types: {summary.analysis_type_counts or {}}",
        f"- Systems: {summary.system_counts or {}}",
        "",
        "## Catalog",
        "",
        _frame_to_markdown(frame),
        "",
        "## Plots",
        "",
        "![catalog_types](catalog_types.png)",
        "",
        "![catalog_systems](catalog_systems.png)",
        "",
    ]
    return "\n".join(lines)


def _build_html(*, title: str, frame: pd.DataFrame, summary: RunCatalogSummary) -> str:
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
            f"<li>Root: <code>{summary.root}</code></li>",
            f"<li>Entry count: <code>{summary.entry_count}</code></li>",
            f"<li>Analysis types: <code>{summary.analysis_type_counts}</code></li>",
            f"<li>Systems: <code>{summary.system_counts}</code></li>",
            "</ul>",
            "<h2>Catalog</h2>",
            frame.to_html(index=False, border=0),
            "<h2>Plots</h2>",
            "<h3>Analysis Types</h3>",
            "<img src='catalog_types.png' alt='catalog_types'>",
            "<h3>Systems</h3>",
            "<img src='catalog_systems.png' alt='catalog_systems'>",
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
        return "_No catalog entries discovered._"
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])
