"""Canonical result models shared across the package."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CounterfactualResult(BaseModel):
    """Counterfactual mitigation summary."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: str
    prevented_failure: bool
    resilience_delta: float
    narrative: str


class SimulationResult(BaseModel):
    """Serializable simulation result."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    seed: int
    status: str
    horizon: float
    event_count: int
    failure_triggered: bool
    failure_reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    node_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)
    edge_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)
    class_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)
    timeline_events_path: str | None = None
    plots: dict[str, str] = Field(default_factory=dict)
    artifacts_dir: str


class SearchResult(BaseModel):
    """Serializable search result."""

    model_config = ConfigDict(extra="forbid")

    objective: str
    success: bool
    best_shock_vector: dict[str, float] = Field(default_factory=dict)
    best_shock_budget: float
    damage_score: float
    failure_triggered: bool
    search_iterations: int
    evaluated_scenarios: int
    baseline_metrics: dict[str, float] = Field(default_factory=dict)
    best_metrics: dict[str, float] = Field(default_factory=dict)
    result_paths: dict[str, str] = Field(default_factory=dict)


class RankedIntervention(BaseModel):
    """Single intervention recommendation."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: str
    label: str | None = None
    action_type: str | None = None
    target: str | None = None
    source: str | None = None
    generated: bool = False
    dynamic: bool = False
    policy_mode: str | None = None
    schedule_start: float | None = None
    schedule_duration: float | None = None
    stage_count: int = 0
    bundle_size: int = 0
    bundle_depth: int = 0
    trigger_metric: str | None = None
    trigger_node: str | None = None
    trigger_threshold: float | None = None
    clear_threshold: float | None = None
    cost: float
    resilience_gain: float
    roi: float
    failure_prevented: bool
    expected_resilience: float | None = None
    worst_case_resilience: float | None = None
    resilience_std: float | None = None
    failure_prevention_rate: float | None = None
    robust_score: float | None = None
    evaluated_scenarios: int | None = None
    fairness_gain: float | None = None
    expected_fairness_score: float | None = None
    worst_case_fairness_score: float | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


class ScenarioSummary(BaseModel):
    """Summary of one stress scenario for robust planning."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    source: str
    shock_vector: dict[str, float] = Field(default_factory=dict)
    shock_budget: float
    failure_triggered: bool
    damage_score: float
    metrics: dict[str, float] = Field(default_factory=dict)


class ScenarioClusterAssignment(BaseModel):
    """Cluster assignment for one scenario in a robust portfolio."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    cluster_id: str
    cluster_label: str
    source: str
    failure_triggered: bool
    shock_budget: float
    damage_score: float
    resilience_score: float
    throughput: float
    mean_wait: float
    blocked_transfers: float


class ScenarioClusterSummary(BaseModel):
    """Aggregate summary of one scenario cluster."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    cluster_label: str
    scenario_count: int
    representative_scenario_id: str
    representative_source: str
    dominant_shock_dimension: str | None = None
    failure_rate: float
    mean_shock_budget: float
    mean_damage_score: float
    mean_resilience_score: float
    mean_throughput: float
    mean_wait: float
    mean_blocked_transfers: float


class InterventionCoverageSummary(BaseModel):
    """How well an intervention covers one family of robust scenarios."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: str
    cluster_id: str
    cluster_label: str
    scenario_count: int
    baseline_failure_rate: float
    treated_failure_rate: float
    failure_prevention_rate: float
    mean_resilience_delta: float
    worst_case_resilience_delta: float
    wait_improvement_rate: float
    blocked_transfer_relief_rate: float
    coverage_score: float


class PortfolioClusterCoverageSummary(BaseModel):
    """How well a selected portfolio covers one scenario family."""

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str
    cluster_id: str
    cluster_label: str
    scenario_count: int
    baseline_failure_rate: float
    treated_failure_rate: float
    failure_prevention_rate: float
    mean_resilience_delta: float
    worst_case_resilience_delta: float
    wait_improvement_rate: float
    blocked_transfer_relief_rate: float
    coverage_score: float
    covered: bool


