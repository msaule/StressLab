from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from stresslab.explain import attribute_failure
from stresslab.optimize import Optimizer
from stresslab.search import Searcher
from stresslab.service.demo import (
    CANONICAL_CLAIM,
    CONTROL_SPECS,
    DEMO_PRESETS,
    _build_demo_spec,
    _figure_caption,
    _normalize_controls,
    _summarize_intervention,
)
from stresslab.systemspec import resolve_spec
from stresslab.utils import ensure_directory, write_json
from stresslab.viz.plots import create_standard_plots

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
DOCS_ASSET_ROOT = DOCS_ROOT / "assets" / "static_demo"
FINAL_SITE_ROOT = REPO_ROOT / "final_public_package" / "site"
FINAL_SITE_ASSET_ROOT = FINAL_SITE_ROOT / "assets" / "static_demo"


@dataclass(frozen=True)
class ScenarioTemplate:
    id: str
    title: str
    description: str
    controls: dict[str, float]


SCENARIO_TEMPLATES: tuple[ScenarioTemplate, ...] = (
    ScenarioTemplate(
        id="buffered_safe",
        title="Buffered safe zone",
        description="Low utilization, lower shock intensity, and extra slack keep the system far from the cliff.",
        controls={"utilization": 0.85, "coupling": 0.90, "slack": 1.15, "shock_intensity": 0.90},
    ),
    ScenarioTemplate(
        id="steady_state",
        title="Steady operating point",
        description="A balanced operating point close to the study baseline.",
        controls={"utilization": 0.95, "coupling": 1.00, "slack": 1.05, "shock_intensity": 0.95},
    ),
    ScenarioTemplate(
        id="baseline",
        title="Baseline",
        description="Reference conditions for the preset with no extra operational pressure.",
        controls={"utilization": 1.00, "coupling": 1.00, "slack": 1.00, "shock_intensity": 1.00},
    ),
    ScenarioTemplate(
        id="utilization_push",
        title="Utilization push",
        description="Higher arrivals push the preset toward the shared transition band.",
        controls={"utilization": 1.10, "coupling": 1.00, "slack": 1.00, "shock_intensity": 1.00},
    ),
    ScenarioTemplate(
        id="transition_band",
        title="Transition band",
        description="A utilization-led regime where collapse risk starts to accelerate.",
        controls={"utilization": 1.15, "coupling": 1.00, "slack": 0.95, "shock_intensity": 1.05},
    ),
    ScenarioTemplate(
        id="coupling_push",
        title="Coupling push",
        description="Same basic load, but tighter coupling concentrates flow and narrows shock margin.",
        controls={"utilization": 1.00, "coupling": 1.15, "slack": 1.00, "shock_intensity": 1.00},
    ),
    ScenarioTemplate(
        id="slack_drop",
        title="Slack erosion",
        description="Buffers shrink while other pressures remain near baseline.",
        controls={"utilization": 1.00, "coupling": 1.00, "slack": 0.85, "shock_intensity": 1.00},
    ),
    ScenarioTemplate(
        id="shock_push",
        title="Shock push",
        description="A stronger shock probes how much failure margin the preset still retains.",
        controls={"utilization": 1.00, "coupling": 1.00, "slack": 1.00, "shock_intensity": 1.15},
    ),
    ScenarioTemplate(
        id="coupled_transition",
        title="Coupled transition",
        description="Higher utilization plus tighter coupling make the transition sharper.",
        controls={"utilization": 1.15, "coupling": 1.15, "slack": 1.00, "shock_intensity": 1.05},
    ),
    ScenarioTemplate(
        id="slack_crunch",
        title="Slack crunch",
        description="Higher utilization and lower slack squeeze the system into a thinner safe band.",
        controls={"utilization": 1.15, "coupling": 1.00, "slack": 0.85, "shock_intensity": 1.05},
    ),
    ScenarioTemplate(
        id="network_lock",
        title="Network lock",
        description="Coupling and slack deterioration combine to create a brittle operating point.",
        controls={"utilization": 1.10, "coupling": 1.10, "slack": 0.90, "shock_intensity": 1.15},
    ),
    ScenarioTemplate(
        id="collapse_combo",
        title="Collapse combo",
        description="High utilization, high coupling, low slack, and elevated shock intensity push the preset past the cliff.",
        controls={"utilization": 1.25, "coupling": 1.15, "slack": 0.80, "shock_intensity": 1.20},
    ),
)


def _selected_or_top(optimization_result):
    if optimization_result.selected_interventions:
        return optimization_result.selected_interventions[0]
    if optimization_result.ranked_interventions:
        return optimization_result.ranked_interventions[0]
    return None


def _figure_path_for(result_figure: str) -> str:
    return f"assets/static_demo/figures/{result_figure}"


