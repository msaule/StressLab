# Theory Layer

StressLab's theory layer turns simulation and search artifacts into reusable scientific measurements.

## Purpose

The `stresslab.theory` package converts systems and collapse experiments into:

- structural features
- collapse metrics
- fragility fits
- phase-transition estimates
- power-law fits
- early-warning summaries

These outputs are the bridge between one-off resilience studies and cross-system scientific discovery.

## Structural Features

`stresslab.theory.features.extract_system_features(...)` computes:

- `node_count`
- `edge_count`
- `average_degree`
- `clustering_coefficient`
- `average_path_length`
- `graph_diameter`
- `redundancy_index`
- `coupling_strength`
- `utilization`
- `capacity_slack`
- `routing_entropy`
- `centralization_index`
- `buffer_ratio`
- centrality summaries
- k-core and component summaries

The feature extractor works on authored YAML systems and generated synthetic systems.

## Collapse Metrics

`stresslab.theory.metrics.collapse_metrics_from_results(...)` combines:

- baseline simulation
- minimum-failure search replay
- worst-case search replay

into collapse-oriented outputs such as:

- `collapse_probability`
- `cascade_size`
- `max_cascade_size`
- `cascade_depth`
- `recovery_time`
- `failure_shock_budget`
- `fragility_index`
- `bottleneck_count`
- `cascade_speed`
- `throughput_loss`

`build_collapse_distribution(...)` then constructs empirical CCDF-style cascade distributions.

## Fragility Fits

`stresslab.theory.fragility.fit_fragility_models(...)` fits lightweight interpretable models:

- linear
- log-feature
- power-law
- small multivariate linear laws

The output tables are designed for research reports, not opaque black-box forecasting.

StressLab now also ships a symbolic-style discovery helper through
`stresslab.discovery.symbolic.symbolic_regression_search(...)`, which evaluates transformed feature
bases and compact multiterm expressions against collapse targets such as
`collapse_probability`.

## Phase Transitions

`stresslab.theory.phase_transition.detect_phase_transition(...)` bins systems by a control variable such as utilization and looks for the sharpest outcome discontinuity.

This is useful for findings like:

- collapse probability stays low below a threshold
- then spikes once utilization crosses a critical region

`stresslab.theory.phase_transition.bootstrap_phase_transition(...)` repeats that threshold search
over bootstrap resamples so theory studies can report threshold stability instead of only one point
estimate.

## Power Laws

`stresslab.theory.powerlaws.fit_power_law(...)` estimates:

- `alpha`
- `xmin`
- `ks_distance`
- `loglog_r2`

for heavy-tailed cascade-size distributions.

`stresslab.theory.powerlaws.compare_tail_models(...)` also compares power-law, exponential, and
lognormal tail fits so discovery reports can test whether a heavy-tail interpretation is actually
better than simpler alternatives.

## Early Warning

`stresslab.theory.early_warning.compute_early_warning_signals(...)` extracts simple pre-collapse indicators from queue traces:

- variance increase
- lag-1 autocorrelation increase
- recovery lag

These support critical-slowing-down style analysis.

`stresslab.theory.early_warning.summarize_early_warning_trends(...)` then compares those signals
between collapse and non-collapse cases to see whether early-warning indicators separate the two
regimes in aggregate.
