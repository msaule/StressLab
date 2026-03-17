"""Correlated shock utilities."""

from __future__ import annotations

from stresslab.shocks.base import Shock


def correlated_targets(shocks: list[Shock], prefix: str) -> list[str]:
    """Return active correlated shock targets matching a prefix."""

    return [shock.target or "" for shock in shocks if shock.id.startswith(prefix)]