def _normalized_control(key: str, value: float) -> float:
    spec = CONTROL_SPECS[key]
    span = float(spec["max"]) - float(spec["min"])
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, (float(value) - float(spec["min"])) / span))


def _static_collapse_risk(
    *,
    controls: dict[str, float],
    scenario_metrics: dict[str, float],
    raw_search_budget: float,
    baseline_failure: bool,
    scenario_failure: bool,
) -> dict[str, object]:
    util = _normalized_control("utilization", controls["utilization"])
    coupling = _normalized_control("coupling", controls["coupling"])
    slack_penalty = 1.0 - _normalized_control("slack", controls["slack"])
    shock = _normalized_control("shock_intensity", controls["shock_intensity"])
    resilience_penalty = max(0.0, min(1.0, 1.0 - float(scenario_metrics.get("resilience_score", 0.0)) / 0.5))
    raw_margin_penalty = max(0.0, min(1.0, 1.0 - min(raw_search_budget, 1.0)))
    score = (
        0.38 * util
        + 0.18 * coupling
        + 0.14 * slack_penalty
        + 0.16 * shock
        + 0.09 * resilience_penalty
        + 0.05 * raw_margin_penalty
        + (0.08 if baseline_failure or scenario_failure else 0.0)
    )
    score = max(0.0, min(1.0, score))
    if score >= 0.66:
        label = "High"
    elif score >= 0.40:
        label = "Moderate"
    else:
        label = "Low"
    return {
        "score": round(score, 3),
        "label": label,
        "utilization": round(float(scenario_metrics.get("utilization", 0.0)), 3),
        "basis": "Static Pages estimate backed by the nearest precomputed StressLab scenario.",
    }


def _static_failure_margin(
    *,
    controls: dict[str, float],
    raw_search_budget: float,
) -> dict[str, object]:
    util = _normalized_control("utilization", controls["utilization"])
    coupling = _normalized_control("coupling", controls["coupling"])
    slack_penalty = 1.0 - _normalized_control("slack", controls["slack"])
    shock = _normalized_control("shock_intensity", controls["shock_intensity"])
    control_margin = 1.0 - (0.50 * util + 0.20 * coupling + 0.15 * shock + 0.15 * slack_penalty)
    display_margin = max(0.0, min(1.0, 0.65 * control_margin + 0.35 * min(raw_search_budget, 1.0)))
    if display_margin >= 0.55:
        label = "Buffered"
    elif display_margin >= 0.30:
        label = "Moderate"
    else:
        label = "Thin"
    return {
        "best_shock_budget": round(display_margin, 3),
        "label": label,
        "raw_search_budget": round(float(raw_search_budget), 3),
        "basis": "Research-backed display margin derived from controls and nearest-scenario search output.",
    }


def _static_result_explanation(
    *,
    controls: dict[str, float],
    collapse_risk: dict[str, object],
    failure_margin: dict[str, object],
    best_intervention: dict[str, object] | None,
) -> str:
    base = (
        f"This Pages demo snaps to a precomputed scenario at utilization {controls['utilization']:.2f}x, "
        f"coupling {controls['coupling']:.2f}x, slack {controls['slack']:.2f}x, and shock intensity "
        f"{controls['shock_intensity']:.2f}x. That places the preset in a "
        f"{str(collapse_risk['label']).lower()}-risk regime with an estimated failure margin of "
        f"{float(failure_margin['best_shock_budget']):.3f}."
    )
    if best_intervention is None:
        return base + " No intervention ranked strongly enough to call out in this precomputed slice."
    return (
        base
        + f" The strongest intervention signal is {best_intervention['label']}, focused on "
        f"{best_intervention['target']} with an estimated resilience gain of "
        f"{best_intervention['resilience_gain']:.3f}."
    )


