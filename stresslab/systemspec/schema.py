"""Typed schema for StressLab system specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stresslab.config import DEFAULT_DAMAGE_WEIGHTS


class SystemMeta(BaseModel):
    """High-level system metadata."""

    model_config = ConfigDict(extra="allow")

    name: str
    domain: str | None = None
    description: str | None = None


class ClockConfig(BaseModel):
    """Simulation time horizon."""

    model_config = ConfigDict(extra="forbid")

    type: str = "continuous"
    start: float = 0.0
    end: float

    @model_validator(mode="after")
    def check_order(self) -> ClockConfig:
        if self.end <= self.start:
            raise ValueError("clock.end must be greater than clock.start")
        return self


class FlowClassSpec(BaseModel):
    """Named priority class."""

    model_config = ConfigDict(extra="forbid")

    id: str
    priority: int = 0


class ServiceTimeConfig(BaseModel):
    """Supported service time models."""

    model_config = ConfigDict(extra="forbid")

    distribution: Literal["exponential", "gamma", "lognormal", "deterministic"] = "exponential"
    rate: float | None = None
    mean: float | None = None
    value: float | None = None
    shape: float | None = None
    scale: float | None = None
    mu: float | None = None
    sigma: float | None = None

    @model_validator(mode="after")
    def validate_distribution(self) -> ServiceTimeConfig:
        dist = self.distribution
        if dist == "exponential" and self.rate is None and self.mean is None:
            raise ValueError("exponential service_time requires rate or mean")
        if dist == "gamma" and (self.shape is None or self.scale is None):
            raise ValueError("gamma service_time requires shape and scale")
        if dist == "lognormal" and (self.mu is None or self.sigma is None):
            raise ValueError("lognormal service_time requires mu and sigma")
        if dist == "deterministic" and self.value is None:
            raise ValueError("deterministic service_time requires value")
        return self


class NodeSpec(BaseModel):
    """Node in the queueing network."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: str = "queue_server"
    servers: int = 1
    buffer_capacity: int | None = None
    queue_policy: Literal["fifo", "priority"] = "fifo"
    priority_classes: list[str] = Field(default_factory=list)
    service_time: ServiceTimeConfig

    @field_validator("servers")
    @classmethod
    def validate_servers(cls, value: int) -> int:
        if value < 0:
            raise ValueError("servers must be non-negative")
        return value