class ClusterResponseRecommendation(BaseModel):
    """Recommended intervention for one scenario family in a regime-aware plan."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    cluster_label: str
    scenario_count: int
    selected_intervention_id: str | None = None
    selected_label: str | None = None
    selected_action_type: str | None = None
    selected_source: str | None = None
    selected_bundle_depth: int = 0
    marginal_cost: float = 0.0
    total_standby_cost: float = 0.0
    coverage_score: float = 0.0
    failure_prevention_rate: float = 0.0
    mean_resilience_delta: float = 0.0
    worst_case_resilience_delta: float = 0.0
    expected_cluster_resilience: float | None = None
    expected_cluster_fairness: float | None = None
    robust_score: float | None = None
    covered: bool = False
    reused_intervention: bool = False


class RegimePlanSummary(BaseModel):
    """Summary of a regime-aware family-specific response plan."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    budget: float | None = None
    total_standby_cost: float
    unique_intervention_count: int
    assigned_cluster_count: int
    covered_cluster_count: int
    weighted_cluster_coverage_rate: float
    mean_cluster_coverage_score: float
    expected_resilience: float
    expected_fairness_score: float
    failure_prevention_rate: float
    selected_intervention_ids: list[str] = Field(default_factory=list)
    method: str = "none"


class RegimeDetectionScenarioResult(BaseModel):
    """Detection outcome for one scenario under noisy signal classification."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    true_cluster_id: str
    true_cluster_label: str
    predicted_cluster_id: str
    predicted_cluster_label: str
    prediction_accuracy: float
    mean_confidence: float
    true_cluster_probability: float
    selected_intervention_id: str | None = None
    selected_label: str | None = None
    selected_source: str | None = None
    expected_resilience: float
    expected_fairness_score: float
    expected_failure_rate: float
    failure_prevention_rate: float


class RegimeDetectionSummary(BaseModel):
    """Aggregate quality of a regime detector and its downstream response map."""

    model_config = ConfigDict(extra="forbid")

    method: str
    noise_scale: float
    trials_per_scenario: int
    scenario_count: int
    cluster_count: int
    detection_accuracy: float
    expected_resilience: float
    expected_fairness_score: float
    expected_failure_rate: float
    failure_prevention_rate: float
    resilience_regret: float
    fairness_regret: float


class OnlineRegimeScenarioResult(BaseModel):
    """Decision-time outcome for one scenario under partial observation."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    true_cluster_id: str
    true_cluster_label: str
    predicted_cluster_id: str
    predicted_cluster_label: str
    decision_fraction: float
    decision_time: float
    first_degraded_time: float | None = None
    lead_time_to_degradation: float | None = None
    pre_degradation_decision: bool = False
    prediction_correct: bool = False
    decision_confidence: float
    true_cluster_probability: float
    selected_intervention_id: str | None = None
    selected_label: str | None = None
    selected_source: str | None = None
    delay_factor: float
    delay_adjusted_resilience: float
    delay_adjusted_fairness_score: float
    delay_adjusted_failure_rate: float
    delay_adjusted_failure_prevention_rate: float


class OnlineRegimeHorizonSummary(BaseModel):
    """Detection quality at one partial-observation horizon."""

    model_config = ConfigDict(extra="forbid")

    observation_fraction: float
    observation_time: float
    scenario_count: int
    detection_accuracy: float
    mean_confidence: float
    mean_true_cluster_probability: float


class OnlineRegimeDetectionSummary(BaseModel):
    """Aggregate quality of online regime detection and delayed response."""

    model_config = ConfigDict(extra="forbid")

    method: str
    confidence_threshold: float
    scenario_count: int
    cluster_count: int
    mean_decision_fraction: float
    mean_decision_time: float
    pre_degradation_decision_rate: float
    detection_accuracy: float
    mean_confidence: float
    expected_resilience: float
    expected_fairness_score: float
    expected_failure_rate: float
    failure_prevention_rate: float
    resilience_regret: float
    fairness_regret: float


