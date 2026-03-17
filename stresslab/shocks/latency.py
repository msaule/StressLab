"""Latency shock helpers."""

from __future__ import annotations

from stresslab.shocks.base import Shock


def delay_factor(shock: Shock) -> float:
    """Normalize latency style shocks."""

    return shock.factor or shock.value or 1.0
