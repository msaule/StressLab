"""Theory analysis and publication-style research artifacts."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from stresslab.discovery.engine import compute_feature_importance, discover_candidate_laws
from stresslab.discovery.symbolic import symbolic_regression_search
from stresslab.models import ResearchSummary, TheorySummary
from stresslab.theory import (
    bootstrap_phase_transition,
    compare_tail_models,
    detect_phase_transition,
    fit_fragility_models,
    fit_power_law,
    summarize_early_warning_dataset,
    summarize_early_warning_trends,
)
from stresslab.utils import ensure_directory, write_dataframe, write_json
from stresslab.viz.discovery import (
    plot_cascade_distribution,
    plot_collapse_heatmap,
    plot_feature_importance,
    plot_fragility_curves,
    plot_law_candidates,
    plot_phase_transition,
)


def build_theory_artifacts(dataset_source: Path, *, output_dir: Path) -> TheorySummary:
    """Analyze a discovery dataset and write theory-layer artifacts."""

    output_dir = ensure_directory(Path(output_dir))
    dataset_bundle = _load_dataset_bundle(dataset_source, output_dir=output_dir)
    dataset_path = dataset_bundle["dataset_path"]
    frame = dataset_bundle["dataset_frame"]
    feature_importance = compute_feature_importance(frame, target="collapse_probability")
    fragility_models, fitted_laws = fit_fragility_models(frame)
    candidate_laws = discover_candidate_laws(frame, target="collapse_probability")
    symbolic_laws = symbolic_regression_search(frame, target="collapse_probability")
    all_laws = _concat_frames([fitted_laws, candidate_laws, symbolic_laws]).drop_duplicates(subset=["formula"], keep="first")
    phase_result, phase_curve = detect_phase_transition(
        frame,
        feature="baseline_utilization" if "baseline_utilization" in frame.columns else "utilization",
        outcome="collapse_probability",
    )
    phase_bootstrap = bootstrap_phase_transition(
        frame,
        feature=phase_result.feature,
        outcome=phase_result.outcome,
    )
    powerlaw = fit_power_law(frame.get("worst_case_cascade_size", pd.Series(dtype=float)))
    tail_models = compare_tail_models(frame.get("worst_case_cascade_size", pd.Series(dtype=float)))
    early_warning_frame = dataset_bundle["early_warning_frame"]
    early_warning_summary = summarize_early_warning_dataset(early_warning_frame)
    early_warning_trends = summarize_early_warning_trends(early_warning_frame)

    write_dataframe(output_dir / "feature_importance.csv", feature_importance)
    write_dataframe(output_dir / "fragility_models.csv", fragility_models)
    write_dataframe(output_dir / "law_candidates.csv", all_laws)
    write_dataframe(output_dir / "symbolic_laws.csv", symbolic_laws)
    write_dataframe(output_dir / "phase_transition_curve.csv", phase_curve)
    write_dataframe(output_dir / "phase_transition_bootstrap.csv", phase_bootstrap)
    write_dataframe(output_dir / "powerlaw_fits.csv", pd.DataFrame([powerlaw.model_dump(mode="json")]))
    write_dataframe(output_dir / "tail_model_comparison.csv", tail_models)
    write_dataframe(
        output_dir / "early_warning_summary.csv",
        pd.DataFrame([early_warning_summary.model_dump(mode="json")]),
    )
    write_dataframe(output_dir / "early_warning_trends.csv", early_warning_trends)
    write_json(output_dir / "phase_transition.json", phase_result)
    write_json(output_dir / "powerlaw_fit.json", powerlaw)
    write_json(output_dir / "early_warning_summary.json", early_warning_summary)

    plot_fragility_curves(frame, output_dir / "fragility_curves.png")
    plot_feature_importance(feature_importance, output_dir / "feature_importance.png")
    plot_law_candidates(all_laws, output_dir / "law_discovery.png")
    plot_phase_transition(
        phase_curve,
        output_dir / "phase_transition.png",
        feature=phase_result.feature,
        outcome=phase_result.outcome,
    )
    plot_collapse_heatmap(frame, output_dir / "collapse_heatmap.png")
    distribution = _collapse_distribution(frame)
    plot_cascade_distribution(distribution, output_dir / "cascade_distribution.png")
    write_dataframe(output_dir / "collapse_distribution.csv", distribution)

    summary = TheorySummary(
        title="StressLab Theory Analysis",
        theory_dir=str(output_dir),
        dataset_path=str(dataset_path),
        source_dataset_count=int(dataset_bundle["source_dataset_count"]),
        fragility_model_count=len(fragility_models),
        law_candidate_count=len(all_laws),
        symbolic_law_count=len(symbolic_laws),
        phase_transition_path=str(output_dir / "phase_transition.json"),
        powerlaw_path=str(output_dir / "powerlaw_fit.json"),
        early_warning_path=str(output_dir / "early_warning_summary.json"),
        report_markdown_path=str(output_dir / "theory_report.md"),
        report_html_path=str(output_dir / "theory_report.html"),
    )
    write_json(output_dir / "theory_summary.json", summary)
    markdown = _build_theory_markdown(
        summary,
        feature_importance,
        all_laws,
        symbolic_laws,
        phase_result,
        powerlaw,
        tail_models,
        early_warning_summary,
        early_warning_trends,
        phase_bootstrap,
    )
    (output_dir / "theory_report.md").write_text(markdown, encoding="utf-8")
    html = _build_theory_html(
        summary,
        feature_importance,
        all_laws,
        symbolic_laws,
        phase_result,
        powerlaw,
        tail_models,
        early_warning_summary,
        early_warning_trends,
        phase_bootstrap,
    )
    (output_dir / "theory_report.html").write_text(html, encoding="utf-8")
    return summary


def build_research_artifacts(
    dataset_source: Path,
    *,
    output_dir: Path,
    theory_dir: Path | None = None,
) -> ResearchSummary:
    """Build publication-style research artifacts from a discovery dataset."""

    output_dir = ensure_directory(Path(output_dir))
    resolved_theory_dir = Path(theory_dir) if theory_dir is not None else output_dir / "theory"
    theory_summary = build_theory_artifacts(dataset_source, output_dir=resolved_theory_dir)
    dataset_path = Path(theory_summary.dataset_path)
    frame = pd.read_csv(dataset_path)
    figures_dir = ensure_directory(output_dir / "figures")
    figures = [
        resolved_theory_dir / "fragility_curves.png",
        resolved_theory_dir / "collapse_heatmap.png",
        resolved_theory_dir / "phase_transition.png",
        resolved_theory_dir / "cascade_distribution.png",
        resolved_theory_dir / "feature_importance.png",
        resolved_theory_dir / "law_discovery.png",
    ]
    figure_rows: list[dict[str, str]] = []
    for figure in figures:
        if not figure.exists():
            continue
        target = figures_dir / figure.name
        shutil.copy2(figure, target)
        figure_rows.append({"figure": figure.name, "path": str(target)})
    write_dataframe(output_dir / "figure_index.csv", pd.DataFrame(figure_rows))
    summary = ResearchSummary(
        title="StressLab Research Report",
        research_dir=str(output_dir),
        dataset_path=str(dataset_path),
        source_dataset_count=theory_summary.source_dataset_count,
        theory_dir=str(resolved_theory_dir),
        report_markdown_path=str(output_dir / "research_report.md"),
        report_html_path=str(output_dir / "research_report.html"),
        figure_count=len(figure_rows),
    )
    write_json(output_dir / "research_summary.json", summary)
    markdown = _build_research_markdown(summary, theory_summary, frame, figure_rows)
    (output_dir / "research_report.md").write_text(markdown, encoding="utf-8")
    html = _build_research_html(summary, theory_summary, frame, figure_rows)
    (output_dir / "research_report.html").write_text(html, encoding="utf-8")
    return summary


def _resolve_dataset_path(dataset_source: Path) -> Path:
    path = Path(dataset_source)
    if path.is_dir():
        candidate = path / "collapse_dataset.csv"
        if candidate.exists():
            return candidate
        candidate = path / "discovery" / "collapse_dataset.csv"
        if candidate.exists():
            return candidate
    return path


def _load_dataset_bundle(dataset_source: Path, *, output_dir: Path) -> dict[str, object]:
    path = Path(dataset_source)
    direct_dataset = _resolve_dataset_path(path)
    if direct_dataset.exists() and direct_dataset.is_file():
        return {
            "dataset_path": direct_dataset,
            "dataset_frame": pd.read_csv(direct_dataset),
            "early_warning_frame": _load_optional_csv(direct_dataset.with_name("early_warning_dataset.csv")),
            "source_dataset_count": 1,
        }

    dataset_paths = sorted(
        candidate
        for candidate in path.rglob("collapse_dataset.csv")
        if candidate.is_file()
    )
    if not dataset_paths:
        raise FileNotFoundError(f"Could not resolve a discovery dataset from '{dataset_source}'.")

    dataset_frames: list[pd.DataFrame] = []
    early_frames: list[pd.DataFrame] = []
    source_rows: list[dict[str, object]] = []
    for dataset_path in dataset_paths:
        frame = pd.read_csv(dataset_path)
        run_dir = dataset_path.parent
        tagged = frame.copy()
        tagged["source_run_dir"] = str(run_dir)
        dataset_frames.append(tagged)
        early_path = dataset_path.with_name("early_warning_dataset.csv")
        early_frame = _load_optional_csv(early_path)
        if not early_frame.empty:
            early_tagged = early_frame.copy()
            early_tagged["source_run_dir"] = str(run_dir)
            early_frames.append(early_tagged)
        source_rows.append(
            {
                "source_run_dir": str(run_dir),
                "dataset_path": str(dataset_path),
                "row_count": int(len(frame)),
                "early_warning_rows": int(len(early_frame)),
            }
        )

    combined_dataset = pd.concat(dataset_frames, ignore_index=True, sort=False)
    combined_early = pd.concat(early_frames, ignore_index=True, sort=False) if early_frames else pd.DataFrame()
    merged_dataset_path = output_dir / "combined_collapse_dataset.csv"
    merged_early_path = output_dir / "combined_early_warning_dataset.csv"
    write_dataframe(merged_dataset_path, combined_dataset)
    write_dataframe(merged_early_path, combined_early)
    write_dataframe(output_dir / "source_dataset_index.csv", pd.DataFrame(source_rows))
    return {
        "dataset_path": merged_dataset_path,
        "dataset_frame": combined_dataset,
        "early_warning_frame": combined_early,
        "source_dataset_count": len(dataset_paths),
    }


def _load_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    valid_frames = [frame for frame in frames if not frame.empty]
    if not valid_frames:
        return pd.DataFrame(columns=["formula"])
    return pd.concat(valid_frames, ignore_index=True, sort=False)


def _collapse_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "worst_case_cascade_size" not in frame.columns:
        return pd.DataFrame(columns=["threshold", "survival_probability"])
    values = frame["worst_case_cascade_size"].astype(float).dropna()
    values = values[values > 0]
    if values.empty:
        return pd.DataFrame(columns=["threshold", "survival_probability"])
    thresholds = sorted(set(float(value) for value in values))
    return pd.DataFrame(
        [
            {
                "threshold": threshold,
                "survival_probability": float((values >= threshold).mean()),
            }
            for threshold in thresholds
        ]
    )


def _build_theory_markdown(
    summary: TheorySummary,
    feature_importance: pd.DataFrame,
    laws: pd.DataFrame,
    symbolic_laws: pd.DataFrame,
    phase_result,
    powerlaw,
    tail_models: pd.DataFrame,
    early_warning_summary,
    early_warning_trends: pd.DataFrame,
    phase_bootstrap: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            f"# {summary.title}",
            "",
            f"- Dataset: `{summary.dataset_path}`",
            f"- Source datasets: `{summary.source_dataset_count}`",
            f"- Fragility fits: `{summary.fragility_model_count}`",
            f"- Law candidates: `{summary.law_candidate_count}`",
            f"- Symbolic laws: `{summary.symbolic_law_count}`",
            "",
            "## Feature importance",
            "",
            _frame_to_markdown(feature_importance.head(12)),
            "",
            "## Candidate laws",
            "",
            _frame_to_markdown(laws.head(12)),
            "",
            "## Symbolic laws",
            "",
            _frame_to_markdown(symbolic_laws.head(12)),
            "",
            "## Phase transition",
            "",
            f"- Feature: `{phase_result.feature}`",
            f"- Outcome: `{phase_result.outcome}`",
            f"- Critical threshold: `{phase_result.critical_threshold}`",
            f"- Discontinuity score: `{phase_result.discontinuity_score}`",
            "",
            "### Threshold Stability",
            "",
            _frame_to_markdown(phase_bootstrap.head(12)),
            "",
            "## Power law",
            "",
            f"- Alpha: `{powerlaw.alpha}`",
            f"- KS distance: `{powerlaw.ks_distance}`",
            f"- Log-log R^2: `{powerlaw.loglog_r2}`",
            "",
            "### Tail-model comparison",
            "",
            _frame_to_markdown(tail_models.head(12)),
            "",
            "## Early warning",
            "",
            f"- Mean variance increase: `{early_warning_summary.mean_variance_increase}`",
            f"- Mean autocorrelation increase: `{early_warning_summary.mean_autocorrelation_increase}`",
            f"- Mean recovery lag: `{early_warning_summary.mean_recovery_lag}`",
            "",
            "### Collapse vs Stable Separation",
            "",
            _frame_to_markdown(early_warning_trends.head(12)),
            "",
            "![Fragility Curves](fragility_curves.png)",
            "",
            "![Feature Importance](feature_importance.png)",
            "",
            "![Phase Transition](phase_transition.png)",
            "",
            "![Cascade Distribution](cascade_distribution.png)",
            "",
            "![Law Discovery](law_discovery.png)",
            "",
        ]
    )


def _build_theory_html(
    summary: TheorySummary,
    feature_importance: pd.DataFrame,
    laws: pd.DataFrame,
    symbolic_laws: pd.DataFrame,
    phase_result,
    powerlaw,
    tail_models: pd.DataFrame,
    early_warning_summary,
    early_warning_trends: pd.DataFrame,
    phase_bootstrap: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "<html><body>",
            f"<h1>{summary.title}</h1>",
            f"<p>Dataset: <strong>{summary.dataset_path}</strong><br>Source datasets: <strong>{summary.source_dataset_count}</strong><br>Fragility fits: <strong>{summary.fragility_model_count}</strong><br>Law candidates: <strong>{summary.law_candidate_count}</strong><br>Symbolic laws: <strong>{summary.symbolic_law_count}</strong></p>",
            "<h2>Feature Importance</h2>",
            feature_importance.head(12).to_html(index=False, border=0),
            "<h2>Candidate Laws</h2>",
            laws.head(12).to_html(index=False, border=0),
            "<h2>Symbolic Laws</h2>",
            symbolic_laws.head(12).to_html(index=False, border=0),
            "<h2>Phase Transition</h2>",
            f"<p>Feature: <strong>{phase_result.feature}</strong><br>Outcome: <strong>{phase_result.outcome}</strong><br>Critical threshold: <strong>{phase_result.critical_threshold}</strong><br>Discontinuity score: <strong>{phase_result.discontinuity_score}</strong></p>",
            "<h3>Threshold Stability</h3>",
            phase_bootstrap.head(12).to_html(index=False, border=0),
            "<h2>Power Law</h2>",
            f"<p>Alpha: <strong>{powerlaw.alpha}</strong><br>KS distance: <strong>{powerlaw.ks_distance}</strong><br>Log-log R^2: <strong>{powerlaw.loglog_r2}</strong></p>",
            "<h3>Tail-model Comparison</h3>",
            tail_models.head(12).to_html(index=False, border=0),
            "<h2>Early Warning</h2>",
            f"<p>Mean variance increase: <strong>{early_warning_summary.mean_variance_increase}</strong><br>Mean autocorrelation increase: <strong>{early_warning_summary.mean_autocorrelation_increase}</strong><br>Mean recovery lag: <strong>{early_warning_summary.mean_recovery_lag}</strong></p>",
            "<h3>Collapse vs Stable Separation</h3>",
            early_warning_trends.head(12).to_html(index=False, border=0),
            "<h2>Fragility Curves</h2><img src='fragility_curves.png' style='max-width: 100%;'>",
            "<h2>Feature Importance</h2><img src='feature_importance.png' style='max-width: 100%;'>",
            "<h2>Phase Transition</h2><img src='phase_transition.png' style='max-width: 100%;'>",
            "<h2>Cascade Distribution</h2><img src='cascade_distribution.png' style='max-width: 100%;'>",
            "<h2>Law Discovery</h2><img src='law_discovery.png' style='max-width: 100%;'>",
            "</body></html>",
        ]
    )


def _build_research_markdown(
    summary: ResearchSummary,
    theory_summary: TheorySummary,
    dataset_frame: pd.DataFrame,
    figure_rows: list[dict[str, str]],
) -> str:
    lines = [
        f"# {summary.title}",
        "",
        "## Study scope",
        "",
        f"- Dataset path: `{summary.dataset_path}`",
        f"- Source datasets: `{summary.source_dataset_count}`",
        f"- Systems analyzed: `{len(dataset_frame)}`",
        f"- Theory directory: `{theory_summary.theory_dir}`",
        f"- Figures: `{summary.figure_count}`",
        "",
        "## Top candidate laws",
        "",
    ]
    law_path = Path(theory_summary.theory_dir) / "law_candidates.csv"
    if law_path.exists():
        lines.append(_frame_to_markdown(pd.read_csv(law_path).head(12)))
    else:
        lines.append("_No candidate laws_")
    lines.extend(
        [
            "",
            "## Figure index",
            "",
            _frame_to_markdown(pd.DataFrame(figure_rows)),
            "",
        ]
    )
    for figure in figure_rows:
        lines.append(f"![{figure['figure']}]({Path(figure['path']).name})")
        lines.append("")
    return "\n".join(lines)


def _build_research_html(
    summary: ResearchSummary,
    theory_summary: TheorySummary,
    dataset_frame: pd.DataFrame,
    figure_rows: list[dict[str, str]],
) -> str:
    law_path = Path(theory_summary.theory_dir) / "law_candidates.csv"
    law_html = pd.read_csv(law_path).head(12).to_html(index=False, border=0) if law_path.exists() else "<p>No candidate laws.</p>"
    figures_html = "\n".join(
        f"<h2>{row['figure']}</h2><img src='{Path(row['path']).name}' style='max-width: 100%;'>"
        for row in figure_rows
    )
    return "\n".join(
        [
            "<html><body>",
            f"<h1>{summary.title}</h1>",
            f"<p>Dataset path: <strong>{summary.dataset_path}</strong><br>Source datasets: <strong>{summary.source_dataset_count}</strong><br>Systems analyzed: <strong>{len(dataset_frame)}</strong><br>Theory directory: <strong>{theory_summary.theory_dir}</strong><br>Figures: <strong>{summary.figure_count}</strong></p>",
            "<h2>Top Candidate Laws</h2>",
            law_html,
            "<h2>Figure Index</h2>",
            pd.DataFrame(figure_rows).to_html(index=False, border=0),
            figures_html,
            "</body></html>",
        ]
    )


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows_"
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])