class ResponseTimingPoint(BaseModel):
    """Aggregate response quality for one deployment-delay fraction."""

    model_config = ConfigDict(extra="forbid")

    deployment_fraction: float
    deployment_time: float
    scenario_count: int
    expected_resilience: float
    expected_fairness_score: float
    expected_failure_rate: float
    failure_prevention_rate: float
    mean_resilience_gain: float
    mean_fairness_gain: float
    pre_degradation_deployment_rate: float
    mean_lead_time_to_degradation: float | None = None


class ResponseTimingSummary(BaseModel):
    """Summary of deployment-delay sensitivity under perfect-information replay."""

    model_config = ConfigDict(extra="forbid")

    method: str
    scenario_count: int
    cluster_count: int
    baseline_expected_resilience: float
    zero_delay_resilience: float
    zero_delay_fairness_score: float
    best_deployment_fraction: float
    best_expected_resilience: float
    best_failure_prevention_rate: float
    latest_high_value_fraction: float
    resilience_half_life_fraction: float
    end_horizon_resilience: float
    response_value_decay: float
    pre_degradation_rate_at_best: float


class ClosedLoopRegimeScenarioResult(BaseModel):
    """Scenario outcome under a live observation-and-deploy controller."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    true_cluster_id: str
    true_cluster_label: str
    final_predicted_cluster_id: str | None = None
    final_predicted_cluster_label: str | None = None
    first_deployed_cluster_id: str | None = None
    first_deployed_cluster_label: str | None = None
    deployed_intervention_ids: list[str] = Field(default_factory=list)
    observation_count: int
    deployment_count: int
    first_observation_time: float | None = None
    first_deployment_time: float | None = None
    first_degraded_time: float | None = None
    pre_degradation_observation: bool = False
    pre_degradation_deployment: bool = False
    prediction_correct: bool = False
    deployment_correct: bool = False
    retargeted: bool = False
    mean_confidence: float
    max_confidence: float
    final_resilience: float
    final_fairness_score: float
    final_failure_rate: float
    failure_prevention_rate: float


class ClosedLoopRegimeSummary(BaseModel):
    """Aggregate quality of a live closed-loop regime controller."""

    model_config = ConfigDict(extra="forbid")

    method: str
    confidence_threshold: float
    allow_retargeting: bool
    confirmation_count: int = 1
    scenario_count: int
    cluster_count: int
    mean_observation_count: float
    mean_deployment_count: float
    prediction_accuracy: float
    deployment_accuracy: float
    pre_degradation_observation_rate: float
    pre_degradation_deployment_rate: float
    retarget_rate: float
    expected_resilience: float
    expected_fairness_score: float
    expected_failure_rate: float
    failure_prevention_rate: float
    resilience_regret: float
    fairness_regret: float


class ControllerPolicyCandidate(BaseModel):
    """One tuned closed-loop controller candidate."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    schedule_id: str
    observation_fractions: list[float] = Field(default_factory=list)
    schedule_start_fraction: float | None = None
    schedule_interval_fraction: float | None = None
    schedule_growth: float | None = None
    schedule_observation_limit: int | None = None
    confidence_threshold: float
    allow_retargeting: bool
    confirmation_count: int = 1
    tuning_scenario_count: int
    mean_observation_count: float = 0.0
    mean_deployment_count: float = 0.0
    monitoring_burden_score: float = 0.0
    search_method: str = "grid"
    generation: int = 0
    parent_policy_id: str | None = None
    objective_score: float
    expected_resilience: float
    expected_fairness_score: float
    failure_prevention_rate: float
    prediction_accuracy: float
    deployment_accuracy: float
    pre_degradation_rate: float
    retarget_rate: float
    resilience_regret: float


