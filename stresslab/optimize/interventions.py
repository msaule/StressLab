"""Intervention application and ranking."""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np

from stresslab.des import Simulator
from stresslab.models import (
    ClosedLoopRegimeScenarioResult,
    ClosedLoopRegimeSummary,
    ControllerPolicyCandidate,
    ControllerTuningSummary,
    InterventionCoverageSummary,
    OnlineRegimeDetectionSummary,
    OnlineRegimeHorizonSummary,
    OnlineRegimeScenarioResult,
    OptimizationResult,
    PortfolioCandidate,
    PortfolioClusterCoverageSummary,
    RankedIntervention,
    RegimeDetectionScenarioResult,
    RegimeDetectionSummary,
    RegimePlanSummary,
    ResponseTimingPoint,
    ResponseTimingSummary,
    ScenarioClusterAssignment,
    ScenarioClusterSummary,
    ScenarioSummary,
)
from stresslab.optimize.controller_frontier import controller_pareto_frontier
from stresslab.optimize.controller_tuning import tune_closed_loop_controller
from stresslab.optimize.online_regime_detection import evaluate_online_regime_detection
from stresslab.optimize.pareto import pareto_frontier
from stresslab.optimize.portfolio_analysis import cluster_scenarios, summarize_intervention_coverage
from stresslab.optimize.portfolio_search import select_robust_portfolio
from stresslab.optimize.regime_detection import evaluate_regime_detection
from stresslab.optimize.regime_planning import build_regime_response_plan
from stresslab.optimize.response_timing import evaluate_response_timing
from stresslab.optimize.robust import (
    build_scenario_portfolio,
    evaluate_intervention_portfolio,
    robust_objective,
)
from stresslab.systemspec.parser import resolve_spec
from stresslab.systemspec.schema import (
    InterventionSpec,
    PolicyScheduleSpec,
    ResolvedSystemSpec,
    SystemSpec,
)


