from __future__ import annotations

from stresslab.des import Simulator
from stresslab.optimize import Optimizer
from stresslab.systemspec import load_spec, resolve_spec


def test_robust_optimizer_builds_clusters_and_coverage():
    spec = load_spec("examples/healthcare/ed_basic.yml")
    baseline = Simulator(resolve_spec(spec), seed=spec.seed).run()
    optimizer = Optimizer(spec, baseline)

    result = optimizer.rank_interventions_robust(
        budget=2500,
        scenario_budget=0.4,
        random_samples=3,
        fairness_weight=0.25,
    )

    assert result.robust_mode
    assert result.cluster_count >= 1
    assert optimizer.last_scenario_clusters
    assert optimizer.last_cluster_summaries
    assert optimizer.last_intervention_coverage
    assert optimizer.last_portfolio_candidates
    assert optimizer.last_portfolio_cluster_coverage
    assert optimizer.last_regime_plan_summary is not None
    assert optimizer.last_cluster_response_plan
    assert optimizer.last_regime_detection_summary is not None
    assert optimizer.last_regime_detection_rows
    assert optimizer.last_regime_detection_confusion
    assert optimizer.last_online_regime_summary is not None
    assert optimizer.last_online_regime_rows
    assert optimizer.last_online_regime_horizons
    assert optimizer.last_response_timing_summary is not None
    assert optimizer.last_response_timing_points
    assert optimizer.last_closed_loop_regime_summary is not None
    assert optimizer.last_closed_loop_regime_rows
    assert optimizer.last_controller_tuning_summary is not None
    assert optimizer.last_controller_policy_candidates
    assert optimizer.last_controller_frontier
    assert result.recommended_portfolio_id is not None
    assert result.portfolio_method in {"exact_subset", "beam_search"}
    assert result.portfolio_cluster_coverage_rate is not None
    assert result.regime_plan_method in {"greedy_regime_map", "cluster_best"}
    assert result.regime_plan_cluster_coverage_rate is not None
    assert result.regime_plan_expected_resilience is not None
    assert result.regime_detection_method == "leave_one_out_noisy_centroid"
    assert result.regime_detection_accuracy is not None
    assert 0.0 <= result.regime_detection_accuracy <= 1.0
    assert result.regime_detection_expected_resilience is not None
    assert result.regime_detection_resilience_regret is not None
    assert result.online_regime_detection_method == "online_partial_observation_centroid"
    assert result.online_regime_detection_accuracy is not None
    assert 0.0 <= result.online_regime_detection_accuracy <= 1.0
    assert result.online_regime_expected_resilience is not None
    assert result.online_regime_resilience_regret is not None
    assert result.online_regime_pre_degradation_rate is not None
    assert result.response_timing_method == "perfect_information_deployment_replay"
    assert result.response_timing_best_fraction is not None
    assert result.response_timing_latest_high_value_fraction is not None
    assert result.response_timing_half_life_fraction is not None
    assert result.response_timing_value_decay is not None
    assert result.closed_loop_regime_method == "closed_loop_partial_observation_controller"
    assert result.closed_loop_regime_prediction_accuracy is not None
    assert result.closed_loop_regime_deployment_accuracy is not None
    assert result.closed_loop_regime_expected_resilience is not None
    assert result.closed_loop_regime_pre_degradation_rate is not None
    assert result.closed_loop_regime_retarget_rate is not None
    assert result.controller_tuning_method == "beam_local_search_representative_scenarios"
    assert result.controller_policy_id is not None
    assert result.controller_schedule_id is not None
    assert result.controller_confidence_threshold is not None
    assert result.controller_confirmation_count is not None
    assert result.controller_schedule_start_fraction is not None
    assert result.controller_schedule_interval_fraction is not None
    assert result.controller_schedule_growth is not None
    assert result.controller_schedule_observation_limit is not None
    assert result.controller_mean_observation_count is not None
    assert result.controller_mean_deployment_count is not None
    assert result.controller_monitoring_burden_score is not None
    assert result.controller_frontier_count >= 1
    assert result.controller_search_rounds >= 1
    assert result.controller_candidate_count >= 1
    assert result.fairness_weight == 0.25
    assert optimizer.last_portfolio_candidates[0].expected_fairness_score is not None
    assert {
        summary.cluster_id for summary in optimizer.last_cluster_summaries
    } == {assignment.cluster_id for assignment in optimizer.last_scenario_clusters}
    assert "add_ward_capacity" in {
        item.intervention_id for item in optimizer.last_intervention_coverage
    }
    assert {
        row.cluster_id for row in optimizer.last_cluster_response_plan
    } == {assignment.cluster_id for assignment in optimizer.last_scenario_clusters}
