"""Budgeted intervention selection helpers."""

from __future__ import annotations

from stresslab.models import RankedIntervention


def total_cost(interventions: list[RankedIntervention]) -> float:
    """Return the total selected intervention cost."""

    return sum(item.cost for item in interventions)
