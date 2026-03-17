"""Shared utility helpers."""

from __future__ import annotations

import json
import platform
import socket
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from stresslab.config import DEFAULT_OUTPUT_ROOT, __version__


def now_utc() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def slugify(value: str) -> str:
    """Create a filesystem-friendly slug."""

    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip().lower())
    return "_".join(part for part in safe.split("_") if part)


def ensure_directory(path: Path) -> Path:
    """Create a directory if it does not exist."""

    path.mkdir(parents=True, exist_ok=True)
    return path


def make_run_dir(system_name: str, suffix: str, root: Path | None = None) -> Path:
    """Create a timestamped run directory."""

    run_root = ensure_directory(root or DEFAULT_OUTPUT_ROOT)
    timestamp = now_utc().strftime("%Y-%m-%d_%H%M%S_%f")
    run_dir = run_root / f"{timestamp}_{slugify(system_name)}_{slugify(suffix)}"
    counter = 0
    while True:
        candidate = run_dir if counter == 0 else Path(f"{run_dir}_{counter:02d}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            counter += 1


def git_commit() -> str | None:
    """Return the current git commit if available."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip() or None


def to_jsonable(value: Any) -> Any:
    """Convert dataclasses and paths to JSON-safe values."""

    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


def write_json(path: Path, payload: Any) -> Path:
    """Write JSON to disk."""

    path.write_text(json.dumps(to_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_yaml(path: Path, payload: Any) -> Path:
    """Write YAML to disk."""

    path.write_text(yaml.safe_dump(to_jsonable(payload), sort_keys=False), encoding="utf-8")
    return path


def write_dataframe(path: Path, frame: pd.DataFrame) -> Path:
    """Write a DataFrame to CSV."""

    frame.to_csv(path, index=False)
    return path


def runtime_metadata(
    *,
    command: str,
    system_name: str,
    seed: int,
    execution_duration: float,
) -> dict[str, Any]:
    """Build artifact metadata."""

    return {
        "project_version": __version__,
        "timestamp": now_utc().isoformat(),
        "git_commit": git_commit(),
        "system_name": system_name,
        "command": command,
        "seed": seed,
        "execution_duration": execution_duration,
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
    }
