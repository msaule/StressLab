"""YAML loading and resolution for StressLab."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from stresslab.errors import SpecValidationError
from stresslab.systemspec.schema import ResolvedSystemSpec, SystemSpec
from stresslab.systemspec.validators import validate_spec


def _normalize_intervention(raw: dict[str, Any]) -> dict[str, Any]:
    item = dict(raw)
    if "action_type" not in item:
        if "action" in item:
            item["action_type"] = item.pop("action")
        elif "type" in item:
            item["action_type"] = item.pop("type")
        elif item.get("parameter") == "servers":
            item["action_type"] = "add_servers"
        elif item.get("parameter") == "buffer_capacity":
            item["action_type"] = "increase_buffer_capacity"
    if item.get("label") is None:
        item["label"] = item["id"].replace("_", " ")
    return item


def _normalize_policy(raw: dict[str, Any]) -> dict[str, Any]:
    item = dict(raw)
    if "action_type" not in item:
        if "action" in item:
            item["action_type"] = item.pop("action")
        elif "type" in item:
            item["action_type"] = item.pop("type")
    if item.get("label") is None and "id" in item:
        item["label"] = str(item["id"]).replace("_", " ")
    return item


def _normalize_raw_spec(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    system = dict(data.get("system", {}))
    if "clock" not in data and "clock" in system:
        data["clock"] = system.pop("clock")
        data["system"] = system
    data.setdefault("clock", {"start": 0, "end": 1440})
    if "system" not in data:
        raise SpecValidationError("Missing required top-level 'system' block.")
    data["interventions"] = [_normalize_intervention(item) for item in data.get("interventions", [])]
    data["policies"] = [_normalize_policy(item) for item in data.get("policies", [])]
    return data


def load_spec(path: str | Path) -> SystemSpec:
    """Load and validate a YAML specification."""

    spec_path = Path(path)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SpecValidationError(f"Spec at {spec_path} must decode to a mapping.")
    normalized = _normalize_raw_spec(raw)
    try:
        spec = SystemSpec.model_validate(normalized)
    except Exception as exc:  # pragma: no cover - pydantic shapes the final message
        raise SpecValidationError(f"Failed to parse {spec_path}: {exc}") from exc
    validation = validate_spec(spec)
    if not validation.valid:
        joined = "\n".join(validation.errors)
        raise SpecValidationError(f"Spec validation failed for {spec_path}:\n{joined}")
    return spec


def resolve_spec(spec: SystemSpec) -> ResolvedSystemSpec:
    """Build indexes required by the simulator."""

    node_index = {node.id: node for node in spec.nodes}
    outgoing_edges: dict[str, list[Any]] = {node.id: [] for node in spec.nodes}
    incoming_edges: dict[str, list[Any]] = {node.id: [] for node in spec.nodes}
    for edge in spec.edges:
        outgoing_edges.setdefault(edge.from_node, []).append(edge)
        incoming_edges.setdefault(edge.to_node, []).append(edge)
    class_priorities = {flow_class.id: flow_class.priority for flow_class in spec.classes}
    for node in spec.nodes:
        if not node.priority_classes:
            continue
        for rank, class_id in enumerate(node.priority_classes):
            class_priorities.setdefault(class_id, rank)
    return ResolvedSystemSpec(
        spec=spec,
        node_index=node_index,
        outgoing_edges=outgoing_edges,
        incoming_edges=incoming_edges,
        class_priorities=class_priorities,
    )
