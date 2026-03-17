from __future__ import annotations

from stresslab.des import Simulator
from stresslab.optimize import Optimizer, pareto_frontier
from stresslab.search import Searcher
from stresslab.systemspec import load_spec, resolve_spec


def test_healthcare_example_regression():
    spec = load_spec("examples/healthcare/ed_basic.yml")
    baseline = Simulator(resolve_spec(spec), seed=spec.seed).run()
    assert not baseline.failure_triggered
    assert 0.07 <= baseline.metrics["throughput"] <= 0.10
    assert baseline.metrics["fairness_score"] >= 0.0
    assert "critical" in baseline.class_metrics

    search_result = Searcher(spec, objective="min_failure", seed=spec.seed).find_min_failure()
    assert search_result.failure_triggered
    assert 0.05 <= search_result.best_shock_budget <= 0.25

    optimization = Optimizer(spec, baseline).rank_interventions(budget=2500)
    assert optimization.ranked_interventions[0].intervention_id == "add_ward_capacity"

    robust_optimization = Optimizer(spec, baseline).rank_interventions_robust(
        budget=2500,
        scenario_budget=0.4,
        random_samples=2,
    )
    assert robust_optimization.robust_mode
    assert robust_optimization.scenario_count >= 3
    assert robust_optimization.cluster_count >= 1
    assert robust_optimization.ranked_interventions[0].intervention_id == "add_ward_capacity"
    assert robust_optimization.recommended_portfolio_id is not None
    assert robust_optimization.portfolio_method == "exact_subset"
    assert robust_optimization.portfolio_cluster_coverage_rate is not None
    assert robust_optimization.regime_plan_method is not None
    assert robust_optimization.regime_plan_standby_cost is not None
    assert robust_optimization.regime_plan_cluster_coverage_rate is not None
    assert robust_optimization.regime_plan_expected_resilience is not None
    assert robust_optimization.regime_detection_method == "leave_one_out_noisy_centroid"
    assert robust_optimization.regime_detection_accuracy is not None
    assert robust_optimization.regime_detection_expected_resilience is not None
    assert robust_optimization.regime_detection_resilience_regret is not None
    assert robust_optimization.online_regime_detection_method == "online_partial_observation_centroid"
    assert robust_optimization.online_regime_detection_accuracy is not None
    assert robust_optimization.online_regime_expected_resilience is not None
    assert robust_optimization.online_regime_resilience_regret is not None
    assert robust_optimization.online_regime_pre_degradation_rate is not None
    assert robust_optimization.response_timing_method == "perfect_information_deployment_replay"
    assert robust_optimization.response_timing_best_fraction is not None
    assert robust_optimization.response_timing_latest_high_value_fraction is not None
    assert robust_optimization.response_timing_half_life_fraction is not None
    assert robust_optimization.response_timing_value_decay is not None
    assert robust_optimization.closed_loop_regime_method == "closed_loop_partial_observation_controller"
    assert robust_optimization.closed_loop_regime_prediction_accuracy is not None
    assert robust_optimization.closed_loop_regime_deployment_accuracy is not None
    assert robust_optimization.closed_loop_regime_expected_resilience is not None
    assert robust_optimization.closed_loop_regime_pre_degradation_rate is not None
    assert robust_optimization.closed_loop_regime_retarget_rate is not None
    assert robust_optimization.controller_tuning_method == "beam_local_search_representative_scenarios"
    assert robust_optimization.controller_policy_id is not None
    assert robust_optimization.controller_schedule_id is not None
    assert robust_optimization.controller_confidence_threshold is not None
    assert robust_optimization.controller_confirmation_count is not None
    assert robust_optimization.controller_schedule_start_fraction is not None
    assert robust_optimization.controller_schedule_interval_fraction is not None
    assert robust_optimization.controller_schedule_growth is not None
    assert robust_optimization.controller_schedule_observation_limit is not None
    assert robust_optimization.controller_mean_observation_count is not None
    assert robust_optimization.controller_mean_deployment_count is not None
    assert robust_optimization.controller_monitoring_burden_score is not None
    assert robust_optimization.controller_frontier_count >= 1
    assert robust_optimization.controller_search_rounds >= 1
    assert robust_optimization.controller_candidate_count >= 1
    assert len(robust_optimization.selected_interventions) >= 1
    assert robust_optimization.ranked_interventions[0].expected_fairness_score is not None
    frontier = pareto_frontier(robust_optimization.ranked_interventions, robust_mode=True)
    assert frontier
    assert "add_ward_capacity" in {item.intervention_id for item in frontier}
