"""Schemas for batch experiment manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BatchJobSpec(BaseModel):
    """One executable job inside a batch campaign."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str | None = None
    command: Literal["run", "search", "optimize", "generate", "discover", "theory", "research"]
    spec_path: str | None = None
    source_dir: str | None = None
    dataset_source: str | None = None
    theory_dir: str | None = None
    resume_run_dir: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    objective: str = "min_failure"
    budget: float | None = None
    worst_case_budget: float | None = None
    robust: bool = False
    scenario_budget: float | None = None
    scenario_samples: int = 4
    fairness_weight: float = 0.0
    count: int = 24
    min_nodes: int = 6
    max_nodes: int = 16
    seed: int = 7
    batch_size: int = 100
    workers: int = 1
    shard_count: int = 1
    shard_index: int = 0
    horizon: float = 360.0
    topology_type: str = "mixed"
    expand_policies: bool = False
    expand_dynamic_policies: bool = False
    expand_adaptive_policies: bool = False
    expand_controller_bundles: bool = False
    expand_hierarchical_playbooks: bool = False
    policy_only: bool = False
    dynamic_only: bool = False
    adaptive_only: bool = False
    bundle_only: bool = False
    playbook_only: bool = False

    @model_validator(mode="after")
    def validate_search_and_policy_modes(self) -> BatchJobSpec:
        if self.command in {"run", "search", "optimize"} and not self.spec_path:
            raise ValueError(f"batch {self.command} jobs require 'spec_path'")
        if self.command in {"theory", "research"} and not self.dataset_source:
            raise ValueError(f"batch {self.command} jobs require 'dataset_source'")
        if self.command == "search" and self.objective not in {"min_failure", "worst_case"}:
            raise ValueError("batch search jobs require objective 'min_failure' or 'worst_case'")
        exclusive_modes = [
            self.policy_only,
            self.dynamic_only,
            self.adaptive_only,
            self.bundle_only,
            self.playbook_only,
        ]
        if sum(bool(flag) for flag in exclusive_modes) > 1:
            raise ValueError("batch optimize jobs can enable at most one *only mode")
        return self


class BatchManifest(BaseModel):
    """Top-level batch campaign configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    continue_on_error: bool = True
    jobs: list[BatchJobSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_job_ids(self) -> BatchManifest:
        ids = [job.id for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("batch job ids must be unique")
        return self


def resolve_manifest_paths(manifest: BatchManifest, manifest_path: Path) -> BatchManifest:
    """Resolve relative job spec paths against the manifest directory."""

    base = manifest_path.parent.resolve()
    updated_jobs = []
    for job in manifest.jobs:
        updates: dict[str, str] = {}
        for field_name in ["spec_path", "source_dir", "dataset_source", "theory_dir", "resume_run_dir"]:
            raw_value = getattr(job, field_name)
            if not raw_value:
                continue
            if _is_job_reference(raw_value):
                updates[field_name] = raw_value
                continue
            resolved = Path(raw_value)
            if not resolved.is_absolute():
                resolved = (base / resolved).resolve()
            updates[field_name] = str(resolved)
        updated_jobs.append(job.model_copy(update=updates))
    return manifest.model_copy(update={"jobs": updated_jobs})


def _is_job_reference(value: str) -> bool:
    return value.strip().startswith("{") and "}" in value