class ControllerTuningSummary(BaseModel):
    """Summary of the selected closed-loop controller policy."""

    model_config = ConfigDict(extra="forbid")

    method: str
    candidate_count: int
    tuning_scenario_count: int
    selected_policy_id: str
    selected_schedule_id: str
    selected_confidence_threshold: float
    selected_allow_retargeting: bool
    selected_confirmation_count: int = 1
    selected_schedule_start_fraction: float | None = None
    selected_schedule_interval_fraction: float | None = None
    selected_schedule_growth: float | None = None
    selected_schedule_observation_limit: int | None = None
    selected_mean_observation_count: float = 0.0
    selected_mean_deployment_count: float = 0.0
    selected_monitoring_burden_score: float = 0.0
    frontier_candidate_count: int = 0
    search_rounds: int = 0
    objective_score: float
    expected_resilience: float
    expected_fairness_score: float
    failure_prevention_rate: float
    deployment_accuracy: float
    pre_degradation_rate: float
    resilience_regret: float


class PortfolioCandidate(BaseModel):
    """Budget-feasible intervention portfolio candidate."""

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str
    intervention_ids: list[str] = Field(default_factory=list)
    total_cost: float
    intervention_count: int
    resilience_gain: float
    expected_resilience: float | None = None
    worst_case_resilience: float | None = None
    fairness_gain: float | None = None
    expected_fairness_score: float | None = None
    failure_prevention_rate: float | None = None
    cluster_coverage_rate: float | None = None
    mean_cluster_coverage_score: float | None = None
    implementation_difficulty: float | None = None
    fairness_impact: float | None = None
    objective_score: float
    search_method: str = "none"


class OptimizationResult(BaseModel):
    """Serializable optimization result."""

    model_config = ConfigDict(extra="forbid")

    budget: float | None
    ranked_interventions: list[RankedIntervention] = Field(default_factory=list)
    selected_interventions: list[RankedIntervention] = Field(default_factory=list)
    baseline_resilience: float
    best_resilience: float
    robust_mode: bool = False
    scenario_count: int = 1
    cluster_count: int = 0
    candidate_count: int = 0
    generated_policy_count: int = 0
    dynamic_policy_count: int = 0
    adaptive_policy_count: int = 0
    bundle_candidate_count: int = 0
    hierarchical_playbook_count: int = 0
    scenario_summary_path: str | None = None
    scenario_clusters_path: str | None = None
    cluster_summary_path: str | None = None
    intervention_coverage_path: str | None = None
    intervention_catalog_path: str | None = None
    bundle_hierarchy_path: str | None = None
    cluster_response_plan_path: str | None = None
    regime_plan_summary_path: str | None = None
    regime_detection_path: str | None = None
    regime_detection_confusion_path: str | None = None
    regime_detection_summary_path: str | None = None
    online_regime_detection_path: str | None = None
    online_regime_horizons_path: str | None = None
    online_regime_summary_path: str | None = None
    response_timing_path: str | None = None
    response_timing_summary_path: str | None = None
    closed_loop_regime_path: str | None = None
    closed_loop_regime_summary_path: str | None = None
    controller_policy_candidates_path: str | None = None
    controller_frontier_path: str | None = None
    controller_tuning_summary_path: str | None = None
    portfolio_candidates_path: str | None = None
    portfolio_cluster_coverage_path: str | None = None
    recommended_portfolio_id: str | None = None
    portfolio_method: str | None = None
    portfolio_objective_score: float | None = None
    portfolio_cluster_coverage_rate: float | None = None
    regime_plan_method: str | None = None
    regime_plan_standby_cost: float | None = None
    regime_plan_cluster_coverage_rate: float | None = None
    regime_plan_expected_resilience: float | None = None
    regime_plan_expected_fairness_score: float | None = None
    regime_detection_method: str | None = None
    regime_detection_accuracy: float | None = None
    regime_detection_expected_resilience: float | None = None
    regime_detection_expected_fairness_score: float | None = None
    regime_detection_failure_prevention_rate: float | None = None
    regime_detection_resilience_regret: float | None = None
    online_regime_detection_method: str | None = None
    online_regime_detection_accuracy: float | None = None
    online_regime_expected_resilience: float | None = None
    online_regime_expected_fairness_score: float | None = None
    online_regime_failure_prevention_rate: float | None = None
    online_regime_resilience_regret: float | None = None
    online_regime_pre_degradation_rate: float | None = None
    response_timing_method: str | None = None
    response_timing_best_fraction: float | None = None
    response_timing_latest_high_value_fraction: float | None = None
    response_timing_half_life_fraction: float | None = None
    response_timing_best_resilience: float | None = None
    response_timing_value_decay: float | None = None
    closed_loop_regime_method: str | None = None
    closed_loop_regime_prediction_accuracy: float | None = None
    closed_loop_regime_deployment_accuracy: float | None = None
    closed_loop_regime_expected_resilience: float | None = None
    closed_loop_regime_expected_fairness_score: float | None = None
    closed_loop_regime_failure_prevention_rate: float | None = None
    closed_loop_regime_pre_degradation_rate: float | None = None
    closed_loop_regime_retarget_rate: float | None = None
    closed_loop_regime_resilience_regret: float | None = None
    controller_tuning_method: str | None = None
    controller_policy_id: str | None = None
    controller_schedule_id: str | None = None
    controller_confidence_threshold: float | None = None
    controller_allow_retargeting: bool | None = None
    controller_confirmation_count: int | None = None
    controller_schedule_start_fraction: float | None = None
    controller_schedule_interval_fraction: float | None = None
    controller_schedule_growth: float | None = None
    controller_schedule_observation_limit: int | None = None
    controller_mean_observation_count: float | None = None
    controller_mean_deployment_count: float | None = None
    controller_monitoring_burden_score: float | None = None
    controller_frontier_count: int = 0
    controller_search_rounds: int = 0
    controller_candidate_count: int = 0
    controller_tuning_scenario_count: int = 0
    fairness_weight: float = 0.0
    pareto_frontier_path: str | None = None
    pareto_intervention_ids: list[str] = Field(default_factory=list)
    roi_table_path: str | None = None


