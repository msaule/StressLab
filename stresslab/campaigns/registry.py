"""Persistent workspace registry for StressLab artifact directories."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stresslab.campaigns.catalog import catalog_entry_from_dir, discover_catalog_entries
from stresslab.models import RunCatalogEntry
from stresslab.utils import ensure_directory, write_dataframe

REGISTRY_CSV = ".stresslab_registry.csv"
REGISTRY_JSON = ".stresslab_registry.json"


def registry_paths(root: Path) -> tuple[Path, Path]:
    """Return the registry CSV and JSON paths for a workspace root."""

    base = ensure_directory(Path(root))
    return base / REGISTRY_CSV, base / REGISTRY_JSON


def load_registry(root: Path) -> pd.DataFrame:
    """Load an existing registry frame if present."""

    csv_path, _ = registry_paths(root)
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path)


def upsert_registry_entry(root: Path, run_dir: Path) -> RunCatalogEntry | None:
    """Upsert one discovered artifact directory into the workspace registry."""

    entry = catalog_entry_from_dir(Path(run_dir))
    if entry is None:
        return None
    frame = load_registry(root)
    new_row = pd.DataFrame([entry.model_dump(mode="json")]).dropna(axis=1, how="all")
    if frame.empty:
        updated = new_row
    else:
        frame = frame.dropna(axis=1, how="all")
        if "run_dir" in frame.columns:
            frame = frame[frame["run_dir"] != str(Path(run_dir))]
        columns = list(dict.fromkeys([*frame.columns.tolist(), *new_row.columns.tolist()]))
        updated = pd.concat(
            [frame.reindex(columns=columns), new_row.reindex(columns=columns)],
            ignore_index=True,
        )
    if "timestamp" in updated.columns:
        updated = updated.sort_values("timestamp", ascending=False)
    write_registry(root, updated)
    return entry


def refresh_registry(root: Path) -> pd.DataFrame:
    """Rebuild the workspace registry by scanning the root recursively."""

    entries = discover_catalog_entries(root)
    frame = pd.DataFrame([entry.model_dump(mode="json") for entry in entries])
    if not frame.empty and "timestamp" in frame.columns:
        frame = frame.sort_values("timestamp", ascending=False)
    write_registry(root, frame)
    return frame


def write_registry(root: Path, frame: pd.DataFrame) -> None:
    """Write registry CSV and JSON artifacts."""

    csv_path, json_path = registry_paths(root)
    write_dataframe(csv_path, frame)
    records = frame.to_dict(orient="records") if not frame.empty else []
    json_path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
