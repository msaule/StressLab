from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from typer.testing import CliRunner

from stresslab.cli.main import app
from stresslab.service import start_workspace_api_server

runner = CliRunner()


def _fetch_json(url: str, *, headers: dict[str, str] | None = None) -> dict:
    request = Request(url, headers=headers or {})  # noqa: S310
    with urlopen(request, timeout=5) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str, *, headers: dict[str, str] | None = None) -> str:
    request = Request(url, headers=headers or {})  # noqa: S310
    with urlopen(request, timeout=5) as response:  # noqa: S310
        return response.read().decode("utf-8")


def _fetch_bytes(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    request = Request(url, headers=headers or {})  # noqa: S310
    with urlopen(request, timeout=5) as response:  # noqa: S310
        return response.read()


def _post_json(url: str, payload: dict, *, headers: dict[str, str] | None = None) -> dict:
    request = Request(  # noqa: S310
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def test_workspace_api_exposes_registry_board_and_artifacts(toy_spec_path, tmp_path: Path):
    workspace = tmp_path / "workspace"
    baseline = runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(workspace)])
    assert baseline.exit_code == 0
    optimize_result = runner.invoke(
        app,
        ["optimize", str(toy_spec_path), "--budget", "100", "--output-dir", str(workspace)],
    )
    assert optimize_result.exit_code == 0

    api = start_workspace_api_server(workspace, host="127.0.0.1", port=0, refresh=True, quiet=True)
    try:
        health = _fetch_json(f"{api.base_url}/health")
        assert health["status"] == "ok"

        app_html = _fetch_text(f"{api.base_url}/app")
        assert "StressLab Control Center" in app_html
        assert "Async Job Desk" in app_html
        assert "Discovery Lab" in app_html

        registry = _fetch_json(f"{api.base_url}/registry?limit=2")
        assert registry["entry_count"] == 2
        assert len(registry["entries"]) == 2

        status = _fetch_json(f"{api.base_url}/status?limit=1")
        assert status["entry_count"] == 2
        assert len(status["recent_entries"]) == 1

        board = _fetch_json(f"{api.base_url}/board?recent_limit=2&watch_limit=2&plan_limit=2")
        assert board["plan_count"] >= 1
        assert board["leaders"]
        assert board["plans"]

        run_id = registry["entries"][0]["run_id"]
        artifact = _fetch_json(f"{api.base_url}/artifacts/{run_id}?expand=1")
        assert artifact["run_id"] == run_id
        assert "metadata.json" in artifact["details"]
        assert artifact["available_files"]

        report_html = _fetch_text(f"{api.base_url}/reports/{run_id}")
        assert "<html" in report_html.lower()

        baseline_file = _fetch_text(f"{api.base_url}/files/{run_id}/baseline_result.json")
        assert "\"run_id\"" in baseline_file

        bundle_bytes = _fetch_bytes(f"{api.base_url}/bundles/{run_id}?include_registry=1")
        with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as archive:
            members = set(archive.namelist())
        assert "bundle_manifest.json" in members
        assert "artifact/baseline_result.json" in members
        assert "registry/.stresslab_registry.csv" in members
    finally:
        api.close()