class AttributionResult(BaseModel):
    """Failure attribution summary."""

    model_config = ConfigDict(extra="forbid")

    first_bottleneck: str | None = None
    dominant_bottlenecks: list[str] = Field(default_factory=list)
    critical_edges: list[str] = Field(default_factory=list)
    recovery_blockers: list[str] = Field(default_factory=list)
    sensitivity_summary: dict[str, float] = Field(default_factory=dict)
    narrative_summary: str


class ReportPaths(BaseModel):
    """Paths created by report generation."""

    model_config = ConfigDict(extra="forbid")

    markdown: str
    html: str
    plots: dict[str, str] = Field(default_factory=dict)


class BenchmarkRecord(BaseModel):
    """Single benchmark entry."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    metrics: dict[str, float] = Field(default_factory=dict)
    status: str
    artifacts_dir: str


class BenchmarkSummary(BaseModel):
    """Benchmark suite result."""

    model_config = ConfigDict(extra="forbid")

    suite: str
    records: list[BenchmarkRecord] = Field(default_factory=list)
    summary_table_path: str | None = None


class ComparisonRecord(BaseModel):
    """Comparable summary for one StressLab artifact directory."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    label: str
    run_dir: str
    report_html_path: str | None = None
    system_name: str
    analysis_type: str
    command: str
    failure_triggered: bool
    throughput: float
    mean_wait: float
    resilience_score: float
    fairness_score: float
    blocked_transfers: float
    recovery_time: float
    robust_mode: bool = False
    scenario_count: int = 1
    cluster_count: int = 0
    best_resilience: float | None = None
    best_shock_budget: float | None = None
    damage_score: float | None = None
    top_intervention_id: str | None = None
    recommended_portfolio_id: str | None = None
    replicate_count: int | None = None
    execution_duration: float | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class ComparisonSummary(BaseModel):
    """Aggregate summary of a multi-run comparison."""

    model_config = ConfigDict(extra="forbid")

    title: str
    run_count: int
    analysis_types: list[str] = Field(default_factory=list)
    best_resilience_run_id: str | None = None
    lowest_wait_run_id: str | None = None
    highest_fairness_run_id: str | None = None
    comparison_summary_path: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None
    tradeoff_plot_path: str | None = None
    metrics_plot_path: str | None = None


