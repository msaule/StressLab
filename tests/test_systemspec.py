from __future__ import annotations

import yaml

from stresslab.systemspec import load_spec, validate_spec


def test_load_spec_parses_toy_yaml(toy_spec_path):
    spec = load_spec(toy_spec_path)
    assert spec.system.name == "toy_queue"
    assert len(spec.nodes) == 1
    assert spec.nodes[0].id == "entry"


def test_load_spec_parses_policy_schedule(toy_spec_dict):
    toy_spec_dict["policies"] = [
        {
            "id": "surge_priority",
            "target": "entry",
            "action_type": "priority_policy_change",
            "start": 15,
            "duration": 30,
            "replacement": "priority",
        }
    ]
    spec = load_inline_spec(toy_spec_dict)
    assert spec.policies[0].id == "surge_priority"
    assert spec.policies[0].end_time() == 45


def test_load_spec_parses_threshold_policy_schedule(toy_spec_dict):
    toy_spec_dict["policies"] = [
        {
            "id": "adaptive_priority",
            "target": "entry",
            "action_type": "priority_policy_change",
            "mode": "threshold",
            "replacement": "priority",
            "trigger_metric": "queue_length",
            "trigger_node": "entry",
            "trigger_threshold": 4,
            "clear_threshold": 2,
            "min_active_duration": 10,
            "cooldown": 5,
        }
    ]
    spec = load_inline_spec(toy_spec_dict)
    assert spec.policies[0].mode == "threshold"
    assert spec.policies[0].trigger_metric == "queue_length"
    assert spec.policies[0].trigger_threshold == 4


def test_load_spec_parses_multistage_threshold_policy(toy_spec_dict):
    toy_spec_dict["policies"] = [
        {
            "id": "adaptive_ladder",
            "target": "entry",
            "action_type": "priority_policy_change",
            "mode": "threshold",
            "replacement": "priority",
            "trigger_metric": "queue_length",
            "trigger_node": "entry",
            "stages": [
                {"id": "watch", "trigger_threshold": 3, "clear_threshold": 1, "replacement": "priority"},
                {"id": "surge", "trigger_threshold": 6, "clear_threshold": 4, "replacement": "priority"},
            ],
        }
    ]
    spec = load_inline_spec(toy_spec_dict)
    assert len(spec.policies[0].stages) == 2
    assert spec.policies[0].stages[1].id == "surge"


def test_validate_spec_rejects_unknown_edge_target(toy_spec_dict):
    toy_spec_dict["edges"] = [
        {
            "from": "entry",
            "to": "missing",
            "routing": {"type": "probabilistic", "probability": 1.0},
        }
    ]
    spec = load_inline_spec(toy_spec_dict)
    validation = validate_spec(spec)
    assert not validation.valid
    assert any("unknown destination node" in error for error in validation.errors)


def test_validate_spec_rejects_duplicate_intervention_ids(toy_spec_dict):
    toy_spec_dict["interventions"] = [
        {"id": "dup", "target": "entry", "action_type": "add_servers", "delta": 1, "cost": 10},
        {"id": "dup", "target": "entry", "action_type": "add_servers", "delta": 2, "cost": 20},
    ]
    spec = load_inline_spec(toy_spec_dict)
    validation = validate_spec(spec)
    assert not validation.valid
    assert any("Intervention IDs must be unique" in error for error in validation.errors)


def load_inline_spec(payload: dict):
    data = yaml.safe_load(yaml.safe_dump(payload))
    from stresslab.systemspec.schema import SystemSpec

    return SystemSpec.model_validate(data)
