"""Domain-specific adapter helpers."""

from stresslab.systemspec.adapters.energy import apply_energy_defaults
from stresslab.systemspec.adapters.healthcare import apply_healthcare_defaults
from stresslab.systemspec.adapters.markets import apply_market_defaults
from stresslab.systemspec.adapters.supply_chain import apply_supply_chain_defaults

__all__ = [
    "apply_energy_defaults",
    "apply_healthcare_defaults",
    "apply_market_defaults",
    "apply_supply_chain_defaults",
]