class BatchJobResult(BaseModel):
    """One batch-manifest job execution result."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    label: str
    command: str
    spec_path: str | None = None
    status: str
    run_dir: str | None = None
    report_html_path: str | None = None
    error: str | None = None
    comparison_record: ComparisonRecord | None = None


class BatchSummary(BaseModel):
    """Summary of one batch experiment campaign."""

    model_config = ConfigDict(extra="forbid")

    campaign_name: str
    description: str | None = None
    manifest_path: str
    batch_dir: str
    continue_on_error: bool = True
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    comparison_summary_path: str | None = None
    comparison_report_html_path: str | None = None
    jobs: list[BatchJobResult] = Field(default_factory=list)


class RunCatalogEntry(BaseModel):
    """One discovered artifact entry in a run catalog."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_dir: str
    timestamp: str | None = None
    system_name: str
    analysis_type: str
    command: str
    status: str = "completed"
    failure_triggered: bool | None = None
    robust_mode: bool | None = None
    scenario_count: int | None = None
    cluster_count: int | None = None
    throughput: float | None = None
    mean_wait: float | None = None
    resilience_score: float | None = None
    fairness_score: float | None = None
    best_resilience: float | None = None
    best_shock_budget: float | None = None
    damage_score: float | None = None
    top_intervention_id: str | None = None
    recommended_portfolio_id: str | None = None
    replicate_count: int | None = None
    execution_duration: float | None = None
    report_html_path: str | None = None
    compared_run_count: int | None = None
    catalog_entry_count: int | None = None
    tracked_entry_count: int | None = None
    batch_job_count: int | None = None
    failed_job_count: int | None = None
    benchmark_record_count: int | None = None
    casebook_record_count: int | None = None
    container_build_ready: bool | None = None
    generated_system_count: int | None = None
    dataset_row_count: int | None = None
    law_candidate_count: int | None = None
    symbolic_law_count: int | None = None
    shard_count: int | None = None
    shard_index: int | None = None
    worker_count: int | None = None
    resumed_system_count: int | None = None


class RunCatalogSummary(BaseModel):
    """Aggregate summary of a discovered run catalog."""

    model_config = ConfigDict(extra="forbid")

    title: str
    root: str
    entry_count: int
    analysis_type_counts: dict[str, int] = Field(default_factory=dict)
    system_counts: dict[str, int] = Field(default_factory=dict)
    catalog_csv_path: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None


class WorkspaceStatusSummary(BaseModel):
    """Aggregate snapshot of a StressLab workspace registry."""

    model_config = ConfigDict(extra="forbid")

    title: str
    root: str
    entry_count: int
    unique_system_count: int = 0
    analysis_type_counts: dict[str, int] = Field(default_factory=dict)
    system_counts: dict[str, int] = Field(default_factory=dict)
    latest_run_dir: str | None = None
    latest_timestamp: str | None = None
    latest_analysis_type: str | None = None
    latest_system_name: str | None = None
    failure_rate: float | None = None
    mean_resilience_score: float | None = None
    mean_fairness_score: float | None = None
    mean_execution_duration: float | None = None
    registry_csv_path: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None


