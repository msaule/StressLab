# CLI Guide

StressLab ships a Typer CLI under the `stresslab` command.

## Commands

### Validate

```bash
stresslab validate examples/healthcare/ed_basic.yml
```

Validates the YAML schema and semantic references.

### Generate

```bash
stresslab generate --count 200 --topology-type mixed
```

Generates synthetic `SystemSpec` YAML files plus a generation summary and plots. Supported topology families are:

- `random_queue`
- `scale_free`
- `small_world`
- `hierarchical_supply`
- `market_microstructure`
- `mixed`

### Discover

```bash
stresslab discover --count 200 --topology-type mixed
stresslab discover --count 200 --topology-type mixed --workers 4
stresslab discover --count 2000 --topology-type mixed --shard-count 4 --shard-index 0 --workers 4
stresslab discover --source-dir runs/<generate_dir>/generated
stresslab discover --resume-run-dir runs/<discover_dir> --workers 4
```

Runs the discovery pipeline:

1. generate or load systems
2. run baseline simulation
3. run minimum-failure search
4. run worst-case search
5. write `collapse_dataset.csv`
6. emit discovery plots and reports

Key discovery artifacts:

- `collapse_dataset.csv`
- `early_warning_dataset.csv`
- `collapse_distribution.csv`
- `feature_importance.csv`
- `candidate_laws.csv`
- `symbolic_laws.csv`
- `batches/collapse_batch_*.csv`
- `discovery_report.html`

`--workers` parallelizes per-system discovery execution, and `--resume-run-dir` lets a partially completed discovery study continue in place from the existing dataset checkpoints.
`--shard-count` and `--shard-index` split a larger discovery campaign into deterministic shards that can later be merged by `stresslab theory`.

### Theory

```bash
stresslab theory runs/<discover_dir>
stresslab theory runs
```

Analyzes a discovery dataset, or recursively merges many discovery runs under one directory, for:

- fragility regressions
- candidate laws
- phase transitions
- cascade power laws
- early-warning summaries

Key theory artifacts:

- `fragility_models.csv`
- `law_candidates.csv`
- `symbolic_laws.csv`
- `combined_collapse_dataset.csv`
- `source_dataset_index.csv`
- `phase_transition.json`
- `phase_transition_bootstrap.csv`
- `powerlaw_fit.json`
- `tail_model_comparison.csv`
- `early_warning_summary.json`
- `early_warning_trends.csv`
- `theory_report.html`

### Research

```bash
stresslab research runs/<discover_dir>
```

Builds a publication-style report bundle on top of the theory layer. The research output includes:

- `research_summary.json`
- `figure_index.csv`
- `research_report.html`
- `figures/`

The browser app at `/app` now also surfaces discovery-specific workspace data through a dedicated Discovery Lab section backed by the `/discovery` API route.

### Run

```bash
stresslab run examples/healthcare/ed_basic.yml
```

Runs the configured scenario, writes artifacts into `runs/`, and builds Markdown/HTML reports.

### Search

```bash
stresslab search examples/healthcare/ed_basic.yml --objective min_failure
stresslab search examples/healthcare/ed_basic.yml --objective worst_case --budget 0.4
```

Performs adversarial search over the configured `search.search_space`.

### Optimize

```bash
stresslab optimize examples/healthcare/ed_basic.yml --budget 2500
stresslab optimize examples/healthcare/ed_basic.yml --robust --scenario-budget 0.4 --scenario-samples 3 --budget 2500
stresslab optimize examples/healthcare/ed_basic.yml --robust --scenario-budget 0.4 --scenario-samples 3 --budget 2500 --fairness-weight 0.35
stresslab optimize examples/markets/liquidity_withdrawal.yml --robust --scenario-budget 0.4 --scenario-samples 2 --budget 500 --fairness-weight 0.5 --expand-policies --policy-only
stresslab optimize examples/healthcare/ed_basic.yml --robust --scenario-budget 0.4 --scenario-samples 2 --budget 600 --expand-dynamic-policies --dynamic-only
stresslab optimize examples/healthcare/ed_basic.yml --robust --scenario-budget 0.4 --scenario-samples 2 --budget 700 --expand-adaptive-policies --adaptive-only
stresslab optimize examples/healthcare/ed_basic.yml --expand-adaptive-policies --expand-controller-bundles --bundle-only --budget 900
stresslab optimize examples/healthcare/ed_basic.yml --expand-adaptive-policies --expand-controller-bundles --expand-hierarchical-playbooks --playbook-only --budget 1200
```

