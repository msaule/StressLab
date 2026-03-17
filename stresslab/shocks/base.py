"""Shock application helpers."""

from __future__ import annotations

from dataclasses import dataclass

from stresslab.des.node import EdgeState, NodeState
from stresslab.systemspec.schema import ShockSpec


@dataclass(slots=True)
class Shock:
    """Flattened runtime shock."""

    id: str
    type: str
    target: str | None
    start: float
    duration: float | None = None
    factor: float | None = None
    delta: float | None = None
    fraction: float | None = None
    value: float | None = None

    def end_time(self) -> float | None:
        if self.duration is None:
            return None
        return self.start + self.duration


def flatten_shocks(shocks: list[ShockSpec]) -> list[Shock]:
    """Flatten compound shocks into simple runtime shocks."""

    flattened: list[Shock] = []
    for shock in shocks:
        if shock.type == "compound":
            for index, component in enumerate(shock.components):
                flattened.extend(
                    flatten_shocks(
                        [
                            component.model_copy(
                                update={
                                    "id": f"{shock.id}__{index}_{component.id}",
                                    "start": shock.start if component.start == 0 else component.start,
                                }
                            )
                        ]
                    )
                )
            continue
        flattened.append(
            Shock(
                id=shock.id,
                type=shock.type,
                target=shock.target,
                start=shock.start,
                duration=shock.duration,
                factor=shock.factor,
                delta=shock.delta,
                fraction=shock.fraction,
                value=shock.value,
            )
        )
    return flattened


def apply_shock(node_or_edge, shock: Shock, now: float) -> None:
    """Apply a shock to a node or edge state."""

    if isinstance(node_or_edge, NodeState):
        _apply_node_shock(node_or_edge, shock, now)
        return
    if isinstance(node_or_edge, EdgeState):
        _apply_edge_shock(node_or_edge, shock)
        return


def remove_shock(node_or_edge, shock: Shock, now: float) -> None:
    """Remove a previously applied shock."""

    if isinstance(node_or_edge, NodeState):
        node_or_edge.active_modifiers.pop(shock.id, None)
        _recompute_node_capacity(node_or_edge, now)
        return
    if isinstance(node_or_edge, EdgeState):
        node_or_edge.active_modifiers.pop(shock.id, None)
        _recompute_edge_state(node_or_edge)
        return


def refresh_node_state(node_state: NodeState, now: float) -> None:
    """Recompute a node state after non-shock spec changes."""

    _recompute_node_capacity(node_state, now)


def refresh_edge_state(edge_state: EdgeState) -> None:
    """Recompute an edge state after non-shock spec changes."""

    _recompute_edge_state(edge_state)


def _apply_node_shock(node_state: NodeState, shock: Shock, now: float) -> None:
    node_state.active_modifiers[shock.id] = {
        "type": shock.type,
        "factor": shock.factor,
        "delta": shock.delta,
        "fraction": shock.fraction,
        "value": shock.value,
    }
    _recompute_node_capacity(node_state, now)


def _apply_edge_shock(edge_state: EdgeState, shock: Shock) -> None:
    edge_state.active_modifiers[shock.id] = {
        "type": shock.type,
        "factor": shock.factor,
        "delta": shock.delta,
        "fraction": shock.fraction,
        "value": shock.value,
    }
    _recompute_edge_state(edge_state)


def _recompute_node_capacity(node_state: NodeState, now: float) -> None:
    retained = 1.0
    node_state.server_delta = 0
    node_state.buffer_delta = 0
    node_state.service_time_factor = 1.0
    for modifier in node_state.active_modifiers.values():
        modifier_type = modifier["type"]
        if modifier_type == "capacity_fraction":
            drop = modifier.get("fraction") or modifier.get("factor") or 0.0
            retained *= max(0.0, 1.0 - drop)
        elif modifier_type == "server_delta":
            node_state.server_delta += int(modifier.get("delta") or 0)
        elif modifier_type in {"service_time_factor", "delay_factor", "latency_factor"}:
            node_state.service_time_factor *= modifier.get("factor") or modifier.get("value") or 1.0
        elif modifier_type == "buffer_delta":
            node_state.buffer_delta += int(modifier.get("delta") or 0)
    node_state.capacity_drop = 1.0 - retained
    base_servers = node_state.spec.servers
    node_state.effective_servers = max(0, int(round(base_servers * retained + node_state.server_delta)))
    if node_state.spec.buffer_capacity is None:
        node_state.effective_buffer_capacity = None
    else:
        node_state.effective_buffer_capacity = max(0, node_state.spec.buffer_capacity + node_state.buffer_delta)
    _update_degraded(node_state, now)


def _recompute_edge_state(edge_state: EdgeState) -> None:
    edge_state.enabled = edge_state.spec.enabled
    edge_state.travel_time = edge_state.spec.travel_time
    edge_state.transfer_capacity = edge_state.spec.transfer_capacity
    for modifier in edge_state.active_modifiers.values():
        modifier_type = modifier["type"]
        if modifier_type == "edge_disable":
            edge_state.enabled = False
        elif modifier_type in {"travel_delay_factor", "delay_factor"}:
            edge_state.travel_time *= modifier.get("factor") or 1.0
        elif modifier_type == "transfer_capacity_fraction" and edge_state.transfer_capacity is not None:
            retained = max(0.0, 1.0 - (modifier.get("fraction") or modifier.get("factor") or 0.0))
            edge_state.transfer_capacity *= retained


def _update_degraded(node_state: NodeState, now: float) -> None:
    degraded = node_state.overflow_count > 0 or len(node_state.queue) > 0 or node_state.effective_servers == 0
    node_state.degraded = degraded
    if degraded and node_state.first_degraded_time is None:
        node_state.first_degraded_time = now
    if degraded:
        node_state.last_degraded_time = now