class WorkspaceBoardSummary(BaseModel):
    """Decision-dashboard summary built from a StressLab workspace registry."""

    model_config = ConfigDict(extra="forbid")

    title: str
    root: str
    entry_count: int
    recent_entry_count: int
    system_leader_count: int
    failure_watch_count: int
    optimize_plan_count: int
    latest_run_dir: str | None = None
    latest_timestamp: str | None = None
    top_system_by_resilience: str | None = None
    top_plan_run_dir: str | None = None
    top_plan_system_name: str | None = None
    mean_resilience_score: float | None = None
    mean_fairness_score: float | None = None
    mean_execution_duration: float | None = None
    registry_csv_path: str | None = None
    recent_entries_path: str | None = None
    leaders_path: str | None = None
    failure_watchlist_path: str | None = None
    plans_path: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None


class ArtifactBundleFile(BaseModel):
    """One file captured in a portable artifact bundle."""

    model_config = ConfigDict(extra="forbid")

    path: str
    size_bytes: int
    sha256: str


class ArtifactBundleSummary(BaseModel):
    """Manifest describing a portable StressLab artifact bundle."""

    model_config = ConfigDict(extra="forbid")

    bundle_version: str
    created_at: str
    source_run_dir: str
    artifact_dir_name: str
    run_id: str
    analysis_type: str | None = None
    system_name: str | None = None
    report_html_path: str | None = None
    included_registry_files: list[str] = Field(default_factory=list)
    file_count: int
    files: list[ArtifactBundleFile] = Field(default_factory=list)
    bundle_path: str | None = None


class ArtifactRestoreSummary(BaseModel):
    """Summary of a restored StressLab artifact bundle."""

    model_config = ConfigDict(extra="forbid")

    bundle_path: str
    restored_run_dir: str
    registry_root: str
    restored_file_count: int
    source_run_id: str
    source_analysis_type: str | None = None
    collision_resolved: bool = False


class EvaluationMetricSummary(BaseModel):
    """Paired metric summary from a replication study."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    direction: str
    baseline_mean: float
    scenario_mean: float
    delta_mean: float
    delta_std: float
    ci_low: float
    ci_high: float
    improvement_rate: float


class EvaluationSummary(BaseModel):
    """Summary of a multi-seed evaluation study."""

    model_config = ConfigDict(extra="forbid")

    evaluation_mode: str
    selection_mode: str
    system_name: str
    replicate_count: int
    seeds: list[int] = Field(default_factory=list)
    selected_intervention_ids: list[str] = Field(default_factory=list)
    selected_intervention_labels: list[str] = Field(default_factory=list)
    baseline_failure_rate: float
    scenario_failure_rate: float
    failure_rate_delta: float
    replicate_metrics_path: str | None = None
    paired_deltas_path: str | None = None
    metric_summary_path: str | None = None
    treatment_plan_path: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None
    metric_summaries: list[EvaluationMetricSummary] = Field(default_factory=list)


class CasebookRecord(BaseModel):
    """One evaluation-backed evidence record inside a casebook."""

    model_config = ConfigDict(extra="forbid")

    system_name: str
    spec_path: str
    evaluation_dir: str
    selected_intervention_ids: list[str] = Field(default_factory=list)
    replicate_count: int
    baseline_failure_rate: float
    scenario_failure_rate: float
    failure_rate_delta: float
    throughput_delta: float
    mean_wait_delta: float
    resilience_delta: float
    fairness_delta: float
    report_html_path: str | None = None


class CasebookSummary(BaseModel):
    """Aggregate evidence report across multiple evaluation studies."""

    model_config = ConfigDict(extra="forbid")

    title: str
    suite: str | None = None
    record_count: int
    replicate_count: int
    casebook_dir: str
    summary_csv_path: str | None = None
    summary_json_path: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None
    records: list[CasebookRecord] = Field(default_factory=list)


class ServiceJobRecord(BaseModel):
    """Persistent service job record exposed by the workspace API."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str
    command: str
    payload: dict[str, object] = Field(default_factory=dict)
    workspace_root: str
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    run_dir: str | None = None
    report_path: str | None = None
    command_line: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    stdout_tail: str | None = None
    stderr_tail: str | None = None
    exit_code: int | None = None
    error: str | None = None
    attempt_count: int = 0


