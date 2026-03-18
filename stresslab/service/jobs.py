"""Persistent background jobs for the StressLab workspace service."""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from stresslab.models import ServiceJobRecord
from stresslab.utils import ensure_directory, now_utc

ALLOWED_COMMANDS = {
    "benchmark",
    "casebook",
    "discover",
    "evaluate",
    "generate",
    "optimize",
    "research",
    "run",
    "search",
    "theory",
}
REPO_ROOT = Path(__file__).resolve().parents[2]
JOB_DB_NAME = ".stresslab_jobs.sqlite"
JOB_STATE_DIR_NAME = ".stresslab_jobs"
JOB_LOG_DIR_NAME = "logs"
COMPLETE_LINE = re.compile(r"^[A-Za-z ]+ complete:\s+(?P<path>.+?)\s*$")
REPORT_LINE = re.compile(r"^Report:\s+(?P<path>.+?)\s*$")


class WorkspaceJobManager:
    """SQLite-backed background job runner for service submissions."""

    def __init__(self, workspace_root: Path, *, poll_interval: float = 0.2) -> None:
        self.workspace_root = ensure_directory(Path(workspace_root))
        self.poll_interval = max(0.05, float(poll_interval))
        self.state_dir = ensure_directory(self.workspace_root / JOB_STATE_DIR_NAME)
        self.log_dir = ensure_directory(self.state_dir / JOB_LOG_DIR_NAME)
        self.db_path = self.workspace_root / JOB_DB_NAME
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, name="stresslab-job-worker", daemon=True)
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[str] | None = None
        self._initialize_schema()
        self._requeue_running_jobs()
        self._worker.start()

    def close(self) -> None:
        """Stop the background worker and terminate any active subprocess."""

        self._stop_event.set()
        with self._process_lock:
            process = self._active_process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
        self._worker.join(timeout=5.0)

    def submit_job(self, payload: dict[str, Any]) -> ServiceJobRecord:
        """Persist a submitted job and return its initial state."""

        normalized = _normalize_payload(payload, workspace_root=self.workspace_root)
        timestamp = now_utc().isoformat()
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id,
                    status,
                    command,
                    payload_json,
                    workspace_root,
                    created_at,
                    updated_at,
                    attempt_count
                )
                VALUES (?, 'queued', ?, ?, ?, ?, ?, 0)
                """,
                (
                    job_id,
                    normalized["command"],
                    json.dumps(normalized, sort_keys=True),
                    str(self.workspace_root),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_job(job_id, expand=False)

    def get_job(self, job_id: str, *, expand: bool = False) -> ServiceJobRecord:
        """Return one persisted job record."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Unknown job id '{job_id}'.")
        return _row_to_job_record(row, expand=expand)

    def list_jobs(
        self,
        *,
        limit: int | None = None,
        status: str | None = None,
        expand: bool = False,
    ) -> dict[str, Any]:
        """Return queue summary and recent jobs."""

        query = "SELECT * FROM jobs"
        params: list[Any] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
            counts_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status ORDER BY status"
            ).fetchall()
        jobs = [_row_to_job_record(row, expand=expand).model_dump(mode="json") for row in rows]
        return {
            "root": str(self.workspace_root.resolve()),
            "db_path": str(self.db_path.resolve()),
            "entry_count": len(jobs),
            "status_counts": {str(row["status"]): int(row["count"]) for row in counts_rows},
            "jobs": jobs,
        }

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    command TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    workspace_root TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    run_dir TEXT,
                    report_path TEXT,
                    command_line TEXT,
                    stdout_path TEXT,
                    stderr_path TEXT,
                    exit_code INTEGER,
                    error TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at
                ON jobs(status, created_at);
                """
            )

    def _requeue_running_jobs(self) -> None:
        timestamp = now_utc().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'queued',
                    updated_at = ?,
                    started_at = NULL,
                    error = CASE
                        WHEN error IS NULL OR error = '' THEN 'Requeued after service restart.'
                        ELSE error
                    END
                WHERE status = 'running'
                """,
                (timestamp,),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self._claim_next_job()
            if job is None:
                self._stop_event.wait(self.poll_interval)
                continue
            self._execute_job(job)

    def _claim_next_job(self) -> ServiceJobRecord | None:
        timestamp = now_utc().isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            updated = connection.execute(
                """
                UPDATE jobs
                SET status = 'running',
                    started_at = ?,
                    updated_at = ?,
                    attempt_count = attempt_count + 1
                WHERE job_id = ? AND status = 'queued'
                """,
                (timestamp, timestamp, row["job_id"]),
            )
            connection.commit()
            if updated.rowcount != 1:
                return None
        return self.get_job(str(row["job_id"]), expand=False)

    def _execute_job(self, job: ServiceJobRecord) -> None:
        stdout_path = self.log_dir / f"{job.job_id}.stdout.log"
        stderr_path = self.log_dir / f"{job.job_id}.stderr.log"
        started_at = now_utc().isoformat()
        command = _build_command(job.payload, workspace_root=self.workspace_root)
        command_line = subprocess.list2cmdline(command)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET command_line = ?, stdout_path = ?, stderr_path = ?, started_at = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    command_line,
                    str(stdout_path),
                    str(stderr_path),
                    started_at,
                    started_at,
                    job.job_id,
                ),
            )

        completed_at = now_utc().isoformat()
        run_dir: str | None = None
        report_path: str | None = None
        exit_code: int | None = None
        error: str | None = None
        status = "failed"
        stdout_text = ""
        stderr_text = ""

        try:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._process_lock:
                self._active_process = process
            stdout_text, stderr_text = process.communicate()
            exit_code = int(process.returncode)
            completed_at = now_utc().isoformat()
            run_dir, report_path = _parse_completion_paths(stdout_text, workspace_root=self.workspace_root)
            if exit_code == 0:
                status = "succeeded"
            else:
                error = stderr_text.strip() or stdout_text.strip() or f"Command exited with code {exit_code}."
        except Exception as exc:  # pragma: no cover - defensive service fallback
            completed_at = now_utc().isoformat()
            error = str(exc)
            status = "failed"
        finally:
            with self._process_lock:
                self._active_process = None
            stdout_path.write_text(stdout_text, encoding="utf-8")
            stderr_path.write_text(stderr_text, encoding="utf-8")
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE jobs
                    SET status = ?,
                        completed_at = ?,
                        updated_at = ?,
                        run_dir = ?,
                        report_path = ?,
                        exit_code = ?,
                        error = ?
                    WHERE job_id = ?
                    """,
                    (
                        status,
                        completed_at,
                        completed_at,
                        run_dir,
                        report_path,
                        exit_code,
                        error,
                        job.job_id,
                    ),
                )


def _normalize_payload(payload: dict[str, Any], *, workspace_root: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Job payload must be a JSON object.")
    normalized = dict(payload)
    options = normalized.pop("options", None)
    if options is not None:
        if not isinstance(options, dict):
            raise ValueError("'options' must be a JSON object when provided.")
        normalized.update(options)
    command = str(normalized.get("command", "")).strip().lower()
    if command not in ALLOWED_COMMANDS:
        supported = ", ".join(sorted(ALLOWED_COMMANDS))
        raise ValueError(f"Unsupported job command '{command}'. Supported commands: {supported}.")
    cleaned: dict[str, Any] = {"command": command}
    if command in {"run", "search", "optimize", "evaluate"}:
        cleaned["spec_path"] = str(
            _resolve_input_path(normalized.get("spec_path"), workspace_root=workspace_root)
        )
    if command == "search":
        cleaned["objective"] = str(normalized.get("objective", "min_failure")).strip().lower()
        if cleaned["objective"] not in {"min_failure", "worst_case"}:
            raise ValueError("Search jobs require objective 'min_failure' or 'worst_case'.")
    if command == "discover" and normalized.get("source_dir") is not None:
        cleaned["source_dir"] = str(
            _resolve_input_path(normalized.get("source_dir"), workspace_root=workspace_root)
        )
    if command == "discover" and normalized.get("resume_run_dir") is not None:
        cleaned["resume_run_dir"] = str(
            _resolve_input_path(normalized.get("resume_run_dir"), workspace_root=workspace_root)
        )
    if command in {"theory", "research"}:
        cleaned["dataset_source"] = str(
            _resolve_input_path(normalized.get("dataset_source"), workspace_root=workspace_root)
        )
        if command == "research" and normalized.get("theory_dir") is not None:
            cleaned["theory_dir"] = str(
                _resolve_input_path(normalized.get("theory_dir"), workspace_root=workspace_root)
            )
    if command == "casebook":
        suite = normalized.get("suite")
        spec_paths = normalized.get("spec_paths")
        if suite is None and not spec_paths:
            raise ValueError("Casebook jobs require 'suite' or 'spec_paths'.")
        if suite is not None:
            cleaned["suite"] = str(suite)
        if spec_paths:
            if not isinstance(spec_paths, list):
                raise ValueError("'spec_paths' must be a list of spec paths.")
            cleaned["spec_paths"] = [
                str(_resolve_input_path(path, workspace_root=workspace_root))
                for path in spec_paths
            ]
    if command == "benchmark" and normalized.get("suite") is not None:
        cleaned["suite"] = str(normalized["suite"])
    _copy_fields(
        cleaned,
        normalized,
        command=command,
    )
    return cleaned


def _copy_fields(target: dict[str, Any], payload: dict[str, Any], *, command: str) -> None:
    common_bool_fields = [
        "robust",
        "expand_policies",
        "expand_dynamic_policies",
        "expand_adaptive_policies",
        "expand_controller_bundles",
        "expand_hierarchical_playbooks",
        "policy_only",
        "dynamic_only",
        "adaptive_only",
        "bundle_only",
        "playbook_only",
    ]
    float_fields = {"budget", "scenario_budget", "fairness_weight", "horizon", "worst_case_budget"}
    int_fields = {
        "scenario_samples",
        "replicates",
        "seed_step",
        "count",
        "min_nodes",
        "max_nodes",
        "seed",
        "batch_size",
        "workers",
        "shard_count",
        "shard_index",
    }
    text_fields = {"topology_type"}

    for key in float_fields:
        if payload.get(key) is not None:
            target[key] = float(payload[key])
    for key in int_fields:
        if payload.get(key) is not None:
            target[key] = int(payload[key])
    for key in common_bool_fields:
        if payload.get(key) is not None:
            target[key] = bool(payload[key])
    for key in text_fields:
        if payload.get(key) is not None:
            target[key] = str(payload[key])

    if command == "evaluate":
        intervention_ids = payload.get("intervention_ids")
        if intervention_ids is not None:
            if not isinstance(intervention_ids, list):
                raise ValueError("'intervention_ids' must be a list of strings.")
            target["intervention_ids"] = [str(value) for value in intervention_ids]
    if command == "casebook":
        if payload.get("title") is not None:
            target["title"] = str(payload["title"])


def _resolve_input_path(value: Any, *, workspace_root: Path) -> Path:
    if value is None:
        raise ValueError("A required path field is missing.")
    path = Path(str(value))
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.extend([REPO_ROOT / path, workspace_root / path, Path.cwd() / path])
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise ValueError(f"Path '{value}' does not exist.")


def _build_command(payload: dict[str, Any], *, workspace_root: Path) -> list[str]:
    command = str(payload["command"])
    argv = [sys.executable, "-m", "stresslab.cli.main", command]
    if command in {"run", "search", "optimize", "evaluate"}:
        argv.append(str(payload["spec_path"]))
    if command == "search":
        argv.extend(["--objective", str(payload.get("objective", "min_failure"))])
    elif command in {"theory", "research"}:
        argv.append(str(payload["dataset_source"]))
    elif command == "casebook":
        for spec_path in payload.get("spec_paths", []):
            argv.append(str(spec_path))
        if payload.get("suite"):
            argv.extend(["--suite", str(payload["suite"])])
    elif command == "benchmark":
        argv.extend(["--suite", str(payload.get("suite", "starter"))])

    if command == "discover" and payload.get("source_dir") is not None:
        argv.extend(["--source-dir", str(payload["source_dir"])])
    if command == "discover" and payload.get("resume_run_dir") is not None:
        argv.extend(["--resume-run-dir", str(payload["resume_run_dir"])])
    if command == "research" and payload.get("theory_dir") is not None:
        argv.extend(["--theory-dir", str(payload["theory_dir"])])

    for key in ["budget", "scenario_budget", "fairness_weight", "horizon", "worst_case_budget"]:
        if payload.get(key) is not None:
            argv.extend([f"--{key.replace('_', '-')}", f"{payload[key]}"])
    for key in [
        "scenario_samples",
        "replicates",
        "seed_step",
        "count",
        "min_nodes",
        "max_nodes",
        "seed",
        "batch_size",
        "workers",
        "shard_count",
        "shard_index",
    ]:
        if payload.get(key) is not None:
            argv.extend([f"--{key.replace('_', '-')}", f"{payload[key]}"])
    if payload.get("topology_type") is not None:
        argv.extend(["--topology-type", str(payload["topology_type"])])
    for key in [
        "robust",
        "expand_policies",
        "expand_dynamic_policies",
        "expand_adaptive_policies",
        "expand_controller_bundles",
        "expand_hierarchical_playbooks",
        "policy_only",
        "dynamic_only",
        "adaptive_only",
        "bundle_only",
        "playbook_only",
    ]:
        if payload.get(key):
            argv.append(f"--{key.replace('_', '-')}")

    if command == "evaluate":
        for intervention_id in payload.get("intervention_ids", []):
            argv.extend(["--intervention-id", str(intervention_id)])
    if command == "casebook" and payload.get("title") is not None:
        argv.extend(["--title", str(payload["title"])])

    if command in {"run", "search", "optimize", "evaluate", "casebook", "benchmark", "generate", "discover", "theory", "research"}:
        argv.extend(["--output-dir", str(workspace_root)])
        argv.extend(["--registry-root", str(workspace_root)])
    return argv


def _parse_completion_paths(stdout_text: str, *, workspace_root: Path) -> tuple[str | None, str | None]:
    run_dir: str | None = None
    report_path: str | None = None
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        complete_match = COMPLETE_LINE.match(line)
        if complete_match:
            candidate = Path(complete_match.group("path"))
            run_dir = str(_resolve_output_path(candidate, workspace_root=workspace_root))
            continue
        report_match = REPORT_LINE.match(line)
        if report_match:
            candidate = Path(report_match.group("path"))
            report_path = str(_resolve_output_path(candidate, workspace_root=workspace_root))
    return run_dir, report_path


def _row_to_job_record(row: sqlite3.Row, *, expand: bool) -> ServiceJobRecord:
    payload = json.loads(str(row["payload_json"]))
    stdout_path = _coerce_optional_path(row["stdout_path"])
    stderr_path = _coerce_optional_path(row["stderr_path"])
    stdout_tail = _tail_text(stdout_path) if expand else None
    stderr_tail = _tail_text(stderr_path) if expand else None
    return ServiceJobRecord(
        job_id=str(row["job_id"]),
        status=str(row["status"]),
        command=str(row["command"]),
        payload=payload,
        workspace_root=str(row["workspace_root"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        started_at=_coerce_optional_text(row["started_at"]),
        completed_at=_coerce_optional_text(row["completed_at"]),
        run_dir=_coerce_optional_text(row["run_dir"]),
        report_path=_coerce_optional_text(row["report_path"]),
        command_line=_coerce_optional_text(row["command_line"]),
        stdout_path=str(stdout_path) if stdout_path is not None else None,
        stderr_path=str(stderr_path) if stderr_path is not None else None,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        exit_code=int(row["exit_code"]) if row["exit_code"] is not None else None,
        error=_coerce_optional_text(row["error"]),
        attempt_count=int(row["attempt_count"]),
    )


def _coerce_optional_path(value: Any) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    return Path(text) if text else None


def _coerce_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _tail_text(path: Path | None, *, limit: int = 4000) -> str | None:
    if path is None or not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    if len(content) <= limit:
        return content
    return content[-limit:]


def _resolve_output_path(path: Path, *, workspace_root: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    for candidate in ((REPO_ROOT / path), (workspace_root / path), (Path.cwd() / path)):
        if candidate.exists():
            return candidate.resolve()
    return (REPO_ROOT / path).resolve()
