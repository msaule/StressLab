"""End-to-end discovery campaigns and law-discovery helpers."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from stresslab.des import Simulator
from stresslab.discovery.symbolic import symbolic_regression_search
from stresslab.generator.synthetic import SyntheticGenerationConfig, generate_spec_records
from stresslab.models import DiscoverySummary
from stresslab.search import Searcher
from stresslab.systemspec import load_spec, resolve_spec
from stresslab.theory.early_warning import compute_early_warning_signals
from stresslab.theory.features import extract_system_features
from stresslab.theory.metrics import (
    build_collapse_distribution,
    collapse_metrics_from_results,
    load_queue_timeseries,
)
from stresslab.utils import ensure_directory, write_dataframe, write_json, write_yaml
from stresslab.viz.discovery import (
    plot_cascade_distribution,
    plot_collapse_heatmap,
    plot_feature_importance,
    plot_fragility_curves,
    plot_law_candidates,
)


def build_discovery_artifacts(
    output_dir: Path,
    *,
    spec_paths: list[Path] | None = None,
    generation_config: SyntheticGenerationConfig | None = None,
    worst_case_budget: float | None = None,
    batch_size: int = 100,
    workers: int = 1,
    resume: bool = False,
) -> DiscoverySummary:
    """Run a synthetic fragility campaign and write dataset artifacts."""

    output_dir = ensure_directory(Path(output_dir))
    generated_dir = ensure_directory(output_dir / "generated")
    systems_dir = ensure_directory(output_dir / "systems")
    if spec_paths is None:
        config = generation_config or SyntheticGenerationConfig()
        spec_paths = [Path(record.spec_path) for record in generate_spec_records(generated_dir, config=config)]
    else:
        spec_paths = [Path(spec_path) for spec_path in spec_paths]
    dataset_rows, early_warning_rows, completed_ids = _load_resume_rows(output_dir, resume=resume)
    pending_paths = [path for path in spec_paths if Path(path).stem not in completed_ids]
    batch_dir = ensure_directory(output_dir / "batches")
    if pending_paths:
        discovered_rows, discovered_early_rows = _execute_discovery_jobs(
            pending_paths,
            systems_dir=systems_dir,
            worst_case_budget=worst_case_budget,
            workers=workers,
            batch_dir=batch_dir,
            checkpoint_rows=max(batch_size, 1),
        )
        dataset_rows.extend(discovered_rows)
        early_warning_rows.extend(discovered_early_rows)

    dataset_frame = pd.DataFrame(dataset_rows).sort_values("system_id").reset_index(drop=True) if dataset_rows else pd.DataFrame()
    early_warning_frame = (
        pd.DataFrame(early_warning_rows).sort_values(["system_id", "scenario"]).reset_index(drop=True)
        if early_warning_rows
        else pd.DataFrame()
    )
    collapse_distribution = build_collapse_distribution(dataset_frame, metric="worst_case_cascade_size")
    feature_importance = compute_feature_importance(dataset_frame, target="collapse_probability")
    candidate_laws = discover_candidate_laws(dataset_frame, target="collapse_probability")
    symbolic_laws = symbolic_regression_search(dataset_frame, target="collapse_probability")

    write_dataframe(output_dir / "collapse_dataset.csv", dataset_frame)
    write_dataframe(output_dir / "early_warning_dataset.csv", early_warning_frame)
    write_dataframe(output_dir / "collapse_distribution.csv", collapse_distribution)
    write_dataframe(output_dir / "feature_importance.csv", feature_importance)
    write_dataframe(output_dir / "candidate_laws.csv", candidate_laws)
    write_dataframe(output_dir / "symbolic_laws.csv", symbolic_laws)
    plot_fragility_curves(dataset_frame, output_dir / "fragility_curves.png")
    plot_cascade_distribution(collapse_distribution, output_dir / "cascade_distribution.png")
    plot_collapse_heatmap(dataset_frame, output_dir / "collapse_heatmap.png")
    plot_feature_importance(feature_importance, output_dir / "feature_importance.png")
    plot_law_candidates(
        _concat_frames([symbolic_laws.head(12), candidate_laws.head(12)]),
        output_dir / "law_discovery.png",
    )

    summary = DiscoverySummary(
        title="StressLab Discovery Campaign",
        discovery_dir=str(output_dir),
        generated_system_count=len(spec_paths),
        dataset_row_count=len(dataset_frame),
        shard_count=max(1, generation_config.shard_count) if generation_config is not None else 1,
        shard_index=max(0, generation_config.shard_index) if generation_config is not None else 0,
        worker_count=max(1, workers),
        resumed_system_count=len(completed_ids),
        topology_type_counts=(
            dataset_frame["topology_type"].value_counts().to_dict()
            if not dataset_frame.empty and "topology_type" in dataset_frame.columns
            else {}
        ),
        dataset_csv_path=str(output_dir / "collapse_dataset.csv"),
        collapse_distribution_path=str(output_dir / "collapse_distribution.csv"),
        early_warning_dataset_path=str(output_dir / "early_warning_dataset.csv"),
        symbolic_law_path=str(output_dir / "symbolic_laws.csv"),
        report_markdown_path=str(output_dir / "discovery_report.md"),
        report_html_path=str(output_dir / "discovery_report.html"),
    )
    write_json(output_dir / "discovery_summary.json", summary)
    markdown = _build_discovery_markdown(summary, dataset_frame, feature_importance, candidate_laws, symbolic_laws)
    (output_dir / "discovery_report.md").write_text(markdown, encoding="utf-8")
    html = _build_discovery_html(summary, dataset_frame, feature_importance, candidate_laws, symbolic_laws)
    (output_dir / "discovery_report.html").write_text(html, encoding="utf-8")
    return summary


def _load_resume_rows(
    output_dir: Path,
    *,
    resume: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]], set[str]]:
    if not resume:
        return [], [], set()
    dataset_path = output_dir / "collapse_dataset.csv"
    early_warning_path = output_dir / "early_warning_dataset.csv"
    dataset_rows: list[dict[str, object]] = []
    early_warning_rows: list[dict[str, object]] = []
    completed_ids: set[str] = set()
    if dataset_path.exists():
        dataset_frame = pd.read_csv(dataset_path)
        dataset_rows = dataset_frame.to_dict(orient="records")
        completed_ids = {str(value) for value in dataset_frame.get("system_id", pd.Series(dtype=str)).tolist()}
    if early_warning_path.exists():
        early_warning_rows = pd.read_csv(early_warning_path).to_dict(orient="records")
    return dataset_rows, early_warning_rows, completed_ids


def _execute_discovery_jobs(
    spec_paths: list[Path],
    *,
    systems_dir: Path,
    worst_case_budget: float | None,
    workers: int,
    batch_dir: Path,
    checkpoint_rows: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    dataset_rows: list[dict[str, object]] = []
    early_warning_rows: list[dict[str, object]] = []
    if max(1, workers) == 1:
        for index, spec_path in enumerate(spec_paths, start=1):
            row, early_rows = _discover_one_system(
                spec_path=Path(spec_path),
                output_dir=ensure_directory(systems_dir / Path(spec_path).stem),
                worst_case_budget=worst_case_budget,
            )
            dataset_rows.append(row)
            early_warning_rows.extend(early_rows)
            if index % checkpoint_rows == 0:
                write_dataframe(batch_dir / f"collapse_batch_{index // checkpoint_rows:04d}.csv", pd.DataFrame(dataset_rows[-checkpoint_rows:]))
        return dataset_rows, early_warning_rows

    with ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(
                _discover_one_system,
                spec_path=Path(spec_path),
                output_dir=ensure_directory(systems_dir / Path(spec_path).stem),
                worst_case_budget=worst_case_budget,
            ): Path(spec_path)
            for spec_path in spec_paths
        }
        for index, future in enumerate(as_completed(future_map), start=1):
            row, early_rows = future.result()
            dataset_rows.append(row)
            early_warning_rows.extend(early_rows)
            if index % checkpoint_rows == 0:
                write_dataframe(batch_dir / f"collapse_batch_{index // checkpoint_rows:04d}.csv", pd.DataFrame(dataset_rows[-checkpoint_rows:]))
    return dataset_rows, early_warning_rows


def compute_feature_importance(frame: pd.DataFrame, *, target: str) -> pd.DataFrame:
    """Rank numeric features by absolute correlation to a target."""

    if frame.empty or target not in frame.columns:
        return pd.DataFrame(columns=["feature", "correlation", "score"])
    numeric = frame.select_dtypes(include=["number"]).replace([np.inf, -np.inf], np.nan)
    candidate_features = [
        column for column in numeric.columns
        if column != target and not column.endswith("_triggered")
    ]
    rows = []
    target_series = numeric[target]
    for feature in candidate_features:
        aligned = pd.concat([numeric[feature], target_series], axis=1).dropna()
        if len(aligned) < 4:
            continue
        correlation = float(aligned.corr().iloc[0, 1])
        rows.append(
            {
                "feature": feature,
                "correlation": correlation,
                "score": abs(correlation),
            }
        )
    frame_out = pd.DataFrame(rows)
    if frame_out.empty:
        return pd.DataFrame(columns=["feature", "correlation", "score"])
    return frame_out.sort_values(["score", "feature"], ascending=[False, True]).reset_index(drop=True)


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    valid_frames = [frame for frame in frames if not frame.empty]
    if not valid_frames:
        return pd.DataFrame()
    return pd.concat(valid_frames, ignore_index=True, sort=False)


def discover_candidate_laws(frame: pd.DataFrame, *, target: str) -> pd.DataFrame:
    """Discover candidate formula families for one collapse target."""

    importance = compute_feature_importance(frame, target=target)
    laws: list[dict[str, object]] = []
    numeric = frame.select_dtypes(include=["number"]).replace([np.inf, -np.inf], np.nan)
    for row in importance.head(8).itertuples(index=False):
        feature = str(row.feature)
        aligned = numeric[[feature, target]].dropna()
        if len(aligned) < 4:
            continue
        x = aligned[feature].to_numpy(dtype=float)
        y = aligned[target].to_numpy(dtype=float)
        design = np.column_stack([np.ones(len(x)), x])
        intercept, coefficient = np.linalg.lstsq(design, y, rcond=None)[0]
        predicted = intercept + coefficient * x
        r2 = _r2_score(y, predicted)
        laws.append(
            {
                "target": target,
                "formula": f"{target} = {intercept:.4f} + {coefficient:.4f} * {feature}",
                "model_type": "linear",
                "feature_set": feature,
                "r2": float(r2),
                "observations": int(len(aligned)),
            }
        )
        positive = aligned[(aligned[feature] > 0) & (aligned[target] > 0)]
        if len(positive) >= 4:
            log_x = np.log(positive[feature].to_numpy(dtype=float))
            log_y = np.log(positive[target].to_numpy(dtype=float))
            power_design = np.column_stack([np.ones(len(log_x)), log_x])
            intercept_log, exponent = np.linalg.lstsq(power_design, log_y, rcond=None)[0]
            predicted_log = intercept_log + exponent * log_x
            laws.append(
                {
                    "target": target,
                    "formula": f"{target} = {np.exp(intercept_log):.4f} * {feature}^{float(exponent):.4f}",
                    "model_type": "power_law",
                    "feature_set": feature,
                    "r2": float(_r2_score(log_y, predicted_log)),
                    "observations": int(len(positive)),
                }
            )
    top_features = [str(value) for value in importance.head(3)["feature"].tolist()]
    if len(top_features) >= 2 and target in numeric.columns:
        aligned = numeric[top_features + [target]].dropna()
        if len(aligned) >= 5:
            design = np.column_stack([np.ones(len(aligned)), *(aligned[feature].to_numpy(dtype=float) for feature in top_features)])
            coefficients = np.linalg.lstsq(design, aligned[target].to_numpy(dtype=float), rcond=None)[0]
            predicted = design @ coefficients
            terms = [f"{coefficients[index + 1]:.4f} * {feature}" for index, feature in enumerate(top_features)]
            laws.append(
                {
                    "target": target,
                    "formula": f"{target} = {coefficients[0]:.4f} + " + " + ".join(terms),
                    "model_type": "multivariate_linear",
                    "feature_set": ", ".join(top_features),
                    "r2": float(_r2_score(aligned[target].to_numpy(dtype=float), predicted)),
                    "observations": int(len(aligned)),
                }
            )
    if not laws:
        return pd.DataFrame(columns=["target", "formula", "model_type", "feature_set", "r2", "observations"])
    return pd.DataFrame(laws).sort_values(["r2", "observations"], ascending=[False, False]).reset_index(drop=True)


def _discover_one_system(
    *,
    spec_path: Path,
    output_dir: Path,
    worst_case_budget: float | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    spec = load_spec(spec_path)
    resolved = resolve_spec(spec)

    baseline_dir = ensure_directory(output_dir / "baseline")
    baseline_simulator = Simulator(resolved, seed=spec.seed)
    baseline_result = baseline_simulator.run(run_id="baseline", artifacts_dir=baseline_dir, capture_events=True)
    write_yaml(baseline_dir / "spec_resolved.yaml", spec.model_dump(mode="json", by_alias=True))
    write_json(baseline_dir / "baseline_result.json", baseline_result)

    min_dir = ensure_directory(output_dir / "min_failure")
    min_searcher = Searcher(spec, objective="min_failure", seed=spec.seed)
    min_search = min_searcher.find_min_failure()
    min_spec, min_simulator, _ = min_searcher.replay_best(min_search)
    min_result = min_simulator.run(run_id="min_failure", artifacts_dir=min_dir, capture_events=True)
    write_yaml(min_dir / "spec_resolved.yaml", min_spec.model_dump(mode="json", by_alias=True))
    write_json(min_dir / "search_result.json", min_search)
    write_json(min_dir / "scenario_result.json", min_result)
    write_dataframe(min_dir / "search_history.csv", pd.DataFrame(min_searcher.history))

    worst_dir = ensure_directory(output_dir / "worst_case")
    worst_searcher = Searcher(spec, objective="worst_case", seed=spec.seed)
    budget = float(worst_case_budget if worst_case_budget is not None else (spec.search.budget or 1.0))
    worst_search = worst_searcher.find_worst_case(budget)
    worst_spec, worst_simulator, _ = worst_searcher.replay_best(worst_search)
    worst_result = worst_simulator.run(run_id="worst_case", artifacts_dir=worst_dir, capture_events=True)
    write_yaml(worst_dir / "spec_resolved.yaml", worst_spec.model_dump(mode="json", by_alias=True))
    write_json(worst_dir / "search_result.json", worst_search)
    write_json(worst_dir / "scenario_result.json", worst_result)
    write_dataframe(worst_dir / "search_history.csv", pd.DataFrame(worst_searcher.history))

    features = extract_system_features(spec, baseline_result=baseline_result)
    collapse = collapse_metrics_from_results(
        spec=spec,
        baseline_result=baseline_result,
        min_search=min_search,
        min_result=min_result,
        worst_search=worst_search,
        worst_result=worst_result,
    )
    row = {
        "system_id": Path(spec_path).stem,
        "spec_path": str(spec_path),
        **features,
        **collapse,
    }
    early_warning_rows = []
    for label, run_dir, result in [
        ("min_failure", min_dir, min_result),
        ("worst_case", worst_dir, worst_result),
    ]:
        signals = compute_early_warning_signals(
            load_queue_timeseries(run_dir / "queue_timeseries.csv"),
            failure_triggered=result.failure_triggered,
        )
        early_warning_rows.append(
            {
                "system_id": Path(spec_path).stem,
                "spec_path": str(spec_path),
                "topology_type": row.get("topology_type"),
                "scenario": label,
                **signals,
            }
        )
    return row, early_warning_rows


def _build_discovery_markdown(
    summary: DiscoverySummary,
    dataset_frame: pd.DataFrame,
    feature_importance: pd.DataFrame,
    candidate_laws: pd.DataFrame,
    symbolic_laws: pd.DataFrame,
) -> str:
    lines = [
        f"# {summary.title}",
        "",
        f"- Systems analyzed: `{summary.generated_system_count}`",
        f"- Dataset rows: `{summary.dataset_row_count}`",
        f"- Workers: `{summary.worker_count}`",
        f"- Resumed systems: `{summary.resumed_system_count}`",
        "",
        "## Topology counts",
        "",
    ]
    for topology, count in summary.topology_type_counts.items():
        lines.append(f"- `{topology}`: `{count}`")
    lines.extend(
        [
            "",
            "## Dataset sample",
            "",
            _frame_to_markdown(dataset_frame.head(20)),
            "",
            "## Feature importance",
            "",
            _frame_to_markdown(feature_importance.head(12)),
            "",
            "## Candidate laws",
            "",
            _frame_to_markdown(candidate_laws.head(12)),
            "",
            "## Symbolic laws",
            "",
            _frame_to_markdown(symbolic_laws.head(12)),
            "",
            "![Fragility Curves](fragility_curves.png)",
            "",
            "![Cascade Distribution](cascade_distribution.png)",
            "",
            "![Collapse Heatmap](collapse_heatmap.png)",
            "",
            "![Law Discovery](law_discovery.png)",
            "",
        ]
    )
    return "\n".join(lines)


def _build_discovery_html(
    summary: DiscoverySummary,
    dataset_frame: pd.DataFrame,
    feature_importance: pd.DataFrame,
    candidate_laws: pd.DataFrame,
    symbolic_laws: pd.DataFrame,
) -> str:
    topology_html = "".join(
        f"<li><strong>{topology}</strong>: {count}</li>" for topology, count in summary.topology_type_counts.items()
    )
    return "\n".join(
        [
            "<html><body>",
            f"<h1>{summary.title}</h1>",
            f"<p>Systems analyzed: <strong>{summary.generated_system_count}</strong><br>Dataset rows: <strong>{summary.dataset_row_count}</strong><br>Workers: <strong>{summary.worker_count}</strong><br>Resumed systems: <strong>{summary.resumed_system_count}</strong></p>",
            "<h2>Topology Counts</h2>",
            f"<ul>{topology_html}</ul>",
            "<h2>Dataset Sample</h2>",
            dataset_frame.head(25).to_html(index=False, border=0),
            "<h2>Feature Importance</h2>",
            feature_importance.head(12).to_html(index=False, border=0),
            "<h2>Candidate Laws</h2>",
            candidate_laws.head(12).to_html(index=False, border=0),
            "<h2>Symbolic Laws</h2>",
            symbolic_laws.head(12).to_html(index=False, border=0),
            "<h2>Fragility Curves</h2><img src='fragility_curves.png' style='max-width: 100%;'>",
            "<h2>Cascade Distribution</h2><img src='cascade_distribution.png' style='max-width: 100%;'>",
            "<h2>Collapse Heatmap</h2><img src='collapse_heatmap.png' style='max-width: 100%;'>",
            "<h2>Law Discovery</h2><img src='law_discovery.png' style='max-width: 100%;'>",
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


def _r2_score(actual: np.ndarray, predicted: np.ndarray) -> float:
    if len(actual) == 0:
        return 0.0
    total = float(np.sum((actual - actual.mean()) ** 2))
    if total <= 1e-12:
        return 1.0
    residual = float(np.sum((actual - predicted) ** 2))
    return 1.0 - residual / total
