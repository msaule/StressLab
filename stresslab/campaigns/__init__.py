"""Campaign orchestration and comparison helpers."""

from stresslab.campaigns.batch import execute_batch_campaign, load_batch_manifest
from stresslab.campaigns.board import build_workspace_board
from stresslab.campaigns.bundles import build_artifact_bundle, restore_artifact_bundle
from stresslab.campaigns.casebook import build_casebook
from stresslab.campaigns.catalog import build_run_catalog, discover_catalog_entries
from stresslab.campaigns.compare import build_comparison_artifacts, summarize_run_dir
from stresslab.campaigns.doctor import build_doctor_report
from stresslab.campaigns.evaluation import build_evaluation_study
from stresslab.campaigns.registry import load_registry, refresh_registry, upsert_registry_entry
from stresslab.campaigns.status import build_workspace_status

__all__ = [
    "build_artifact_bundle",
    "build_casebook",
    "build_comparison_artifacts",
    "build_doctor_report",
    "build_evaluation_study",
    "build_run_catalog",
    "build_workspace_board",
    "build_workspace_status",
    "discover_catalog_entries",
    "execute_batch_campaign",
    "load_batch_manifest",
    "load_registry",
    "refresh_registry",
    "restore_artifact_bundle",
    "summarize_run_dir",
    "upsert_registry_entry",
]
