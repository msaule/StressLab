"""Workspace status snapshots backed by the persistent registry."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
import seaborn as sns

from stresslab.campaigns.catalog import plot_catalog_systems, plot_catalog_types
from stresslab.campaigns.registry import refresh_registry, registry_paths
from stresslab.models import WorkspaceStatusSummary
from stresslab.utils import write_dataframe, write_json

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid")


def build_workspace_status(
    root: Path,
    *,
    output_dir: Path,
    title: str,
    refresh: bool = False,
    limit: int | None = 25,
) -> WorkspaceStatusSummary:
    """Build a workspace-status snapshot from the persistent registry."""

    output_dir.mkdir(parents=True, exist_ok=True)
    registry_frame = refresh_registry(root) if refresh else _load_registry_frame(root)
    if registry_frame.empty:
        registry_frame = refresh_registry(root)
    if not registry_frame.empty and "timestamp" in registry_frame.columns:
        registry_frame = registry_frame.sort_values("timestamp", ascending=False).reset_index(drop=True)

    export_frame = registry_frame.head(limit).copy() if limit is not None and not registry_frame.empty else registry_frame
    write_dataframe(output_dir / "workspace_status.csv", export_frame)
    plot_catalog_types(registry_frame, output_dir / "status_analysis_types.png")
    plot_catalog_systems(registry_frame, output_dir / "status_systems.png")
    plot_workspace_timeline(registry_frame, output_dir / "status_timeline.png")

    latest = registry_frame.iloc[0] if not registry_frame.empty else None
    summary = WorkspaceStatusSummary(
        title=title,
        root=str(Path(root).resolve()),
        entry_count=len(registry_frame),
        unique_system_count=_unique_count(registry_frame, "system_name"),
        analysis_type_counts=_value_counts(registry_frame, "analysis_type"),
        system_counts=_value_counts(registry_frame, "system_name", limit=10),
        latest_run_dir=_value_or_none(latest, "run_dir"),
        latest_timestamp=_value_or_none(latest, "timestamp"),
        latest_analysis_type=_value_or_none(latest, "analysis_type"),
        latest_system_name=_value_or_none(latest, "system_name"),
        failure_rate=_mean_or_none(registry_frame, "failure_triggered"),
        mean_resilience_score=_mean_or_none(registry_frame, "resilience_score"),
        mean_fairness_score=_mean_or_none(registry_frame, "fairness_score"),
        mean_execution_duration=_mean_or_none(registry_frame, "execution_duration"),
        registry_csv_path=str(registry_paths(root)[0]),
        report_markdown_path=str(output_dir / "workspace_status_report.md"),
        report_html_path=str(output_dir / "workspace_status_report.html"),
    )
    write_json(output_dir / "workspace_status_summary.json", summary)
    (output_dir / "workspace_status_report.md").write_text(
        _build_markdown(title=title, frame=export_frame, summary=summary),
        encoding="utf-8",
    )
    (output_dir / "workspace_status_report.html").write_text(
        _build_html(title=title, frame=export_frame, summary=summary),
        encoding="utf-8",
    )
    return summary


def plot_workspace_timeline(frame: pd.DataFrame, path: Path) -> Path:
    """Plot discovered artifact volume across timestamps."""

    plot_frame = frame.copy()
    if plot_frame.empty or "timestamp" not in plot_frame.columns:
        plot_frame = pd.DataFrame([{"timestamp": "none", "count": 0}])
        x_col = "timestamp"
    else:
        plot_frame["timestamp"] = pd.to_datetime(plot_frame["timestamp"], errors="coerce")
        plot_frame = plot_frame.dropna(subset=["timestamp"]).sort_values("timestamp")
        if plot_frame.empty:
            plot_frame = pd.DataFrame([{"timestamp": "none", "count": 0}])
            x_col = "timestamp"
        else:
            plot_frame["count"] = range(1, len(plot_frame) + 1)
            x_col = "timestamp"
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    if "count" in plot_frame.columns:
        sns.lineplot(data=plot_frame, x=x_col, y="count", marker="o", ax=ax, color="#2c7a7b")
    else:
        sns.barplot(data=plot_frame, x=x_col, y="count", ax=ax, color="#2c7a7b")
    ax.set_title("Workspace Artifact Timeline")
    ax.set_xlabel("Timestamp")
    ax.set_ylabel("Cumulative Artifacts")
    for label in ax.get_xticklabels():
        label.set_rotation(25)
        label.set_horizontalalignment("right")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _load_registry_frame(root: Path) -> pd.DataFrame:
    csv_path, _ = registry_paths(root)
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path)


def _value_counts(frame: pd.DataFrame, column: str, *, limit: int | None = None) -> dict[str, int]:
    if frame.empty or column not in frame.columns:
        return {}
    counts = frame[column].fillna("unknown").astype(str).value_counts()
    if limit is not None:
        counts = counts.head(limit)
    return {str(index): int(value) for index, value in counts.items()}


def _unique_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(frame[column].dropna().astype(str).nunique())


def _mean_or_none(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def _value_or_none(row: pd.Series | None, column: str) -> str | None:
    if row is None or column not in row.index:
        return None
    value = row[column]
    if pd.isna(value):
        return None
    return str(value)


def _build_markdown(*, title: str, frame: pd.DataFrame, summary: WorkspaceStatusSummary) -> str:
    lines = [
        f"# {title}",
        "",
        "## Snapshot",
        "",
        f"- Root: `{summary.root}`",
        f"- Registry: `{summary.registry_csv_path}`",
        f"- Tracked artifacts: `{summary.entry_count}`",
        f"- Unique systems: `{summary.unique_system_count}`",
        f"- Latest artifact: `{summary.latest_run_dir}`",
        f"- Latest timestamp: `{summary.latest_timestamp}`",
        f"- Latest analysis type: `{summary.latest_analysis_type}`",
        f"- Mean resilience score: `{summary.mean_resilience_score}`",
        f"- Mean fairness score: `{summary.mean_fairness_score}`",
        f"- Mean execution duration: `{summary.mean_execution_duration}`",
        f"- Failure rate: `{summary.failure_rate}`",
        f"- Analysis types: `{summary.analysis_type_counts}`",
        "",
        "## Recent Entries",
        "",
        _frame_to_markdown(frame),
        "",
        "## Plots",
        "",
        "![status_analysis_types](status_analysis_types.png)",
        "",
        "![status_systems](status_systems.png)",
        "",
        "![status_timeline](status_timeline.png)",
        "",
    ]
    return "\n".join(lines)


def _build_html(*, title: str, frame: pd.DataFrame, summary: WorkspaceStatusSummary) -> str:
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
            "<h2>Snapshot</h2>",
            "<ul>",
            f"<li>Root: <code>{summary.root}</code></li>",
            f"<li>Registry: <code>{summary.registry_csv_path}</code></li>",
            f"<li>Tracked artifacts: <code>{summary.entry_count}</code></li>",
            f"<li>Unique systems: <code>{summary.unique_system_count}</code></li>",
            f"<li>Latest artifact: <code>{summary.latest_run_dir}</code></li>",
            f"<li>Latest timestamp: <code>{summary.latest_timestamp}</code></li>",
            f"<li>Latest analysis type: <code>{summary.latest_analysis_type}</code></li>",
            f"<li>Mean resilience score: <code>{summary.mean_resilience_score}</code></li>",
            f"<li>Mean fairness score: <code>{summary.mean_fairness_score}</code></li>",
            f"<li>Mean execution duration: <code>{summary.mean_execution_duration}</code></li>",
            f"<li>Failure rate: <code>{summary.failure_rate}</code></li>",
            f"<li>Analysis types: <code>{summary.analysis_type_counts}</code></li>",
            "</ul>",
            "<h2>Recent Entries</h2>",
            frame.to_html(index=False, border=0),
            "<h2>Plots</h2>",
            "<h3>Analysis Types</h3>",
            "<img src='status_analysis_types.png' alt='status_analysis_types'>",
            "<h3>Systems</h3>",
            "<img src='status_systems.png' alt='status_systems'>",
            "<h3>Timeline</h3>",
            "<img src='status_timeline.png' alt='status_timeline'>",
            "</body>",
            "</html>",
        ]
    )


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No workspace artifacts discovered._"
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])
