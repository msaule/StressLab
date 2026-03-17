"""Project-wide configuration constants."""

from __future__ import annotations

from pathlib import Path

__version__ = "0.1.0"
SCHEMA_VERSION = "0.1"
DEFAULT_OUTPUT_ROOT = Path("runs")
DEFAULT_TOP_N_NODES = 3
DEFAULT_DAMAGE_WEIGHTS = {
    "throughput_loss": 0.25,
    "mean_wait_norm": 0.2,
    "p95_wait_norm": 0.15,
    "backlog_norm": 0.2,
    "holding_norm": 0.0,
    "recovery_norm": 0.1,
    "cascade_norm": 0.1,
    "edge_cascade_norm": 0.0,
    "fairness_degradation": 0.0,
}
DEFAULT_RESILIENCE_WEIGHTS = {
    "recovery": 0.35,
    "throughput": 0.4,
    "cascade": 0.25,
}
