"""Runtime node and edge state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from stresslab.systemspec.schema import EdgeSpec, NodeSpec


@dataclass(slots=True)
class Job:
    """A unit of flow through the network."""

    job_id: int
    class_id: str
    created_at: float
    node_arrival_time: float
    queue_sequence: int
    history: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NodeState:
    """Mutable runtime state for a queueing node."""

    spec: NodeSpec
    queue: list[Job] = field(default_factory=list)
    in_service: dict[int, tuple[Job, float, float]] = field(default_factory=dict)
    effective_servers: int = 0
    effective_buffer_capacity: int | None = None
    service_time_factor: float = 1.0
    capacity_drop: float = 0.0
    server_delta: int = 0
    buffer_delta: int = 0
    arrival_count: int = 0
    completion_count: int = 0
    dropped_count: int = 0
    class_arrival_counts: dict[str, int] = field(default_factory=dict)
    class_completion_counts: dict[str, int] = field(default_factory=dict)
    class_dropped_counts: dict[str, int] = field(default_factory=dict)
    class_wait_times: dict[str, list[float]] = field(default_factory=dict)
    overflow_count: int = 0
    queue_integral: float = 0.0
    utilization_integral: float = 0.0
    wait_times: list[float] = field(default_factory=list)
    service_times: list[float] = field(default_factory=list)
    max_queue_length: int = 0
    blocked_routing_count: int = 0
    holding_integral: float = 0.0
    routed_hold_count: int = 0
    degraded: bool = False
    first_degraded_time: float | None = None
    last_degraded_time: float | None = None
    queue_times: list[float] = field(default_factory=list)
    queue_lengths: list[float] = field(default_factory=list)
    utilization_times: list[float] = field(default_factory=list)
    utilization_values: list[float] = field(default_factory=list)
    active_modifiers: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class EdgeState:
    """Mutable runtime state for an edge."""

    spec: EdgeSpec
    enabled: bool = True
    travel_time: float = 0.0
    transfer_capacity: float | None = None
    transferred_count: int = 0
    blocked_count: int = 0
    total_delay: float = 0.0
    max_delay: float = 0.0
    next_available_time: float = 0.0
    degraded: bool = False
    first_degraded_time: float | None = None
    last_degraded_time: float | None = None
    active_modifiers: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class SimulationState:
    """Top-level mutable simulator state."""

    current_time: float
    future_event_queue: list[Any]
    node_states: dict[str, NodeState]
    edge_states: dict[str, EdgeState]
    active_shocks: dict[str, Any]
    failure_flags: list[str] = field(default_factory=list)
