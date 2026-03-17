"""Deterministic discrete-event simulation engine."""

from __future__ import annotations

import heapq
import math
from pathlib import Path

import numpy as np
import pandas as pd

from stresslab.des.controller import ControllerDecision
from stresslab.des.event import Event
from stresslab.des.metrics import evaluate_failure_conditions, summarize_metrics
from stresslab.des.node import EdgeState, Job, NodeState, SimulationState
from stresslab.des.policies import select_next_job
from stresslab.des.queue import enqueue_job
from stresslab.des.routing import choose_downstream_edge
from stresslab.models import SimulationResult
from stresslab.shocks import apply_shock, flatten_shocks, remove_shock
from stresslab.shocks.base import refresh_edge_state, refresh_node_state
from stresslab.shocks.demand import demand_multiplier_at_time
from stresslab.systemspec import resolve_spec
from stresslab.systemspec.schema import (
    ArrivalSpec,
    InterventionSpec,
    PolicyScheduleSpec,
    PolicyStageSpec,
    ResolvedSystemSpec,
)
from stresslab.utils import write_dataframe


class Simulator:
    """Continuous-time queueing simulator."""

    def __init__(
        self,
        spec: ResolvedSystemSpec,
        seed: int | None = None,
        baseline_metrics: dict[str, float] | None = None,
    ) -> None:
        self.spec = spec
        self._pristine_spec = spec.spec.model_copy(deep=True)
        self.seed = seed if seed is not None else spec.spec.seed
        self.baseline_metrics = baseline_metrics or {}
        self.reset()

    def reset(self) -> None:
        """Reset all runtime state."""

        # Re-resolve a fresh copy so runtime deployments never leak across runs.
        self.spec = resolve_spec(self._pristine_spec.model_copy(deep=True))
        self._flattened_shocks = flatten_shocks(self.spec.spec.shocks)
        self.now = self.spec.spec.clock.start
        self.event_queue: list[Event] = []
        self.event_sequence = 0
        self.job_sequence = 0
        self.queue_sequence = 0
        self.processed_event_count = 0
        self.external_arrival_count = 0
        self.departed_jobs = 0
        self.external_arrival_class_counts: dict[str, int] = {}
        self.departed_class_counts: dict[str, int] = {}
        self.active_policies: dict[str, PolicyScheduleSpec] = {}
        self.policy_runtime_state: dict[str, dict[str, float | bool | None]] = {}
        self.active_shocks: dict[str, object] = {}
        self.rng = np.random.default_rng(self.seed)
        self.event_log: list[dict[str, object]] = []
        self.policy_event_log: list[dict[str, object]] = []
        self.deployment_event_log: list[dict[str, object]] = []
        self.controller_event_log: list[dict[str, object]] = []
        self.deployed_intervention_ids: set[str] = set()
        self.node_states = {
            node.id: NodeState(
                spec=node,
                effective_servers=node.servers,
                effective_buffer_capacity=node.buffer_capacity,
            )
            for node in self.spec.spec.nodes
        }
        self.edge_states = {
            f"{edge.from_node}->{edge.to_node}": EdgeState(
                spec=edge,
                enabled=edge.enabled,
                travel_time=edge.travel_time,
                transfer_capacity=edge.transfer_capacity,
                next_available_time=self.now,
            )
            for edge in self.spec.spec.edges
        }
        self.base_node_queue_policies = {node.id: node.queue_policy for node in self.spec.spec.nodes}
        self.base_edge_enabled = {
            f"{edge.from_node}->{edge.to_node}": edge.enabled for edge in self.spec.spec.edges
        }
        self.base_edge_probabilities = {
            f"{edge.from_node}->{edge.to_node}": edge.routing.probability for edge in self.spec.spec.edges
        }
        self.policy_runtime_state = {
            policy.id: {
                "active": False,
                "active_stage_index": None,
                "max_stage_index": None,
                "activation_count": 0,
                "last_activation_time": None,
                "last_deactivation_time": None,
                "last_stage_change_time": None,
                "last_signal": None,
            }
            for policy in self.spec.spec.policies
        }
        self._arrival_max_rates = {
            id(arrival): max(self._max_arrival_rate(arrival), 1e-9) for arrival in self.spec.spec.arrivals
        }
        self.state = SimulationState(
            current_time=self.now,
            future_event_queue=self.event_queue,
            node_states=self.node_states,
            edge_states=self.edge_states,
            active_shocks=self.active_shocks,
        )
        for state in self.node_states.values():
            self._record_node_state(state, self.now)
        self._schedule_initial_events()

    def run(
        self,
        *,
        run_id: str | None = None,
        artifacts_dir: Path | None = None,
        capture_events: bool = False,
        deployments: list[tuple[float, InterventionSpec]] | None = None,
        controller: object | None = None,
    ) -> SimulationResult:
        """Execute the simulation until the configured horizon."""

        self.reset()
        self._schedule_deployments(deployments or [])
        self._schedule_controller(controller)
        horizon_end = self.spec.spec.clock.end

        while self.event_queue:
            event = heapq.heappop(self.event_queue)
            if event.time > horizon_end:
                break
            self._advance_time(event.time)
            self._process_event(event, capture_events=capture_events)
            self.processed_event_count += 1

        self._advance_time(horizon_end)
        metrics, node_metrics, class_metrics = summarize_metrics(
            self.spec,
            self.node_states,
            self.edge_states,
            event_count=self.processed_event_count,
            horizon=horizon_end - self.spec.spec.clock.start,
            departed_jobs=self.departed_jobs,
            external_arrivals=self.external_arrival_count,
            external_arrival_class_counts=self.external_arrival_class_counts,
            departed_class_counts=self.departed_class_counts,
            baseline_metrics=self.baseline_metrics,
        )
        edge_metrics = metrics.pop("__edge_metrics__")
        policy_schedule_rows = self._policy_schedule_rows(horizon_end)
        metrics["policy_schedule_count"] = float(len(self.spec.spec.policies))
        metrics["policy_activation_count"] = float(
            sum(1 for event in self.policy_event_log if event["event"] == "start")
        )
        metrics["adaptive_policy_activation_count"] = float(
            sum(
                1
                for event in self.policy_event_log
                if event["event"] == "start" and event.get("mode") == "threshold"
            )
        )
        metrics["policy_stage_change_count"] = float(
            sum(
                1
                for event in self.policy_event_log
                if event["event"] in {"stage_up", "stage_down"}
            )
        )
        metrics["policy_active_time"] = float(
            sum(row["active_duration"] for row in policy_schedule_rows)
        )
        metrics["deployment_count"] = float(len(self.deployment_event_log))
        metrics["first_deployment_time"] = (
            float(self.deployment_event_log[0]["time"])
            if self.deployment_event_log
            else 0.0
        )
        metrics["controller_tick_count"] = float(len(self.controller_event_log))
        metrics["controller_action_count"] = float(
            sum(1 for row in self.controller_event_log if row.get("action") not in {None, "observe"})
        )
        metrics["controller_retarget_count"] = float(
            sum(1 for row in self.controller_event_log if bool(row.get("retargeted", False)))
        )
        failure_reasons = evaluate_failure_conditions(
            self.spec.spec.failure_conditions,
            metrics,
            node_metrics,
        )
        result = SimulationResult(
            run_id=run_id or "simulation",
            seed=self.seed,
            status="completed",
            horizon=horizon_end - self.spec.spec.clock.start,
            event_count=self.processed_event_count,
            failure_triggered=bool(failure_reasons),
            failure_reasons=failure_reasons,
            metrics=metrics,
            node_metrics=node_metrics,
            edge_metrics=edge_metrics,
            class_metrics=class_metrics,
            timeline_events_path=None,
            plots={},
            artifacts_dir=str(artifacts_dir or ""),
        )
        if artifacts_dir is not None:
            self._write_metrics_artifacts(
                artifacts_dir,
                metrics,
                node_metrics,
                edge_metrics,
                class_metrics,
                policy_schedule_rows,
                capture_events,
            )
            if capture_events:
                result.timeline_events_path = str(artifacts_dir / "timeline_events.csv")
        return result

    def _schedule_initial_events(self) -> None:
        for arrival in self.spec.spec.arrivals:
            next_time = self._sample_next_arrival_time(arrival, self.now)
            if next_time is not None:
                self._schedule(next_time, 10, "arrival", {"arrival": arrival})
        for policy in self.spec.spec.policies:
            if policy.mode == "scheduled":
                self._schedule(policy.start, 6, "policy_start", {"policy": policy})
                if policy.end_time() is not None:
                    self._schedule(policy.end_time(), 94, "policy_end", {"policy": policy})
        for shock in self._flattened_shocks:
            self._schedule(shock.start, 5, "shock_start", {"shock": shock})
            if shock.end_time() is not None:
                self._schedule(shock.end_time(), 95, "shock_end", {"shock": shock})
        self._evaluate_threshold_policies()

    def _schedule_deployments(self, deployments: list[tuple[float, InterventionSpec]]) -> None:
        for time, intervention in sorted(deployments, key=lambda item: (item[0], item[1].id)):
            self._schedule(float(time), 7, "intervention_deploy", {"intervention": intervention})

    def _schedule_controller(self, controller: object | None) -> None:
        if controller is None or not hasattr(controller, "observation_schedule"):
            return
        schedule = controller.observation_schedule(
            start=float(self.spec.spec.clock.start),
            end=float(self.spec.spec.clock.end),
        )
        for time, observation_fraction in schedule:
            self._schedule(
                float(time),
                8,
                "controller_tick",
                {
                    "controller": controller,
                    "observation_fraction": float(observation_fraction),
                },
            )

    def _schedule(self, time: float, priority: int, kind: str, payload: dict[str, object]) -> None:
        self.event_sequence += 1
        heapq.heappush(self.event_queue, Event(time=time, priority=priority, sequence=self.event_sequence, kind=kind, payload=payload))

    def _advance_time(self, new_time: float) -> None:
        dt = max(0.0, new_time - self.now)
        if dt <= 0:
            self.now = new_time
            self.state.current_time = self.now
            return
        for state in self.node_states.values():
            state.queue_integral += len(state.queue) * dt
            state.holding_integral += state.routed_hold_count * dt
            utilization = self._utilization(state)
            state.utilization_integral += utilization * dt
            self._update_degradation(state, new_time)
        self.now = new_time
        self.state.current_time = self.now

    def _process_event(self, event: Event, *, capture_events: bool) -> None:
        if event.kind == "arrival":
            self._process_arrival_event(event.payload["arrival"])  # type: ignore[index]
        elif event.kind == "internal_arrival":
            self._accept_job(event.payload["target"], event.payload["job"])  # type: ignore[index]
        elif event.kind == "service_complete":
            self._process_service_completion(event.payload["node_id"], event.payload["service_id"])  # type: ignore[index]
        elif event.kind == "routing_retry":
            self._process_routing_retry(
                event.payload["node_id"],  # type: ignore[index]
                event.payload["job"],  # type: ignore[index]
            )
        elif event.kind == "shock_start":
            self._process_shock_start(event.payload["shock"])  # type: ignore[index]
        elif event.kind == "shock_end":
            self._process_shock_end(event.payload["shock"])  # type: ignore[index]
        elif event.kind == "policy_start":
            self._process_policy_start(event.payload["policy"])  # type: ignore[index]
        elif event.kind == "policy_end":
            self._process_policy_end(event.payload["policy"])  # type: ignore[index]
        elif event.kind == "intervention_deploy":
            self._process_intervention_deploy(event.payload["intervention"])  # type: ignore[index]
        elif event.kind == "controller_tick":
            self._process_controller_tick(
                event.payload["controller"],  # type: ignore[index]
                float(event.payload["observation_fraction"]),  # type: ignore[index]
            )
        self._evaluate_threshold_policies()
        if capture_events:
            self.event_log.append(
                {
                    "time": self.now,
                    "kind": event.kind,
                    "payload": self._stringify_payload(event.payload),
                }
            )

    def _process_arrival_event(self, arrival: ArrivalSpec) -> None:
        for _ in range(arrival.batch_size):
            self.external_arrival_count += 1
            class_id = self._sample_class(arrival)
            self.external_arrival_class_counts[class_id] = self.external_arrival_class_counts.get(class_id, 0) + 1
            self.job_sequence += 1
            self.queue_sequence += 1
            job = Job(
                job_id=self.job_sequence,
                class_id=class_id,
                created_at=self.now,
                node_arrival_time=self.now,
                queue_sequence=self.queue_sequence,
            )
            self._accept_job(arrival.node, job)
        next_time = self._sample_next_arrival_time(arrival, self.now)
        if next_time is not None:
            self._schedule(next_time, 10, "arrival", {"arrival": arrival})

    def _accept_job(self, node_id: str, job: Job) -> None:
        state = self.node_states[node_id]
        state.arrival_count += 1
        state.class_arrival_counts[job.class_id] = state.class_arrival_counts.get(job.class_id, 0) + 1
        job.node_arrival_time = self.now
        job.history.append(node_id)
        if len(state.in_service) < state.effective_servers and not state.queue:
            self._start_service(node_id, job)
        else:
            accepted = enqueue_job(state, job)
            if accepted:
                self._record_node_state(state, self.now)
            else:
                state.class_dropped_counts[job.class_id] = state.class_dropped_counts.get(job.class_id, 0) + 1
                self._update_degradation(state, self.now)
                self._record_node_state(state, self.now)

    def _start_service(self, node_id: str, job: Job) -> None:
        state = self.node_states[node_id]
        service_time = self._sample_service_time(state)
        self.event_sequence += 1
        service_id = self.event_sequence
        state.in_service[service_id] = (job, self.now, self.now + service_time)
        wait_time = max(0.0, self.now - job.node_arrival_time)
        state.wait_times.append(wait_time)
        state.class_wait_times.setdefault(job.class_id, []).append(wait_time)
        state.service_times.append(service_time)
        self._schedule(self.now + service_time, 20, "service_complete", {"node_id": node_id, "service_id": service_id})
        self._record_node_state(state, self.now)

    def _fill_servers(self, node_id: str) -> None:
        state = self.node_states[node_id]
        while len(state.in_service) < state.effective_servers and state.queue:
            job = select_next_job(state, self.spec.class_priorities)
            if job is None:
                break
            self._start_service(node_id, job)

    def _process_service_completion(self, node_id: str, service_id: int) -> None:
        state = self.node_states[node_id]
        payload = state.in_service.pop(service_id, None)
        if payload is None:
            return
        job, _, _ = payload
        state.completion_count += 1
        state.class_completion_counts[job.class_id] = state.class_completion_counts.get(job.class_id, 0) + 1
        self._record_node_state(state, self.now)
        self._dispatch_downstream(node_id, job)
        self._fill_servers(node_id)

    def _process_routing_retry(self, node_id: str, job: Job) -> None:
        self._dispatch_downstream(node_id, job, from_hold=True)

    def _process_shock_start(self, shock) -> None:
        self.active_shocks[shock.id] = shock
        target = shock.target
        if target is None:
            return
        if target in self.node_states:
            state = self.node_states[target]
            apply_shock(state, shock, self.now)
            self._record_node_state(state, self.now)
            self._fill_servers(target)
            return
        edge_state = self.edge_states.get(target)
        if edge_state is not None:
            apply_shock(edge_state, shock, self.now)

    def _process_shock_end(self, shock) -> None:
        self.active_shocks.pop(shock.id, None)
        target = shock.target
        if target is None:
            return
        if target in self.node_states:
            state = self.node_states[target]
            remove_shock(state, shock, self.now)
            self._record_node_state(state, self.now)
            self._fill_servers(target)
            return
        edge_state = self.edge_states.get(target)
        if edge_state is not None:
            remove_shock(edge_state, shock, self.now)

    def _process_policy_start(self, policy: PolicyScheduleSpec) -> None:
        self._activate_policy(policy, event_kind="start", trigger_value=None)

    def _process_policy_end(self, policy: PolicyScheduleSpec) -> None:
        self._deactivate_policy(policy, trigger_value=None)

    def _process_intervention_deploy(self, intervention: InterventionSpec) -> None:
        self._deploy_intervention_runtime(intervention)

    def _process_controller_tick(self, controller: object, observation_fraction: float) -> None:
        if not hasattr(controller, "on_tick"):
            return
        decision = controller.on_tick(self, observation_fraction=observation_fraction)
        normalized = self._normalize_controller_decision(decision)
        log_row = {
            "time": self.now,
            "observation_fraction": observation_fraction,
            **normalized.log,
        }
        self.controller_event_log.append(log_row)
        for intervention in normalized.interventions:
            self._deploy_intervention_runtime(intervention)

    def _normalize_controller_decision(self, decision: object) -> ControllerDecision:
        if decision is None:
            return ControllerDecision(log={"action": "observe", "deployment_count": 0})
        if isinstance(decision, ControllerDecision):
            if "action" not in decision.log:
                decision.log["action"] = "observe"
            decision.log.setdefault("deployment_count", len(decision.interventions))
            return decision
        if isinstance(decision, list):
            interventions = [item for item in decision if isinstance(item, InterventionSpec)]
            return ControllerDecision(
                interventions=interventions,
                log={
                    "action": "deploy" if interventions else "observe",
                    "deployment_count": len(interventions),
                },
            )
        raise TypeError("Controller decisions must be None, ControllerDecision, or a list of interventions.")

    def _deploy_intervention_runtime(
        self,
        intervention: InterventionSpec,
        *,
        active_stack: tuple[str, ...] = (),
    ) -> None:
        if intervention.id in self.deployed_intervention_ids:
            return
        if intervention.action_type == "bundle" or intervention.bundle_members:
            if intervention.id in active_stack:
                raise ValueError(f"Bundle cycle detected involving '{intervention.id}'.")
            lookup = {candidate.id: candidate for candidate in self.spec.spec.interventions}
            for member_id in intervention.bundle_members:
                member = lookup.get(member_id)
                if member is None:
                    raise ValueError(
                        f"Unknown bundle member '{member_id}' in deployed intervention '{intervention.id}'."
                    )
                self._deploy_intervention_runtime(member, active_stack=(*active_stack, intervention.id))
            self.deployed_intervention_ids.add(intervention.id)
            self.deployment_event_log.append(
                {
                    "time": self.now,
                    "intervention_id": intervention.id,
                    "label": intervention.label,
                    "target": intervention.target,
                    "action_type": intervention.action_type,
                    "source": (intervention.applicability_constraints or {}).get("source", "authored"),
                    "deployed_policy_id": None,
                }
            )
            return

        deployed_policy_id = None
        node_lookup = self.node_states
        edge_lookup = self.edge_states
        action_type = intervention.action_type
        if action_type.startswith("scheduled_"):
            deployed_policy_id = self._install_policy_from_intervention(
                intervention,
                mode="scheduled",
                action_type=action_type.removeprefix("scheduled_"),
            )
        elif action_type.startswith("threshold_"):
            deployed_policy_id = self._install_policy_from_intervention(
                intervention,
                mode="threshold",
                action_type=action_type.removeprefix("threshold_"),
            )
        elif intervention.target in node_lookup:
            self._deploy_node_intervention(intervention)
        elif intervention.target in edge_lookup:
            self._deploy_edge_intervention(intervention)
        else:
            raise ValueError(f"Unknown deployment target '{intervention.target}'.")

        self.deployed_intervention_ids.add(intervention.id)
        self.deployment_event_log.append(
            {
                "time": self.now,
                "intervention_id": intervention.id,
                "label": intervention.label,
                "target": intervention.target,
                "action_type": intervention.action_type,
                "source": (intervention.applicability_constraints or {}).get("source", "authored"),
                "deployed_policy_id": deployed_policy_id,
            }
        )

    def _deploy_node_intervention(self, intervention: InterventionSpec) -> None:
        state = self.node_states[intervention.target]
        action_type = intervention.action_type
        if action_type == "add_servers":
            state.spec.servers += int(intervention.delta or 0)
            refresh_node_state(state, self.now)
            self._record_node_state(state, self.now)
            self._fill_servers(intervention.target)
            return
        if action_type == "increase_buffer_capacity":
            current = state.spec.buffer_capacity or 0
            state.spec.buffer_capacity = current + int(intervention.delta or 0)
            refresh_node_state(state, self.now)
            self._record_node_state(state, self.now)
            return
        if action_type == "reduce_service_time_factor":
            factor = intervention.replacement if intervention.replacement is not None else intervention.delta
            factor = float(factor if factor is not None else 1.0)
            _apply_service_time_factor(state.spec, factor)
            return
        if action_type == "priority_policy_change":
            replacement = str(intervention.replacement or intervention.parameter or "priority")
            self.base_node_queue_policies[intervention.target] = replacement
            self._recompute_policy_state()
            return
        raise ValueError(f"Unsupported node deployment '{action_type}'.")

    def _deploy_edge_intervention(self, intervention: InterventionSpec) -> None:
        edge_state = self.edge_states[intervention.target]
        action_type = intervention.action_type
        if action_type == "enable_backup_edge":
            self.base_edge_enabled[intervention.target] = True
            edge_state.spec.enabled = True
            self._recompute_policy_state()
            return
        if action_type == "reroute_fraction":
            edge_key = intervention.target
            current_probability = self.base_edge_probabilities.get(edge_key, edge_state.spec.routing.probability)
            updated_probability = min(1.0, current_probability + float(intervention.delta or 0.0))
            self.base_edge_probabilities[edge_key] = updated_probability
            edge_state.spec.routing.probability = updated_probability
            siblings = [
                candidate
                for candidate in self.spec.spec.edges
                if candidate.from_node == edge_state.spec.from_node and f"{candidate.from_node}->{candidate.to_node}" != edge_key
            ]
            if siblings:
                residual = max(0.0, 1.0 - updated_probability)
                share = residual / len(siblings)
                for sibling in siblings:
                    sibling_key = f"{sibling.from_node}->{sibling.to_node}"
                    self.base_edge_probabilities[sibling_key] = share
                    sibling.routing.probability = share
            self._recompute_policy_state()
            return
        raise ValueError(f"Unsupported edge deployment '{action_type}'.")

    def _install_policy_from_intervention(
        self,
        intervention: InterventionSpec,
        *,
        mode: str,
        action_type: str,
    ) -> str:
        policy = PolicyScheduleSpec(
            id=f"deploy__{intervention.id}",
            label=intervention.label,
            target=intervention.target,
            action_type=action_type,
            mode=mode,
            start=self.now,
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
            applicability_constraints={
                **(intervention.applicability_constraints or {}),
                "deployed_runtime": True,
                "source": (intervention.applicability_constraints or {}).get("source", "runtime_deployment"),
            },
        )
        self.spec.spec.policies.append(policy)
        self.policy_runtime_state[policy.id] = {
            "active": False,
            "active_stage_index": None,
            "max_stage_index": None,
            "activation_count": 0,
            "last_activation_time": None,
            "last_deactivation_time": None,
            "last_stage_change_time": None,
            "last_signal": None,
        }
        if policy.end_time() is not None:
            self._schedule(policy.end_time(), 94, "policy_end", {"policy": policy})
        if policy.mode == "scheduled":
            self._activate_policy(policy, event_kind="deployment_start", trigger_value=None)
        return policy.id

    def _activate_policy(
        self,
        policy: PolicyScheduleSpec,
        *,
        event_kind: str,
        trigger_value: float | None,
        stage_index: int | None = None,
    ) -> None:
        runtime = self.policy_runtime_state.setdefault(
            policy.id,
            {
                "active": False,
                "active_stage_index": None,
                "max_stage_index": None,
                "activation_count": 0,
                "last_activation_time": None,
                "last_deactivation_time": None,
                "last_stage_change_time": None,
                "last_signal": None,
            },
        )
        if runtime.get("active"):
            return
        runtime["active"] = True
        runtime["active_stage_index"] = stage_index
        runtime["max_stage_index"] = stage_index
        runtime["activation_count"] = int(runtime.get("activation_count") or 0) + 1
        runtime["last_activation_time"] = self.now
        runtime["last_stage_change_time"] = self.now
        runtime["last_signal"] = trigger_value
        self.active_policies[policy.id] = policy
        self._recompute_policy_state()
        self.policy_event_log.append(
            {
                "time": self.now,
                "policy_id": policy.id,
                "label": policy.label,
                "target": policy.target,
                "action_type": policy.action_type,
                "mode": policy.mode,
                "event": event_kind,
                "trigger_metric": policy.trigger_metric,
                "trigger_node": policy.trigger_node,
                "trigger_value": trigger_value,
                "stage_index": stage_index,
                "stage_id": self._stage_id(policy, stage_index),
            }
        )

    def _deactivate_policy(
        self,
        policy: PolicyScheduleSpec,
        *,
        trigger_value: float | None,
    ) -> None:
        runtime = self.policy_runtime_state.setdefault(
            policy.id,
            {
                "active": False,
                "active_stage_index": None,
                "max_stage_index": None,
                "activation_count": 0,
                "last_activation_time": None,
                "last_deactivation_time": None,
                "last_stage_change_time": None,
                "last_signal": None,
            },
        )
        if not runtime.get("active"):
            return
        prior_stage_index = runtime.get("active_stage_index")
        runtime["active"] = False
        runtime["active_stage_index"] = None
        runtime["last_deactivation_time"] = self.now
        runtime["last_stage_change_time"] = self.now
        runtime["last_signal"] = trigger_value
        self.active_policies.pop(policy.id, None)
        self._recompute_policy_state()
        self.policy_event_log.append(
            {
                "time": self.now,
                "policy_id": policy.id,
                "label": policy.label,
                "target": policy.target,
                "action_type": policy.action_type,
                "mode": policy.mode,
                "event": "end",
                "trigger_metric": policy.trigger_metric,
                "trigger_node": policy.trigger_node,
                "trigger_value": trigger_value,
                "stage_index": prior_stage_index,
                "stage_id": self._stage_id(policy, prior_stage_index),
            }
        )

    def _evaluate_threshold_policies(self) -> None:
        for policy in self.spec.spec.policies:
            if policy.mode != "threshold":
                continue
            signal = self._policy_signal(policy)
            runtime = self.policy_runtime_state.setdefault(
                policy.id,
                {
                    "active": False,
                    "active_stage_index": None,
                    "max_stage_index": None,
                    "activation_count": 0,
                    "last_activation_time": None,
                    "last_deactivation_time": None,
                    "last_stage_change_time": None,
                    "last_signal": None,
                },
            )
            runtime["last_signal"] = signal
            active = bool(runtime.get("active"))
            desired_stage = self._desired_policy_stage(policy, signal)
            if not active:
                last_deactivation = runtime.get("last_deactivation_time")
                if last_deactivation is not None and self.now - float(last_deactivation) < policy.cooldown:
                    continue
                if desired_stage is not None:
                    self._activate_policy(
                        policy,
                        event_kind="start",
                        trigger_value=signal,
                        stage_index=desired_stage,
                    )
                continue
            current_stage = runtime.get("active_stage_index")
            if desired_stage is not None and current_stage is not None and desired_stage > int(current_stage):
                self._change_policy_stage(policy, desired_stage, trigger_value=signal)
                continue
            last_change = runtime.get("last_stage_change_time")
            if last_change is not None and self.now - float(last_change) < policy.min_active_duration:
                continue
            if current_stage is None:
                continue
            if desired_stage is None:
                if signal <= self._policy_clear_threshold(policy, int(current_stage)):
                    self._deactivate_policy(policy, trigger_value=signal)
                continue
            if desired_stage < int(current_stage) and signal <= self._policy_clear_threshold(policy, int(current_stage)):
                self._change_policy_stage(policy, desired_stage, trigger_value=signal)

    def _change_policy_stage(
        self,
        policy: PolicyScheduleSpec,
        stage_index: int,
        *,
        trigger_value: float | None,
    ) -> None:
        runtime = self.policy_runtime_state.setdefault(
            policy.id,
            {
                "active": False,
                "active_stage_index": None,
                "max_stage_index": None,
                "activation_count": 0,
                "last_activation_time": None,
                "last_deactivation_time": None,
                "last_stage_change_time": None,
                "last_signal": None,
            },
        )
        current_stage = runtime.get("active_stage_index")
        if current_stage == stage_index:
            return
        runtime["active_stage_index"] = stage_index
        runtime["max_stage_index"] = max(
            int(runtime["max_stage_index"]) if runtime.get("max_stage_index") is not None else stage_index,
            stage_index,
        )
        runtime["last_stage_change_time"] = self.now
        runtime["last_signal"] = trigger_value
        self._recompute_policy_state()
        self.policy_event_log.append(
            {
                "time": self.now,
                "policy_id": policy.id,
                "label": policy.label,
                "target": policy.target,
                "action_type": policy.action_type,
                "mode": policy.mode,
                "event": "stage_up" if current_stage is None or stage_index > int(current_stage) else "stage_down",
                "trigger_metric": policy.trigger_metric,
                "trigger_node": policy.trigger_node,
                "trigger_value": trigger_value,
                "stage_index": stage_index,
                "stage_id": self._stage_id(policy, stage_index),
            }
        )

    def _policy_signal(self, policy: PolicyScheduleSpec) -> float:
        node_id = policy.trigger_node
        if node_id is None:
            if policy.target in self.node_states:
                node_id = policy.target
            elif policy.target in self.edge_states:
                node_id = self.edge_states[policy.target].spec.from_node
        if node_id is None or node_id not in self.node_states:
            return 0.0
        state = self.node_states[node_id]
        if policy.trigger_metric == "utilization":
            return self._utilization(state)
        if policy.trigger_metric == "holding_count":
            return float(state.routed_hold_count)
        return float(len(state.queue))

    def _policy_stages(self, policy: PolicyScheduleSpec) -> list[PolicyStageSpec]:
        if policy.stages:
            return policy.stages
        return [
            PolicyStageSpec(
                id="stage_1",
                label=policy.label,
                trigger_threshold=float(policy.trigger_threshold or 0.0),
                clear_threshold=policy.clear_threshold,
                action_type=policy.action_type,
                parameter=policy.parameter,
                delta=policy.delta,
                replacement=policy.replacement,
            )
        ]

    def _desired_policy_stage(self, policy: PolicyScheduleSpec, signal: float) -> int | None:
        desired_stage: int | None = None
        for index, stage in enumerate(self._policy_stages(policy)):
            if signal >= float(stage.trigger_threshold):
                desired_stage = index
        return desired_stage

    def _policy_clear_threshold(
        self,
        policy: PolicyScheduleSpec,
        stage_index: int | None = None,
    ) -> float:
        stages = self._policy_stages(policy)
        if stage_index is not None and 0 <= stage_index < len(stages):
            stage_clear_threshold = stages[stage_index].clear_threshold
            if stage_clear_threshold is not None:
                return float(stage_clear_threshold)
            return _default_clear_threshold(float(stages[stage_index].trigger_threshold))
        if policy.clear_threshold is not None:
            return float(policy.clear_threshold)
        return _default_clear_threshold(float(policy.trigger_threshold or 0.0))

    def _policy_action_values(self, policy: PolicyScheduleSpec) -> tuple[str, float | None, object | None]:
        runtime = self.policy_runtime_state.get(policy.id, {})
        stage_index = runtime.get("active_stage_index")
        if stage_index is None or not policy.stages:
            return policy.action_type, policy.delta, policy.replacement
        stage = policy.stages[int(stage_index)]
        return (
            stage.action_type or policy.action_type,
            stage.delta if stage.delta is not None else policy.delta,
            stage.replacement if stage.replacement is not None else policy.replacement,
        )

    def _stage_id(self, policy: PolicyScheduleSpec, stage_index: int | None) -> str | None:
        if stage_index is None:
            return None
        stages = self._policy_stages(policy)
        if not 0 <= stage_index < len(stages):
            return None
        return stages[stage_index].id

    def _recompute_policy_state(self) -> None:
        for node_id, state in self.node_states.items():
            state.spec.queue_policy = self.base_node_queue_policies[node_id]
        for edge_id, edge_state in self.edge_states.items():
            edge_state.spec.enabled = self.base_edge_enabled[edge_id]
            edge_state.spec.routing.probability = self.base_edge_probabilities[edge_id]
        for policy in sorted(
            self.active_policies.values(),
            key=lambda item: (0 if item.mode == "scheduled" else 1, item.start, item.id),
        ):
            self._apply_policy_overlay(policy)
        for edge_state in self.edge_states.values():
            refresh_edge_state(edge_state)
        for node_id, state in self.node_states.items():
            self._record_node_state(state, self.now)
            if state.queue and len(state.in_service) < state.effective_servers:
                self._fill_servers(node_id)

    def _apply_policy_overlay(self, policy: PolicyScheduleSpec) -> None:
        action_type, delta, replacement = self._policy_action_values(policy)
        if policy.target in self.node_states:
            state = self.node_states[policy.target]
            if action_type == "priority_policy_change":
                resolved_replacement = str(replacement or policy.parameter or "priority")
                state.spec.queue_policy = resolved_replacement
            return
        edge_state = self.edge_states.get(policy.target)
        if edge_state is None:
            return
        if action_type == "enable_backup_edge":
            edge_state.spec.enabled = True
            return
        if action_type != "reroute_fraction":
            return
        edge_state.spec.routing.probability = min(
            1.0,
            edge_state.spec.routing.probability + float(delta or 0.0),
        )
        siblings = [
            candidate
            for candidate in self.spec.spec.edges
            if candidate.from_node == edge_state.spec.from_node and candidate is not edge_state.spec
        ]
        if siblings:
            residual = max(0.0, 1.0 - edge_state.spec.routing.probability)
            share = residual / len(siblings)
            for sibling in siblings:
                sibling.routing.probability = share

    def _dispatch_downstream(self, node_id: str, job: Job, *, from_hold: bool = False) -> None:
        outgoing_edges = self.spec.outgoing_edges.get(node_id, [])
        if not outgoing_edges:
            self.departed_jobs += 1
            self.departed_class_counts[job.class_id] = self.departed_class_counts.get(job.class_id, 0) + 1
            if from_hold:
                self.node_states[node_id].routed_hold_count = max(
                    0,
                    self.node_states[node_id].routed_hold_count - 1,
                )
            return

        edge_state = choose_downstream_edge(self.spec, self.edge_states, node_id, self.rng)
        if edge_state is None or not self._schedule_edge_transfer(edge_state, job):
            self._hold_for_routing(node_id, job, count_new_hold=not from_hold)
            return

        if from_hold:
            self.node_states[node_id].routed_hold_count = max(
                0,
                self.node_states[node_id].routed_hold_count - 1,
            )
            self._record_node_state(self.node_states[node_id], self.now)

    def _hold_for_routing(self, node_id: str, job: Job, *, count_new_hold: bool) -> None:
        state = self.node_states[node_id]
        state.blocked_routing_count += 1
        if count_new_hold:
            state.routed_hold_count += 1
        self._record_node_state(state, self.now)
        self._schedule(self.now + 1.0, 25, "routing_retry", {"node_id": node_id, "job": job})

    def _schedule_edge_transfer(self, edge_state: EdgeState, job: Job) -> bool:
        if not edge_state.enabled:
            edge_state.blocked_count += 1
            self._update_edge_degradation(edge_state, self.now, delayed=True)
            return False
        if edge_state.transfer_capacity is not None and edge_state.transfer_capacity <= 0:
            edge_state.blocked_count += 1
            self._update_edge_degradation(edge_state, self.now, delayed=True)
            return False

        departure_time = self.now
        if edge_state.transfer_capacity:
            departure_time = max(self.now, edge_state.next_available_time)
            spacing = 1.0 / max(edge_state.transfer_capacity, 1e-9)
            edge_state.next_available_time = departure_time + spacing
        delay = max(0.0, departure_time - self.now)
        if delay > 0:
            edge_state.blocked_count += 1
            edge_state.total_delay += delay
            edge_state.max_delay = max(edge_state.max_delay, delay)
        edge_state.transferred_count += 1
        self._update_edge_degradation(edge_state, departure_time, delayed=delay > 0)
        downstream_job = Job(
            job_id=job.job_id,
            class_id=job.class_id,
            created_at=job.created_at,
            node_arrival_time=departure_time + edge_state.travel_time,
            queue_sequence=job.queue_sequence,
            history=list(job.history),
        )
        self._schedule(
            departure_time + edge_state.travel_time,
            15,
            "internal_arrival",
            {"target": edge_state.spec.to_node, "job": downstream_job},
        )
        return True

    def _sample_service_time(self, state: NodeState) -> float:
        config = state.spec.service_time
        factor = max(state.service_time_factor, 1e-9)
        distribution = config.distribution
        if distribution == "exponential":
            mean = config.mean if config.mean is not None else 1.0 / float(config.rate)
            return float(self.rng.exponential(mean * factor))
        if distribution == "gamma":
            return float(self.rng.gamma(shape=float(config.shape), scale=float(config.scale) * factor))
        if distribution == "lognormal":
            return float(self.rng.lognormal(mean=float(config.mu), sigma=float(config.sigma)) * factor)
        return float(config.value) * factor

    def _sample_class(self, arrival: ArrivalSpec) -> str:
        if not arrival.class_mix:
            return "default"
        labels = list(arrival.class_mix)
        probabilities = np.array(list(arrival.class_mix.values()), dtype=float)
        probabilities = probabilities / probabilities.sum()
        return str(self.rng.choice(labels, p=probabilities))

    def _sample_next_arrival_time(self, arrival: ArrivalSpec, after_time: float) -> float | None:
        max_rate = self._arrival_max_rates[id(arrival)]
        current = after_time
        clock_end = self.spec.spec.clock.end
        while current <= clock_end:
            current += float(self.rng.exponential(1.0 / max_rate))
            if current > clock_end:
                return None
            rate = self._arrival_rate(arrival, current)
            if rate <= 0:
                continue
            if self.rng.random() <= min(1.0, rate / max_rate):
                return current
        return None

    def _arrival_rate(self, arrival: ArrivalSpec, now: float) -> float:
        process = arrival.process
        base_rate = process.base_rate if process.base_rate is not None else process.rate or 0.0
        seasonality_factor = 1.0
        if process.type == "nonhomogeneous_poisson" and process.seasonality is not None:
            period = _period_to_minutes(process.seasonality.period)
            angle = 2.0 * math.pi * (now - self.spec.spec.clock.start) / max(period, 1.0)
            seasonality_factor = max(0.0, 1.0 + process.seasonality.amplitude * math.sin(angle))
        demand_factor = demand_multiplier_at_time(self._flattened_shocks, arrival.node, now)
        return max(0.0, base_rate * seasonality_factor * demand_factor)

    def _max_arrival_rate(self, arrival: ArrivalSpec) -> float:
        process = arrival.process
        base_rate = process.base_rate if process.base_rate is not None else process.rate or 0.0
        amplitude = abs(process.seasonality.amplitude) if process.seasonality is not None else 0.0
        multiplier = 1.0
        for shock in self._flattened_shocks:
            if shock.type == "demand_multiplier" and shock.target == arrival.node:
                multiplier *= shock.factor or shock.value or 1.0
        return max(base_rate * (1.0 + amplitude) * multiplier, 1e-9)

    def _record_node_state(self, state: NodeState, when: float) -> None:
        queue_length = float(len(state.queue))
        utilization = self._utilization(state)
        if state.queue_times and state.queue_times[-1] == when:
            state.queue_lengths[-1] = queue_length
        else:
            state.queue_times.append(when)
            state.queue_lengths.append(queue_length)
        if state.utilization_times and state.utilization_times[-1] == when:
            state.utilization_values[-1] = utilization
        else:
            state.utilization_times.append(when)
            state.utilization_values.append(utilization)
        self._update_degradation(state, when)

    def _update_degradation(self, state: NodeState, when: float) -> None:
        degraded = (
            state.overflow_count > 0
            or len(state.queue) > 0
            or state.routed_hold_count > 0
            or self._utilization(state) > 0.95
        )
        state.degraded = degraded
        if degraded and state.first_degraded_time is None:
            state.first_degraded_time = when
        if degraded:
            state.last_degraded_time = when

    def _update_edge_degradation(
        self,
        edge_state: EdgeState,
        when: float,
        *,
        delayed: bool,
    ) -> None:
        degraded = delayed or not edge_state.enabled
        edge_state.degraded = degraded
        if degraded and edge_state.first_degraded_time is None:
            edge_state.first_degraded_time = when
        if degraded:
            edge_state.last_degraded_time = when

    def _utilization(self, state: NodeState) -> float:
        if state.effective_servers <= 0:
            return 1.0 if state.in_service else 0.0
        return min(1.0, len(state.in_service) / state.effective_servers)

    def _write_metrics_artifacts(
        self,
        artifacts_dir: Path,
        metrics: dict[str, float],
        node_metrics: dict[str, dict[str, float]],
        edge_metrics: dict[str, dict[str, float]],
        class_metrics: dict[str, dict[str, float]],
        policy_schedule_rows: list[dict[str, object]],
        capture_events: bool,
    ) -> None:
        metrics_frame = pd.DataFrame([{"metric": key, "value": value} for key, value in metrics.items()])
        node_frame = pd.DataFrame(
            [
                {"node": node_id, **node_metric}
                for node_id, node_metric in node_metrics.items()
            ]
        )
        edge_frame = pd.DataFrame(
            [
                {"edge": edge_id, **edge_metric}
                for edge_id, edge_metric in edge_metrics.items()
            ]
        )
        class_frame = pd.DataFrame(
            [
                {"class_id": class_id, **class_metric}
                for class_id, class_metric in class_metrics.items()
            ]
        )
        policy_schedule_frame = pd.DataFrame(policy_schedule_rows)
        policy_event_frame = pd.DataFrame(self.policy_event_log)
        controller_event_frame = pd.DataFrame(self.controller_event_log)
        write_dataframe(artifacts_dir / "metrics.csv", metrics_frame)
        write_dataframe(artifacts_dir / "node_metrics.csv", node_frame)
        write_dataframe(artifacts_dir / "edge_metrics.csv", edge_frame)
        write_dataframe(artifacts_dir / "class_metrics.csv", class_frame)
        write_dataframe(artifacts_dir / "policy_schedule.csv", policy_schedule_frame)
        write_dataframe(artifacts_dir / "policy_events.csv", policy_event_frame)
        write_dataframe(artifacts_dir / "deployment_events.csv", pd.DataFrame(self.deployment_event_log))
        write_dataframe(artifacts_dir / "controller_events.csv", controller_event_frame)
        queue_series = []
        utilization_series = []
        for node_id, state in self.node_states.items():
            queue_series.extend(
                {"node": node_id, "time": time, "queue_length": value}
                for time, value in zip(state.queue_times, state.queue_lengths, strict=True)
            )
            utilization_series.extend(
                {"node": node_id, "time": time, "utilization": value}
                for time, value in zip(state.utilization_times, state.utilization_values, strict=True)
            )
        write_dataframe(artifacts_dir / "queue_timeseries.csv", pd.DataFrame(queue_series))
        write_dataframe(artifacts_dir / "utilization_timeseries.csv", pd.DataFrame(utilization_series))
        if capture_events:
            write_dataframe(artifacts_dir / "timeline_events.csv", pd.DataFrame(self.event_log))

    def _policy_schedule_rows(self, horizon_end: float) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for policy in self.spec.spec.policies:
            event_rows = [event for event in self.policy_event_log if event["policy_id"] == policy.id]
            intervals = self._policy_intervals(policy.id, horizon_end)
            first_activation_time = intervals[0][0] if intervals else None
            last_deactivation_time = intervals[-1][1] if intervals else None
            runtime = self.policy_runtime_state.get(policy.id, {})
            rows.append(
                {
                    "policy_id": policy.id,
                    "label": policy.label,
                    "target": policy.target,
                    "action_type": policy.action_type,
                    "mode": policy.mode,
                    "stage_count": len(self._policy_stages(policy)),
                    "start": policy.start,
                    "duration": policy.duration,
                    "end": policy.end_time(),
                    "replacement": policy.replacement,
                    "delta": policy.delta,
                    "trigger_metric": policy.trigger_metric,
                    "trigger_node": policy.trigger_node,
                    "trigger_threshold": policy.trigger_threshold,
                    "clear_threshold": self._policy_clear_threshold(policy) if policy.mode == "threshold" else None,
                    "min_active_duration": policy.min_active_duration,
                    "cooldown": policy.cooldown,
                    "source": (policy.applicability_constraints or {}).get("source", "authored"),
                    "generated": bool((policy.applicability_constraints or {}).get("generated", False)),
                    "active_duration": float(sum(end - start for start, end in intervals)),
                    "activated": bool(event_rows),
                    "activation_count": sum(1 for event in event_rows if event["event"] == "start"),
                    "stage_change_count": sum(
                        1 for event in event_rows if event["event"] in {"stage_up", "stage_down"}
                    ),
                    "max_stage_reached": runtime.get("max_stage_index"),
                    "first_activation_time": first_activation_time,
                    "last_deactivation_time": last_deactivation_time,
                    "active_at_horizon": policy.id in self.active_policies,
                }
            )
        return rows

    def _policy_intervals(self, policy_id: str, horizon_end: float) -> list[tuple[float, float]]:
        starts = [
            float(event["time"])
            for event in self.policy_event_log
            if event["policy_id"] == policy_id and event["event"] == "start"
        ]
        ends = [
            float(event["time"])
            for event in self.policy_event_log
            if event["policy_id"] == policy_id and event["event"] == "end"
        ]
        intervals: list[tuple[float, float]] = []
        for index, start in enumerate(starts):
            end = ends[index] if index < len(ends) else horizon_end
            intervals.append((start, min(end, horizon_end)))
        return intervals

    def _stringify_payload(self, payload: dict[str, object]) -> dict[str, object]:
        rendered: dict[str, object] = {}
        for key, value in payload.items():
            if hasattr(value, "id"):
                rendered[key] = value.id
            elif hasattr(value, "node"):
                rendered[key] = value.node
            elif isinstance(value, Job):
                rendered[key] = value.job_id
            else:
                rendered[key] = str(value)
        return rendered


def _period_to_minutes(period: str | float) -> float:
    if isinstance(period, (int, float)):
        return float(period)
    mapping = {
        "hourly": 60.0,
        "daily": 1440.0,
        "weekly": 10080.0,
    }
    return mapping.get(period, 1440.0)


def _default_clear_threshold(trigger: float) -> float:
    if trigger <= 1.0:
        return max(0.0, 0.8 * trigger)
    return max(0.0, trigger - max(1.0, 0.2 * trigger))


def _apply_service_time_factor(node_spec, factor: float) -> None:
    config = node_spec.service_time
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
