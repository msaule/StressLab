"""Demand shock helpers."""

from __future__ import annotations

from stresslab.shocks.base import Shock


def demand_multiplier_at_time(shocks: list[Shock], target: str, now: float) -> float:
    """Return the product of active demand multipliers for a target."""

    multiplier = 1.0
    for shock in shocks:
        if shock.type != "demand_multiplier" or shock.target != target:
            continue
        end = shock.end_time()
        active = shock.start <= now and (end is None or now <= end)
        if active:
            multiplier *= shock.factor or shock.value or 1.0
    return multiplier
