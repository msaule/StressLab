from __future__ import annotations

from pathlib import Path

from stresslab.utils import make_run_dir


def test_make_run_dir_creates_unique_directories(tmp_path: Path):
    first = make_run_dir("discovery", "discover", root=tmp_path)
    second = make_run_dir("discovery", "discover", root=tmp_path)
    assert first != second
    assert first.exists()
    assert second.exists()
