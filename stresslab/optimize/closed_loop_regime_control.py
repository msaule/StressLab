"""Closed-loop regime control with runtime observation and deployment."""

from __future__ import annotations

import numpy as np

from stresslab.des import Simulator
from stresslab.des.controller import ControllerDecision
from stresslab.models import (
    ClosedLoopRegimeScenarioResult,
    ClosedLoopRegimeSummary,
    ClusterResponseRecommendation,
    ScenarioClusterAssignment,
    ScenarioSummary,
)
from stresslab.optimize.deployment_replay import resolve_intervention_sequence
from stresslab.optimize.online_regime_detection import (
    _observation_feature_vector,
    _scenario_observations,
    _softmax_inverse_distance,
)
from stresslab.search.common import apply_shock_vector
from stresslab.systemspec import resolve_spec
from stresslab.systemspec.schema import InterventionSpec, SystemSpec

_OBSERVATION_FRACTIONS = (0.2, 0.35, 0.5, 0.7, 1.0)


class ClosedLoopRegimeController:
    """Confidence-gated regime detector that deploys plan interventions during a run."""

    def __init__(
        self,
        *,
        spec: SystemSpec,
        ordered_clusters: list[str],
        centroids_by_fraction: dict[float, np.ndarray],
        cluster_response_plan: list[ClusterResponseRecommendation],
        observation_fractions: tuple[float, ...],
        confidence_threshold: float,
        allow_retargeting: bool,
        confirmation_count: int,
    ) -> None:
        self.spec = spec
        self.ordered_clusters = ordered_clusters
        self.centroids_by_fraction = centroids_by_fraction
        self.plan_by_cluster = {row.cluster_id: row for row in cluster_response_plan}
        self.observation_fractions = observation_fractions
        self.confidence_threshold = confidence_threshold
        self.allow_retargeting = allow_retargeting
        self.confirmation_count = max(1, int(confirmation_count))
        self.prediction_log: list[dict[str, object]] = []
        self.deployed_cluster_ids: list[str] = []
        self._last_high_confidence_cluster: str | None = None
        self._consecutive_high_confidence = 0

    def observation_schedule(self, *, start: float, end: float) -> list[tuple[float, float]]:
        horizon = max(end - start, 0.0)
        return [
            (start + horizon * fraction, fraction)
            for fraction in self.observation_fractions
            if start + horizon * fraction <= end + 1e-9
        ]

    def on_tick(self, simulator: Simulator, *, observation_fraction: float) -> ControllerDecision:
        feature = _observation_feature_vector(
            simulator,
            start=float(simulator.spec.spec.clock.start),
            until=max(float(simulator.now), float(simulator.spec.spec.clock.start)),
        )
        centroid_matrix = self.centroids_by_fraction[observation_fraction]
        distances = np.linalg.norm(centroid_matrix - feature[None, :], axis=1)
        probabilities = _softmax_inverse_distance(distances)
        predicted_index = int(np.argmin(distances))
        predicted_cluster = self.ordered_clusters[predicted_index]
        confidence = float(probabilities[predicted_index])
        plan_row = self.plan_by_cluster.get(predicted_cluster)
        selected_id = plan_row.selected_intervention_id if plan_row is not None else None
        leaf_interventions = (
            resolve_intervention_sequence(self.spec, [selected_id])
            if selected_id is not None
            else []
        )
        new_interventions = [
            intervention
            for intervention in leaf_interventions
            if intervention.id not in simulator.deployed_intervention_ids
        ]
        retargeted = bool(self.prediction_log and predicted_cluster != self.prediction_log[-1]["predicted_cluster_id"])
        confirmed = self._update_confirmation_state(predicted_cluster, confidence)
        if confidence < self.confidence_threshold:
            action = "defer"
            deployments: list[InterventionSpec] = []
        elif not confirmed:
            action = "confirming"
            deployments = []
        elif selected_id is None:
            action = "no_plan"
            deployments = []
        elif simulator.deployed_intervention_ids and not self.allow_retargeting and new_interventions:
            action = "locked"
            deployments = []
        elif new_interventions:
            action = "deploy"
            deployments = new_interventions
            self.deployed_cluster_ids.append(predicted_cluster)
        else:
            action = "already_deployed"
            deployments = []

        log = {
            "predicted_cluster_id": predicted_cluster,
            "predicted_cluster_label": plan_row.cluster_label if plan_row is not None else predicted_cluster,
            "selected_intervention_id": selected_id,
            "selected_label": plan_row.selected_label if plan_row is not None else None,
            "confidence": confidence,
            "action": action,
            "deployment_count": len(deployments),
            "retargeted": retargeted,
            "confirmation_count": self.confirmation_count,
            "confirmed": confirmed,
            "consecutive_high_confidence": self._consecutive_high_confidence,
        }
        self.prediction_log.append(log)
        return ControllerDecision(interventions=deployments, log=log)

    def _update_confirmation_state(self, predicted_cluster: str, confidence: float) -> bool:
        if confidence < self.confidence_threshold:
            self._last_high_confidence_cluster = None
            self._consecutive_high_confidence = 0
            return False
        if predicted_cluster == self._last_high_confidence_cluster:
            self._consecutive_high_confidence += 1
        else:
            self._last_high_confidence_cluster = predicted_cluster
            self._consecutive_high_confidence = 1
        return self._consecutive_high_confidence >= self.confirmation_count


