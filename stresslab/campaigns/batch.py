"""Batch-manifest execution for repeatable StressLab experiment campaigns."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import yaml

from stresslab.campaigns.compare import build_comparison_artifacts, summarize_run_dir
from stresslab.campaigns.schema import BatchManifest, resolve_manifest_paths
from stresslab.models import BatchJobResult, BatchSummary
from stresslab.utils import (
    ensure_directory,
    make_run_dir,
    slugify,
    write_dataframe,
    write_json,
    write_yaml,
)

JobRunner = Callable[..., None]


def load_batch_manifest(path: Path) -> BatchManifest:
    """Load and resolve a batch manifest from YAML."""

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    manifest = BatchManifest.model_validate(raw)
    return resolve_manifest_paths(manifest, Path(path))


def execute_batch_campaign(
    manifest_path: Path,
    *,
    output_dir: Path | None,
    registry_root: Path | None = None,
    runners: dict[str, JobRunner],
) -> tuple[Path, BatchSummary]:
    """Execute a batch campaign using the provided command runners."""

    manifest = load_batch_manifest(manifest_path)
    batch_dir = make_run_dir(manifest.name, "batch", root=output_dir)
    write_yaml(batch_dir / "batch_manifest_resolved.yaml", manifest.model_dump(mode="json"))

    job_results: list[BatchJobResult] = []
    successful_records = []
    successful_dirs = []
    completed_run_dirs: dict[str, Path] = {}

    for job in manifest.jobs:
        job_root = ensure_directory(batch_dir / slugify(job.id))
        runner = runners.get(job.command)
        if runner is None:
            error = f"No runner registered for batch command '{job.command}'."
            job_results.append(
                BatchJobResult(
                    job_id=job.id,
                    label=job.label or job.id,
                    command=job.command,
                    spec_path=job.spec_path,
                    status="failed",
                    error=error,
                )
            )
            if not manifest.continue_on_error:
                break
            continue
        try:
            _run_job(
                job=job,
                job_root=job_root,
                runner=runner,
                registry_root=registry_root,
                completed_run_dirs=completed_run_dirs,
            )
            run_dir = _latest_run_dir(job_root)
            completed_run_dirs[job.id] = run_dir
            record = summarize_run_dir(
                run_dir,
                label=job.label or job.id,
                notes=job.notes,
                tags=job.tags,
            )
            successful_records.append(record)
            successful_dirs.append(run_dir)
            job_results.append(
                BatchJobResult(
                    job_id=job.id,
                    label=job.label or job.id,
                    command=job.command,
                    spec_path=job.spec_path,
                    status="completed",
                    run_dir=str(run_dir),
                    report_html_path=record.report_html_path,
                    comparison_record=record,
                )
            )
        except Exception as exc:  # pragma: no cover - exercised through CLI integration
            job_results.append(
                BatchJobResult(
                    job_id=job.id,
                    label=job.label or job.id,
                    command=job.command,
                    spec_path=job.spec_path,
                    status="failed",
                    error=str(exc),
                )
            )
            if not manifest.continue_on_error:
                break

    comparison_summary = None
    if successful_dirs:
        comparison_summary = build_comparison_artifacts(
            successful_dirs,
            output_dir=batch_dir,
            title=f"{manifest.name} Campaign Comparison",
            labels_by_dir={str(Path(record.run_dir).resolve()): record.label for record in successful_records},
            notes_by_dir={str(Path(record.run_dir).resolve()): record.notes or "" for record in successful_records},
            tags_by_dir={str(Path(record.run_dir).resolve()): record.tags for record in successful_records},
        )

    summary = BatchSummary(
        campaign_name=manifest.name,
        description=manifest.description,
        manifest_path=str(Path(manifest_path).resolve()),
        batch_dir=str(batch_dir),
        continue_on_error=manifest.continue_on_error,
        total_jobs=len(manifest.jobs),
        completed_jobs=sum(result.status == "completed" for result in job_results),
        failed_jobs=sum(result.status == "failed" for result in job_results),
        comparison_summary_path=(
            comparison_summary.comparison_summary_path
            if comparison_summary is not None
            else None
        ),
        comparison_report_html_path=(
            comparison_summary.report_html_path
            if comparison_summary is not None
            else None
        ),
        jobs=job_results,
    )
    write_dataframe(
        batch_dir / "batch_summary.csv",
        pd.DataFrame(
            [
                {
                    "job_id": job.job_id,
                    "label": job.label,
                    "command": job.command,
                    "status": job.status,
                    "spec_path": job.spec_path,
                    "run_dir": job.run_dir,
                    "report_html_path": job.report_html_path,
                    "error": job.error,
                }
                for job in job_results
            ]
        ),
    )
    write_json(batch_dir / "batch_summary.json", summary)
    _write_batch_report(batch_dir=batch_dir, summary=summary)
    return batch_dir, summary


def _run_job(
    *,
    job,
    job_root: Path,
    runner: JobRunner,
    registry_root: Path | None,
    completed_run_dirs: dict[str, Path],
) -> None:
    resolved = _resolve_job_references(job, completed_run_dirs=completed_run_dirs)
    spec_path = Path(resolved.spec_path) if resolved.spec_path else None
    if resolved.command == "run":
        runner(spec_path, output_dir=job_root, registry_root=registry_root)
        return
    if resolved.command == "search":
        runner(
            spec_path,
            objective=resolved.objective,
            budget=resolved.budget,
            output_dir=job_root,
            registry_root=registry_root,
        )
        return
    if resolved.command == "optimize":
        runner(
            spec_path,
            budget=resolved.budget,
            output_dir=job_root,
            registry_root=registry_root,
            robust=resolved.robust,
            scenario_budget=resolved.scenario_budget,
            scenario_samples=resolved.scenario_samples,
            fairness_weight=resolved.fairness_weight,
            expand_policies=resolved.expand_policies,
            expand_dynamic_policies=resolved.expand_dynamic_policies,
            expand_adaptive_policies=resolved.expand_adaptive_policies,
            expand_controller_bundles=resolved.expand_controller_bundles,
            expand_hierarchical_playbooks=resolved.expand_hierarchical_playbooks,
            policy_only=resolved.policy_only,
            dynamic_only=resolved.dynamic_only,
            adaptive_only=resolved.adaptive_only,
            bundle_only=resolved.bundle_only,
            playbook_only=resolved.playbook_only,
        )
        return
    if resolved.command == "generate":
        runner(
            count=resolved.count,
            topology_type=resolved.topology_type,
            min_nodes=resolved.min_nodes,
            max_nodes=resolved.max_nodes,
            seed=resolved.seed,
            batch_size=resolved.batch_size,
            shard_count=resolved.shard_count,
            shard_index=resolved.shard_index,
            horizon=resolved.horizon,
            output_dir=job_root,
            registry_root=registry_root,
        )
        return
    if resolved.command == "discover":
        runner(
            source_dir=Path(resolved.source_dir) if resolved.source_dir else None,
            count=resolved.count,
            topology_type=resolved.topology_type,
            min_nodes=resolved.min_nodes,
            max_nodes=resolved.max_nodes,
            seed=resolved.seed,
            batch_size=resolved.batch_size,
            worst_case_budget=resolved.worst_case_budget,
            shard_count=resolved.shard_count,
            shard_index=resolved.shard_index,
            workers=resolved.workers,
            resume_run_dir=Path(resolved.resume_run_dir) if resolved.resume_run_dir else None,
            output_dir=job_root,
            registry_root=registry_root,
        )
        return
    if resolved.command == "theory":
        runner(
            Path(resolved.dataset_source),
            output_dir=job_root,
            registry_root=registry_root,
        )
        return
    if resolved.command == "research":
        runner(
            Path(resolved.dataset_source),
            output_dir=job_root,
            theory_dir=Path(resolved.theory_dir) if resolved.theory_dir else None,
            registry_root=registry_root,
        )
        return
    raise ValueError(f"Unsupported batch job command '{resolved.command}'.")


def _resolve_job_references(job, *, completed_run_dirs: dict[str, Path]):
    updates: dict[str, str] = {}
    for field_name in ["spec_path", "source_dir", "dataset_source", "theory_dir", "resume_run_dir"]:
        raw_value = getattr(job, field_name, None)
        if not raw_value:
            continue
        updates[field_name] = _resolve_reference_string(str(raw_value), completed_run_dirs=completed_run_dirs)
    return job.model_copy(update=updates)


def _resolve_reference_string(value: str, *, completed_run_dirs: dict[str, Path]) -> str:
    resolved = value
    for job_id, run_dir in completed_run_dirs.items():
        resolved = resolved.replace(f"{{{job_id}}}", str(run_dir))
    if "{" in resolved and "}" in resolved:
        raise ValueError(f"Unresolved batch job reference in '{value}'.")
    return resolved


def _latest_run_dir(job_root: Path) -> Path:
    candidates = [path for path in job_root.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No StressLab artifact directory created under '{job_root}'.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _write_batch_report(*, batch_dir: Path, summary: BatchSummary) -> None:
    rows = [
        {
            "job_id": job.job_id,
            "label": job.label,
            "command": job.command,
            "status": job.status,
            "spec_path": job.spec_path,
            "run_dir": job.run_dir,
            "report_html_path": job.report_html_path,
            "error": job.error,
        }
        for job in summary.jobs
    ]
    lines = [
        f"# Batch Campaign: {summary.campaign_name}",
        "",
        f"- Total jobs: `{summary.total_jobs}`",
        f"- Completed jobs: `{summary.completed_jobs}`",
        f"- Failed jobs: `{summary.failed_jobs}`",
        f"- Continue on error: `{summary.continue_on_error}`",
        "",
        "## Jobs",
        "",
        _rows_to_markdown(rows),
        "",
    ]
    if summary.comparison_report_html_path:
        lines.extend(
            [
                "## Comparison",
                "",
                f"- Comparison summary: `{summary.comparison_summary_path}`",
                f"- Comparison report: `{summary.comparison_report_html_path}`",
                "",
            ]
        )
    (batch_dir / "batch_report.md").write_text("\n".join(lines), encoding="utf-8")
    html = [
        "<html><body>",
        f"<h1>Batch Campaign: {summary.campaign_name}</h1>",
        "<ul>",
        f"<li>Total jobs: <code>{summary.total_jobs}</code></li>",
        f"<li>Completed jobs: <code>{summary.completed_jobs}</code></li>",
        f"<li>Failed jobs: <code>{summary.failed_jobs}</code></li>",
        f"<li>Continue on error: <code>{summary.continue_on_error}</code></li>",
        "</ul>",
        "<h2>Jobs</h2>",
        _rows_to_html(rows),
    ]
    if summary.comparison_report_html_path:
        html.extend(
            [
                "<h2>Comparison</h2>",
                f"<p>Comparison summary: <code>{summary.comparison_summary_path}</code></p>",
                f"<p>Comparison report: <code>{summary.comparison_report_html_path}</code></p>",
            ]
        )
    html.extend(["</body></html>"])
    (batch_dir / "batch_report.html").write_text("\n".join(html), encoding="utf-8")


def _rows_to_markdown(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "_No jobs executed._"
    columns = list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = [
        "| " + " | ".join(str(row[column]) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def _rows_to_html(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>No jobs executed.</p>"
    return (
        "<table>"
        + "<thead><tr>"
        + "".join(f"<th>{column}</th>" for column in rows[0].keys())
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{row[column]}</td>" for column in rows[0].keys()) + "</tr>"
            for row in rows
        )
        + "</tbody></table>"
    )
