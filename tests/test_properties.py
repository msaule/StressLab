from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from stresslab.search.common import budget_from_vector
from stresslab.systemspec.schema import SearchDimensionConfig


@given(st.floats(min_value=1.0, max_value=2.0))
def test_budget_function_stays_within_expected_bounds(value: float):
    dimension = SearchDimensionConfig(
        id="shock",
        kind="demand_multiplier",
        target="node",
        min=1.0,
        max=2.0,
        cost_weight=1.5,
    )
    budget = budget_from_vector({"shock": value}, [dimension])
    assert 0.0 <= budget <= 1.5
