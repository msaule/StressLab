"""Thin preset-backed demo orchestration for StressLab Frontend V1."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from stresslab.generator import generate_system_spec
from stresslab.systemspec import load_spec, validate_spec
from stresslab.systemspec.schema import SystemSpec
from stresslab.utils import ensure_directory, now_utc, write_yaml

if TYPE_CHECKING:
    from stresslab.service.jobs import WorkspaceJobManager


REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ASSETS_ROOT = REPO_ROOT / "docs" / "assets" / "public"
DEMO_STATE_DIR = ".stresslab_demo"
DEMO_SPECS_DIR = "specs"
DEMO_SESSIONS_DIR = "sessions"

CANONICAL_CLAIM = (
    "Across domains, collapse thresholds are primarily utilization-led; "
    "coupling mainly narrows the failure margin rather than moving the threshold much."
)

CONTROL_SPECS = {
    "utilization": {"label": "Utilization", "min": 0.75, "max": 1.40, "step": 0.05, "default": 1.0},
    "coupling": {"label": "Coupling", "min": 0.80, "max": 1.35, "step": 0.05, "default": 1.0},
    "slack": {"label": "Slack", "min": 0.70, "max": 1.30, "step": 0.05, "default": 1.0},
    "shock_intensity": {
        "label": "Shock intensity",
        "min": 0.80,
        "max": 1.50,
        "step": 0.05,
        "default": 1.0,
    },
}

DEMO_PRESETS: dict[str, dict[str, Any]] = {
    "healthcare_ed": {
        "id": "healthcare_ed",
        "label": "Healthcare ED",
        "domain": "healthcare",
        "description": "Emergency department flow with triage, imaging, and ward bottlenecks.",
        "kind": "spec",
        "spec_path": REPO_ROOT / "examples" / "healthcare" / "ed_basic.yml",
        "optimize_budget": 2500.0,
        "figure": "healthcare_case.png",
        "story": "Best for showing overload, bottlenecks, and concrete intervention impact.",
    },
    "supply_chain_port": {
        "id": "supply_chain_port",
        "label": "Supply Chain Port",
        "domain": "supply_chain",
        "description": "Two suppliers feed a plant through a constrained port and warehouse path.",
        "kind": "spec",
        "spec_path": REPO_ROOT / "examples" / "supply_chain" / "two_supplier_port.yml",
        "optimize_budget": 1700.0,
        "figure": "failure_margin.png",
        "story": "Best for showing how coupling tightens the failure buffer in a logistics network.",
    },
    "market_liquidity": {
        "id": "market_liquidity",
        "label": "Market Liquidity",
        "domain": "markets",
        "description": "Liquidity withdrawal, venue latency, and maker-pool degradation in a market graph.",
        "kind": "spec",
        "spec_path": REPO_ROOT / "examples" / "markets" / "liquidity_withdrawal.yml",
        "optimize_budget": 1600.0,
        "figure": "phase_transition.png",
        "story": "Best for showing how a stressed network can look fine until the shock margin disappears.",
    },
    "synthetic_generic": {
        "id": "synthetic_generic",
        "label": "Synthetic Generic",
        "domain": "synthetic",
        "description": "A deterministic small-world synthetic network used as a generic demo preset.",
        "kind": "generated",
        "topology_type": "small_world",
        "generation_seed": 31,
        "node_count": 8,
        "horizon": 360.0,
        "optimize_budget": 900.0,
        "figure": "main_result.png",
        "story": "Best for showing the core collapse mechanics without domain-specific jargon.",
    },
}


def list_demo_presets() -> dict[str, Any]:
    """Return UI metadata for the demo frontend."""

    presets = []
    for preset in DEMO_PRESETS.values():
        item = dict(preset)
        item["spec_path"] = str(item["spec_path"]) if "spec_path" in item else None
        item["controls"] = CONTROL_SPECS
        item["supporting_figure"] = f"/demo-assets/{item['figure']}"
        presets.append(item)
    return {
        "claim": CANONICAL_CLAIM,
        "headline": "Utilization leads the collapse cliff.",
        "summary": (
            "Use a domain preset, adjust utilization, coupling, slack, and shock intensity, "
            "and StressLab will run a live stress scenario plus intervention ranking."
        ),
        "flagship_stats": {
            "systems": 5000,
            "topology_families": 5,
            "shared_transition_band": "0.10-0.19",
            "coupling_margin_shrink": "39.2%",
        },
        "controls": CONTROL_SPECS,
        "presets": presets,
    }


def prepare_demo_session(
    workspace_root: Path,
    job_manager: WorkspaceJobManager,
    *,
    preset_id: str,
    controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a temp demo spec, submit search plus optimize jobs, and persist the session."""

    if preset_id not in DEMO_PRESETS:
        supported = ", ".join(sorted(DEMO_PRESETS))
        raise ValueError(f"Unknown demo preset '{preset_id}'. Supported presets: {supported}.")
    normalized_controls = _normalize_controls(controls or {})
    preset = DEMO_PRESETS[preset_id]
    session_id = f"demo_{uuid.uuid4().hex[:10]}"
    spec = _build_demo_spec(preset, normalized_controls, session_id=session_id)
    spec_path = _write_demo_spec(workspace_root, session_id=session_id, spec=spec)
    search_job = job_manager.submit_job(
        {
            "command": "search",
            "spec_path": str(spec_path),
            "objective": "min_failure",
        }
    )
    optimize_job = job_manager.submit_job(
        {
            "command": "optimize",
            "spec_path": str(spec_path),
            "budget": float(preset["optimize_budget"]),
        }
    )
    session = {
        "session_id": session_id,
        "created_at": now_utc().isoformat(),
        "preset_id": preset_id,
        "preset_label": preset["label"],
        "controls": normalized_controls,
        "spec_path": str(spec_path),
        "search_job_id": search_job.job_id,
        "optimize_job_id": optimize_job.job_id,
        "claim": CANONICAL_CLAIM,
        "supporting_figure": f"/demo-assets/{preset['figure']}",
    }
    _write_session(workspace_root, session_id=session_id, payload=session)
    return _build_demo_session_payload(workspace_root, job_manager, session)


