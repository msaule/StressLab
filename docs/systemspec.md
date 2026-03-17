# SystemSpec

StressLab models systems through a YAML schema with these main sections:

- `system`: name, domain, and description
- `clock`: simulation horizon
- `classes`: optional flow classes with priorities
- `nodes`: queue servers with service models and buffer limits
- `edges`: routing connections between nodes
- `edges.transfer_capacity`: optional link throughput cap for constrained routes
- `arrivals`: external demand processes
- `policies`: optional scheduled operating rules such as temporary priority queues or reroutes
- `shocks`: demand, capacity, delay, topology-style edge shocks, and compound shocks
- `failure_conditions`: composable predicates such as `mean_wait`, `queue_integral`, and `throughput_loss`
- `interventions`: add servers, expand buffers, reroute flow, or change service behavior
- `search`: searchable shock dimensions, objective, and iteration budget
- `report`: plotting/reporting preferences

Example snippet:

```yaml
nodes:
  - id: triage
    type: queue_server
    servers: 3
    buffer_capacity: 40
    queue_policy: priority
    priority_classes: [critical, urgent, routine]
    service_time:
      distribution: gamma
      shape: 2.0
      scale: 6.0

policies:
  - id: surge_priority
    target: triage
    action_type: priority_policy_change
    start: 120
    duration: 180
    replacement: priority

  - id: adaptive_priority
    target: triage
    action_type: priority_policy_change
    mode: threshold
    replacement: priority
    trigger_metric: queue_length
    trigger_node: triage
    trigger_threshold: 6
    clear_threshold: 3
    min_active_duration: 15
    cooldown: 10

  - id: adaptive_routing_ladder
    target: triage->ward
    action_type: reroute_fraction
    mode: threshold
    trigger_metric: utilization
    trigger_node: triage
    stages:
      - id: watch
        trigger_threshold: 0.75
        clear_threshold: 0.60
        delta: 0.15
      - id: surge
        trigger_threshold: 0.90
        clear_threshold: 0.75
        delta: 0.30

interventions:
  - id: triage_playbook
    target: __bundle__
    action_type: bundle
    bundle_members: [adaptive_routing_ladder, surge_priority]
```

Validation covers:

- missing node references
- invalid routing probabilities
- invalid search targets
- invalid edge-targeted shock and intervention references
- malformed failure conditions
- negative costs and durations
- invalid policy targets or unsupported scheduled policy actions

Use `stresslab validate path/to/spec.yml` to check a spec before running it.
