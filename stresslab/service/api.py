"""Lightweight HTTP API for StressLab workspace artifacts."""

from __future__ import annotations

import json
import mimetypes
import sqlite3
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np
import pandas as pd

from stresslab.campaigns import build_artifact_bundle
from stresslab.campaigns.registry import refresh_registry, registry_paths
from stresslab.service.jobs import WorkspaceJobManager
from stresslab.service.web_app import render_workspace_app

JSON_FILES = [
    "metadata.json",
    "baseline_result.json",
    "scenario_result.json",
    "search_result.json",
    "optimization.json",
    "evaluation_summary.json",
    "attribution.json",
    "benchmark_summary.json",
    "comparison_summary.json",
    "batch_summary.json",
    "run_catalog_summary.json",
    "workspace_status_summary.json",
    "workspace_board_summary.json",
    "casebook_summary.json",
    "generation_summary.json",
    "discovery_summary.json",
    "theory_summary.json",
    "research_summary.json",
    "treatment_plan.json",
]
NUMERIC_COLUMNS = [
    "scenario_count",
    "cluster_count",
    "throughput",
    "mean_wait",
    "resilience_score",
    "fairness_score",
    "best_resilience",
    "best_shock_budget",
    "damage_score",
    "execution_duration",
]


class WorkspaceAPIServer(ThreadingHTTPServer):
    """Threading HTTP server with StressLab workspace context attached."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        workspace_root: Path,
        default_refresh: bool,
        quiet: bool,
        api_token: str | None,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.workspace_root = Path(workspace_root)
        self.default_refresh = default_refresh
        self.quiet = quiet
        self.api_token = api_token.strip() if api_token else None
        self.job_manager = WorkspaceJobManager(self.workspace_root)


@dataclass
class RunningWorkspaceAPIServer:
    """Running API server plus base URL and shutdown helper."""

    server: WorkspaceAPIServer
    thread: threading.Thread
    base_url: str

    def close(self) -> None:
        """Shutdown the server and wait for the thread to exit."""

        self.server.shutdown()
        self.thread.join(timeout=5.0)
        self.server.job_manager.close()
        self.server.server_close()


def create_workspace_api_server(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    refresh: bool = False,
    quiet: bool = False,
    api_token: str | None = None,
) -> tuple[WorkspaceAPIServer, str]:
    """Create an API server instance for a workspace root."""

    handler = _build_request_handler()
    server = WorkspaceAPIServer(
        (host, port),
        handler,
        workspace_root=Path(root),
        default_refresh=refresh,
        quiet=quiet,
        api_token=api_token,
    )
    bound_host, bound_port = server.server_address[:2]
    base_url = f"http://{bound_host}:{bound_port}"
    return server, base_url


def start_workspace_api_server(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    refresh: bool = False,
    quiet: bool = False,
    api_token: str | None = None,
) -> RunningWorkspaceAPIServer:
    """Start the workspace API in a background thread."""

    server, base_url = create_workspace_api_server(
        root,
        host=host,
        port=port,
        refresh=refresh,
        quiet=quiet,
        api_token=api_token,
    )
    thread = threading.Thread(target=server.serve_forever, name="stresslab-api", daemon=True)
    thread.start()
    return RunningWorkspaceAPIServer(server=server, thread=thread, base_url=base_url)


def serve_workspace_api(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    refresh: bool = False,
    quiet: bool = False,
    duration_seconds: float | None = None,
    api_token: str | None = None,
) -> str:
    """Serve the workspace API until interrupted or until the duration elapses."""

    server, base_url = create_workspace_api_server(
        root,
        host=host,
        port=port,
        refresh=refresh,
        quiet=quiet,
        api_token=api_token,
    )
    try:
        if duration_seconds is None:
            server.serve_forever()
        else:
            server.timeout = min(max(duration_seconds, 0.05), 0.25)
            deadline = time.monotonic() + duration_seconds
            while time.monotonic() < deadline:
                server.handle_request()
    finally:
        server.job_manager.close()
        server.server_close()
    return base_url


def _build_request_handler() -> type[BaseHTTPRequestHandler]:
    class StressLabRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            parts = [segment for segment in parsed.path.split("/") if segment]
            query = parse_qs(parsed.query, keep_blank_values=True)
            refresh = _query_bool(query, "refresh", self.server.default_refresh)
            try:
                if not self._authorized(parsed.path, query):
                    self._send_json({"error": "Unauthorized."}, status=HTTPStatus.UNAUTHORIZED)
                    return
                if parsed.path == "/":
                    self._send_html(_landing_page(self.server.workspace_root, refresh=refresh))
                    return
                if parsed.path in {"/app", "/app/"}:
                    self._send_html(render_workspace_app(auth_required=bool(self.server.api_token)))
                    return
                if parsed.path == "/health":
                    self._send_json(
                        {
                            "status": "ok",
                            "workspace_root": str(self.server.workspace_root.resolve()),
                            "registry_csv_path": str(registry_paths(self.server.workspace_root)[0]),
                            "job_db_path": str(self.server.job_manager.db_path.resolve()),
                            "auth_required": bool(self.server.api_token),
                        }
                    )
                    return
                if parsed.path == "/registry":
                    limit = _query_int(query, "limit")
                    payload = _registry_payload(
                        self.server.workspace_root,
                        refresh=refresh,
                        analysis_type=_query_value(query, "analysis_type"),
                        system_name=_query_value(query, "system_name"),
                        limit=limit,
                    )
                    self._send_json(payload)
                    return
                if parsed.path == "/status":
                    payload = _status_payload(
                        self.server.workspace_root,
                        refresh=refresh,
                        limit=_query_int(query, "limit") or 25,
                    )
                    self._send_json(payload)
                    return
                if parsed.path == "/board":
                    payload = _board_payload(
                        self.server.workspace_root,
                        refresh=refresh,
                        recent_limit=_query_int(query, "recent_limit") or 20,
                        watch_limit=_query_int(query, "watch_limit") or 12,
                        plan_limit=_query_int(query, "plan_limit") or 12,
                    )
                    self._send_json(payload)
                    return
                if parsed.path == "/discovery":
                    payload = _discovery_payload(
                        self.server.workspace_root,
                        refresh=refresh,
                        limit=_query_int(query, "limit") or 12,
                    )
                    self._send_json(payload)
                    return
                if parsed.path == "/jobs":
                    payload = self.server.job_manager.list_jobs(
                        limit=_query_int(query, "limit"),
                        status=_query_value(query, "status"),
                        expand=_query_bool(query, "expand", False),
                    )
                    self._send_json(payload)
                    return
                if len(parts) >= 2 and parts[0] == "artifacts":
                    run_dir = _resolve_artifact_dir(self.server.workspace_root, unquote(parts[1]), refresh=refresh)
                    payload = _artifact_payload(
                        run_dir,
                        refresh=refresh,
                        expand=_query_bool(query, "expand", False),
                    )
                    self._send_json(payload)
                    return
                if len(parts) >= 2 and parts[0] == "reports":
                    run_dir = _resolve_artifact_dir(self.server.workspace_root, unquote(parts[1]), refresh=refresh)
                    report_path = run_dir / "report.html"
                    if not report_path.exists():
                        report_path = (
                            run_dir / "evaluation_report.html"
                            if (run_dir / "evaluation_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "comparison_report.html"
                            if (run_dir / "comparison_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "benchmark_report.html"
                            if (run_dir / "benchmark_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "workspace_status_report.html"
                            if (run_dir / "workspace_status_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "workspace_board_report.html"
                            if (run_dir / "workspace_board_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "run_catalog_report.html"
                            if (run_dir / "run_catalog_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "casebook_report.html"
                            if (run_dir / "casebook_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "generation_report.html"
                            if (run_dir / "generation_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "discovery_report.html"
                            if (run_dir / "discovery_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "theory_report.html"
                            if (run_dir / "theory_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        report_path = (
                            run_dir / "research_report.html"
                            if (run_dir / "research_report.html").exists()
                            else report_path
                        )
                    if not report_path.exists():
                        raise FileNotFoundError(f"No HTML report found for artifact '{parts[1]}'.")
                    self._send_file(report_path)
                    return
                if len(parts) >= 2 and parts[0] == "bundles":
                    run_dir = _resolve_artifact_dir(self.server.workspace_root, unquote(parts[1]), refresh=refresh)
                    include_registry = _query_bool(query, "include_registry", False)
                    with TemporaryDirectory() as temp_dir_name:
                        summary = build_artifact_bundle(
                            run_dir,
                            output_dir=Path(temp_dir_name),
                            include_registry=include_registry,
                        )
                        self._send_file(
                            Path(summary.bundle_path),
                            content_type="application/zip",
                            filename=Path(summary.bundle_path).name,
                        )
                    return
                if len(parts) >= 3 and parts[0] == "files":
                    run_dir = _resolve_artifact_dir(self.server.workspace_root, unquote(parts[1]), refresh=refresh)
                    relative_path = _safe_relative_path(parts[2:])
                    self._send_file(run_dir / relative_path)
                    return
                if len(parts) == 2 and parts[0] == "jobs":
                    payload = self.server.job_manager.get_job(
                        unquote(parts[1]),
                        expand=_query_bool(query, "expand", False),
                    )
                    self._send_json(payload.model_dump(mode="json"))
                    return
                self._send_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)
            except FileNotFoundError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # pragma: no cover - defensive API fallback
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            try:
                if not self._authorized(parsed.path, query):
                    self._send_json({"error": "Unauthorized."}, status=HTTPStatus.UNAUTHORIZED)
                    return
                if parsed.path == "/jobs":
                    payload = self._read_json_body()
                    record = self.server.job_manager.submit_job(payload)
                    self._send_json(record.model_dump(mode="json"), status=HTTPStatus.CREATED)
                    return
                self._send_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)
            except FileNotFoundError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # pragma: no cover - defensive API fallback
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def log_message(self, format: str, *args: object) -> None:
            if not self.server.quiet:
                super().log_message(format, *args)

        def _send_json(self, payload: dict[str, object], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self, path: str, query: dict[str, list[str]]) -> bool:
            token = self.server.api_token
            if not token:
                return True
            if path in {"/", "/app", "/app/", "/health"}:
                return True
            provided = self._extract_token(query)
            return provided == token

        def _extract_token(self, query: dict[str, list[str]]) -> str | None:
            authorization = self.headers.get("Authorization", "").strip()
            if authorization:
                if authorization.lower().startswith("bearer "):
                    return authorization[7:].strip()
                if authorization.lower().startswith("token "):
                    return authorization[6:].strip()
                return authorization
            header_token = self.headers.get("X-StressLab-Token", "").strip()
            if header_token:
                return header_token
            return _query_value(query, "token")

        def _read_json_body(self) -> dict[str, Any]:
            length_header = self.headers.get("Content-Length")
            if length_header is None:
                raise ValueError("Missing Content-Length header.")
            try:
                length = int(length_header)
            except ValueError as exc:
                raise ValueError("Content-Length must be an integer.") from exc
            if length <= 0:
                raise ValueError("Request body is empty.")
            raw_body = self.rfile.read(length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("Request body must be valid JSON.") from exc
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
            return payload

        def _send_file(
            self,
            path: Path,
            *,
            content_type: str | None = None,
            filename: str | None = None,
        ) -> None:
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"File '{path}' does not exist.")
            detected_type, _ = mimetypes.guess_type(str(path))
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type or detected_type or "application/octet-stream")
            if filename is not None:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return StressLabRequestHandler


def _registry_payload(
    root: Path,
    *,
    refresh: bool,
    analysis_type: str | None,
    system_name: str | None,
    limit: int | None,
) -> dict[str, object]:
    frame = _load_registry_frame(root, refresh=refresh)
    if analysis_type is not None and "analysis_type" in frame.columns:
        frame = frame[frame["analysis_type"] == analysis_type].copy()
    if system_name is not None and "system_name" in frame.columns:
        lowered = system_name.lower()
        frame = frame[frame["system_name"].fillna("").str.lower().str.contains(lowered)].copy()
    if limit is not None:
        frame = frame.head(limit)
    return {
        "root": str(Path(root).resolve()),
        "entry_count": len(frame),
        "analysis_type_counts": _value_counts(frame, "analysis_type"),
        "system_counts": _value_counts(frame, "system_name", limit=10),
        "entries": _frame_records(frame),
    }


def _status_payload(root: Path, *, refresh: bool, limit: int) -> dict[str, object]:
    frame = _load_registry_frame(root, refresh=refresh)
    recent = frame.head(limit).copy()
    latest = frame.iloc[0] if not frame.empty else None
    return {
        "root": str(Path(root).resolve()),
        "entry_count": len(frame),
        "recent_count": len(recent),
        "latest_run_dir": _value_or_none(latest, "run_dir"),
        "latest_timestamp": _value_or_none(latest, "timestamp"),
        "latest_analysis_type": _value_or_none(latest, "analysis_type"),
        "latest_system_name": _value_or_none(latest, "system_name"),
        "analysis_type_counts": _value_counts(frame, "analysis_type"),
        "system_counts": _value_counts(frame, "system_name", limit=10),
        "failure_rate": _mean_or_none(frame, "failure_triggered"),
        "mean_resilience_score": _mean_or_none(frame, "resilience_score"),
        "mean_fairness_score": _mean_or_none(frame, "fairness_score"),
        "mean_execution_duration": _mean_or_none(frame, "execution_duration"),
        "recent_entries": _frame_records(recent),
    }


def _board_payload(
    root: Path,
    *,
    refresh: bool,
    recent_limit: int,
    watch_limit: int,
    plan_limit: int,
) -> dict[str, object]:
    frame = _load_registry_frame(root, refresh=refresh)
    recent = frame.head(recent_limit).copy()
    leaders = _build_system_leaders(frame)
    watchlist = _build_failure_watchlist(frame, limit=watch_limit)
    plans = _build_plan_table(frame, limit=plan_limit)
    latest = frame.iloc[0] if not frame.empty else None
    leader = leaders.iloc[0] if not leaders.empty else None
    plan = plans.iloc[0] if not plans.empty else None
    return {
        "root": str(Path(root).resolve()),
        "entry_count": len(frame),
        "recent_count": len(recent),
        "leader_count": len(leaders),
        "watchlist_count": len(watchlist),
        "plan_count": len(plans),
        "latest_run_dir": _value_or_none(latest, "run_dir"),
        "latest_timestamp": _value_or_none(latest, "timestamp"),
        "top_system_by_resilience": _value_or_none(leader, "system_name"),
        "top_plan_run_dir": _value_or_none(plan, "run_dir"),
        "top_plan_system_name": _value_or_none(plan, "system_name"),
        "mean_resilience_score": _mean_or_none(frame, "resilience_score"),
        "mean_fairness_score": _mean_or_none(frame, "fairness_score"),
        "recent_entries": _frame_records(recent),
        "leaders": _frame_records(leaders),
        "failure_watchlist": _frame_records(watchlist),
        "plans": _frame_records(plans),
    }


def _discovery_payload(root: Path, *, refresh: bool, limit: int) -> dict[str, object]:
    frame = _load_registry_frame(root, refresh=refresh)
    if frame.empty or "analysis_type" not in frame.columns:
        return {
            "root": str(Path(root).resolve()),
            "entry_count": 0,
            "analysis_type_counts": {},
            "latest_entries": [],
            "top_symbolic_laws": [],
            "top_candidate_laws": [],
        }
    discovery_frame = frame[frame["analysis_type"].isin(["generate", "discover", "theory", "research"])].copy()
    latest_entries = _frame_records(discovery_frame.head(limit))
    latest_theory_dir = _first_existing_run_dir(discovery_frame, analysis_type="theory")
    latest_research_dir = _first_existing_run_dir(discovery_frame, analysis_type="research")
    symbolic_laws = _load_csv(latest_theory_dir / "symbolic_laws.csv") if latest_theory_dir is not None else pd.DataFrame()
    candidate_laws = _load_csv(latest_theory_dir / "law_candidates.csv") if latest_theory_dir is not None else pd.DataFrame()
    figure_index = _load_csv(latest_research_dir / "figure_index.csv") if latest_research_dir is not None else pd.DataFrame()
    return {
        "root": str(Path(root).resolve()),
        "entry_count": len(discovery_frame),
        "analysis_type_counts": _value_counts(discovery_frame, "analysis_type"),
        "latest_entries": latest_entries,
        "latest_theory_run_dir": str(latest_theory_dir) if latest_theory_dir is not None else None,
        "latest_research_run_dir": str(latest_research_dir) if latest_research_dir is not None else None,
        "top_symbolic_laws": _frame_records(symbolic_laws.head(10)),
        "top_candidate_laws": _frame_records(candidate_laws.head(10)),
        "research_figures": _frame_records(figure_index.head(20)),
    }


def _artifact_payload(run_dir: Path, *, refresh: bool, expand: bool) -> dict[str, object]:
    root = run_dir.parent
    registry_frame = _load_registry_frame(root, refresh=refresh)
    summary_frame = registry_frame[registry_frame["run_dir"] == str(run_dir)]
    summary = _frame_records(summary_frame.head(1))
    payload: dict[str, object] = {
        "run_id": run_dir.name,
        "run_dir": str(run_dir.resolve()),
        "summary": summary[0] if summary else None,
        "available_files": sorted(
            str(path.relative_to(run_dir))
            for path in run_dir.rglob("*")
            if path.is_file()
        ),
    }
    if expand:
        details: dict[str, object] = {}
        for name in JSON_FILES:
            path = run_dir / name
            if path.exists():
                details[name] = json.loads(path.read_text(encoding="utf-8"))
        payload["details"] = details
    return payload


def _resolve_artifact_dir(root: Path, run_id: str, *, refresh: bool) -> Path:
    candidate = Path(run_id)
    if candidate.exists() and candidate.is_dir():
        return candidate
    direct = Path(root) / run_id
    if direct.exists() and direct.is_dir():
        return direct
    frame = _load_registry_frame(root, refresh=refresh)
    if "run_id" in frame.columns:
        matches = frame[frame["run_id"] == run_id]
        if not matches.empty:
            run_dir = Path(str(matches.iloc[0]["run_dir"]))
            if run_dir.exists():
                return run_dir
    raise FileNotFoundError(f"Unknown artifact id '{run_id}'.")


def _load_registry_frame(root: Path, *, refresh: bool) -> pd.DataFrame:
    csv_path, _ = registry_paths(root)
    if refresh or not csv_path.exists():
        frame = refresh_registry(root)
    else:
        frame = pd.read_csv(csv_path)
    if frame.empty:
        return frame
    normalized = frame.copy()
    for column in NUMERIC_COLUMNS:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "failure_triggered" in normalized.columns:
        normalized["failure_triggered"] = normalized["failure_triggered"].astype("boolean")
    if "robust_mode" in normalized.columns:
        normalized["robust_mode"] = normalized["robust_mode"].astype("boolean")
    if "timestamp" in normalized.columns:
        normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="coerce", utc=True)
        normalized = normalized.sort_values("timestamp", ascending=False, na_position="last").reset_index(drop=True)
    return normalized


def _frame_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    export = frame.copy()
    for column in export.columns:
        if pd.api.types.is_datetime64_any_dtype(export[column]):
            export[column] = export[column].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        elif str(export[column].dtype) == "boolean":
            export[column] = export[column].astype(object)
    export = export.where(pd.notna(export), None)
    return export.to_dict(orient="records")


def _value_counts(frame: pd.DataFrame, column: str, *, limit: int | None = None) -> dict[str, int]:
    if frame.empty or column not in frame.columns:
        return {}
    counts = frame[column].fillna("unknown").astype(str).value_counts()
    if limit is not None:
        counts = counts.head(limit)
    return {str(index): int(value) for index, value in counts.items()}


def _mean_or_none(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def _first_existing_run_dir(frame: pd.DataFrame, *, analysis_type: str) -> Path | None:
    if frame.empty or "analysis_type" not in frame.columns or "run_dir" not in frame.columns:
        return None
    matches = frame[frame["analysis_type"] == analysis_type]
    if matches.empty:
        return None
    candidate = Path(str(matches.iloc[0]["run_dir"]))
    return candidate if candidate.exists() else None


def _value_or_none(row: pd.Series | None, column: str) -> str | None:
    if row is None or column not in row.index:
        return None
    value = row[column]
    if pd.isna(value):
        return None
    return str(value)


def _build_system_leaders(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "system_name" not in frame.columns or "resilience_score" not in frame.columns:
        return pd.DataFrame()
    candidate = frame.dropna(subset=["system_name", "resilience_score"]).copy()
    if candidate.empty:
        return pd.DataFrame()
    candidate = candidate.sort_values(
        ["resilience_score", "fairness_score", "timestamp"],
        ascending=[False, False, False],
        na_position="last",
    )
    return candidate.groupby("system_name", as_index=False).head(1).reset_index(drop=True)


def _build_failure_watchlist(frame: pd.DataFrame, *, limit: int) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    candidate = frame.copy()
    if "analysis_type" in candidate.columns:
        candidate = candidate[candidate["analysis_type"].isin(["run", "search", "optimize"])].copy()
    if candidate.empty:
        return pd.DataFrame()
    failures = candidate[candidate["failure_triggered"] == True].copy() if "failure_triggered" in candidate.columns else pd.DataFrame()  # noqa: E712
    if len(failures) < limit:
        filler = candidate.sort_values(
            ["resilience_score", "mean_wait", "timestamp"],
            ascending=[True, False, False],
            na_position="last",
        )
        candidate = pd.concat([failures, filler], ignore_index=True)
    else:
        candidate = failures
    candidate = candidate.drop_duplicates(subset=["run_dir"], keep="first")
    return candidate.head(limit).reset_index(drop=True)


def _build_plan_table(frame: pd.DataFrame, *, limit: int) -> pd.DataFrame:
    if frame.empty or "analysis_type" not in frame.columns:
        return pd.DataFrame()
    plans = frame[frame["analysis_type"].isin(["optimize", "evaluation"])].copy()
    if plans.empty:
        return pd.DataFrame()
    if "replicate_count" not in plans.columns:
        plans["replicate_count"] = 0
    plans["replicate_count"] = pd.to_numeric(plans["replicate_count"], errors="coerce").fillna(0.0)
    plans["evidence_rank"] = np.where(plans["analysis_type"] == "evaluation", 1.0, 0.0)
    plans = plans.sort_values(
        ["evidence_rank", "replicate_count", "robust_mode", "resilience_score", "fairness_score", "timestamp"],
        ascending=[False, False, False, False, False, False],
        na_position="last",
    )
    return plans.head(limit).reset_index(drop=True)


def _safe_relative_path(parts: list[str]) -> Path:
    relative = Path(*[unquote(part) for part in parts])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid file path.")
    return relative


def _query_bool(query: dict[str, list[str]], key: str, default: bool) -> bool:
    value = _query_value(query, key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _query_int(query: dict[str, list[str]], key: str) -> int | None:
    value = _query_value(query, key)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Query parameter '{key}' must be an integer.") from exc


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _landing_page(root: Path, *, refresh: bool) -> str:
    payload = _status_payload(root, refresh=refresh, limit=8)
    job_payload = _jobs_payload(root, limit=8)
    rows = "".join(
        "<tr>"
        + "".join(f"<td>{entry.get(column)}</td>" for column in ["run_id", "analysis_type", "system_name", "timestamp"])
        + "</tr>"
        for entry in payload["recent_entries"]
    )
    return "\n".join(
        [
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            "<title>StressLab API</title>",
            "<style>",
            "body { font-family: Georgia, serif; margin: 2rem auto; max-width: 1000px; color: #182026; }",
            "code { background: #f4f7f8; padding: 0.15rem 0.3rem; }",
            "table { border-collapse: collapse; width: 100%; margin-top: 1rem; }",
            "td, th { border: 1px solid #d6dde2; padding: 0.45rem 0.6rem; text-align: left; }",
            ".grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.9rem; }",
            ".card { border: 1px solid #d6dde2; padding: 0.9rem; background: #fafcfd; }",
            "</style>",
            "</head>",
            "<body>",
            "<h1>StressLab Workspace API</h1>",
            f"<p>Workspace root: <code>{Path(root).resolve()}</code></p>",
            "<div class='grid'>",
            f"<div class='card'><strong>Tracked artifacts</strong><br><code>{payload['entry_count']}</code></div>",
            f"<div class='card'><strong>Latest type</strong><br><code>{payload['latest_analysis_type']}</code></div>",
            f"<div class='card'><strong>Latest system</strong><br><code>{payload['latest_system_name']}</code></div>",
            f"<div class='card'><strong>Mean resilience</strong><br><code>{payload['mean_resilience_score']}</code></div>",
            f"<div class='card'><strong>Queued jobs</strong><br><code>{job_payload['status_counts'].get('queued', 0)}</code></div>",
            f"<div class='card'><strong>Running jobs</strong><br><code>{job_payload['status_counts'].get('running', 0)}</code></div>",
            "</div>",
            "<p><a href='/app'>Open the interactive StressLab Control Center</a></p>",
            "<h2>Endpoints</h2>",
            "<ul>",
            "<li><code>/health</code></li>",
            "<li><code>/app</code></li>",
            "<li><code>/registry?limit=20</code></li>",
            "<li><code>/status?limit=25</code></li>",
            "<li><code>/board?recent_limit=20&amp;watch_limit=12&amp;plan_limit=12</code></li>",
            "<li><code>/discovery?limit=12</code></li>",
            "<li><code>/jobs?limit=20</code></li>",
            "<li><code>POST /jobs</code></li>",
            "<li><code>/jobs/&lt;job_id&gt;?expand=1</code></li>",
            "<li><code>/artifacts/&lt;run_id&gt;?expand=1</code></li>",
            "<li><code>/reports/&lt;run_id&gt;</code></li>",
            "<li><code>/bundles/&lt;run_id&gt;?include_registry=1</code></li>",
            "<li><code>/files/&lt;run_id&gt;/&lt;relative_path&gt;</code></li>",
            "</ul>",
            "<h2>Recent Activity</h2>",
            "<table>",
            "<thead><tr><th>run_id</th><th>analysis_type</th><th>system_name</th><th>timestamp</th></tr></thead>",
            f"<tbody>{rows}</tbody>",
            "</table>",
            "</body>",
            "</html>",
        ]
    )


def _jobs_payload(root: Path, *, limit: int) -> dict[str, object]:
    db_path = Path(root) / ".stresslab_jobs.sqlite"
    if not db_path.exists():
        return {
            "root": str(Path(root).resolve()),
            "db_path": str(db_path.resolve()),
            "entry_count": 0,
            "status_counts": {},
            "jobs": [],
        }
    with sqlite3.connect(db_path, timeout=30.0) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT job_id, status, command, created_at, completed_at, run_dir FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        counts_rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status ORDER BY status"
        ).fetchall()
    return {
        "root": str(Path(root).resolve()),
        "db_path": str(db_path.resolve()),
        "entry_count": len(rows),
        "status_counts": {str(row["status"]): int(row["count"]) for row in counts_rows},
        "jobs": [dict(row) for row in rows],
    }
