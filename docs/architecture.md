# Architecture

StressLab is organized as a set of narrow modules around a deterministic simulation kernel.

## Layers

- `stresslab.systemspec`
  Parses YAML, validates semantics, and resolves adjacency/index structures.
- `stresslab.des`
  Runs the event queue, node execution, constrained routing, queue policies, shock hooks, and metric accumulation,
  including class-level wait/drop/departure tracking for fairness analysis, scheduled policy start/end hooks,
  threshold-triggered controller activation, and staged escalation/de-escalation.
- `stresslab.shocks`
  Flattens compound shocks and applies capacity, delay, and topology modifiers.
- `stresslab.search`
  Encodes shock vectors, computes budgets, and runs minimum-failure or worst-case search.
- `stresslab.optimize`
  Applies interventions to copied specs, evaluates marginal resilience improvement, clusters robust
  scenario portfolios into failure families, measures intervention coverage by family, and selects
  budget-feasible intervention portfolios for broad failure-family coverage, with optional fairness
  weighting and synthesized static, scheduled, adaptive, bundled, or hierarchical-playbook policy
  candidates for queue/routing tuning. It also builds regime-aware response maps that assign
  cluster-specific interventions and estimate the standby cost of those contingency plans, then
  evaluates those plans under noisy signal-based regime detection to estimate confusion and regret,
  under partial-observation online detection to estimate whether the right plan can be chosen
  early enough for the response window to remain useful, and under deployment-delay replay to
  measure how fast response value decays once interventions are activated later in the run. It can
  also execute a closed-loop controller that observes the live simulator state at configured
  checkpoints and deploys interventions inside the replay itself, and it can tune that controller
  over a lightweight candidate catalog plus mutation-based schedule search before replaying the
  selected policy on the full portfolio. The learned controller surface now includes timing-shape
  parameters such as start fraction, interval spacing, interval growth, and observation limit.
- `stresslab.explain`
  Produces bottleneck attribution and simple counterfactual narratives.
- `stresslab.viz`
  Generates queue, utilization, fragility, ROI, Pareto, scenario-family, coverage, heatmap, and graph plots.
- `stresslab.reports`
  Builds Markdown and HTML reports from run artifacts.
- `stresslab.cli`
  Exposes the workflow as `stresslab validate|run|search|optimize|report|benchmark`.

## Execution flow

1. Load a YAML spec.
2. Validate references and semantics.
3. Resolve adjacency and class-priority indexes.
4. Run the simulator with deterministic seeding.
5. Serialize node metrics, edge metrics, policy schedules, and time series.
6. Build search/optimization outputs if requested.
7. For robust optimization, cluster the scenario portfolio and score intervention coverage by cluster.
8. For budgeted robust optimization, search portfolio combinations and score family coverage.
9. Replay regime-plan interventions under delayed deployment to build response-timing curves.
10. Run closed-loop regime controllers over scenario replays when robust planning is enabled.
11. Tune controller schedules and confidence policies on representative scenario families.
12. Generate plots and reports.