def evaluate_closed_loop_regime_control(
    *,
    spec: SystemSpec,
    untreated: list[ScenarioSummary],
    scenario_clusters: list[ScenarioClusterAssignment],
    cluster_response_plan: list[ClusterResponseRecommendation],
    regime_plan_summary,
    seed: int,
    observation_fractions: tuple[float, ...] = _OBSERVATION_FRACTIONS,
    confidence_threshold: float = 0.6,
    allow_retargeting: bool = True,
    confirmation_count: int = 1,
) -> tuple[ClosedLoopRegimeSummary | None, list[ClosedLoopRegimeScenarioResult]]:
    """Evaluate a closed-loop controller that observes and deploys during the replay itself."""

    if not untreated or not scenario_clusters or not cluster_response_plan:
        return None, []

    fractions = tuple(sorted({min(max(float(fraction), 0.0), 1.0) for fraction in observation_fractions} | {1.0}))
    scenario_order = [scenario.scenario_id for scenario in untreated]
    cluster_by_scenario = {assignment.scenario_id: assignment.cluster_id for assignment in scenario_clusters}
    label_by_cluster = {assignment.cluster_id: assignment.cluster_label for assignment in scenario_clusters}
    ordered_clusters = sorted({assignment.cluster_id for assignment in scenario_clusters})
    if not ordered_clusters:
        return None, []

    observations: dict[str, dict[float, np.ndarray]] = {}
    timing: dict[str, tuple[float, float | None]] = {}
    for scenario in untreated:
        profile, horizon, first_degraded_time = _scenario_observations(
            spec,
            scenario,
            seed=seed,
            observation_fractions=fractions,
        )
        observations[scenario.scenario_id] = profile
        timing[scenario.scenario_id] = (horizon, first_degraded_time)

    rows: list[ClosedLoopRegimeScenarioResult] = []
    resilience_values: list[float] = []
    fairness_values: list[float] = []
    failure_values: list[float] = []
    prevention_values: list[float] = []
    observation_counts: list[float] = []
    deployment_counts: list[float] = []
    prediction_accuracy_flags: list[float] = []
    deployment_accuracy_flags: list[float] = []
    pre_degradation_observation_flags: list[float] = []
    pre_degradation_deployment_flags: list[float] = []
    retarget_flags: list[float] = []

    feature_by_fraction = {
        fraction: np.asarray(
            [observations[scenario_id][fraction] for scenario_id in scenario_order],
            dtype=float,
        )
        for fraction in fractions
    }

    for scenario_index, scenario in enumerate(untreated):
        true_cluster = cluster_by_scenario.get(scenario.scenario_id)
        if true_cluster is None:
            continue
        centroids_by_fraction = {
            fraction: _cluster_centroids(
                features=feature_by_fraction[fraction],
                ordered_clusters=ordered_clusters,
                cluster_by_scenario=cluster_by_scenario,
                scenario_order=scenario_order,
                exclude_index=scenario_index,
            )
            for fraction in fractions
        }
        controller = ClosedLoopRegimeController(
            spec=spec,
            ordered_clusters=ordered_clusters,
            centroids_by_fraction=centroids_by_fraction,
            cluster_response_plan=cluster_response_plan,
            observation_fractions=fractions,
            confidence_threshold=confidence_threshold,
            allow_retargeting=allow_retargeting,
            confirmation_count=confirmation_count,
        )
        scenario_spec = apply_shock_vector(spec, scenario.shock_vector)
        simulator = Simulator(
            resolve_spec(scenario_spec),
            seed=seed,
            baseline_metrics=scenario.metrics,
        )
        result = simulator.run(controller=controller)

        horizon, first_degraded_time = timing[scenario.scenario_id]
        first_observation_time = (
            float(simulator.controller_event_log[0]["time"])
            if simulator.controller_event_log
            else None
        )
        first_deployment_time = (
            float(simulator.deployment_event_log[0]["time"])
            if simulator.deployment_event_log
            else None
        )
        final_prediction = controller.prediction_log[-1]["predicted_cluster_id"] if controller.prediction_log else None
        deployed_cluster = controller.deployed_cluster_ids[0] if controller.deployed_cluster_ids else None
        deployed_intervention_ids = [
            str(event["intervention_id"])
            for event in simulator.deployment_event_log
            if event.get("intervention_id") is not None
        ]
        pre_degradation_observation = bool(
            first_observation_time is not None
            and (first_degraded_time is None or first_observation_time <= first_degraded_time + 1e-9)
        )
        pre_degradation_deployment = bool(
            first_deployment_time is not None
            and (first_degraded_time is None or first_deployment_time <= first_degraded_time + 1e-9)
        )
        prediction_correct = final_prediction == true_cluster
        deployment_correct = deployed_cluster == true_cluster
        retargeted = len({row["predicted_cluster_id"] for row in controller.prediction_log}) > 1
        row = ClosedLoopRegimeScenarioResult(
            scenario_id=scenario.scenario_id,
            true_cluster_id=true_cluster,
            true_cluster_label=label_by_cluster.get(true_cluster, true_cluster),
            final_predicted_cluster_id=str(final_prediction) if final_prediction is not None else None,
            final_predicted_cluster_label=(
                label_by_cluster.get(str(final_prediction), str(final_prediction))
                if final_prediction is not None
                else None
            ),
            first_deployed_cluster_id=deployed_cluster,
            first_deployed_cluster_label=(
                label_by_cluster.get(deployed_cluster, deployed_cluster)
                if deployed_cluster is not None
                else None
            ),
            deployed_intervention_ids=deployed_intervention_ids,
            observation_count=len(simulator.controller_event_log),
            deployment_count=len(simulator.deployment_event_log),
            first_observation_time=first_observation_time,
            first_deployment_time=first_deployment_time,
            first_degraded_time=first_degraded_time,
            pre_degradation_observation=pre_degradation_observation,
            pre_degradation_deployment=pre_degradation_deployment,
            prediction_correct=prediction_correct,
            deployment_correct=deployment_correct,
            retargeted=retargeted,
            mean_confidence=float(
                np.mean([float(event.get("confidence", 0.0)) for event in simulator.controller_event_log])
            ) if simulator.controller_event_log else 0.0,
            max_confidence=float(
                max((float(event.get("confidence", 0.0)) for event in simulator.controller_event_log), default=0.0)
            ),
            final_resilience=float(result.metrics.get("resilience_score", 0.0)),
            final_fairness_score=float(result.metrics.get("fairness_score", 0.0)),
            final_failure_rate=float(result.failure_triggered),
            failure_prevention_rate=max(0.0, float(scenario.failure_triggered) - float(result.failure_triggered)),
        )
        rows.append(row)
        resilience_values.append(row.final_resilience)
        fairness_values.append(row.final_fairness_score)
        failure_values.append(row.final_failure_rate)
        prevention_values.append(row.failure_prevention_rate)
        observation_counts.append(float(row.observation_count))
        deployment_counts.append(float(row.deployment_count))
        prediction_accuracy_flags.append(float(prediction_correct))
        deployment_accuracy_flags.append(float(deployment_correct))
        pre_degradation_observation_flags.append(float(pre_degradation_observation))
        pre_degradation_deployment_flags.append(float(pre_degradation_deployment))
        retarget_flags.append(float(retargeted))

    if not rows:
        return None, []

    summary = ClosedLoopRegimeSummary(
        method="closed_loop_partial_observation_controller",
        confidence_threshold=confidence_threshold,
        allow_retargeting=allow_retargeting,
        confirmation_count=max(1, int(confirmation_count)),
        scenario_count=len(rows),
        cluster_count=len(ordered_clusters),
        mean_observation_count=float(np.mean(observation_counts)),
        mean_deployment_count=float(np.mean(deployment_counts)),
        prediction_accuracy=float(np.mean(prediction_accuracy_flags)),
        deployment_accuracy=float(np.mean(deployment_accuracy_flags)),
        pre_degradation_observation_rate=float(np.mean(pre_degradation_observation_flags)),
        pre_degradation_deployment_rate=float(np.mean(pre_degradation_deployment_flags)),
        retarget_rate=float(np.mean(retarget_flags)),
        expected_resilience=float(np.mean(resilience_values)),
        expected_fairness_score=float(np.mean(fairness_values)),
        expected_failure_rate=float(np.mean(failure_values)),
        failure_prevention_rate=float(np.mean(prevention_values)),
        resilience_regret=max(
            float(getattr(regime_plan_summary, "expected_resilience", 0.0)) - float(np.mean(resilience_values)),
            0.0,
        ),
        fairness_regret=max(
            float(getattr(regime_plan_summary, "expected_fairness_score", 0.0)) - float(np.mean(fairness_values)),
            0.0,
        ),
    )
    rows.sort(key=lambda row: (row.true_cluster_id, row.scenario_id))
    return summary, rows


def _cluster_centroids(
    *,
    features: np.ndarray,
    ordered_clusters: list[str],
    cluster_by_scenario: dict[str, str],
    scenario_order: list[str],
    exclude_index: int,
) -> np.ndarray:
    centroids: list[np.ndarray] = []
    for cluster_id in ordered_clusters:
        member_indexes = [
            index
            for index, scenario_id in enumerate(scenario_order)
            if cluster_by_scenario.get(scenario_id) == cluster_id and index != exclude_index
        ]
        if not member_indexes:
            member_indexes = [
                index
                for index, scenario_id in enumerate(scenario_order)
                if cluster_by_scenario.get(scenario_id) == cluster_id
            ]
        if not member_indexes:
            centroids.append(np.zeros(features.shape[1], dtype=float))
        else:
            centroids.append(features[member_indexes].mean(axis=0))
    return np.asarray(centroids, dtype=float)
