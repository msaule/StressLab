"""Deployment and environment readiness reporting for StressLab."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from stresslab.models import DoctorCheck, DoctorSummary
from stresslab.utils import ensure_directory, write_dataframe, write_json


def build_doctor_report(
    workspace_root: Path,
    *,
    output_dir: Path,
    title: str = "StressLab Environment Doctor",
) -> DoctorSummary:
    """Inspect local readiness for StressLab service and container workflows."""

    output_dir = ensure_directory(Path(output_dir))
    checks = collect_doctor_checks(Path(workspace_root))
    frame = pd.DataFrame([check.model_dump(mode="json") for check in checks])
    write_dataframe(output_dir / "doctor_checks.csv", frame)

    required_checks = [check for check in checks if check.required]
    passed_required = [check for check in required_checks if check.status == "pass"]
    failed_required = [check for check in required_checks if check.status == "fail"]
    summary = DoctorSummary(
        title=title,
        workspace_root=str(Path(workspace_root).resolve()),
        platform_system=platform.system(),
        platform_release=platform.release(),
        python_version=platform.python_version(),
        ready_for_container_build=not failed_required,
        checks=checks,
        check_count=len(checks),
        passing_required_checks=len(passed_required),
        failing_required_checks=len(failed_required),
        report_markdown_path=str(output_dir / "doctor_report.md"),
        report_html_path=str(output_dir / "doctor_report.html"),
        checks_csv_path=str(output_dir / "doctor_checks.csv"),
    )
    write_json(output_dir / "doctor_summary.json", summary)
    (output_dir / "doctor_report.md").write_text(_build_markdown(summary), encoding="utf-8")
    (output_dir / "doctor_report.html").write_text(_build_html(summary, frame), encoding="utf-8")
    return summary


def collect_doctor_checks(workspace_root: Path) -> list[DoctorCheck]:
    """Collect environment checks for local service and container readiness."""

    system = platform.system()
    checks: list[DoctorCheck] = []
    checks.append(
        DoctorCheck(
            check_id="workspace_root",
            label="Workspace root exists",
            status="pass" if Path(workspace_root).exists() else "warn",
            value=str(Path(workspace_root)),
            message="StressLab can still create the workspace if it does not exist yet.",
            required=False,
        )
    )
    checks.append(
        DoctorCheck(
            check_id="python_runtime",
            label="Python runtime",
            status="pass",
            value=platform.python_version(),
            message=f"Platform: {system} {platform.release()}",
            required=True,
        )
    )

    docker_path = _resolve_executable("docker")
    checks.append(
        DoctorCheck(
            check_id="docker_cli",
            label="Docker CLI installed",
            status="pass" if docker_path else "fail",
            value=docker_path,
            message="Install the Docker CLI package if this is missing.",
            required=True,
        )
    )

    docker_version = _run_command(["docker", "--version"])
    checks.append(
        DoctorCheck(
            check_id="docker_client_version",
            label="Docker client version",
            status="pass" if docker_version["returncode"] == 0 else "warn",
            value=docker_version["stdout"] or None,
            message=docker_version["stderr"] or "Client version unavailable.",
            required=False,
        )
    )

    buildx_version = _run_command(["docker", "buildx", "version"])
    checks.append(
        DoctorCheck(
            check_id="docker_buildx",
            label="Docker Buildx available",
            status="pass" if buildx_version["returncode"] == 0 else "fail",
            value=buildx_version["stdout"] or None,
            message=buildx_version["stderr"] or "Buildx plugin is unavailable.",
            required=True,
        )
    )

    compose_version = _run_command(["docker", "compose", "version"])
    checks.append(
        DoctorCheck(
            check_id="docker_compose",
            label="Docker Compose available",
            status="pass" if compose_version["returncode"] == 0 else "warn",
            value=compose_version["stdout"] or None,
            message=compose_version["stderr"] or "Compose plugin is unavailable.",
            required=False,
        )
    )

    daemon_version = _run_command(["docker", "version"])
    daemon_ok = daemon_version["returncode"] == 0
    daemon_message = daemon_version["stderr"] or daemon_version["stdout"] or "Docker daemon not reachable."
    checks.append(
        DoctorCheck(
            check_id="docker_daemon",
            label="Docker daemon reachable",
            status="pass" if daemon_ok else "fail",
            value="reachable" if daemon_ok else "unreachable",
            message=daemon_message,
            required=True,
        )
    )

    if system == "Windows":
        admin_status = _windows_admin_status()
        checks.append(
            DoctorCheck(
                check_id="windows_admin",
                label="Administrator session",
                status="pass" if admin_status else "warn",
                value=str(admin_status),
                message="Some host features, including WSL and Windows Containers, typically need elevation.",
                required=False,
            )
        )
        wsl_status = _run_command(["wsl", "--status"])
        wsl_installed = wsl_status["returncode"] == 0 and "not installed" not in (wsl_status["stdout"] + wsl_status["stderr"]).lower()
        checks.append(
            DoctorCheck(
                check_id="wsl",
                label="WSL installed",
                status="pass" if wsl_installed else "warn",
                value="installed" if wsl_installed else "missing",
                message=wsl_status["stderr"] or wsl_status["stdout"] or "WSL status unavailable.",
                required=False,
            )
        )
        vmcompute_status = _run_command(["sc.exe", "query", "vmcompute"])
        vmcompute_present = vmcompute_status["returncode"] == 0 and "STATE" in vmcompute_status["stdout"]
        checks.append(
            DoctorCheck(
                check_id="windows_containers_service",
                label="Windows Containers service",
                status="pass" if vmcompute_present else "fail",
                value="present" if vmcompute_present else "missing",
                message=vmcompute_status["stderr"] or vmcompute_status["stdout"] or "vmcompute service not detected.",
                required=True,
            )
        )
    else:
        checks.append(
            DoctorCheck(
                check_id="windows_admin",
                label="Administrator session",
                status="skip",
                value=system,
                message="Windows-specific check.",
                required=False,
            )
        )
        checks.append(
            DoctorCheck(
                check_id="wsl",
                label="WSL installed",
                status="skip",
                value=system,
                message="Windows-specific check.",
                required=False,
            )
        )
        checks.append(
            DoctorCheck(
                check_id="windows_containers_service",
                label="Windows Containers service",
                status="skip",
                value=system,
                message="Windows-specific check.",
                required=False,
            )
        )
    return checks


def _run_command(argv: list[str]) -> dict[str, object]:
    env = os.environ.copy()
    plugin_dir = Path.home() / ".docker" / "cli-plugins"
    if plugin_dir.exists():
        env["DOCKER_CLI_PLUGIN_EXTRA_DIRS"] = str(plugin_dir)
    executable = _resolve_executable(argv[0]) if argv else None
    resolved_argv = [str(executable or argv[0]), *argv[1:]]
    try:
        completed = subprocess.run(
            resolved_argv,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        return {"returncode": 127, "stdout": "", "stderr": str(exc)}
    return {
        "returncode": int(completed.returncode),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _resolve_executable(name: str) -> str | None:
    direct = shutil.which(name)
    if direct:
        return direct
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    user_profile = Path.home()
    docker_candidates = {
        "docker": [
            local_app_data
            / "Microsoft"
            / "WinGet"
            / "Packages"
            / "Docker.DockerCLI_Microsoft.Winget.Source_8wekyb3d8bbwe"
            / "docker"
            / "docker.exe",
        ],
        "dockerd": [
            local_app_data
            / "Microsoft"
            / "WinGet"
            / "Packages"
            / "Docker.DockerCLI_Microsoft.Winget.Source_8wekyb3d8bbwe"
            / "docker"
            / "dockerd.exe",
        ],
        "wsl": [
            Path("C:/Windows/System32/wsl.exe"),
        ],
        "sc.exe": [
            Path("C:/Windows/System32/sc.exe"),
        ],
    }
    for candidate in docker_candidates.get(name, []):
        if candidate.exists():
            return str(candidate)
    fallback = user_profile / ".docker" / "cli-plugins" / f"{name}.exe"
    if fallback.exists():
        return str(fallback)
    return None


def _windows_admin_status() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # pragma: no cover - defensive platform fallback
        return False


def _build_markdown(summary: DoctorSummary) -> str:
    lines = [
        f"# {summary.title}",
        "",
        f"- Workspace root: `{summary.workspace_root}`",
        f"- Platform: `{summary.platform_system} {summary.platform_release}`",
        f"- Python: `{summary.python_version}`",
        f"- Ready for container build: `{summary.ready_for_container_build}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Required | Value | Message |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in summary.checks:
        lines.append(
            f"| {check.label} | {check.status} | {check.required} | {check.value or ''} | {check.message or ''} |"
        )
    return "\n".join(lines)


def _build_html(summary: DoctorSummary, frame: pd.DataFrame) -> str:
    rows = ""
    if not frame.empty:
        for _, row in frame.iterrows():
            rows += (
                "<tr>"
                f"<td>{row.get('label', '')}</td>"
                f"<td>{row.get('status', '')}</td>"
                f"<td>{row.get('required', '')}</td>"
                f"<td>{row.get('value', '')}</td>"
                f"<td>{row.get('message', '')}</td>"
                "</tr>"
            )
    return "\n".join(
        [
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            f"<title>{summary.title}</title>",
            "<style>",
            "body { font-family: Georgia, serif; margin: 2rem auto; max-width: 1080px; color: #1a2830; }",
            ".grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 0.9rem; }",
            ".card { border: 1px solid #d6dde2; padding: 0.9rem; background: #f7faf9; }",
            "table { border-collapse: collapse; width: 100%; margin-top: 1rem; }",
            "th, td { border: 1px solid #d6dde2; padding: 0.5rem 0.6rem; text-align: left; }",
            "th { background: #eef3f2; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{summary.title}</h1>",
            "<div class='grid'>",
            f"<div class='card'><strong>Workspace</strong><br>{summary.workspace_root}</div>",
            f"<div class='card'><strong>Platform</strong><br>{summary.platform_system} {summary.platform_release}</div>",
            f"<div class='card'><strong>Python</strong><br>{summary.python_version}</div>",
            f"<div class='card'><strong>Container Ready</strong><br>{summary.ready_for_container_build}</div>",
            "</div>",
            "<h2>Checks</h2>",
            "<table>",
            "<thead><tr><th>Check</th><th>Status</th><th>Required</th><th>Value</th><th>Message</th></tr></thead>",
            f"<tbody>{rows}</tbody>",
            "</table>",
            "</body>",
            "</html>",
        ]
    )
