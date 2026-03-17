# Metrics

StressLab emits both system-level and node-level metrics.

## Core metrics

- `throughput`
- `throughput_efficiency`
- `throughput_loss`
- `mean_wait`
- `p95_wait`
- `queue_integral`
- `holding_integral`
- `backlog_integral`
- `utilization`
- `recovery_time`
- `cascade_size`
- `cascade_norm`
- `blocked_transfers`
- `mean_edge_delay`
- `dropped_jobs`
- `fairness_score`
- `fairness_degradation`
- `wait_inequity`
- `throughput_inequity`
- `drop_inequity`
- `priority_wait_gradient`
- `policy_schedule_count`
- `policy_activation_count`
- `adaptive_policy_activation_count`
- `policy_stage_change_count`
- `policy_active_time`
- `deployment_count`
- `first_deployment_time`
- `resilience_score`

## Node metrics

- `mean_wait`
- `p95_wait`
- `queue_integral`
- `utilization`
- `throughput`
- `completed`
- `arrivals`
- `dropped`
- `overflow_count`
- `max_queue_length`
- `blocked_routing_count`

## Edge metrics

- `enabled`
- `travel_time`
- `transfer_capacity`
- `transferred_count`
- `blocked_count`
- `mean_delay`
- `max_delay`
- `degraded`

## Class metrics

- `arrivals`
- `completed_jobs`
- `dropped_jobs`
- `mean_wait`
- `p95_wait`
- `throughput`
- `throughput_efficiency`
- `drop_rate`

## Definitions

- Queue integral approximates the backlog integral by accumulating queue length over time.
- Holding integral captures completed work that cannot move downstream because the route is constrained or blocked.
- Throughput efficiency is `completed_jobs / arrival_count`.
- Throughput loss is measured relative to a baseline run when one is available.
- Cascade norm is the fraction of nodes that became materially degraded.
- Blocked transfers count edge movements delayed or prevented by route constraints.
- Recovery score is `1 / (1 + recovery_time)`.
- Resilience score combines recovery, throughput efficiency, and cascade containment.
- Fairness score is a bounded equity score derived from class-level wait, throughput-efficiency,
  and drop-rate disparities.
- Fairness degradation compares the current fairness score to a provided baseline run when available.
- Priority wait gradient measures how much lower-priority classes are being pushed into longer waits.

## Optimization and response-timing summaries

- `response_timing_best_fraction` is the deployment fraction that achieved the best expected resilience under perfect-information replay.
- `response_timing_latest_high_value_fraction` is the latest deployment fraction that still retains about 90% of the best achievable resilience lift.
- `response_timing_half_life_fraction` is the latest deployment fraction that still retains about 50% of the best achievable resilience lift.
- `response_timing_value_decay` measures how much expected resilience is lost between the best replayed deployment point and the end-of-horizon deployment point.
- `closed_loop_regime_deployment_accuracy` measures how often the first deployed regime matched the true scenario family.
- `closed_loop_regime_pre_degradation_rate` measures how often the controller deployed before first degradation.
- `closed_loop_regime_retarget_rate` measures how often the controller changed predicted regimes across the run.
- `closed_loop_regime_resilience_regret` compares closed-loop expected resilience to the perfect-information regime plan.
- `controller_candidate_count` is the number of controller policies explored during tuning.
- `controller_confidence_threshold` is the selected deployment threshold for the tuned controller.
- `controller_confirmation_count` is the number of consecutive high-confidence predictions required before the tuned controller deploys.
- `controller_schedule_start_fraction` is the first checkpoint fraction for the tuned controller.
- `controller_schedule_interval_fraction` is the base spacing between checkpoints before growth is applied.
- `controller_schedule_growth` controls how checkpoint spacing expands or contracts over the run.
- `controller_schedule_observation_limit` caps the number of observation checkpoints the tuned controller can use.
- `controller_mean_observation_count` is the average number of controller observations used per scenario by the selected closed-loop policy.
- `controller_mean_deployment_count` is the average number of intervention deployments issued per scenario by the selected controller.
- `controller_monitoring_burden_score` is a simple operating-cost proxy that combines observation load with deployment churn for the selected controller.
- `controller_frontier_count` is the number of non-dominated controller candidates on the resilience-versus-monitoring-burden frontier.
- `controller_search_rounds` is the number of refinement rounds used while learning the selected controller policy.
