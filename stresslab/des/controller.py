"""Runtime controller primitives for closed-loop simulation."""

from __future__ import annotations

from dataclasses import dataclass, field

from stresslab.systemspec.schema import InterventionSpec


@dataclass(slots=True)
class ControllerDecision:
    """One controller decision taken at a runtime observation tick."""

    interventions: list[InterventionSpec] = field(default_factory=list)
    log: dict[str, object] = field(default_factory=dict)