class RoutingConfig(BaseModel):
    """Routing rule for an edge."""

    model_config = ConfigDict(extra="allow")

    type: Literal["probabilistic"] = "probabilistic"
    probability: float = 1.0

    @field_validator("probability")
    @classmethod
    def validate_probability(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("routing.probability must be between 0 and 1")
        return value


class EdgeSpec(BaseModel):
    """Directed edge between nodes."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    enabled: bool = True
    travel_time: float = 0.0
    transfer_capacity: float | None = None

    @field_validator("travel_time")
    @classmethod
    def validate_travel_time(cls, value: float) -> float:
        if value < 0:
            raise ValueError("travel_time must be non-negative")
        return value


class SeasonalityConfig(BaseModel):
    """Sinusoidal seasonality configuration."""

    model_config = ConfigDict(extra="forbid")

    period: str | float = "daily"
    amplitude: float = 0.0


class ArrivalProcessConfig(BaseModel):
    """External arrival process."""

    model_config = ConfigDict(extra="allow")

    type: Literal["poisson", "nonhomogeneous_poisson"] = "poisson"
    rate: float | None = None
    base_rate: float | None = None
    seasonality: SeasonalityConfig | None = None

    @model_validator(mode="after")
    def validate_rate(self) -> ArrivalProcessConfig:
        rate = self.base_rate if self.base_rate is not None else self.rate
        if rate is None or rate <= 0:
            raise ValueError("arrival process requires a positive rate or base_rate")
        return self


class ArrivalSpec(BaseModel):
    """Arrival stream attached to a node."""

    model_config = ConfigDict(extra="allow")

    node: str
    process: ArrivalProcessConfig
    class_mix: dict[str, float] = Field(default_factory=dict)
    batch_size: int = 1

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, value: int) -> int:
        if value < 1:
            raise ValueError("batch_size must be at least 1")
        return value


class ShockSpec(BaseModel):
    """Shock applied to a node, edge, or arrival stream."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    target: str | None = None
    start: float = 0.0
    duration: float | None = None
    factor: float | None = None
    delta: float | None = None
    fraction: float | None = None
    value: float | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    components: list[ShockSpec] = Field(default_factory=list)
    label: str | None = None

    def end_time(self) -> float | None:
        """Return the shock end time if duration is finite."""

        if self.duration is None:
            return None
        return self.start + self.duration


class FailureConditionSpec(BaseModel):
    """Composable failure condition definition."""

    model_config = ConfigDict(extra="allow")

    type: str
    node: str | None = None
    threshold: float | None = None
    duration: float | None = None
    conditions: list[FailureConditionSpec] = Field(default_factory=list)


class PolicyStageSpec(BaseModel):
    """One escalation stage inside a threshold policy."""

    model_config = ConfigDict(extra="allow")

    id: str
    label: str | None = None
    trigger_threshold: float
    clear_threshold: float | None = None
    action_type: str | None = None
    parameter: str | None = None
    delta: float | None = None
    replacement: Any | None = None

    @field_validator("trigger_threshold", "clear_threshold")
    @classmethod
    def validate_thresholds(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("policy stage thresholds must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_hysteresis(self) -> PolicyStageSpec:
        if self.clear_threshold is not None and self.clear_threshold > self.trigger_threshold:
            raise ValueError("policy stage clear_threshold must be <= trigger_threshold")
        return self


class PolicyScheduleSpec(BaseModel):
    """Timed policy schedule applied during a simulation run."""

    model_config = ConfigDict(extra="allow")

    id: str
    label: str | None = None
    target: str
    action_type: str
    mode: Literal["scheduled", "threshold"] = "scheduled"
    start: float = 0.0
    duration: float | None = None
    parameter: str | None = None
    delta: float | None = None
    replacement: Any | None = None
    trigger_metric: Literal["queue_length", "utilization", "holding_count"] | None = None
    trigger_node: str | None = None
    trigger_threshold: float | None = None
    clear_threshold: float | None = None
    min_active_duration: float = 0.0
    cooldown: float = 0.0
    stages: list[PolicyStageSpec] = Field(default_factory=list)
    applicability_constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("start")
    @classmethod
    def validate_start(cls, value: float) -> float:
        if value < 0:
            raise ValueError("policy.start must be non-negative")
        return value

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("policy.duration must be non-negative")
        return value

    @field_validator("trigger_threshold", "clear_threshold", "min_active_duration", "cooldown")
    @classmethod
    def validate_nonnegative_fields(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("policy trigger fields must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_mode(self) -> PolicyScheduleSpec:
        if self.mode == "threshold":
            if self.trigger_metric is None:
                raise ValueError("threshold policies require trigger_metric")
            if self.trigger_threshold is None and not self.stages:
                raise ValueError("threshold policies require trigger_threshold or explicit stages")
            if (
                self.trigger_threshold is not None
                and self.clear_threshold is not None
                and self.clear_threshold > self.trigger_threshold
            ):
                raise ValueError("clear_threshold must be less than or equal to trigger_threshold")
            if self.stages:
                thresholds = [stage.trigger_threshold for stage in self.stages]
                if thresholds != sorted(thresholds):
                    raise ValueError("policy stages must be ordered by trigger_threshold")
        return self

    def end_time(self) -> float | None:
        """Return the policy end time if duration is finite."""

        if self.duration is None:
            return None
        return self.start + self.duration


class InterventionSpec(BaseModel):
    """Supported intervention definition."""

    model_config = ConfigDict(extra="allow")

    id: str
    label: str | None = None
    target: str
    action_type: str
    policy_mode: Literal["scheduled", "threshold"] | None = None
    start: float | None = None
    duration: float | None = None
    parameter: str | None = None
    delta: float | None = None
    replacement: Any | None = None
    trigger_metric: Literal["queue_length", "utilization", "holding_count"] | None = None
    trigger_node: str | None = None
    trigger_threshold: float | None = None
    clear_threshold: float | None = None
    min_active_duration: float | None = None
    cooldown: float | None = None
    stages: list[PolicyStageSpec] = Field(default_factory=list)
    bundle_members: list[str] = Field(default_factory=list)
    cost: float
    implementation_difficulty: float | None = None
    fairness_impact: float | None = None
    applicability_constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("start")
    @classmethod
    def validate_start(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("intervention.start must be non-negative")
        return value

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("intervention.duration must be non-negative")
        return value

    @field_validator("trigger_threshold", "clear_threshold", "min_active_duration", "cooldown")
    @classmethod
    def validate_trigger_fields(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("intervention trigger fields must be non-negative")
        return value

    def end_time(self) -> float | None:
        """Return the intervention end time if scheduled."""

        if self.start is None or self.duration is None:
            return None
        return self.start + self.duration


class SearchDimensionConfig(BaseModel):
    """One searchable shock dimension."""

    model_config = ConfigDict(extra="allow")

    id: str
    kind: str
    target: str
    min: float
    max: float
    cost_weight: float = 1.0
    transform: str | None = None
    start: float = 0.0
    duration: float | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> SearchDimensionConfig:
        if self.max < self.min:
            raise ValueError("search dimension max must be greater than or equal to min")
        return self


class SearchConfig(BaseModel):
    """Search configuration."""

    model_config = ConfigDict(extra="allow")

    objective: str = "min_failure"
    max_iterations: int = 24
    direction_samples: int = 12
    damage_function: str = "composite_damage"
    damage_weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_DAMAGE_WEIGHTS))
    search_space: list[SearchDimensionConfig] = Field(default_factory=list)
    budget: float | None = None


class ReportConfig(BaseModel):
    """Report generation configuration."""

    model_config = ConfigDict(extra="allow")

    top_n_nodes: int = 3
    include_plots: bool = True


class ValidationResult(BaseModel):
    """Structured validation output."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SystemSpec(BaseModel):
    """Top-level StressLab system definition."""

    model_config = ConfigDict(extra="allow")

    system: SystemMeta
    clock: ClockConfig
    classes: list[FlowClassSpec] = Field(default_factory=list)
    nodes: list[NodeSpec] = Field(default_factory=list)
    edges: list[EdgeSpec] = Field(default_factory=list)
    arrivals: list[ArrivalSpec] = Field(default_factory=list)
    policies: list[PolicyScheduleSpec] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    shocks: list[ShockSpec] = Field(default_factory=list)
    failure_conditions: list[FailureConditionSpec] = Field(default_factory=list)
    interventions: list[InterventionSpec] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    search: SearchConfig = Field(default_factory=SearchConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    seed: int = 7


@dataclass(slots=True)
class ResolvedSystemSpec:
    """SystemSpec with semantic indexes for fast simulation."""

    spec: SystemSpec
    node_index: dict[str, NodeSpec]
    outgoing_edges: dict[str, list[EdgeSpec]]
    incoming_edges: dict[str, list[EdgeSpec]]
    class_priorities: dict[str, int]