class DoctorCheck(BaseModel):
    """One deployment or environment readiness check."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    label: str
    status: str
    value: str | None = None
    message: str | None = None
    required: bool = False


class DoctorSummary(BaseModel):
    """Summary of StressLab environment and deployment readiness."""

    model_config = ConfigDict(extra="forbid")

    title: str
    workspace_root: str
    platform_system: str
    platform_release: str
    python_version: str
    ready_for_container_build: bool
    checks: list[DoctorCheck] = Field(default_factory=list)
    check_count: int = 0
    passing_required_checks: int = 0
    failing_required_checks: int = 0
    report_markdown_path: str | None = None
    report_html_path: str | None = None
    checks_csv_path: str | None = None


class GenerationRecord(BaseModel):
    """One generated synthetic system specification."""

    model_config = ConfigDict(extra="forbid")

    system_id: str
    topology_type: str
    domain: str
    spec_path: str
    seed: int
    node_count: int
    edge_count: int
    average_degree: float
    redundancy_score: float
    coupling_score: float


class GenerationSummary(BaseModel):
    """Summary of a synthetic-system generation run."""

    model_config = ConfigDict(extra="forbid")

    title: str
    topology_type: str
    generation_dir: str
    system_count: int
    shard_count: int = 1
    shard_index: int = 0
    summary_csv_path: str | None = None
    summary_json_path: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None
    records: list[GenerationRecord] = Field(default_factory=list)


class DiscoverySummary(BaseModel):
    """Summary of a synthetic fragility discovery campaign."""

    model_config = ConfigDict(extra="forbid")

    title: str
    discovery_dir: str
    generated_system_count: int
    dataset_row_count: int
    shard_count: int = 1
    shard_index: int = 0
    worker_count: int = 1
    resumed_system_count: int = 0
    topology_type_counts: dict[str, int] = Field(default_factory=dict)
    dataset_csv_path: str | None = None
    collapse_distribution_path: str | None = None
    early_warning_dataset_path: str | None = None
    symbolic_law_path: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None


class FragilityModelResult(BaseModel):
    """One fitted fragility relationship."""

    model_config = ConfigDict(extra="forbid")

    target: str
    feature: str
    model_type: str
    coefficient: float | None = None
    intercept: float | None = None
    exponent: float | None = None
    r2: float | None = None
    observations: int = 0
    formula: str | None = None


class PhaseTransitionResult(BaseModel):
    """Detected critical threshold for a collapse regime shift."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    outcome: str
    critical_threshold: float | None = None
    discontinuity_score: float | None = None
    pre_transition_mean: float | None = None
    post_transition_mean: float | None = None


class PowerLawFitResult(BaseModel):
    """Heavy-tail fit summary for cascade sizes."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    alpha: float | None = None
    xmin: float | None = None
    sample_size: int = 0
    ks_distance: float | None = None
    loglog_r2: float | None = None


class EarlyWarningSummary(BaseModel):
    """Aggregate early warning indicator summary."""

    model_config = ConfigDict(extra="forbid")

    mean_variance_increase: float | None = None
    mean_autocorrelation_increase: float | None = None
    mean_recovery_lag: float | None = None
    collapse_case_count: int = 0
    total_case_count: int = 0


class TheorySummary(BaseModel):
    """Summary of theory-layer analysis over a discovery dataset."""

    model_config = ConfigDict(extra="forbid")

    title: str
    theory_dir: str
    dataset_path: str
    source_dataset_count: int = 1
    fragility_model_count: int
    law_candidate_count: int
    symbolic_law_count: int = 0
    phase_transition_path: str | None = None
    powerlaw_path: str | None = None
    early_warning_path: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None


class ResearchSummary(BaseModel):
    """Publication-style research artifact summary."""

    model_config = ConfigDict(extra="forbid")

    title: str
    research_dir: str
    dataset_path: str
    source_dataset_count: int = 1
    theory_dir: str | None = None
    report_markdown_path: str | None = None
    report_html_path: str | None = None
    figure_count: int = 0