Ranks interventions and optionally chooses a greedy portfolio under budget.

With `--robust`, StressLab builds a scenario portfolio from the configured system, minimum-failure search,
worst-case search under budget, and additional random budgeted scenarios. Interventions are then ranked by
expected resilience, worst-case resilience, variability, and failure-prevention rate across that portfolio.

Optimization artifacts also include a Pareto frontier CSV and frontier plot to show cost-versus-resilience
tradeoffs among non-dominated interventions.
The robust workflow now also writes scenario-family artifacts:

- `scenario_summary.csv`
- `scenario_clusters.csv`
- `cluster_summary.csv`
- `intervention_coverage.csv`

These describe which stress scenarios belong to the same failure family and how well each intervention
covers each family.

When `--robust` is combined with `--budget`, StressLab also evaluates budget-feasible intervention
portfolios and writes:

- `portfolio_candidates.csv`
- `portfolio_cluster_coverage.csv`

These summarize the best portfolio plans under budget and show how the recommended portfolio covers
each scenario family.

Robust optimization now also emits a regime-aware contingency map:

- `cluster_response_plan.csv`
- `regime_plan_summary.json`

These artifacts assign the best intervention or playbook to each discovered scenario family and
estimate the standby cost of maintaining that family-specific response map.

Robust optimization also emits imperfect-detection artifacts:

- `regime_detection.csv`
- `regime_detection_confusion.csv`
- `regime_detection_summary.json`

These estimate how often a noisy signal-based detector confuses scenario families, which
intervention would be deployed under those mistakes, and how much resilience is lost relative to
the perfect-information regime plan.

Robust optimization now also emits online partial-observation artifacts:

- `online_regime_detection.csv`
- `online_regime_horizons.csv`
- `online_regime_summary.json`

These estimate how accurately StressLab can classify scenario families as only part of the run has
been observed, how often the chosen response arrives before first degradation, and how much
response quality survives once late detection shrinks the available intervention window.

Robust optimization now also emits actual deployment-delay replay artifacts:

- `response_timing.csv`
- `response_timing_summary.json`

These replay the selected regime-plan response with true mid-run intervention deployment at
different fractions of the horizon, which makes it possible to estimate the practical response
window, the resilience half-life of a delayed response, and how much value is lost when teams act
too late.

Robust optimization now also emits closed-loop control artifacts:

- `closed_loop_regime.csv`
- `closed_loop_regime_summary.json`
- `controller_policy_candidates.csv`
- `controller_frontier.csv`
- `controller_tuning_summary.json`

These run a live controller over each scenario. The controller observes the simulated system at
scheduled checkpoints, predicts the active regime, and deploys plan interventions when confidence
crosses a threshold. This exposes deployment accuracy, retargeting behavior, and how much
resilience survives in a true observe-decide-act loop.
StressLab now also searches a lightweight catalog of controller policies on representative scenario
families, mutates schedules around the strongest seeds, and can tune repeated-confirmation rules
before promoting the best controller into the full closed-loop replay.
Those controller candidates now expose learned schedule parameters directly, including start
fraction, interval fraction, growth factor, and observation limit.
The controller learner now also runs local-search refinement and writes a controller frontier so
teams can compare expected resilience against monitoring burden rather than only inspecting the
single selected policy.

`--fairness-weight` turns on fairness-aware scoring using class-level wait, throughput-efficiency,
and drop-rate disparities. This is especially useful for systems with critical/urgent/routine
classes where the best average-performance intervention may not be the fairest.

`--expand-policies` synthesizes queue-policy and routing-policy interventions from the current
system graph and appends them to the authored intervention catalog.

`--policy-only` restricts optimization to those synthesized policy candidates, which is useful
when you want to study operational tuning separately from staffing or capacity changes.