class Optimizer:
    """Evaluate and rank interventions."""

    def __init__(self, spec, baseline_result) -> None:
        if isinstance(spec, ResolvedSystemSpec):
            self.spec = spec.spec
        elif isinstance(spec, SystemSpec):
            self.spec = spec
        else:
            raise TypeError("Optimizer expects a SystemSpec or ResolvedSystemSpec.")
        self.baseline_result = baseline_result
        self.seed = self.spec.seed
        self.last_scenario_summaries: list[ScenarioSummary] = []
        self.last_intervention_summaries: dict[str, list[ScenarioSummary]] = {}
        self.last_scenario_clusters: list[ScenarioClusterAssignment] = []
        self.last_cluster_summaries: list[ScenarioClusterSummary] = []
        self.last_intervention_coverage: list[InterventionCoverageSummary] = []
        self.last_portfolio_candidates: list[PortfolioCandidate] = []
        self.last_portfolio_cluster_coverage: list[PortfolioClusterCoverageSummary] = []
        self.last_cluster_response_plan = []
        self.last_regime_plan_summary: RegimePlanSummary | None = None
        self.last_regime_detection_rows: list[RegimeDetectionScenarioResult] = []
        self.last_regime_detection_confusion: list[dict[str, object]] = []
        self.last_regime_detection_summary: RegimeDetectionSummary | None = None
        self.last_online_regime_rows: list[OnlineRegimeScenarioResult] = []
        self.last_online_regime_horizons: list[OnlineRegimeHorizonSummary] = []
        self.last_online_regime_summary: OnlineRegimeDetectionSummary | None = None
        self.last_response_timing_points: list[ResponseTimingPoint] = []
        self.last_response_timing_summary: ResponseTimingSummary | None = None
        self.last_closed_loop_regime_rows: list[ClosedLoopRegimeScenarioResult] = []
        self.last_closed_loop_regime_summary: ClosedLoopRegimeSummary | None = None
        self.last_controller_policy_candidates: list[ControllerPolicyCandidate] = []
        self.last_controller_frontier: list[ControllerPolicyCandidate] = []
        self.last_controller_tuning_summary: ControllerTuningSummary | None = None
        self.last_portfolio_method: str | None = None

    def _candidate_interventions(self) -> list[InterventionSpec]:
        return [
            intervention
            for intervention in self.spec.interventions
            if not (intervention.applicability_constraints or {}).get("shadow_reference", False)
        ]

    def _ranked_metadata(self, intervention: InterventionSpec) -> dict[str, object]:
        constraints = intervention.applicability_constraints or {}
        lookup = {candidate.id: candidate for candidate in self.spec.interventions}
        return {
            "label": intervention.label,
            "action_type": intervention.action_type,
            "target": intervention.target,
            "source": str(constraints.get("source", "authored")),
            "generated": bool(constraints.get("generated", False)),
            "dynamic": bool(constraints.get("dynamic", False)),
            "policy_mode": intervention.policy_mode,
            "schedule_start": intervention.start,
            "schedule_duration": intervention.duration,
            "stage_count": len(intervention.stages),
            "bundle_size": len(intervention.bundle_members),
            "bundle_depth": self._bundle_depth(intervention, lookup),
            "trigger_metric": intervention.trigger_metric,
            "trigger_node": self._trigger_node(intervention, lookup),
            "trigger_threshold": intervention.trigger_threshold,
            "clear_threshold": intervention.clear_threshold,
        }

    def rank_interventions(
        self,
        budget: float | None = None,
        *,
        fairness_weight: float = 0.0,
    ) -> OptimizationResult:
        """Rank independent interventions and optionally select a greedy portfolio."""

        self.last_scenario_summaries = []
        self.last_intervention_summaries = {}
        self.last_scenario_clusters = []
        self.last_cluster_summaries = []
        self.last_intervention_coverage = []
        self.last_portfolio_candidates = []
        self.last_portfolio_cluster_coverage = []
        self.last_cluster_response_plan = []
        self.last_regime_plan_summary = None
        self.last_regime_detection_rows = []
        self.last_regime_detection_confusion = []
        self.last_regime_detection_summary = None
        self.last_online_regime_rows = []
        self.last_online_regime_horizons = []
        self.last_online_regime_summary = None
        self.last_response_timing_points = []
        self.last_response_timing_summary = None
        self.last_closed_loop_regime_rows = []
        self.last_closed_loop_regime_summary = None
        self.last_controller_policy_candidates = []
        self.last_controller_frontier = []
        self.last_controller_tuning_summary = None
        self.last_portfolio_method = None
        baseline_resilience = self.baseline_result.metrics.get("resilience_score", 0.0)
        baseline_fairness = self.baseline_result.metrics.get("fairness_score", 0.0)
        candidates = self._candidate_interventions()
        ranked: list[RankedIntervention] = []
        for intervention in candidates:
            result = self._evaluate([intervention])
            resilience = result.metrics.get("resilience_score", 0.0)
            fairness_score = result.metrics.get("fairness_score", baseline_fairness)
            gain = resilience - baseline_resilience
            objective_gain = gain + fairness_weight * (fairness_score - baseline_fairness)
            cost = max(intervention.cost, 1e-9)
            ranked.append(
                RankedIntervention(
                    intervention_id=intervention.id,
                    **self._ranked_metadata(intervention),
                    cost=intervention.cost,
                    resilience_gain=gain,
                    roi=gain / cost,
                    failure_prevented=self.baseline_result.failure_triggered and not result.failure_triggered,
                    fairness_gain=fairness_score - baseline_fairness,
                    expected_fairness_score=fairness_score,
                    worst_case_fairness_score=fairness_score,
                    metrics={**result.metrics, "objective_gain": objective_gain},
                )
            )
        ranked.sort(
            key=lambda item: (
                item.metrics.get("objective_gain", item.resilience_gain),
                item.roi,
                item.fairness_gain or 0.0,
            ),
            reverse=True,
        )
        selected = self._greedy_select(budget, fairness_weight=fairness_weight) if budget is not None else []
        best_resilience = max(
            [baseline_resilience] + [entry.metrics.get("resilience_score", baseline_resilience) for entry in ranked]
        )
        if selected:
            best_resilience = max(best_resilience, selected[-1].metrics.get("resilience_score", best_resilience))
        frontier = pareto_frontier(ranked, robust_mode=False)
        return OptimizationResult(
            budget=budget,
            ranked_interventions=ranked,
            selected_interventions=selected,
            baseline_resilience=baseline_resilience,
            best_resilience=best_resilience,
            robust_mode=False,
            scenario_count=1,
            cluster_count=0,
            candidate_count=len(candidates),
            generated_policy_count=sum(
                1
                for intervention in candidates
                if (intervention.applicability_constraints or {}).get("generated", False)
            ),
            dynamic_policy_count=sum(
                1
                for intervention in candidates
                if (intervention.applicability_constraints or {}).get("dynamic", False)
            ),
            adaptive_policy_count=sum(
                1
                for intervention in candidates
                if (intervention.applicability_constraints or {}).get("adaptive", False)
            ),
            bundle_candidate_count=sum(
                1
                for intervention in candidates
                if intervention.action_type == "bundle"
            ),
            hierarchical_playbook_count=sum(
                1
                for intervention in candidates
                if (intervention.applicability_constraints or {}).get("hierarchical_bundle", False)
            ),
            fairness_weight=fairness_weight,
            pareto_intervention_ids=[item.intervention_id for item in frontier],
            roi_table_path=None,
        )

    def rank_interventions_robust(
        self,
        budget: float | None = None,
        *,
        scenario_budget: float | None = None,
        random_samples: int = 4,
        fairness_weight: float = 0.0,
    ) -> OptimizationResult:
        """Rank interventions across a portfolio of stress scenarios."""

        scenario_summaries = build_scenario_portfolio(
            self.spec,
            seed=self.seed,
            scenario_budget=scenario_budget,
            random_samples=random_samples,
        )
        self.last_scenario_summaries = scenario_summaries
        self.last_intervention_summaries = {}
        self.last_portfolio_candidates = []
        self.last_portfolio_cluster_coverage = []
        self.last_cluster_response_plan = []
        self.last_regime_plan_summary = None
        self.last_regime_detection_rows = []
        self.last_regime_detection_confusion = []
        self.last_regime_detection_summary = None
        self.last_online_regime_rows = []
        self.last_online_regime_horizons = []
        self.last_online_regime_summary = None
        self.last_response_timing_points = []
        self.last_response_timing_summary = None
        self.last_closed_loop_regime_rows = []
        self.last_closed_loop_regime_summary = None
        self.last_controller_policy_candidates = []
        self.last_controller_frontier = []
        self.last_controller_tuning_summary = None
        self.last_portfolio_method = None
        baseline_resilience = float(
            np.mean([scenario.metrics.get("resilience_score", 0.0) for scenario in scenario_summaries])
        )
        baseline_fairness = float(
            np.mean([scenario.metrics.get("fairness_score", 0.0) for scenario in scenario_summaries])
        )
        candidates = self._candidate_interventions()
        ranked: list[RankedIntervention] = []
        for intervention in candidates:
            evaluated = evaluate_intervention_portfolio(
                self.spec,
                [intervention],
                scenario_summaries,
                seed=self.seed,
            )
            self.last_intervention_summaries[intervention.id] = evaluated
            ranked.append(
                self._ranked_intervention_from_scenarios(
                    intervention,
                    evaluated,
                    untreated=scenario_summaries,
                    baseline_resilience=baseline_resilience,
                    baseline_fairness=baseline_fairness,
                    fairness_weight=fairness_weight,
                )
            )
        ranked.sort(
            key=lambda item: (
                item.robust_score if item.robust_score is not None else float("-inf"),
                item.roi,
                item.worst_case_resilience if item.worst_case_resilience is not None else float("-inf"),
            ),
            reverse=True,
        )
        best_resilience = max(
            [baseline_resilience]
            + [entry.expected_resilience or baseline_resilience for entry in ranked]
        )
        frontier = pareto_frontier(ranked, robust_mode=True)
        shock_defaults = {
            dimension.id: float(dimension.min)
            for dimension in self.spec.search.search_space
        }
        self.last_scenario_clusters, self.last_cluster_summaries = cluster_scenarios(
            scenario_summaries,
            shock_defaults=shock_defaults,
        )
        self.last_intervention_coverage = summarize_intervention_coverage(
            untreated=scenario_summaries,
            treated_by_intervention=self.last_intervention_summaries,
            scenario_clusters=self.last_scenario_clusters,
        )
        self.last_regime_plan_summary, self.last_cluster_response_plan = build_regime_response_plan(
            untreated=scenario_summaries,
            treated_by_intervention=self.last_intervention_summaries,
            intervention_coverage=self.last_intervention_coverage,
            scenario_clusters=self.last_scenario_clusters,
            ranked_interventions=ranked,
            budget=budget,
            fairness_weight=fairness_weight,
        )
        if self.last_regime_plan_summary is not None and self.last_cluster_response_plan:
            (
                self.last_regime_detection_summary,
                self.last_regime_detection_rows,
                self.last_regime_detection_confusion,
            ) = evaluate_regime_detection(
                untreated=scenario_summaries,
                scenario_clusters=self.last_scenario_clusters,
                cluster_response_plan=self.last_cluster_response_plan,
                treated_by_intervention=self.last_intervention_summaries,
                regime_plan_summary=self.last_regime_plan_summary,
                seed=self.seed,
            )
            (
                self.last_online_regime_summary,
                self.last_online_regime_rows,
                self.last_online_regime_horizons,
            ) = evaluate_online_regime_detection(
                spec=self.spec,
                untreated=scenario_summaries,
                scenario_clusters=self.last_scenario_clusters,
                cluster_response_plan=self.last_cluster_response_plan,
                treated_by_intervention=self.last_intervention_summaries,
                regime_plan_summary=self.last_regime_plan_summary,
                seed=self.seed,
            )
            (
                self.last_response_timing_summary,
                self.last_response_timing_points,
            ) = evaluate_response_timing(
                spec=self.spec,
                untreated=scenario_summaries,
                scenario_clusters=self.last_scenario_clusters,
                cluster_response_plan=self.last_cluster_response_plan,
                seed=self.seed,
            )
            (
                self.last_controller_tuning_summary,
                self.last_controller_policy_candidates,
                self.last_closed_loop_regime_summary,
                self.last_closed_loop_regime_rows,
            ) = tune_closed_loop_controller(
                spec=self.spec,
                untreated=scenario_summaries,
                scenario_clusters=self.last_scenario_clusters,
                cluster_response_plan=self.last_cluster_response_plan,
                regime_plan_summary=self.last_regime_plan_summary,
                seed=self.seed,
                fairness_weight=fairness_weight,
            )
            self.last_controller_frontier = controller_pareto_frontier(
                self.last_controller_policy_candidates,
                fairness_weight=fairness_weight,
            )
            if self.last_controller_tuning_summary is not None:
                self.last_controller_tuning_summary = self.last_controller_tuning_summary.model_copy(
                    update={"frontier_candidate_count": len(self.last_controller_frontier)}
                )
        portfolio_candidates: list[PortfolioCandidate] = []
        portfolio_coverage: list[PortfolioClusterCoverageSummary] = []
        portfolio_method = None
        selected: list[RankedIntervention] = []
        recommended_portfolio_id = None
        portfolio_objective_score = None
        portfolio_cluster_coverage_rate = None
        if budget is not None:
            portfolio_candidates, portfolio_coverage, portfolio_method = select_robust_portfolio(
                self.spec,
                budget=budget,
                untreated=scenario_summaries,
                scenario_clusters=self.last_scenario_clusters,
                baseline_resilience=baseline_resilience,
                baseline_fairness=baseline_fairness,
                seed=self.seed,
                fairness_weight=fairness_weight,
            )
            self.last_portfolio_candidates = portfolio_candidates
            self.last_portfolio_cluster_coverage = portfolio_coverage
            self.last_portfolio_method = portfolio_method
            if portfolio_candidates:
                chosen = portfolio_candidates[0]
                ranked_lookup = {entry.intervention_id: entry for entry in ranked}
                selected = [
                    ranked_lookup[intervention_id]
                    for intervention_id in chosen.intervention_ids
                    if intervention_id in ranked_lookup
                ]
                recommended_portfolio_id = chosen.portfolio_id
                portfolio_objective_score = chosen.objective_score
                portfolio_cluster_coverage_rate = chosen.cluster_coverage_rate
                best_resilience = max(best_resilience, chosen.expected_resilience or best_resilience)
        else:
            self.last_portfolio_candidates = []
            self.last_portfolio_cluster_coverage = []
            self.last_portfolio_method = None
        return OptimizationResult(
            budget=budget,
            ranked_interventions=ranked,
            selected_interventions=selected,
            baseline_resilience=baseline_resilience,
            best_resilience=best_resilience,
            robust_mode=True,
            scenario_count=len(scenario_summaries),
            cluster_count=len(self.last_cluster_summaries),
            candidate_count=len(candidates),
            generated_policy_count=sum(
                1
                for intervention in candidates
                if (intervention.applicability_constraints or {}).get("generated", False)
            ),
            dynamic_policy_count=sum(
                1
                for intervention in candidates
                if (intervention.applicability_constraints or {}).get("dynamic", False)
            ),
            adaptive_policy_count=sum(
                1
                for intervention in candidates
                if (intervention.applicability_constraints or {}).get("adaptive", False)
            ),
            bundle_candidate_count=sum(
                1
                for intervention in candidates
                if intervention.action_type == "bundle"
            ),
            hierarchical_playbook_count=sum(
                1
                for intervention in candidates
                if (intervention.applicability_constraints or {}).get("hierarchical_bundle", False)
            ),
            recommended_portfolio_id=recommended_portfolio_id,
            portfolio_method=portfolio_method,
            portfolio_objective_score=portfolio_objective_score,
            portfolio_cluster_coverage_rate=portfolio_cluster_coverage_rate,
            regime_plan_method=(
                self.last_regime_plan_summary.method
                if self.last_regime_plan_summary is not None
                else None
            ),
            regime_plan_standby_cost=(
                self.last_regime_plan_summary.total_standby_cost
                if self.last_regime_plan_summary is not None
                else None
            ),
            regime_plan_cluster_coverage_rate=(
                self.last_regime_plan_summary.weighted_cluster_coverage_rate
                if self.last_regime_plan_summary is not None
                else None
            ),
            regime_plan_expected_resilience=(
                self.last_regime_plan_summary.expected_resilience
                if self.last_regime_plan_summary is not None
                else None
            ),
            regime_plan_expected_fairness_score=(
                self.last_regime_plan_summary.expected_fairness_score
                if self.last_regime_plan_summary is not None
                else None
            ),
            regime_detection_method=(
                self.last_regime_detection_summary.method
                if self.last_regime_detection_summary is not None
                else None
            ),
            regime_detection_accuracy=(
                self.last_regime_detection_summary.detection_accuracy
                if self.last_regime_detection_summary is not None
                else None
            ),
            regime_detection_expected_resilience=(
                self.last_regime_detection_summary.expected_resilience
                if self.last_regime_detection_summary is not None
                else None
            ),
            regime_detection_expected_fairness_score=(
                self.last_regime_detection_summary.expected_fairness_score
                if self.last_regime_detection_summary is not None
                else None
            ),
            regime_detection_failure_prevention_rate=(
                self.last_regime_detection_summary.failure_prevention_rate
                if self.last_regime_detection_summary is not None
                else None
            ),
            regime_detection_resilience_regret=(
                self.last_regime_detection_summary.resilience_regret
                if self.last_regime_detection_summary is not None
                else None
            ),
            online_regime_detection_method=(
                self.last_online_regime_summary.method
                if self.last_online_regime_summary is not None
                else None
            ),
            online_regime_detection_accuracy=(
                self.last_online_regime_summary.detection_accuracy
                if self.last_online_regime_summary is not None
                else None
            ),
            online_regime_expected_resilience=(
                self.last_online_regime_summary.expected_resilience
                if self.last_online_regime_summary is not None
                else None
            ),
            online_regime_expected_fairness_score=(
                self.last_online_regime_summary.expected_fairness_score
                if self.last_online_regime_summary is not None
                else None
            ),
            online_regime_failure_prevention_rate=(
                self.last_online_regime_summary.failure_prevention_rate
                if self.last_online_regime_summary is not None
                else None
            ),
            online_regime_resilience_regret=(
                self.last_online_regime_summary.resilience_regret
                if self.last_online_regime_summary is not None
                else None
            ),
            online_regime_pre_degradation_rate=(
                self.last_online_regime_summary.pre_degradation_decision_rate
                if self.last_online_regime_summary is not None
                else None
            ),
            response_timing_method=(
                self.last_response_timing_summary.method
                if self.last_response_timing_summary is not None
                else None
            ),
            response_timing_best_fraction=(
                self.last_response_timing_summary.best_deployment_fraction
                if self.last_response_timing_summary is not None
                else None
            ),
            response_timing_latest_high_value_fraction=(
                self.last_response_timing_summary.latest_high_value_fraction
                if self.last_response_timing_summary is not None
                else None
            ),
            response_timing_half_life_fraction=(
                self.last_response_timing_summary.resilience_half_life_fraction
                if self.last_response_timing_summary is not None
                else None
            ),
            response_timing_best_resilience=(
                self.last_response_timing_summary.best_expected_resilience
                if self.last_response_timing_summary is not None
                else None
            ),
            response_timing_value_decay=(
                self.last_response_timing_summary.response_value_decay
                if self.last_response_timing_summary is not None
                else None
            ),
            closed_loop_regime_method=(
                self.last_closed_loop_regime_summary.method
                if self.last_closed_loop_regime_summary is not None
                else None
            ),
            closed_loop_regime_prediction_accuracy=(
                self.last_closed_loop_regime_summary.prediction_accuracy
                if self.last_closed_loop_regime_summary is not None
                else None
            ),
            closed_loop_regime_deployment_accuracy=(
                self.last_closed_loop_regime_summary.deployment_accuracy
                if self.last_closed_loop_regime_summary is not None
                else None
            ),
            closed_loop_regime_expected_resilience=(
                self.last_closed_loop_regime_summary.expected_resilience
                if self.last_closed_loop_regime_summary is not None
                else None
            ),
            closed_loop_regime_expected_fairness_score=(
                self.last_closed_loop_regime_summary.expected_fairness_score
                if self.last_closed_loop_regime_summary is not None
                else None
            ),
            closed_loop_regime_failure_prevention_rate=(
                self.last_closed_loop_regime_summary.failure_prevention_rate
                if self.last_closed_loop_regime_summary is not None
                else None
            ),
            closed_loop_regime_pre_degradation_rate=(
                self.last_closed_loop_regime_summary.pre_degradation_deployment_rate
                if self.last_closed_loop_regime_summary is not None
                else None
            ),
            closed_loop_regime_retarget_rate=(
                self.last_closed_loop_regime_summary.retarget_rate
                if self.last_closed_loop_regime_summary is not None
                else None
            ),
            closed_loop_regime_resilience_regret=(
                self.last_closed_loop_regime_summary.resilience_regret
                if self.last_closed_loop_regime_summary is not None
                else None
            ),
            controller_tuning_method=(
                self.last_controller_tuning_summary.method
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_policy_id=(
                self.last_controller_tuning_summary.selected_policy_id
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_schedule_id=(
                self.last_controller_tuning_summary.selected_schedule_id
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_confidence_threshold=(
                self.last_controller_tuning_summary.selected_confidence_threshold
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_allow_retargeting=(
                self.last_controller_tuning_summary.selected_allow_retargeting
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_confirmation_count=(
                self.last_controller_tuning_summary.selected_confirmation_count
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_schedule_start_fraction=(
                self.last_controller_tuning_summary.selected_schedule_start_fraction
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_schedule_interval_fraction=(
                self.last_controller_tuning_summary.selected_schedule_interval_fraction
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_schedule_growth=(
                self.last_controller_tuning_summary.selected_schedule_growth
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_schedule_observation_limit=(
                self.last_controller_tuning_summary.selected_schedule_observation_limit
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_mean_observation_count=(
                self.last_controller_tuning_summary.selected_mean_observation_count
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_mean_deployment_count=(
                self.last_controller_tuning_summary.selected_mean_deployment_count
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_monitoring_burden_score=(
                self.last_controller_tuning_summary.selected_monitoring_burden_score
                if self.last_controller_tuning_summary is not None
                else None
            ),
            controller_frontier_count=len(self.last_controller_frontier),
            controller_search_rounds=(
                self.last_controller_tuning_summary.search_rounds
                if self.last_controller_tuning_summary is not None
                else 0
            ),
            controller_candidate_count=len(self.last_controller_policy_candidates),
            controller_tuning_scenario_count=(
                self.last_controller_tuning_summary.tuning_scenario_count
                if self.last_controller_tuning_summary is not None
                else 0
            ),
            fairness_weight=fairness_weight,
            pareto_intervention_ids=[item.intervention_id for item in frontier],
            roi_table_path=None,
        )

    def _greedy_select(
        self,
        budget: float,
        *,
        fairness_weight: float = 0.0,
    ) -> list[RankedIntervention]:
        remaining = list(self._candidate_interventions())
        selected_specs: list[InterventionSpec] = []
        selected: list[RankedIntervention] = []
        remaining_budget = budget
        current_resilience = self.baseline_result.metrics.get("resilience_score", 0.0)
        current_fairness = self.baseline_result.metrics.get("fairness_score", 0.0)
        while remaining:
            best_candidate = None
            best_result = None
            best_gain = float("-inf")
            best_resilience_gain = 0.0
            for intervention in remaining:
                if intervention.cost > remaining_budget:
                    continue
                result = self._evaluate([*selected_specs, intervention])
                resilience = result.metrics.get("resilience_score", 0.0)
                fairness = result.metrics.get("fairness_score", current_fairness)
                resilience_gain = resilience - current_resilience
                composite_gain = (
                    resilience_gain
                    + fairness_weight * (fairness - current_fairness)
                )
                if composite_gain > best_gain:
                    best_gain = composite_gain
                    best_resilience_gain = resilience_gain
                    best_candidate = intervention
                    best_result = result
            if best_candidate is None or best_result is None:
                break
            selected_specs.append(best_candidate)
            remaining.remove(best_candidate)
            remaining_budget -= best_candidate.cost
            current_resilience = best_result.metrics.get("resilience_score", current_resilience)
            current_fairness = best_result.metrics.get("fairness_score", current_fairness)
            selected.append(
                RankedIntervention(
                    intervention_id=best_candidate.id,
                    **self._ranked_metadata(best_candidate),
                    cost=best_candidate.cost,
                    resilience_gain=best_resilience_gain,
                    roi=best_resilience_gain / max(best_candidate.cost, 1e-9),
                    failure_prevented=self.baseline_result.failure_triggered and not best_result.failure_triggered,
                    fairness_gain=current_fairness - self.baseline_result.metrics.get("fairness_score", 0.0),
                    expected_fairness_score=current_fairness,
                    worst_case_fairness_score=current_fairness,
                    metrics=best_result.metrics,
                )
            )
        return selected

    def _evaluate(self, interventions: Iterable[InterventionSpec]):
        scenario_spec = apply_interventions(self.spec.model_copy(deep=True), interventions)
        resolved = resolve_spec(scenario_spec)
        simulator = Simulator(
            resolved,
            seed=self.seed,
            baseline_metrics=self.baseline_result.metrics,
        )
        return simulator.run()

    def _ranked_intervention_from_scenarios(
        self,
        intervention: InterventionSpec,
        evaluated: list[ScenarioSummary],
        *,
        untreated: list[ScenarioSummary],
        baseline_resilience: float,
        baseline_fairness: float,
        fairness_weight: float,
    ) -> RankedIntervention:
        resilience_values = np.array(
            [scenario.metrics.get("resilience_score", 0.0) for scenario in evaluated],
            dtype=float,
        )
        fairness_values = np.array(
            [scenario.metrics.get("fairness_score", 0.0) for scenario in evaluated],
            dtype=float,
        )
        untreated_failures = [scenario.failure_triggered for scenario in untreated]
        treated_failures = [scenario.failure_triggered for scenario in evaluated]
        expected_resilience = float(resilience_values.mean()) if resilience_values.size else 0.0
        worst_case_resilience = float(resilience_values.min()) if resilience_values.size else 0.0
        resilience_std = float(resilience_values.std()) if resilience_values.size else 0.0
        expected_fairness_score = float(fairness_values.mean()) if fairness_values.size else 0.0
        worst_case_fairness_score = float(fairness_values.min()) if fairness_values.size else 0.0
        prevented_pairs = [
            before and not after
            for before, after in zip(untreated_failures, treated_failures, strict=True)
        ]
        failing_baseline = max(sum(untreated_failures), 1)
        prevention_rate = sum(prevented_pairs) / failing_baseline
        gain = expected_resilience - baseline_resilience
        fairness_gain = expected_fairness_score - baseline_fairness
        aggregate_metrics = {
            "expected_resilience": expected_resilience,
            "worst_case_resilience": worst_case_resilience,
            "resilience_std": resilience_std,
            "expected_fairness_score": expected_fairness_score,
            "worst_case_fairness_score": worst_case_fairness_score,
            "expected_mean_wait": float(
                np.mean([scenario.metrics.get("mean_wait", 0.0) for scenario in evaluated])
            ),
            "expected_throughput": float(
                np.mean([scenario.metrics.get("throughput", 0.0) for scenario in evaluated])
            ),
            "expected_blocked_transfers": float(
                np.mean([scenario.metrics.get("blocked_transfers", 0.0) for scenario in evaluated])
            ),
        }
        robust_score = robust_objective(
            expected_resilience,
            worst_case_resilience,
            resilience_std,
            intervention.cost,
            fairness_score=expected_fairness_score,
            fairness_weight=fairness_weight,
        )
        return RankedIntervention(
            intervention_id=intervention.id,
            **self._ranked_metadata(intervention),
            cost=intervention.cost,
            resilience_gain=gain,
            roi=gain / max(intervention.cost, 1e-9),
            failure_prevented=bool(sum(prevented_pairs)),
            fairness_gain=fairness_gain,
            expected_resilience=expected_resilience,
            worst_case_resilience=worst_case_resilience,
            expected_fairness_score=expected_fairness_score,
            worst_case_fairness_score=worst_case_fairness_score,
            resilience_std=resilience_std,
            failure_prevention_rate=prevention_rate,
            robust_score=robust_score,
            evaluated_scenarios=len(evaluated),
            metrics=aggregate_metrics,
        )

    def _bundle_depth(
        self,
        intervention: InterventionSpec,
        lookup: dict[str, InterventionSpec],
        *,
        visited: set[str] | None = None,
    ) -> int:
        if not intervention.bundle_members:
            return 0
        seen = set() if visited is None else set(visited)
        if intervention.id in seen:
            return 0
        seen.add(intervention.id)
        child_depths = [
            self._bundle_depth(member, lookup, visited=seen)
            for member_id in intervention.bundle_members
            if (member := lookup.get(member_id)) is not None
        ]
        if not child_depths:
            return 1
        return 1 + max(child_depths)

    def _trigger_node(
        self,
        intervention: InterventionSpec,
        lookup: dict[str, InterventionSpec],
        *,
        visited: set[str] | None = None,
    ) -> str | None:
        if intervention.trigger_node:
            return intervention.trigger_node
        if not intervention.bundle_members:
            return None
        seen = set() if visited is None else set(visited)
        if intervention.id in seen:
            return None
        seen.add(intervention.id)
        trigger_nodes: set[str] = set()
        for member_id in intervention.bundle_members:
            member = lookup.get(member_id)
            if member is None:
                continue
            trigger_node = self._trigger_node(member, lookup, visited=seen)
            if trigger_node:
                trigger_nodes.add(trigger_node)
        if not trigger_nodes:
            return None
        return sorted(trigger_nodes)[0]


def apply_intervention(spec: SystemSpec, intervention: InterventionSpec) -> SystemSpec:
    """Apply one intervention to a copied SystemSpec."""

    return apply_intervention_with_lookup(spec, intervention)


def apply_intervention_with_lookup(
    spec: SystemSpec,
    intervention: InterventionSpec,
    *,
    lookup: dict[str, InterventionSpec] | None = None,
    applied_ids: set[str] | None = None,
    active_stack: tuple[str, ...] = (),
) -> SystemSpec:
    """Apply one intervention with optional bundle expansion and deduplication."""

    updated = spec.model_copy(deep=True)
    catalog = lookup or {candidate.id: candidate for candidate in updated.interventions}
    seen = applied_ids if applied_ids is not None else set()
    if intervention.id in seen:
        return updated
    if intervention.action_type == "bundle" or intervention.bundle_members:
        if intervention.id in active_stack:
            raise ValueError(f"Bundle cycle detected involving '{intervention.id}'.")
        nested = updated
        for member_id in intervention.bundle_members:
            member = catalog.get(member_id)
            if member is None:
                raise ValueError(f"Unknown bundle member '{member_id}' in intervention '{intervention.id}'.")
            nested = apply_intervention_with_lookup(
                nested,
                member,
                lookup=catalog,
                applied_ids=seen,
                active_stack=(*active_stack, intervention.id),
            )
        seen.add(intervention.id)
        return nested
    seen.add(intervention.id)
    action_type = intervention.action_type
    if action_type.startswith("scheduled_"):
        scheduled_action = action_type.removeprefix("scheduled_")
        updated.policies.append(
            PolicyScheduleSpec(
                id=intervention.id,
                label=intervention.label,
                target=intervention.target,
                action_type=scheduled_action,
                mode="scheduled",
                start=intervention.start or 0.0,
                duration=intervention.duration,
                parameter=intervention.parameter,
                delta=intervention.delta,
                replacement=intervention.replacement,
                stages=intervention.stages,
                applicability_constraints=intervention.applicability_constraints,
            )
        )
        return updated
    if action_type.startswith("threshold_"):
        threshold_action = action_type.removeprefix("threshold_")
        updated.policies.append(
            PolicyScheduleSpec(
                id=intervention.id,
                label=intervention.label,
                target=intervention.target,
                action_type=threshold_action,
                mode="threshold",
                start=intervention.start or 0.0,
                duration=intervention.duration,
                parameter=intervention.parameter,
                delta=intervention.delta,
                replacement=intervention.replacement,
                trigger_metric=intervention.trigger_metric,
                trigger_node=intervention.trigger_node,
                trigger_threshold=intervention.trigger_threshold,
                clear_threshold=intervention.clear_threshold,
                min_active_duration=float(intervention.min_active_duration or 0.0),
                cooldown=float(intervention.cooldown or 0.0),
                stages=intervention.stages,
                applicability_constraints=intervention.applicability_constraints,
            )
        )
        return updated
    edge_lookup = {f"{edge.from_node}->{edge.to_node}": edge for edge in updated.edges}
    node_lookup = {node.id: node for node in updated.nodes}
    if intervention.target in node_lookup:
        node = node_lookup[intervention.target]
        if action_type == "add_servers":
            node.servers += int(intervention.delta or 0)
        elif action_type == "increase_buffer_capacity":
            current = node.buffer_capacity or 0
            node.buffer_capacity = current + int(intervention.delta or 0)
        elif action_type == "reduce_service_time_factor":
            factor = intervention.replacement if intervention.replacement is not None else intervention.delta
            factor = float(factor if factor is not None else 1.0)
            _apply_service_time_factor(node, factor)
        elif action_type == "priority_policy_change":
            replacement = str(intervention.replacement or intervention.parameter or "priority")
            node.queue_policy = replacement
        else:
            raise ValueError(f"Unsupported node intervention '{action_type}'.")
        return updated

    if intervention.target in edge_lookup:
        edge = edge_lookup[intervention.target]
        if action_type == "enable_backup_edge":
            edge.enabled = True
        elif action_type == "reroute_fraction":
            edge.routing.probability = min(1.0, edge.routing.probability + float(intervention.delta or 0.0))
            siblings = [candidate for candidate in updated.edges if candidate.from_node == edge.from_node and candidate is not edge]
            if siblings:
                residual = max(0.0, 1.0 - edge.routing.probability)
                share = residual / len(siblings)
                for sibling in siblings:
                    sibling.routing.probability = share
        else:
            raise ValueError(f"Unsupported edge intervention '{action_type}'.")
        return updated

    raise ValueError(f"Unknown intervention target '{intervention.target}'.")


def apply_interventions(spec: SystemSpec, interventions: Iterable[InterventionSpec]) -> SystemSpec:
    """Apply a sequence of interventions while expanding bundles safely."""

    updated = spec.model_copy(deep=True)
    lookup = {candidate.id: candidate for candidate in updated.interventions}
    applied_ids: set[str] = set()
    for intervention in interventions:
        updated = apply_intervention_with_lookup(
            updated,
            intervention,
            lookup=lookup,
            applied_ids=applied_ids,
        )
    return updated


def _apply_service_time_factor(node, factor: float) -> None:
    config = node.service_time
    if config.distribution == "exponential":
        if config.mean is not None:
            config.mean *= factor
        elif config.rate is not None:
            config.rate /= factor
    elif config.distribution == "gamma":
        config.scale *= factor
    elif config.distribution == "lognormal":
        config.mu += math.log(max(factor, 1e-9))
    else:
        config.value *= factor
