"""Regime-switch helper utilities."""

from __future__ import annotations

from stresslab.shocks.base import Shock


def active_regimes(shocks: list[Shock], now: float) -> list[str]:
    """List active regime-switch shock identifiers."""

    active: list[str] = []
    for shock in shocks:
        if shock.type != "regime_switch":
            continue
        end = shock.end_time()
        if shock.start <= now and (end is None or now <= end):
            active.append(shock.id)
    return active