`--expand-dynamic-policies` synthesizes scheduled policy candidates tied to detected stress
windows. These candidates use timed queue-policy shifts and temporary rerouting instead of
permanent model edits.

`--dynamic-only` restricts optimization to those scheduled policy candidates, which is useful
when you want StressLab to recommend operating rules that activate only during congestion or
shock windows.

`--expand-adaptive-policies` synthesizes threshold-triggered controllers from live congestion
signals like queue length and utilization. These candidates behave like simple operating rules
that turn on and off as the system state changes.

`--adaptive-only` restricts optimization to those threshold-triggered controllers when you want
to study congestion-response policies separately from static capacity changes or fixed-time rules.

Adaptive expansion now also includes multi-stage escalation ladders for routing policies, so the
optimizer can compare single-threshold controllers against staged responses that intensify as
congestion grows.

`--expand-controller-bundles` synthesizes coordinated playbook candidates from adaptive policies.
These bundle multiple controllers into one candidate so StressLab can compare individual control
rules against cross-target response packages.

`--bundle-only` restricts optimization to those generated playbooks while keeping hidden member
interventions available for bundle expansion during simulation.

`--expand-hierarchical-playbooks` synthesizes nested playbook candidates that wrap controller
bundles together with supporting adaptive controllers. These candidates are useful when one
response package should coordinate multiple operating rules under the same congestion regime.

`--playbook-only` restricts optimization to those hierarchical playbooks while keeping hidden
member bundles and controllers available for expansion during simulation. Runs in this mode also
write `bundle_hierarchy.csv` so you can inspect each nested playbook tree directly.

### Compare

```bash
stresslab compare runs/<run_a> runs/<run_b>
```

Builds a comparison summary across multiple existing StressLab run directories. The command writes:

- `comparison_summary.csv`
- `comparison_summary.json`
- `comparison_report.md`
- `comparison_report.html`
- `comparison_tradeoff.png`
- `comparison_metrics.png`

This is useful for decision review when you want to compare different intervention portfolios,
search outputs, or baseline/scenario runs side by side.

### Batch

```bash
stresslab batch examples/campaigns/healthcare_decision_campaign.yml
```

Executes a YAML manifest of `run`, `search`, and `optimize` jobs. Each job writes its own run
directory under the batch campaign folder, and the campaign root also emits:

- `batch_manifest_resolved.yaml`
- `batch_summary.csv`
- `batch_summary.json`
- `batch_report.md`
- `batch_report.html`
- `comparison_summary.csv`
- `comparison_report.html`

This is useful for repeatable resilience campaigns where the same set of scenarios and decision
workflows should be rerun over time or across system revisions.

### Catalog

```bash
stresslab catalog runs
```

Scans a workspace root recursively for StressLab artifact directories and writes:

- `run_catalog.csv`
- `run_catalog_summary.json`
- `run_catalog_report.md`
- `run_catalog_report.html`
- `catalog_types.png`
- `catalog_systems.png`

This is useful when a workspace already contains many runs, comparisons, batch campaigns, and
benchmark suites and you want one inventory view instead of manually browsing directories.

### Status

```bash
stresslab status runs --refresh
```

Builds a workspace-status snapshot from the persistent registry and writes:

- `workspace_status.csv`
- `workspace_status_summary.json`
- `workspace_status_report.md`
- `workspace_status_report.html`
- `status_analysis_types.png`
- `status_systems.png`
- `status_timeline.png`

This is useful when you want a lightweight operational snapshot of what has been run recently in a
workspace, which systems dominate the artifact mix, and how the workspace has evolved over time.

### Board

```bash
stresslab board runs --refresh
```

Builds a decision dashboard from the persistent registry and writes:

- `workspace_board_recent.csv`
- `workspace_board_leaders.csv`
- `workspace_board_failure_watchlist.csv`
- `workspace_board_plans.csv`
- `workspace_board_summary.json`
- `workspace_board_report.md`
- `workspace_board_report.html`
- `board_analysis_mix.png`
- `board_system_resilience.png`
- `board_failure_watchlist.png`
- `board_plan_tradeoff.png`

This is useful when you want one operator-facing view of recent activity, strongest known systems,
highest-risk failures, and the most actionable optimize plans in the workspace.