def get_demo_session(
    workspace_root: Path,
    job_manager: WorkspaceJobManager,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Return the latest state of one demo session."""

    session = _read_session(workspace_root, session_id=session_id)
    return _build_demo_session_payload(workspace_root, job_manager, session)


def demo_asset_path(relative_name: str) -> Path:
    """Resolve one public demo asset from the docs asset bundle."""

    candidate = (PUBLIC_ASSETS_ROOT / relative_name).resolve()
    if not candidate.exists() or candidate.is_dir():
        raise FileNotFoundError(f"Unknown demo asset '{relative_name}'.")
    if PUBLIC_ASSETS_ROOT.resolve() not in candidate.parents and candidate != PUBLIC_ASSETS_ROOT.resolve():
        raise ValueError("Invalid demo asset path.")
    return candidate


def _build_demo_session_payload(
    workspace_root: Path,
    job_manager: WorkspaceJobManager,
    session: dict[str, Any],
) -> dict[str, Any]:
    search_job = job_manager.get_job(str(session["search_job_id"]), expand=False)
    optimize_job = job_manager.get_job(str(session["optimize_job_id"]), expand=False)
    status = _session_status(search_job.status, optimize_job.status)
    payload: dict[str, Any] = {
        "session_id": session["session_id"],
        "created_at": session["created_at"],
        "preset_id": session["preset_id"],
        "preset_label": session["preset_label"],
        "controls": session["controls"],
        "claim": session["claim"],
        "supporting_figure": session["supporting_figure"],
        "status": status,
        "jobs": {
            "search": search_job.model_dump(mode="json"),
            "optimize": optimize_job.model_dump(mode="json"),
        },
    }
    if status == "complete":
        payload["result"] = _build_demo_result(session, search_job.run_dir, optimize_job.run_dir)
    elif status == "failed":
        payload["error"] = search_job.error or optimize_job.error or "One or more demo jobs failed."
    return payload


def _build_demo_result(session: dict[str, Any], search_run_dir: str | None, optimize_run_dir: str | None) -> dict[str, Any]:
    if not search_run_dir or not optimize_run_dir:
        raise FileNotFoundError("Demo session is missing completed search or optimize artifacts.")
    search_dir = Path(search_run_dir)
    optimize_dir = Path(optimize_run_dir)
    search_result = json.loads((search_dir / "search_result.json").read_text(encoding="utf-8"))
    optimization = json.loads((optimize_dir / "optimization.json").read_text(encoding="utf-8"))
    attribution = json.loads((optimize_dir / "attribution.json").read_text(encoding="utf-8"))
    baseline = json.loads((optimize_dir / "baseline_result.json").read_text(encoding="utf-8"))
    metrics = baseline.get("metrics", {})

    best_shock_budget = float(search_result.get("best_shock_budget") or 0.0)
    collapse_risk = _collapse_risk(metrics=metrics, best_shock_budget=best_shock_budget, controls=session["controls"])
    failure_margin = _failure_margin(best_shock_budget)
    selected = optimization.get("selected_interventions") or optimization.get("ranked_interventions") or []
    best_intervention = selected[0] if selected else None
    figure_name = _choose_demo_figure(optimize_dir)
    optimize_run_id = optimize_dir.name
    search_run_id = search_dir.name

    return {
        "system_name": baseline.get("run_id") or session["preset_label"],
        "optimize_run_id": optimize_run_id,
        "search_run_id": search_run_id,
        "collapse_risk": collapse_risk,
        "failure_margin": failure_margin,
        "bottlenecks": attribution.get("dominant_bottlenecks", [])[:3],
        "critical_edges": attribution.get("critical_edges", [])[:3],
        "narrative_summary": attribution.get("narrative_summary"),
        "best_intervention": _summarize_intervention(best_intervention),
        "metrics": {
            "utilization": float(metrics.get("utilization", 0.0)),
            "mean_wait": float(metrics.get("mean_wait", 0.0)),
            "throughput": float(metrics.get("throughput", 0.0)),
            "resilience_score": float(metrics.get("resilience_score", 0.0)),
        },
        "figure": {
            "run_id": optimize_run_id,
            "relative_path": figure_name,
            "caption": _figure_caption(figure_name),
        },
        "reports": {
            "search_report": f"/reports/{search_run_id}",
            "optimize_report": f"/reports/{optimize_run_id}",
        },
        "explanation": _build_result_explanation(
            collapse_risk=collapse_risk,
            failure_margin=failure_margin,
            best_intervention=_summarize_intervention(best_intervention),
            controls=session["controls"],
        ),
    }


def _build_result_explanation(
    *,
    collapse_risk: dict[str, Any],
    failure_margin: dict[str, Any],
    best_intervention: dict[str, Any] | None,
    controls: dict[str, float],
) -> str:
    base = (
        f"The live demo rates this scenario as {collapse_risk['label'].lower()} risk because the preset is running "
        f"at utilization {controls['utilization']:.2f}x with coupling {controls['coupling']:.2f}x, and the minimum "
        f"shock-to-failure margin is {failure_margin['best_shock_budget']:.3f}."
    )
    if best_intervention is None:
        return base + " No intervention was ranked for this particular run."
    return (
        base
        + f" The top recommendation is {best_intervention['label']}, which targets {best_intervention['target']} "
        f"at a cost of {best_intervention['cost']:.0f}."
    )


def _collapse_risk(*, metrics: dict[str, Any], best_shock_budget: float, controls: dict[str, float]) -> dict[str, Any]:
    utilization = float(metrics.get("utilization", 0.0))
    util_score = float(np.clip(utilization, 0.0, 1.0))
    margin_score = float(np.clip(1.0 - min(best_shock_budget, 1.0), 0.0, 1.0))
    coupling_score = float(np.clip((controls["coupling"] - CONTROL_SPECS["coupling"]["min"]) / 0.55, 0.0, 1.0))
    slack_penalty = float(
        np.clip(
            1.0 - (controls["slack"] - CONTROL_SPECS["slack"]["min"]) / 0.60,
            0.0,
            1.0,
        )
    )
    score = 0.40 * util_score + 0.35 * margin_score + 0.15 * coupling_score + 0.10 * slack_penalty
    if score >= 0.75:
        label = "High"
    elif score >= 0.45:
        label = "Moderate"
    else:
        label = "Low"
    return {
        "score": round(float(score), 3),
        "label": label,
        "utilization": round(utilization, 3),
    }


def _failure_margin(best_shock_budget: float) -> dict[str, Any]:
    if best_shock_budget <= 0.25:
        label = "Thin"
    elif best_shock_budget <= 0.70:
        label = "Moderate"
    else:
        label = "Buffered"
    return {
        "best_shock_budget": round(float(best_shock_budget), 3),
        "label": label,
    }


def _summarize_intervention(intervention: dict[str, Any] | None) -> dict[str, Any] | None:
    if not intervention:
        return None
    return {
        "id": intervention.get("intervention_id"),
        "label": intervention.get("label") or intervention.get("intervention_id") or "Unknown intervention",
        "target": intervention.get("target") or "system",
        "cost": float(intervention.get("cost") or 0.0),
        "resilience_gain": float(intervention.get("resilience_gain") or 0.0),
        "failure_prevention_rate": float(intervention.get("failure_prevention_rate") or 0.0),
    }


def _choose_demo_figure(run_dir: Path) -> str:
    for name in ["queue_lengths.png", "utilization.png", "intervention_roi.png", "system_graph.png"]:
        if (run_dir / name).exists():
            return name
    matches = [path.name for path in run_dir.glob("*.png")]
    if matches:
        return sorted(matches)[0]
    raise FileNotFoundError(f"No demo figure found under '{run_dir}'.")


def _figure_caption(name: str) -> str:
    captions = {
        "queue_lengths.png": "Queue response under the current preset and control settings.",
        "utilization.png": "Utilization trace for the live preset run.",
        "intervention_roi.png": "Intervention return-on-resilience for the current preset.",
        "system_graph.png": "System graph for the current preset.",
    }
    return captions.get(name, "Live figure from the current preset run.")


def _session_status(search_status: str, optimize_status: str) -> str:
    if "failed" in {search_status, optimize_status}:
        return "failed"
    if search_status == "succeeded" and optimize_status == "succeeded":
        return "complete"
    return "running"


def _build_demo_spec(preset: dict[str, Any], controls: dict[str, float], *, session_id: str) -> SystemSpec:
    if preset["kind"] == "spec":
        base_spec = load_spec(Path(preset["spec_path"]))
    else:
        node_count = int(preset["node_count"])
        base_spec = generate_system_spec(
            topology_type=str(preset["topology_type"]),
            index=0,
            base_seed=int(preset["generation_seed"]),
            min_nodes=node_count,
            max_nodes=node_count,
            horizon=float(preset["horizon"]),
            system_prefix="demo_generic",
        )
    data = base_spec.model_dump(mode="json", by_alias=True)
    data["system"]["name"] = f"{preset['id']}_{session_id}"
    data["system"]["description"] = (
        f"{preset['description']} Demo controls: utilization={controls['utilization']:.2f}, "
        f"coupling={controls['coupling']:.2f}, slack={controls['slack']:.2f}, "
        f"shock_intensity={controls['shock_intensity']:.2f}."
    )
    _scale_arrivals(data.get("arrivals", []), factor=controls["utilization"])
    _scale_slack(data.get("nodes", []), factor=controls["slack"])
    _scale_coupling(data.get("edges", []), factor=controls["coupling"])
    _scale_shocks(data.get("shocks", []), intensity=controls["shock_intensity"])
    spec = SystemSpec.model_validate(data)
    validation = validate_spec(spec)
    if not validation.valid:
        raise ValueError(f"Generated demo spec is invalid: {'; '.join(validation.errors)}")
    return spec


def _scale_arrivals(arrivals: list[dict[str, Any]], *, factor: float) -> None:
    for arrival in arrivals:
        process = arrival.get("process", {})
        if process.get("base_rate") is not None:
            process["base_rate"] = round(float(process["base_rate"]) * factor, 6)
        if process.get("rate") is not None:
            process["rate"] = round(float(process["rate"]) * factor, 6)


def _scale_slack(nodes: list[dict[str, Any]], *, factor: float) -> None:
    for node in nodes:
        if node.get("buffer_capacity") is not None:
            node["buffer_capacity"] = max(4, int(round(float(node["buffer_capacity"]) * factor)))


def _scale_coupling(edges: list[dict[str, Any]], *, factor: float) -> None:
    by_source: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        by_source.setdefault(str(edge.get("from")), []).append(edge)
        if edge.get("transfer_capacity") is not None:
            edge["transfer_capacity"] = round(max(0.01, float(edge["transfer_capacity"]) / factor), 6)
        if edge.get("travel_time") is not None:
            edge["travel_time"] = round(float(edge["travel_time"]) * (1.0 + max(0.0, factor - 1.0) * 0.25), 6)
    for group in by_source.values():
        if len(group) < 2:
            continue
        probabilities = np.array([float(edge.get("routing", {}).get("probability", 0.0)) for edge in group], dtype=float)
        total = float(probabilities.sum())
        if total <= 0:
            continue
        normalized = probabilities / total
        adjusted = np.power(normalized, factor)
        adjusted_total = float(adjusted.sum())
        if adjusted_total <= 0:
            continue
        target_total = min(total, 1.0)
        adjusted = (adjusted / adjusted_total) * target_total
        rounded = [round(float(probability), 6) for probability in adjusted]
        if rounded:
            rounded[-1] = round(max(0.0, target_total - sum(rounded[:-1])), 6)
        for edge, probability in zip(group, rounded, strict=True):
            edge.setdefault("routing", {})["probability"] = probability


def _scale_shocks(shocks: list[dict[str, Any]], *, intensity: float) -> None:
    for shock in shocks:
        _scale_one_shock(shock, intensity=intensity)


def _scale_one_shock(shock: dict[str, Any], *, intensity: float) -> None:
    if shock.get("factor") is not None:
        base = float(shock["factor"])
        shock["factor"] = round(1.0 + (base - 1.0) * intensity, 6)
    if shock.get("fraction") is not None:
        shock["fraction"] = round(float(np.clip(float(shock["fraction"]) * intensity, 0.0, 1.0)), 6)
    for component in shock.get("components", []):
        _scale_one_shock(component, intensity=intensity)


def _normalize_controls(controls: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, spec in CONTROL_SPECS.items():
        raw = controls.get(key, spec["default"])
        value = float(raw)
        normalized[key] = float(np.clip(value, float(spec["min"]), float(spec["max"])))
    return normalized


def _demo_dirs(workspace_root: Path) -> tuple[Path, Path]:
    root = ensure_directory(Path(workspace_root) / DEMO_STATE_DIR)
    specs_dir = ensure_directory(root / DEMO_SPECS_DIR)
    sessions_dir = ensure_directory(root / DEMO_SESSIONS_DIR)
    return specs_dir, sessions_dir


def _write_demo_spec(workspace_root: Path, *, session_id: str, spec: SystemSpec) -> Path:
    specs_dir, _ = _demo_dirs(workspace_root)
    spec_path = specs_dir / f"{session_id}.yml"
    write_yaml(spec_path, spec.model_dump(mode="json", by_alias=True))
    return spec_path


def _write_session(workspace_root: Path, *, session_id: str, payload: dict[str, Any]) -> Path:
    _, sessions_dir = _demo_dirs(workspace_root)
    path = sessions_dir / f"{session_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _read_session(workspace_root: Path, *, session_id: str) -> dict[str, Any]:
    _, sessions_dir = _demo_dirs(workspace_root)
    path = sessions_dir / f"{session_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown demo session '{session_id}'.")
    return json.loads(path.read_text(encoding="utf-8"))
