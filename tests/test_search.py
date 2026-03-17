from __future__ import annotations

from stresslab.optimize import build_scenario_portfolio
from stresslab.search import Searcher
from stresslab.systemspec import load_spec


def test_min_failure_search_finds_positive_budget(toy_spec_path):
    spec = load_spec(toy_spec_path)
    result = Searcher(spec, objective="min_failure", seed=spec.seed).find_min_failure()
    assert result.success
    assert result.failure_triggered
    assert 0 < result.best_shock_budget <= 1.0


def test_build_scenario_portfolio_returns_multiple_scenarios(toy_spec_path):
    spec = load_spec(toy_spec_path)
    scenarios = build_scenario_portfolio(spec, seed=spec.seed, scenario_budget=0.5, random_samples=2)
    assert len(scenarios) >= 3
    assert scenarios[0].scenario_id == "configured"