### Doctor

```bash
stresslab doctor runs
```

Builds a deployment-preflight artifact that checks local container and service readiness. Artifacts
include:

- `doctor_checks.csv`
- `doctor_summary.json`
- `doctor_report.md`
- `doctor_report.html`

This is useful when a machine is failing to run container workflows and you need a structured answer
about whether the blocker is Docker CLI availability, plugin wiring, daemon reachability, WSL, or
Windows container services.

### Serve

```bash
stresslab serve runs --refresh --port 8765 --api-token change-me
```

Starts a lightweight HTTP API over the workspace registry and artifact tree.
The same server now also hosts an interactive browser app at `http://127.0.0.1:8765/app`.
When `--api-token` is set, non-public endpoints require a bearer token, `X-StressLab-Token`,
or `?token=` query parameter.

Key endpoints:

- `/health`
- `/app`
- `/registry?limit=20`
- `/status?limit=25`
- `/board?recent_limit=20&watch_limit=12&plan_limit=12`
- `/jobs?limit=20`
- `POST /jobs`
- `/jobs/<job_id>?expand=1`
- `/artifacts/<run_id>?expand=1`
- `/reports/<run_id>`
- `/bundles/<run_id>?include_registry=1`
- `/files/<run_id>/<relative_path>`

This is useful when another tool, script, notebook, or dashboard needs live access to StressLab
run metadata and reports without scraping directories by hand.
The async job surface is especially useful when an external system wants to submit a long-running
`run`, `optimize`, `evaluate`, `casebook`, or `benchmark` workflow and poll for completion.

### Evaluate

```bash
stresslab evaluate examples/healthcare/ed_basic.yml --replicates 8 --budget 2500 --robust
stresslab evaluate examples/healthcare/ed_basic.yml --replicates 8 --intervention-id add_ward_capacity
```

Runs a paired multi-seed evaluation study for a proposed treatment plan. The treatment can come
from explicit `--intervention-id` values or from the optimizer itself.

Artifacts include:

- `replicate_metrics.csv`
- `paired_deltas.csv`
- `evaluation_metric_summary.csv`
- `evaluation_summary.json`
- `treatment_plan.json`
- `evaluation_report.md`
- `evaluation_report.html`
- `evaluation_distributions.png`
- `evaluation_deltas.png`
- `evaluation_failures.png`

This is useful when a team wants statistical evidence that a chosen plan improves resilience or
reduces failure risk across multiple seeds instead of trusting one stochastic draw.

### Casebook

```bash
stresslab casebook --suite starter --replicates 4
stresslab casebook examples/healthcare/ed_basic.yml examples/markets/liquidity_withdrawal.yml --replicates 4
```

Builds a cross-system evidence report from multiple evaluation studies and writes:

- `casebook_summary.csv`
- `casebook_summary.json`
- `casebook_report.md`
- `casebook_report.html`
- `casebook_resilience.png`
- `casebook_failure_reduction.png`
- one evaluation subdirectory per included system

This is useful when teams want a single validation package that summarizes which systems benefited,
which plans were chosen, and how strongly those gains held up across replications.

### Bundle

```bash
stresslab bundle runs/<run_dir> --output-dir bundles --include-registry
```

Packages one StressLab artifact directory into a portable zip bundle with:

- `bundle_manifest.json`
- `artifact/<all artifact files>`
- optional `registry/.stresslab_registry.csv`
- optional `registry/.stresslab_registry.json`

The manifest records the run id, analysis type, system name, file list, file sizes, and SHA-256
checksums for reproducible handoff.

### Restore

```bash
stresslab restore bundles/<run_bundle>.zip --output-dir runs
```

Restores a bundled artifact into a workspace, writes `bundle_restore.json` inside the restored
artifact directory, and updates the workspace registry so the restored artifact immediately shows
up in `stresslab status`, `stresslab board`, `stresslab catalog`, and the HTTP API.

### Report

```bash
stresslab report runs/<timestamp>_ed_basic_run
```

Rebuilds Markdown and HTML output from artifact files.

### Benchmark

```bash
stresslab benchmark --suite starter
```

Runs the healthcare, supply-chain, and market examples and writes a suite summary.
