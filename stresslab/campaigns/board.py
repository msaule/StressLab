"""Workspace decision dashboard built from the persistent registry."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import seaborn as sns

from stresslab.campaigns.catalog import plot_catalog_types
from stresslab.campaigns.registry import refresh_registry, registry_paths
from stresslab.models import WorkspaceBoardSummary
from stresslab.utils import write_dataframe, write_json

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid")


def build_workspace_board(
    root: Path,
    *,
    output_dir: Path,
    title: str,
    refresh: bool = False,
    recent_limit: int = 20,
    watch_limit: int = 12,
    plan_limit: int = 12,
) -> WorkspaceBoardSummary:
    """Build a decision dashboard from the workspace registry."""

    output_dir.mkdir(parents=True, exist_ok=True)
    registry_frame = refresh_registry(root) if refresh else _load_registry_frame(root)
    if registry_frame.empty:
        registry_frame = refresh_registry(root)
    registry_frame = _normalize_frame(registry_frame)

    recent_frame = registry_frame.head(recent_limit).copy()
    leaders_frame = _build_system_leaders(registry_frame)
    watch_frame = _build_failure_watchlist(registry_frame, limit=watch_limit)
    plans_frame = _build_actionable_plans(registry_frame, limit=plan_limit)

    write_dataframe(output_dir / "workspace_board_recent.csv", recent_frame)
    write_dataframe(output_dir / "workspace_board_leaders.csv", leaders_frame)
    write_dataframe(output_dir / "workspace_board_failure_watchlist.csv", watch_frame)
    write_dataframe(output_dir / "workspace_board_plans.csv", plans_frame)

    plot_catalog_types(registry_frame, output_dir / "board_analysis_mix.png")
    plot_board_system_leaders(leaders_frame, output_dir / "board_system_resilience.png")
    plot_board_failure_watchlist(watch_frame, output_dir / "board_failure_watchlist.png")
    plot_board_plan_tradeoff(plans_frame, output_dir / "board_plan_tradeoff.png")

    latest = registry_frame.iloc[0] if not registry_frame.empty else None
    top_system = leaders_frame.iloc[0] if not leaders_frame.empty else None
    top_plan = plans_frame.iloc[0] if not plans_frame.empty else None
    summary = WorkspaceBoardSummary(
        title=title,
        root=str(Path(root).resolve()),
        entry_count=len(registry_frame),
        recent_entry_count=len(recent_frame),
        system_leader_count=len(leaders_frame),
        failure_watch_count=len(watch_frame),
        optimize_plan_count=len(plans_frame),
        latest_run_dir=_value_or_none(latest, "run_dir"),
        latest_timestamp=_value_or_none(latest, "timestamp"),
        top_system_by_resilience=_value_or_none(top_system, "system_name"),
        top_plan_run_dir=_value_or_none(top_plan, "run_dir"),
        top_plan_system_name=_value_or_none(top_plan, "system_name"),
        mean_resilience_score=_mean_or_none(registry_frame, "resilience_score"),
        mean_fairness_score=_mean_or_none(registry_frame, "fairness_score"),
        mean_execution_duration=_mean_or_none(registry_frame, "execution_duration"),
        registry_csv_path=str(registry_paths(root)[0]),
        recent_entries_path=str(output_dir / "workspace_board_recent.csv"),
        leaders_path=str(output_dir / "workspace_board_leaders.csv"),
        failure_watchlist_path=str(output_dir / "workspace_board_failure_watchlist.csv"),
        plans_path=str(output_dir / "workspace_board_plans.csv"),
        report_markdown_path=str(output_dir / "workspace_board_report.md"),
        report_html_path=str(output_dir / "workspace_board_report.html"),
    )
    write_json(output_dir / "workspace_board_summary.json", summary)
    (output_dir / "workspace_board_report.md").write_text(
        _build_markdown(
            title=title,
            summary=summary,
            recent_frame=recent_frame,
            leaders_frame=leaders_frame,
            watch_frame=watch_frame,
            plans_frame=plans_frame,
        ),
        encoding="utf-8",
    )
    (output_dir / "workspace_board_report.html").write_text(
        _build_html(
            title=title,
            summary=summary,
            recent_frame=recent_frame,
            leaders_frame=leaders_frame,
            watch_frame=watch_frame,
            plans_frame=plans_frame,
        ),
        encoding="utf-8",
    )
    return summary


def plot_board_system_leaders(frame: pd.DataFrame, path: Path) -> Path:
    """Plot the strongest known artifact per system by resilience."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame([{"system_name": "none", "resilience_score": 0.0, "analysis_type": "run"}])
    fig, ax = plt.subplots(figsize=(9.5, max(4.8, 0.45 * len(plot_frame) + 1.8)))
    sns.barplot(
        data=plot_frame,
        x="resilience_score",
        y="system_name",
        hue="analysis_type" if "analysis_type" in plot_frame.columns else None,
        ax=ax,
    )
    ax.set_title("System Leaders by Resilience")
    ax.set_xlabel("Resilience score")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_board_failure_watchlist(frame: pd.DataFrame, path: Path) -> Path:
    """Plot the highest-risk recent artifacts."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame([{"run_id": "none", "mean_wait": 0.0, "failure_triggered": False}])
    y_column = "run_id" if "run_id" in plot_frame.columns else plot_frame.columns[0]
    fig, ax = plt.subplots(figsize=(10.0, max(4.8, 0.42 * len(plot_frame) + 1.8)))
    sns.barplot(
        data=plot_frame,
        x="mean_wait",
        y=y_column,
        hue="failure_triggered" if "failure_triggered" in plot_frame.columns else None,
        ax=ax,
    )
    ax.set_title("Failure Watchlist by Mean Wait")
    ax.set_xlabel("Mean wait")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_board_plan_tradeoff(frame: pd.DataFrame, path: Path) -> Path:
    """Plot optimize-plan tradeoffs across resilience and fairness."""

    plot_frame = frame.copy()
    if plot_frame.empty:
        plot_frame = pd.DataFrame(
            [
                {
                    "system_name": "none",
                    "resilience_score": 0.0,
                    "fairness_score": 0.0,
                    "robust_mode": False,
                }
            ]
        )
    if "replicate_count" in plot_frame.columns:
        evidence_size = pd.to_numeric(plot_frame["replicate_count"], errors="coerce").fillna(0.0)
    elif "scenario_count" in plot_frame.columns:
        evidence_size = pd.to_numeric(plot_frame["scenario_count"], errors="coerce").fillna(0.0)
    else:
        evidence_size = pd.Series([1.0] * len(plot_frame), index=plot_frame.index)
    plot_frame["evidence_size"] = evidence_size.replace(0.0, 1.0)
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    sns.scatterplot(
        data=plot_frame,
        x="fairness_score",
        y="resilience_score",
        hue="system_name",
        style="analysis_type" if "analysis_type" in plot_frame.columns else None,
        size="evidence_size",
        sizes=(90, 240),
        ax=ax,
    )
    for row in plot_frame.itertuples(index=False):
        label = getattr(row, "recommended_portfolio_id", None) or getattr(row, "top_intervention_id", None) or getattr(row, "run_id", "plan")
        ax.annotate(str(label), (row.fairness_score, row.resilience_score), xytext=(4, 4), textcoords="offset points", fontsize=7)
    ax.set_title("Optimize Plans: Fairness vs Resilience")
    ax.set_xlabel("Fairness score")
    ax.set_ylabel("Resilience score")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    normalized = frame.copy()
    if "timestamp" in normalized.columns:
        normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="coerce")
        normalized = normalized.sort_values("timestamp", ascending=False, na_position="last").reset_index(drop=True)
        normalized["timestamp"] = normalized["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    for column in [
        "resilience_score",
        "fairness_score",
        "mean_wait",
        "throughput",
        "execution_duration",
        "best_resilience",
        "best_shock_budget",
        "damage_score",
        "scenario_count",
        "cluster_count",
    ]:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "failure_triggered" in normalized.columns:
        normalized["failure_triggered"] = normalized["failure_triggered"].astype("boolean")
    if "robust_mode" in normalized.columns:
        normalized["robust_mode"] = normalized["robust_mode"].astype("boolean")
    return normalized


def _build_system_leaders(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "system_name" not in frame.columns or "resilience_score" not in frame.columns:
        return pd.DataFrame()
    candidate = frame.dropna(subset=["system_name", "resilience_score"]).copy()
    if candidate.empty:
        return pd.DataFrame()
    candidate = candidate.sort_values(
        ["resilience_score", "fairness_score", "timestamp"],
        ascending=[False, False, False],
        na_position="last",
    )
    leaders = candidate.groupby("system_name", as_index=False).head(1).reset_index(drop=True)
    return leaders[
        [
            column
            for column in [
                "system_name",
                "analysis_type",
                "run_id",
                "run_dir",
                "timestamp",
                "resilience_score",
                "fairness_score",
                "throughput",
                "mean_wait",
                "top_intervention_id",
                "recommended_portfolio_id",
            ]
            if column in leaders.columns
        ]
    ]


def _build_failure_watchlist(frame: pd.DataFrame, *, limit: int) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    candidate = frame.copy()
    if "analysis_type" in candidate.columns:
        candidate = candidate[candidate["analysis_type"].isin(["run", "search", "optimize"])]
    if candidate.empty:
        return pd.DataFrame()
    if "failure_triggered" in candidate.columns:
        failures = candidate[candidate["failure_triggered"] == True]  # noqa: E712
    else:
        failures = pd.DataFrame()
    if len(failures) < limit and "resilience_score" in candidate.columns:
        filler = candidate.sort_values(
            ["resilience_score", "mean_wait", "timestamp"],
            ascending=[True, False, False],
            na_position="last",
        )
        candidate = pd.concat([failures, filler], ignore_index=True)
    else:
        candidate = failures
    candidate = candidate.drop_duplicates(subset=["run_dir"], keep="first")
    candidate = candidate.sort_values(
        ["failure_triggered", "resilience_score", "mean_wait", "timestamp"],
        ascending=[False, True, False, False],
        na_position="last",
    ).head(limit)
    return candidate[
        [
            column
            for column in [
                "run_id",
                "system_name",
                "analysis_type",
                "timestamp",
                "failure_triggered",
                "resilience_score",
                "fairness_score",
                "mean_wait",
                "throughput",
                "run_dir",
            ]
            if column in candidate.columns
        ]
    ]


def _build_actionable_plans(frame: pd.DataFrame, *, limit: int) -> pd.DataFrame:
    if frame.empty or "analysis_type" not in frame.columns:
        return pd.DataFrame()
    plans = frame[frame["analysis_type"].isin(["optimize", "evaluation"])].copy()
    if plans.empty:
        return pd.DataFrame()
    if "replicate_count" not in plans.columns:
        plans["replicate_count"] = 0
    plans["replicate_count"] = pd.to_numeric(plans["replicate_count"], errors="coerce").fillna(0.0)
    plans["evidence_rank"] = np.where(plans["analysis_type"] == "evaluation", 1.0, 0.0)
    plans = plans.sort_values(
        ["evidence_rank", "replicate_count", "robust_mode", "resilience_score", "fairness_score", "timestamp"],
        ascending=[False, False, False, False, False, False],
        na_position="last",
    ).head(limit)
    return plans[
        [
            column
            for column in [
                "run_id",
                "system_name",
                "analysis_type",
                "timestamp",
                "robust_mode",
                "replicate_count",
                "scenario_count",
                "cluster_count",
                "resilience_score",
                "fairness_score",
                "mean_wait",
                "top_intervention_id",
                "recommended_portfolio_id",
                "run_dir",
            ]
            if column in plans.columns
        ]
    ]


def _load_registry_frame(root: Path) -> pd.DataFrame:
    csv_path, _ = registry_paths(root)
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path)


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


def _build_markdown(
    *,
    title: str,
    summary: WorkspaceBoardSummary,
    recent_frame: pd.DataFrame,
    leaders_frame: pd.DataFrame,
    watch_frame: pd.DataFrame,
    plans_frame: pd.DataFrame,
) -> str:
    lines = [
        f"# {title}",
        "",
        "## Snapshot",
        "",
        f"- Root: `{summary.root}`",
        f"- Registry: `{summary.registry_csv_path}`",
        f"- Tracked artifacts: `{summary.entry_count}`",
        f"- Recent entries shown: `{summary.recent_entry_count}`",
        f"- System leaders: `{summary.system_leader_count}`",
        f"- Failure watchlist entries: `{summary.failure_watch_count}`",
        f"- Optimize plans: `{summary.optimize_plan_count}`",
        f"- Latest artifact: `{summary.latest_run_dir}`",
        f"- Top system by resilience: `{summary.top_system_by_resilience}`",
        f"- Top plan system: `{summary.top_plan_system_name}`",
        "",
        "## Recent Activity",
        "",
        _frame_to_markdown(recent_frame),
        "",
        "## System Leaders",
        "",
        _frame_to_markdown(leaders_frame),
        "",
        "## Failure Watchlist",
        "",
        _frame_to_markdown(watch_frame),
        "",
        "## Actionable Plans",
        "",
        _frame_to_markdown(plans_frame),
        "",
        "## Plots",
        "",
        "![board_analysis_mix](board_analysis_mix.png)",
        "",
        "![board_system_resilience](board_system_resilience.png)",
        "",
        "![board_failure_watchlist](board_failure_watchlist.png)",
        "",
        "![board_plan_tradeoff](board_plan_tradeoff.png)",
        "",
    ]
    return "\n".join(lines)


def _build_html(
    *,
    title: str,
    summary: WorkspaceBoardSummary,
    recent_frame: pd.DataFrame,
    leaders_frame: pd.DataFrame,
    watch_frame: pd.DataFrame,
    plans_frame: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            f"<title>{title}</title>",
            "<style>",
            "body { font-family: Georgia, serif; margin: 2rem auto; max-width: 1180px; color: #182026; }",
            "table { border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }",
            "td, th { border: 1px solid #d6dde2; padding: 0.45rem 0.6rem; text-align: left; }",
            "img { max-width: 100%; border: 1px solid #d6dde2; margin-bottom: 1.5rem; }",
            ".grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.9rem; margin-bottom: 1.5rem; }",
            ".card { border: 1px solid #d6dde2; padding: 0.9rem; background: #fafcfd; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{title}</h1>",
            "<div class='grid'>",
            f"<div class='card'><strong>Tracked artifacts</strong><br><code>{summary.entry_count}</code></div>",
            f"<div class='card'><strong>System leaders</strong><br><code>{summary.system_leader_count}</code></div>",
            f"<div class='card'><strong>Failure watchlist</strong><br><code>{summary.failure_watch_count}</code></div>",
            f"<div class='card'><strong>Optimize plans</strong><br><code>{summary.optimize_plan_count}</code></div>",
            f"<div class='card'><strong>Latest artifact</strong><br><code>{summary.latest_run_dir}</code></div>",
            f"<div class='card'><strong>Top system</strong><br><code>{summary.top_system_by_resilience}</code></div>",
            f"<div class='card'><strong>Top plan system</strong><br><code>{summary.top_plan_system_name}</code></div>",
            f"<div class='card'><strong>Registry</strong><br><code>{summary.registry_csv_path}</code></div>",
            "</div>",
            "<h2>Recent Activity</h2>",
            recent_frame.to_html(index=False, border=0),
            "<h2>System Leaders</h2>",
            leaders_frame.to_html(index=False, border=0),
            "<h2>Failure Watchlist</h2>",
            watch_frame.to_html(index=False, border=0),
            "<h2>Actionable Plans</h2>",
            plans_frame.to_html(index=False, border=0),
            "<h2>Plots</h2>",
            "<h3>Analysis Mix</h3>",
            "<img src='board_analysis_mix.png' alt='board_analysis_mix'>",
            "<h3>System Leaders</h3>",
            "<img src='board_system_resilience.png' alt='board_system_resilience'>",
            "<h3>Failure Watchlist</h3>",
            "<img src='board_failure_watchlist.png' alt='board_failure_watchlist'>",
            "<h3>Actionable Plans</h3>",
            "<img src='board_plan_tradeoff.png' alt='board_plan_tradeoff'>",
            "</body>",
            "</html>",
        ]
    )


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows available._"
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])
