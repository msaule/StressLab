from __future__ import annotations

from stresslab.models import ControllerPolicyCandidate
from stresslab.optimize.controller_frontier import controller_pareto_frontier


def test_controller_frontier_prefers_performance_burden_tradeoffs():
    dominated = ControllerPolicyCandidate(
        policy_id="controller__dominated",
        schedule_id="dominated",
        observation_fractions=[0.2, 0.5, 1.0],
        schedule_start_fraction=0.2,
        schedule_interval_fraction=0.2,
        schedule_growth=1.1,
        schedule_observation_limit=3,
        confidence_threshold=0.6,
        allow_retargeting=False,
        confirmation_count=1,
        tuning_scenario_count=3,
        mean_observation_count=5.0,
        mean_deployment_count=1.0,
        monitoring_burden_score=6.5,
        search_method="seed_grid",
        generation=0,
        objective_score=0.55,
        expected_resilience=0.62,
        expected_fairness_score=0.80,
        failure_prevention_rate=0.30,
        prediction_accuracy=0.50,
        deployment_accuracy=0.45,
        pre_degradation_rate=0.30,
        retarget_rate=0.40,
        resilience_regret=0.12,
    )
    low_burden = dominated.model_copy(
        update={
            "policy_id": "controller__low_burden",
            "monitoring_burden_score": 4.0,
            "mean_observation_count": 3.0,
            "objective_score": 0.58,
        }
    )
    higher_performance = dominated.model_copy(
        update={
            "policy_id": "controller__higher_performance",
            "expected_resilience": 0.70,
            "deployment_accuracy": 0.60,
            "pre_degradation_rate": 0.42,
            "objective_score": 0.68,
        }
    )

    frontier = controller_pareto_frontier([dominated, low_burden, higher_performance])

    assert {candidate.policy_id for candidate in frontier} == {
        "controller__low_burden",
        "controller__higher_performance",
    }
