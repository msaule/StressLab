"""Intervention optimization interfaces."""

from stresslab.optimize.closed_loop_regime_control import evaluate_closed_loop_regime_control
from stresslab.optimize.controller_frontier import controller_pareto_frontier
from stresslab.optimize.controller_tuning import tune_closed_loop_controller
from stresslab.optimize.interventions import Optimizer, apply_intervention, apply_interventions
from stresslab.optimize.online_regime_detection import evaluate_online_regime_detection
from stresslab.optimize.pareto import pareto_frontier
from stresslab.optimize.policy_catalog import (
    bundle_hierarchy_rows,
    expand_intervention_catalog,
    intervention_catalog_rows,
    synthesize_adaptive_policy_interventions,
    synthesize_controller_bundles,
    synthesize_dynamic_policy_interventions,
    synthesize_hierarchical_playbooks,
    synthesize_policy_interventions,
)
from stresslab.optimize.portfolio_analysis import (
    cluster_scenarios,
    summarize_intervention_coverage,
    summarize_portfolio_coverage,
)
from stresslab.optimize.portfolio_search import robust_portfolio_objective, select_robust_portfolio
from stresslab.optimize.regime_detection import evaluate_regime_detection
from stresslab.optimize.regime_planning import build_regime_response_plan
from stresslab.optimize.response_timing import evaluate_response_timing
from stresslab.optimize.robust import build_scenario_portfolio, robust_objective

__all__ = [
    "Optimizer",
    "apply_intervention",
    "apply_interventions",
    "build_scenario_portfolio",
    "controller_pareto_frontier",
    "evaluate_closed_loop_regime_control",
    "tune_closed_loop_controller",
    "evaluate_regime_detection",
    "evaluate_online_regime_detection",
    "evaluate_response_timing",
    "build_regime_response_plan",
    "bundle_hierarchy_rows",
    "cluster_scenarios",
    "expand_intervention_catalog",
    "intervention_catalog_rows",
    "pareto_frontier",
    "robust_portfolio_objective",
    "robust_objective",
    "select_robust_portfolio",
    "synthesize_adaptive_policy_interventions",
    "synthesize_controller_bundles",
    "synthesize_hierarchical_playbooks",
    "summarize_intervention_coverage",
    "summarize_portfolio_coverage",
    "synthesize_dynamic_policy_interventions",
    "synthesize_policy_interventions",
]
