# Overview

StressLab is a production-oriented research framework for resilience testing in queue, flow, and dependency networks.

The v0.1 release focuses on four end-to-end capabilities:

1. Parse a domain-agnostic YAML system definition.
2. Simulate queueing behavior under arrivals, routing, buffers, priorities, and shocks.
3. Search for minimum-failure and high-damage scenarios under a budget.
4. Rank interventions, generate plots, and emit Markdown/HTML reports.

The current robust-planning workflow goes a step further by clustering generated stress scenarios into
scenario families and estimating intervention coverage across those families, which helps teams see
whether a mitigation is broadly protective or only useful against one narrow failure mode.
With a budget, StressLab also searches intervention portfolios and recommends compact plans that
cover the widest set of scenario families rather than only optimizing one intervention at a time.
The framework now also emits class-level equity metrics and supports fairness-aware optimization,
which is useful when protecting high-priority throughput alone would otherwise hide damage to
other classes.
The optimizer can now also synthesize policy candidates from the system itself, including queue
policy changes and routing biases, which makes it possible to search operational changes even when
the original YAML intervention catalog is sparse.
It can also synthesize scheduled policy candidates tied to stress windows, allowing recommendations
for temporary operating rules that activate only during a surge or disruption.
It can now also synthesize adaptive controllers that trigger on live congestion thresholds,
which makes it possible to search practical "if backlog rises, then reroute/prioritize" rules.
Those adaptive controllers can now also operate as multi-stage ladders, making it possible to
recommend escalation logic rather than only one binary trigger.
The optimizer can now also synthesize coordinated controller bundles, which turns several
compatible adaptive rules into one playbook candidate for cross-target response design.
It can now also synthesize hierarchical playbooks, which layer those controller bundles with
supporting controllers and expose the resulting bundle tree as a reportable artifact.
Robust optimization now also produces regime-aware response maps, so teams can see which
intervention should fire for each discovered scenario family instead of forcing one global plan
to cover every failure mode.
That response-map layer is now evaluated under imperfect regime detection as well, so the system
can estimate how much resilience survives when observed signals misclassify the active failure
family.
It now also evaluates online regime detection from partial observations over the course of a run,
which helps teams see whether the right response can be selected before congestion and degradation
have already become irreversible.
That same response layer is now also replayed under delayed deployment, so teams can see the true
timing sensitivity of their response map instead of only whether classification was accurate.
StressLab now also evaluates a closed-loop controller that periodically observes the run,
predicts the active regime, and deploys interventions inside that same replay, which turns the
analysis into a true observe-decide-act experiment.
That controller is now tuned automatically on representative scenario families, so the system can
learn a better observation cadence and confidence policy before replaying the full closed-loop
portfolio.
The learned controller can also trade speed for certainty by requiring repeated high-confidence
predictions before deployment.
It now also searches over parameterized checkpoint schedules, which lets StressLab learn not just
when to trust a prediction, but how frequently and how aggressively the controller should observe
the system in the first place.
That search layer now also performs local refinement around strong controller candidates and emits
a controller frontier so operators can compare resilience gains against monitoring burden and
decision overhead.
The CLI now also supports repeatable batch manifests and cross-run comparison reports, which makes
it easier to rerun curated resilience campaigns and review decision tradeoffs across many runs.
It now also supports workspace cataloging, which turns a directory of StressLab artifacts into a
reportable inventory of runs, comparisons, batch campaigns, and benchmarks.
It now also maintains a lightweight workspace registry and can emit a status snapshot from that
registry, which helps teams see recent activity and workspace mix without rescanning everything by
hand.
That registry now also feeds a workspace board, which surfaces top-performing systems, failure
watchlists, and actionable optimize plans in a single report.
The CLI now also includes a deployment doctor, which turns local Docker and container-runtime
readiness into a reportable artifact instead of leaving environment blockers implicit.
The same workspace layer now also has a lightweight HTTP API, which makes it easier to integrate
StressLab into notebooks, local dashboards, and external orchestration tooling.
That HTTP layer now also includes a persistent SQLite-backed job queue, so external tools can
submit long-running workflows asynchronously and poll them to completion instead of shelling out
to the CLI directly.
It now also includes an interactive browser control center for live workspace monitoring, quick
job submission, artifact inspection, and side-by-side decision review.
The service layer now also supports optional token-based protection and containerized deployment,
which makes it easier to run StressLab as an internal tool instead of only a local developer app.
Artifact directories can now also be exported into portable bundles with manifests and checksums
and restored into another workspace, which helps teams share, archive, and review runs without
losing provenance.
The framework now also supports multi-seed evaluation studies, which makes it possible to validate
candidate plans with replication, paired deltas, and confidence intervals instead of treating a
single run as ground truth.
Those evaluation studies can now also be rolled up into evidence casebooks, making it easier to
share cross-system validation results with decision-makers instead of handing them isolated study
folders.
StressLab now also includes a discovery-engine layer with synthetic topology generation,
cross-system collapse datasets, theory fitting, and publication-style research reports. That turns
the project from a decision-support simulator into a lightweight computational lab for discovering
repeatable fragility relationships across many generated systems.

StressLab is intentionally lightweight and interpretable. The core stack is Python, NumPy, pandas, NetworkX, matplotlib, seaborn, Pydantic, and Typer.
