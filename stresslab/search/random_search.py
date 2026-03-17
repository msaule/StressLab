"""Random scenario sampling helpers."""

from __future__ import annotations

import numpy as np

from stresslab.search.common import budget_from_vector
from stresslab.systemspec.schema import SearchDimensionConfig


def sample_direction(rng: np.random.Generator, dimensions: int) -> np.ndarray:
    """Sample an L1-normalized non-negative direction."""

    if dimensions == 1:
        return np.array([1.0], dtype=float)
    return rng.dirichlet(np.ones(dimensions))


def vector_from_direction(
    direction: np.ndarray,
    search_space: list[SearchDimensionConfig],
    scale: float,
) -> dict[str, float]:
    """Project a direction and scalar scale into the configured search space."""

    vector: dict[str, float] = {}
    for dimension, component in zip(search_space, direction, strict=True):
        span = dimension.max - dimension.min
        vector[dimension.id] = dimension.min + scale * component * span
    return vector


def sample_under_budget(
    rng: np.random.Generator,
    search_space: list[SearchDimensionConfig],
    budget: float,
) -> dict[str, float]:
    """Sample a random shock vector whose budget stays under a target."""

    if not search_space:
        return {}
    allocation = rng.dirichlet(np.ones(len(search_space)))
    vector: dict[str, float] = {}
    for share, dimension in zip(allocation, search_space, strict=True):
        if dimension.cost_weight <= 0:
            normalized = 0.0
        else:
            normalized = min(1.0, (budget * share) / dimension.cost_weight)
        vector[dimension.id] = dimension.min + normalized * (dimension.max - dimension.min)
    if budget_from_vector(vector, search_space) > budget:
        vector = {dimension.id: dimension.min for dimension in search_space}
    return vector
