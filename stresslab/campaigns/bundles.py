"""Portable bundle export and restore helpers for StressLab artifacts."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from stresslab.campaigns.catalog import catalog_entry_from_dir
from stresslab.campaigns.registry import registry_paths, upsert_registry_entry
from stresslab.models import (
    ArtifactBundleFile,
    ArtifactBundleSummary,
    ArtifactRestoreSummary,
)
from stresslab.utils import ensure_directory, now_utc, write_json

BUNDLE_MANIFEST = "bundle_manifest.json"
BUNDLE_VERSION = "0.1"


def build_artifact_bundle(
    run_dir: Path,
    *,
    output_dir: Path | None = None,
    bundle_path: Path | None = None,
    include_registry: bool = False,
) -> ArtifactBundleSummary:
    """Package one StressLab artifact directory into a portable zip bundle."""

    run_dir = Path(run_dir).resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        raise FileNotFoundError(f"Artifact directory '{run_dir}' does not exist.")
    output_file = _resolve_bundle_path(run_dir, output_dir=output_dir, bundle_path=bundle_path)

    files = sorted(path for path in run_dir.rglob("*") if path.is_file())
    bundle_files = [
        ArtifactBundleFile(
            path=str(path.relative_to(run_dir)).replace("\\", "/"),
            size_bytes=path.stat().st_size,
            sha256=_sha256_file(path),
        )
        for path in files
    ]
    entry = catalog_entry_from_dir(run_dir)
    included_registry_files: list[str] = []
    registry_members: list[Path] = []
    if include_registry:
        registry_csv, registry_json = registry_paths(run_dir.parent)
        for registry_path in [registry_csv, registry_json]:
            if registry_path.exists():
                registry_members.append(registry_path)
                included_registry_files.append(registry_path.name)
    summary = ArtifactBundleSummary(
        bundle_version=BUNDLE_VERSION,
        created_at=now_utc().isoformat(),
        source_run_dir=str(run_dir),
        artifact_dir_name=run_dir.name,
        run_id=run_dir.name,
        analysis_type=entry.analysis_type if entry is not None else None,
        system_name=entry.system_name if entry is not None else None,
        report_html_path=entry.report_html_path if entry is not None else None,
        included_registry_files=included_registry_files,
        file_count=len(bundle_files),
        files=bundle_files,
        bundle_path=str(output_file),
    )
    with zipfile.ZipFile(output_file, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(BUNDLE_MANIFEST, json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True))
        for path in files:
            archive.write(path, arcname=f"artifact/{path.relative_to(run_dir).as_posix()}")
        for registry_path in registry_members:
            archive.write(registry_path, arcname=f"registry/{registry_path.name}")
    return summary


def restore_artifact_bundle(
    bundle_path: Path,
    *,
    output_dir: Path,
    registry_root: Path | None = None,
) -> ArtifactRestoreSummary:
    """Restore a portable StressLab bundle into a workspace directory."""

    bundle_path = Path(bundle_path).resolve()
    if not bundle_path.exists() or not bundle_path.is_file():
        raise FileNotFoundError(f"Bundle '{bundle_path}' does not exist.")
    output_root = ensure_directory(Path(output_dir).resolve())

    with zipfile.ZipFile(bundle_path) as archive:
        if BUNDLE_MANIFEST not in archive.namelist():
            raise ValueError("Bundle is missing bundle_manifest.json.")
        manifest = ArtifactBundleSummary.model_validate(
            json.loads(archive.read(BUNDLE_MANIFEST).decode("utf-8"))
        )
        target_dir, collision_resolved = _resolve_restore_dir(output_root, manifest.artifact_dir_name)
        ensure_directory(target_dir)
        restored_file_count = 0
        for member in archive.infolist():
            if member.is_dir():
                continue
            if member.filename.startswith("artifact/"):
                relative = Path(member.filename.removeprefix("artifact/"))
                destination = target_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(member))
                restored_file_count += 1
            elif member.filename.startswith("registry/"):
                relative = Path(member.filename.removeprefix("registry/"))
                destination = target_dir / "_bundle_registry" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(member))

    restore_summary = ArtifactRestoreSummary(
        bundle_path=str(bundle_path),
        restored_run_dir=str(target_dir),
        registry_root=str(Path(registry_root or output_root).resolve()),
        restored_file_count=restored_file_count,
        source_run_id=manifest.run_id,
        source_analysis_type=manifest.analysis_type,
        collision_resolved=collision_resolved,
    )
    write_json(target_dir / "bundle_restore.json", restore_summary)
    upsert_registry_entry(Path(registry_root or output_root), target_dir)
    return restore_summary


def _resolve_bundle_path(run_dir: Path, *, output_dir: Path | None, bundle_path: Path | None) -> Path:
    if bundle_path is not None and output_dir is not None:
        raise ValueError("Provide either output_dir or bundle_path, not both.")
    if bundle_path is not None:
        target = Path(bundle_path)
        if target.suffix.lower() != ".zip":
            target = target.with_suffix(".zip")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target.resolve()
    root = ensure_directory(Path(output_dir).resolve()) if output_dir is not None else run_dir.parent
    return (root / f"{run_dir.name}_bundle.zip").resolve()


def _resolve_restore_dir(output_root: Path, directory_name: str) -> tuple[Path, bool]:
    base = output_root / directory_name
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = output_root / f"{directory_name}_restored_{counter:02d}"
        counter += 1
    return candidate, candidate != base


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