def test_workspace_api_exposes_discovery_payloads(tmp_path: Path):
    workspace = tmp_path / "workspace"
    generate_result = runner.invoke(
        app,
        ["generate", "--count", "5", "--topology-type", "mixed", "--output-dir", str(workspace)],
    )
    assert generate_result.exit_code == 0
    discover_result = runner.invoke(
        app,
        ["discover", "--count", "5", "--topology-type", "mixed", "--output-dir", str(workspace)],
    )
    assert discover_result.exit_code == 0
    discover_dirs = [path for path in workspace.iterdir() if path.is_dir() and path.name.endswith("_discover")]
    assert discover_dirs
    discover_dir = sorted(discover_dirs)[-1]
    theory_result = runner.invoke(app, ["theory", str(discover_dir), "--output-dir", str(workspace)])
    assert theory_result.exit_code == 0
    research_result = runner.invoke(app, ["research", str(discover_dir), "--output-dir", str(workspace)])
    assert research_result.exit_code == 0

    api = start_workspace_api_server(workspace, host="127.0.0.1", port=0, refresh=True, quiet=True)
    try:
        discovery = _fetch_json(f"{api.base_url}/discovery?limit=12")
        assert discovery["entry_count"] >= 4
        assert discovery["analysis_type_counts"]["discover"] >= 1
        assert discovery["analysis_type_counts"]["theory"] >= 1
        assert discovery["analysis_type_counts"]["research"] >= 1
        assert discovery["latest_theory_run_dir"]
        assert discovery["latest_research_run_dir"]
        assert discovery["top_symbolic_laws"] or discovery["top_candidate_laws"]
        assert discovery["research_figures"]

        theory_run_id = Path(discovery["latest_theory_run_dir"]).name
        theory_report = _fetch_text(f"{api.base_url}/reports/{theory_run_id}")
        assert "Theory Analysis" in theory_report

        research_run_id = Path(discovery["latest_research_run_dir"]).name
        research_report = _fetch_text(f"{api.base_url}/reports/{research_run_id}")
        assert "Research Report" in research_report
    finally:
        api.close()


def test_workspace_api_submits_and_tracks_background_jobs(toy_spec_path, tmp_path: Path):
    workspace = tmp_path / "workspace"
    api = start_workspace_api_server(workspace, host="127.0.0.1", port=0, refresh=True, quiet=True)
    try:
        created = _post_json(
            f"{api.base_url}/jobs",
            {
                "command": "run",
                "spec_path": str(toy_spec_path),
            },
        )
        assert created["status"] == "queued"
        job_id = created["job_id"]

        latest = created
        deadline = time.time() + 20.0
        while time.time() < deadline:
            latest = _fetch_json(f"{api.base_url}/jobs/{job_id}?expand=1")
            if latest["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.1)
        assert latest["status"] == "succeeded", latest
        assert latest["run_dir"]
        assert latest["report_path"]
        assert latest["stdout_tail"]
        assert "Run complete:" in latest["stdout_tail"]

        listing = _fetch_json(f"{api.base_url}/jobs?limit=5")
        assert listing["entry_count"] >= 1
        assert listing["status_counts"]["succeeded"] >= 1

        run_id = Path(latest["run_dir"]).name
        artifact = _fetch_json(f"{api.base_url}/artifacts/{run_id}?expand=1")
        assert artifact["run_id"] == run_id
        report_html = _fetch_text(f"{api.base_url}/reports/{run_id}")
        assert "<html" in report_html.lower()
    finally:
        api.close()


def test_workspace_api_optional_token_auth_protects_private_routes(toy_spec_path, tmp_path: Path):
    workspace = tmp_path / "workspace"
    runner.invoke(app, ["run", str(toy_spec_path), "--output-dir", str(workspace)])
    api = start_workspace_api_server(
        workspace,
        host="127.0.0.1",
        port=0,
        refresh=True,
        quiet=True,
        api_token="secret-token",
    )
    try:
        health = _fetch_json(f"{api.base_url}/health")
        assert health["auth_required"] is True

        app_html = _fetch_text(f"{api.base_url}/app")
        assert "StressLab Control Center" in app_html

        try:
            _fetch_json(f"{api.base_url}/registry?limit=1")
        except HTTPError as exc:
            assert exc.code == 401
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("Expected registry access without a token to fail.")

        authorized_registry = _fetch_json(
            f"{api.base_url}/registry?limit=1",
            headers={"Authorization": "Bearer secret-token"},
        )
        assert authorized_registry["entry_count"] == 1

        authorized_jobs = _post_json(
            f"{api.base_url}/jobs",
            {"command": "run", "spec_path": str(toy_spec_path)},
            headers={"X-StressLab-Token": "secret-token"},
        )
        assert authorized_jobs["status"] == "queued"
    finally:
        api.close()
