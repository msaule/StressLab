"""Clock helpers for the simulator."""

from __future__ import annotations


def horizon_length(start: float, end: float) -> float:
    """Return the simulation horizon length."""

    return max(0.0, end - start)
