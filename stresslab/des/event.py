"""Event primitives for the simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True, slots=True)
class Event:
    """Single scheduled event."""

    time: float
    priority: int
    sequence: int
    kind: str = field(compare=False)
    payload: dict[str, Any] = field(default_factory=dict, compare=False)
