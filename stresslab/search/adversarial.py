"""Adversarial search strategies for StressLab."""

from __future__ import annotations

import numpy as np

from stresslab.des import Simulator
from stresslab.errors import SearchError
from stresslab.models import SearchResult
from stresslab.search.binary_search import binary_threshold_search
from stresslab.search.common import apply_shock_vector, budget_from_vector, damage_score
from stresslab.search.random_search import (
    sample_direction,
    sample_under_budget,
    vector_from_direction,
)
from stresslab.systemspec.parser import resolve_spec
from stresslab.systemspec.schema import ResolvedSystemSpec, SystemSpec


class Searcher:
    """Run minimum-failure and worst-case searches."""

    def __init__(self, spec, objective: str, seed: int | None = None) -> None:
        if isinstance(spec, ResolvedSystemSpec):
            self.spec = spec.spec
            self.resolved = spec
        elif isinstance(spec, SystemSpec):
            self.spec = spec
            self.resolved = resolve_spec(spec)
        else:
            raise SearchError("Searcher expects a SystemSpec or ResolvedSystemSpec.")
        self.objective = objective
        self.seed = seed if seed is not None else self.spec.seed
        self.rng = np.random.default_rng(self.seed)
        baseline_simulator = Simulator(self.resolved, seed=self.seed)
        self.baseline_result = baseline_simulator.run()
        self.history: list[dict[str, float | bool]] = []
        self._cache: dict[tuple[float, ...], object] = {}

    def find_min_failure(self) -> SearchResult:
        """Find the lowest-budget scenario that triggers failure."""

        search_space = self.spec.search.search_space
        if not search_space:
            raise SearchError("find_min_failure requires search.search_space in the spec.")
        if self.baseline_result.failure_triggered:
            return SearchResult(
                objective="min_failure",
                success=True,
                best_shock_vector={dimension.id: dimension.min for dimension in search_space},
                best_shock_budget=0.0,
                damage_score=damage_score(
                    self.baseline_result,
                    objective=self.spec.search.damage_function,
                    weights=self.spec.search.damage_weights,
                ),
                failure_triggered=True,
                search_iterations=0,
                evaluated_scenarios=1,
                baseline_metrics=self.baseline_result.metrics,
                best_metrics=self.baseline_result.metrics,
                result_paths={},
            )

        directions = [np.ones(len(search_space), dtype=float)]
        directions.extend(np.eye(len(search_space), dtype=float))
        while len(directions) < max(self.spec.search.direction_samples, len(directions)):
            directions.append(sample_direction(self.rng, len(search_space)))

        best_vector: dict[str, float] | None = None
        best_budget = float("inf")
        best_result = None
        evaluations = 1
        self._cache[self._vector_key({dimension.id: dimension.min for dimension in search_space})] = self.baseline_result

        for direction in directions:
            if direction.sum() > 0:
                direction = direction / direction.sum()
            max_vector = vector_from_direction(direction, search_space, 1.0)
            max_result = self._evaluate_vector(max_vector)
            evaluations += 1
            if not max_result.failure_triggered:
                continue

            def evaluate(scale: float, current_direction=direction):
                vector = vector_from_direction(current_direction, search_space, scale)
                return self._evaluate_vector(vector)

            scale, threshold_result = binary_threshold_search(
                evaluate,
                iterations=self.spec.search.max_iterations,
            )
            evaluations += self.spec.search.max_iterations
            if threshold_result is None:
                continue
            vector = vector_from_direction(direction, search_space, scale)
            budget = budget_from_vector(vector, search_space)
            if budget < best_budget:
                best_budget = budget
                best_vector = vector
                best_result = threshold_result

        if best_vector is None or best_result is None:
            return SearchResult(
                objective="min_failure",
                success=False,
                best_shock_vector={dimension.id: dimension.min for dimension in search_space},
                best_shock_budget=float("inf"),
                damage_score=0.0,
                failure_triggered=False,
                search_iterations=len(directions),
                evaluated_scenarios=evaluations,
                baseline_metrics=self.baseline_result.metrics,
                best_metrics=self.baseline_result.metrics,
                result_paths={},
            )

        best_damage = damage_score(
            best_result,
            objective=self.spec.search.damage_function,
            weights=self.spec.search.damage_weights,
        )
        return SearchResult(
            objective="min_failure",
            success=True,
            best_shock_vector=best_vector,
            best_shock_budget=best_budget,
            damage_score=best_damage,
            failure_triggered=True,
            search_iterations=len(directions),
            evaluated_scenarios=evaluations,
            baseline_metrics=self.baseline_result.metrics,
            best_metrics=best_result.metrics,
            result_paths={},
        )

    def find_worst_case(self, budget: float) -> SearchResult:
        """Find a high-damage scenario subject to a shock budget."""

        search_space = self.spec.search.search_space
        if not search_space:
            raise SearchError("find_worst_case requires search.search_space in the spec.")
        best_vector = {dimension.id: dimension.min for dimension in search_space}
        best_result = self.baseline_result
        best_damage = damage_score(
            self.baseline_result,
            objective=self.spec.search.damage_function,
            weights=self.spec.search.damage_weights,
        )
        evaluations = 1
        candidates = self._candidate_vectors_for_budget(budget)
        for vector in candidates:
            result = self._evaluate_vector(vector)
            evaluations += 1
            score = damage_score(
                result,
                objective=self.spec.search.damage_function,
                weights=self.spec.search.damage_weights,
            )
            if score > best_damage:
                best_damage = score
                best_vector = vector
                best_result = result
        best_vector, best_result, best_damage, evaluations = self._coordinate_refine(
            best_vector,
            best_result,
            best_damage,
            budget,
            evaluations,
        )
        return SearchResult(
            objective="worst_case",
            success=True,
            best_shock_vector=best_vector,
            best_shock_budget=budget_from_vector(best_vector, search_space),
            damage_score=best_damage,
            failure_triggered=best_result.failure_triggered,
            search_iterations=self.spec.search.max_iterations,
            evaluated_scenarios=evaluations,
            baseline_metrics=self.baseline_result.metrics,
            best_metrics=best_result.metrics,
            result_paths={},
        )

    def replay_best(self, search_result: SearchResult):
        """Run the best scenario again and return the full simulation result."""

        scenario_spec = apply_shock_vector(self.spec, search_result.best_shock_vector)
        scenario_resolved = resolve_spec(scenario_spec)
        simulator = Simulator(
            scenario_resolved,
            seed=self.seed,
            baseline_metrics=self.baseline_result.metrics,
        )
        return scenario_spec, simulator, simulator.run()

    def _evaluate_vector(self, vector: dict[str, float]):
        cache_key = self._vector_key(vector)
        cached = cache_key in self._cache
        if cached:
            result = self._cache[cache_key]
        else:
            scenario_spec = apply_shock_vector(self.spec, vector)
            scenario_resolved = resolve_spec(scenario_spec)
            simulator = Simulator(
                scenario_resolved,
                seed=self.seed,
                baseline_metrics=self.baseline_result.metrics,
            )
            result = simulator.run()
            self._cache[cache_key] = result
        record: dict[str, float | bool] = {
            "budget": budget_from_vector(vector, self.spec.search.search_space),
            "damage": damage_score(
                result,
                objective=self.spec.search.damage_function,
                weights=self.spec.search.damage_weights,
            ),
            "failure": result.failure_triggered,
            "cached": cached,
        }
        for dimension in self.spec.search.search_space:
            record[dimension.id] = vector.get(dimension.id, dimension.min)
        self.history.append(record)
        return result

    def _vector_key(self, vector: dict[str, float]) -> tuple[float, ...]:
        return tuple(
            round(vector.get(dimension.id, dimension.min), 8)
            for dimension in self.spec.search.search_space
        )

    def _candidate_vectors_for_budget(self, budget: float) -> list[dict[str, float]]:
        search_space = self.spec.search.search_space
        candidates = [{dimension.id: dimension.min for dimension in search_space}]
        for dimension in search_space:
            normalized = 0.0 if dimension.cost_weight <= 0 else min(1.0, budget / dimension.cost_weight)
            candidates.append(
                {
                    item.id: (
                        item.min + normalized * (item.max - item.min)
                        if item.id == dimension.id
                        else item.min
                    )
                    for item in search_space
                }
            )
        if len(search_space) > 1:
            equal_share = budget / len(search_space)
            candidates.append(
                {
                    dimension.id: dimension.min
                    + min(1.0, equal_share / max(dimension.cost_weight, 1e-9))
                    * (dimension.max - dimension.min)
                    for dimension in search_space
                }
            )
        for _ in range(self.spec.search.max_iterations):
            candidates.append(sample_under_budget(self.rng, search_space, budget))
        return candidates

    def _coordinate_refine(
        self,
        best_vector: dict[str, float],
        best_result,
        best_damage: float,
        budget: float,
        evaluations: int,
    ) -> tuple[dict[str, float], object, float, int]:
        search_space = self.spec.search.search_space
        step = 0.15
        refined_vector = dict(best_vector)
        refined_result = best_result
        refined_damage = best_damage
        for _ in range(3):
            improved = False
            for dimension in search_space:
                span = dimension.max - dimension.min
                for direction in (-1.0, 1.0):
                    candidate = dict(refined_vector)
                    candidate[dimension.id] = min(
                        dimension.max,
                        max(
                            dimension.min,
                            candidate[dimension.id] + direction * span * step,
                        ),
                    )
                    if budget_from_vector(candidate, search_space) > budget:
                        continue
                    candidate_result = self._evaluate_vector(candidate)
                    evaluations += 1
                    candidate_damage = damage_score(
                        candidate_result,
                        objective=self.spec.search.damage_function,
                        weights=self.spec.search.damage_weights,
                    )
                    if candidate_damage > refined_damage:
                        refined_vector = candidate
                        refined_result = candidate_result
                        refined_damage = candidate_damage
                        improved = True
            if not improved:
                step *= 0.5
        return refined_vector, refined_result, refined_damage, evaluations
