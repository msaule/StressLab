"""Capacity shock helpers."""

from __future__ import annotations

from stresslab.shocks.base import Shock


def capacity_drop(shock: Shock) -> float:
    """Normalize a capacity drop shock into a fractional loss."""

    return shock.fraction or shock.factor or 0.0