def _run_one_scenario(
    *,
    preset_id: str,
    template: ScenarioTemplate,
    figure_dir: Path,
) -> dict[str, object]:
    preset = DEMO_PRESETS[preset_id]
    controls = _normalize_controls(template.controls)
    session_id = f"static_{preset_id}_{template.id}"
    spec = _build_demo_spec(preset, controls, session_id=session_id)
    searcher = Searcher(spec, objective="min_failure", seed=spec.seed)
    search_result = searcher.find_min_failure()
    scenario_spec, search_simulator, _ = searcher.replay_best(search_result)
    scenario_result = search_simulator.run(run_id="scenario", capture_events=True)
    attribution = attribute_failure(scenario_result)
    optimizer = Optimizer(spec, searcher.baseline_result)
    optimization_result = optimizer.rank_interventions(budget=float(preset["optimize_budget"]))
    best_intervention = _selected_or_top(optimization_result)
    collapse_risk = _static_collapse_risk(
        controls=controls,
        scenario_metrics=scenario_result.metrics,
        raw_search_budget=search_result.best_shock_budget,
        baseline_failure=searcher.baseline_result.failure_triggered,
        scenario_failure=scenario_result.failure_triggered,
    )
    failure_margin = _static_failure_margin(
        controls=controls,
        raw_search_budget=search_result.best_shock_budget,
    )

    with TemporaryDirectory(prefix="stresslab_static_demo_") as temp_root:
        temp_dir = Path(temp_root)
        plots = create_standard_plots(
            resolved_spec=resolve_spec(scenario_spec),
            simulator=search_simulator,
            result=scenario_result,
            output_dir=temp_dir,
            search_history=searcher.history,
            optimization_result=optimization_result,
            top_n=3,
        )
        preferred_plot = next(
            (
                plots[key]
                for key in ("queue_lengths", "utilization", "intervention_roi", "system_graph", "fragility_curve")
                if key in plots
            ),
            None,
        )
        if preferred_plot is None:
            raise FileNotFoundError(f"No demo figure generated for {preset_id}:{template.id}.")
        figure_name = f"{preset_id}__{template.id}.png"
        target_figure = figure_dir / figure_name
        shutil.copy2(preferred_plot, target_figure)
        figure_caption = _figure_caption(Path(preferred_plot).name)

    summarized_intervention = _summarize_intervention(best_intervention.model_dump(mode="json") if best_intervention else None)
    explanation = _static_result_explanation(
        collapse_risk=collapse_risk,
        failure_margin=failure_margin,
        best_intervention=summarized_intervention,
        controls=controls,
    )
    result_payload: dict[str, object] = {
        "collapse_risk": collapse_risk,
        "failure_margin": failure_margin,
        "metrics": {
            "utilization": round(float(searcher.baseline_result.metrics.get("utilization", 0.0)), 3),
            "mean_wait": round(float(scenario_result.metrics.get("mean_wait", 0.0)), 3),
            "throughput": round(float(scenario_result.metrics.get("throughput", 0.0)), 3),
            "resilience_score": round(float(scenario_result.metrics.get("resilience_score", 0.0)), 3),
        },
        "bottlenecks": attribution.dominant_bottlenecks[:3],
        "critical_edges": attribution.critical_edges[:3],
        "narrative_summary": attribution.narrative_summary,
        "best_intervention": summarized_intervention,
        "figure": {
            "path": _figure_path_for(figure_name),
            "caption": figure_caption,
        },
        "explanation": explanation,
        "baseline_failure": bool(searcher.baseline_result.failure_triggered),
        "scenario_failure": bool(scenario_result.failure_triggered),
        "best_shock_vector": search_result.best_shock_vector,
        "damage_score": round(float(search_result.damage_score), 3),
    }
    return {
        "id": template.id,
        "title": template.title,
        "description": template.description,
        "controls": controls,
        "result": result_payload,
    }


def build_static_demo_package(output_root: Path) -> Path:
    output_root = ensure_directory(output_root)
    figure_dir = ensure_directory(output_root / "figures")
    library: dict[str, object] = {
        "mode": "static_precomputed",
        "claim": CANONICAL_CLAIM,
        "summary": (
            "This GitHub Pages demo uses a curated library of precomputed StressLab runs. "
            "Slider settings snap to the nearest real scenario so the experience stays free, fast, and honest."
        ),
        "flagship_stats": {
            "systems": 5000,
            "topology_families": 5,
            "shared_transition_band": "0.10-0.19",
            "coupling_margin_shrink": "39.2%",
        },
        "controls": CONTROL_SPECS,
        "presets": [],
    }
    for preset_id in ("healthcare_ed", "supply_chain_port", "market_liquidity", "synthetic_generic"):
        preset = DEMO_PRESETS[preset_id]
        preset_payload = {
            "id": preset["id"],
            "label": preset["label"],
            "domain": preset["domain"],
            "description": preset["description"],
            "story": preset["story"],
            "demo_mode": "nearest precomputed scenario",
            "default_controls": {
                key: float(CONTROL_SPECS[key]["default"])
                for key in CONTROL_SPECS
            },
            "scenarios": [],
        }
        for template in SCENARIO_TEMPLATES:
            preset_payload["scenarios"].append(
                _run_one_scenario(
                    preset_id=preset_id,
                    template=template,
                    figure_dir=figure_dir,
                )
            )
        library["presets"].append(preset_payload)
    write_json(output_root / "scenario_library.json", library)
    return output_root / "scenario_library.json"


def main() -> None:
    docs_json = build_static_demo_package(DOCS_ASSET_ROOT)
    if FINAL_SITE_ROOT.exists():
        if FINAL_SITE_ASSET_ROOT.exists():
            shutil.rmtree(FINAL_SITE_ASSET_ROOT)
        ensure_directory(FINAL_SITE_ASSET_ROOT.parent)
        shutil.copytree(DOCS_ASSET_ROOT, FINAL_SITE_ASSET_ROOT)
    print(f"Static demo library written to {docs_json}")


if __name__ == "__main__":
    main()
