from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def toy_spec_dict() -> dict:
    return {
        "system": {
            "name": "toy_queue",
            "domain": "test",
        },
        "clock": {
            "type": "continuous",
            "start": 0,
            "end": 240,
        },
        "nodes": [
            {
                "id": "entry",
                "type": "queue_server",
                "servers": 1,
                "buffer_capacity": 20,
                "queue_policy": "fifo",
                "service_time": {
                    "distribution": "deterministic",
                    "value": 10,
                },
            }
        ],
        "arrivals": [
            {
                "node": "entry",
                "process": {
                    "type": "poisson",
                    "rate": 0.05,
                },
            }
        ],
        "failure_conditions": [
            {
                "type": "mean_wait",
                "node": "entry",
                "threshold": 8,
            }
        ],
        "interventions": [
            {
                "id": "add_capacity",
                "target": "entry",
                "action_type": "add_servers",
                "delta": 1,
                "cost": 100,
            }
        ],
        "search": {
            "objective": "min_failure",
            "max_iterations": 8,
            "direction_samples": 4,
            "search_space": [
                {
                    "id": "entry_demand_multiplier",
                    "kind": "demand_multiplier",
                    "target": "entry",
                    "min": 1.0,
                    "max": 2.0,
                    "cost_weight": 1.0,
                    "start": 0,
                    "duration": 240,
                }
            ],
        },
        "report": {
            "top_n_nodes": 1,
        },
        "seed": 11,
    }


@pytest.fixture()
def toy_spec_path(tmp_path: Path, toy_spec_dict: dict) -> Path:
    path = tmp_path / "toy.yml"
    path.write_text(yaml.safe_dump(toy_spec_dict, sort_keys=False), encoding="utf-8")
    return path
