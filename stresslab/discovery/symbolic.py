"""Deterministic symbolic-style law search for collapse datasets."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd


@dataclass(slots=True)
class ExpressionCandidate:
    """One symbolic expression candidate evaluated on a dataset."""

    name: str
    values: np.ndarray
    complexity: int
    feature_set: tuple[str, ...]


def symbolic_regression_search(
    frame: pd.DataFrame,
    *,
    target: str,
    feature_candidates: list[str] | None = None,
    beam_width: int = 18,
    max_depth: int = 3,
    max_terms: int = 3,
) -> pd.DataFrame:
    """Search a compact symbolic-expression space and return ranked candidate laws."""

    if frame.empty or target not in frame.columns:
        return _empty_symbolic_frame()
    numeric = frame.select_dtypes(include=["number"]).replace([np.inf, -np.inf], np.nan)
    if target not in numeric.columns:
        return _empty_symbolic_frame()
    candidate_features = feature_candidates or [
        column
        for column in numeric.columns
        if column != target and not column.endswith("_triggered")
    ]
    candidate_features = [column for column in candidate_features if column in numeric.columns]
    if not candidate_features:
        return _empty_symbolic_frame()
    aligned = numeric[candidate_features + [target]].dropna()
    if len(aligned) < 5:
        return _empty_symbolic_frame()

    target_values = aligned[target].to_numpy(dtype=float)
    base_candidates = _base_expressions(aligned, feature_columns=candidate_features)
    if not base_candidates:
        return _empty_symbolic_frame()
    beam = _score_expressions(base_candidates, target_values, target=target)
    all_rows = list(beam)
    lookup = {candidate.name: candidate for candidate in base_candidates}
    frontier = [lookup[str(row["expression"])] for row in beam[:beam_width] if str(row["expression"]) in lookup]

    for _depth in range(2, max_depth + 1):
        expanded = _expand_expressions(frontier, beam_width=beam_width)
        if not expanded:
            break
        scored = _score_expressions(expanded, target_values, target=target)
        all_rows.extend(scored)
        if not scored:
            break
        scored_names = {str(row["expression"]) for row in scored[:beam_width]}
        frontier = [candidate for candidate in expanded if candidate.name in scored_names][:beam_width]

    # Multiterm linear combinations over the strongest symbolic basis expressions.
    final_basis = frontier[: max(beam_width, max_terms * 3)]
    multiterm_rows = _score_multiterm_laws(final_basis, target_values, target=target, max_terms=max_terms)
    all_rows.extend(multiterm_rows)
    if not all_rows:
        return _empty_symbolic_frame()
    result = pd.DataFrame(all_rows).drop_duplicates(subset=["formula"], keep="first")
    result = result.sort_values(["r2", "observations", "complexity"], ascending=[False, False, True]).reset_index(drop=True)
    return result


def _base_expressions(frame: pd.DataFrame, *, feature_columns: list[str]) -> list[ExpressionCandidate]:
    candidates: list[ExpressionCandidate] = []
    for feature in feature_columns:
        values = frame[feature].to_numpy(dtype=float)
        if np.std(values) <= 1e-9:
            continue
        candidates.append(ExpressionCandidate(name=feature, values=values, complexity=1, feature_set=(feature,)))
        positive = np.clip(np.abs(values), 0.0, None)
        candidates.append(
            ExpressionCandidate(
                name=f"log1p(abs({feature}))",
                values=np.log1p(positive),
                complexity=2,
                feature_set=(feature,),
            )
        )
        candidates.append(
            ExpressionCandidate(
                name=f"sqrt(abs({feature}))",
                values=np.sqrt(positive),
                complexity=2,
                feature_set=(feature,),
            )
        )
        candidates.append(
            ExpressionCandidate(
                name=f"({feature}^2)",
                values=np.square(values),
                complexity=2,
                feature_set=(feature,),
            )
        )
        candidates.append(
            ExpressionCandidate(
                name=f"inv1p(abs({feature}))",
                values=1.0 / (1.0 + positive),
                complexity=2,
                feature_set=(feature,),
            )
        )
    return candidates


def _expand_expressions(candidates: list[ExpressionCandidate], *, beam_width: int) -> list[ExpressionCandidate]:
    expanded: list[ExpressionCandidate] = []
    limited = candidates[:beam_width]
    seen: set[str] = set()
    for left, right in combinations(limited, 2):
        for candidate in _combine_pair(left, right):
            if candidate.name in seen:
                continue
            seen.add(candidate.name)
            expanded.append(candidate)
    return expanded


def _combine_pair(left: ExpressionCandidate, right: ExpressionCandidate) -> list[ExpressionCandidate]:
    rows: list[ExpressionCandidate] = []
    union_features = tuple(sorted(set(left.feature_set).union(right.feature_set)))
    values_left = left.values
    values_right = right.values
    rows.append(
        ExpressionCandidate(
            name=f"({left.name} + {right.name})",
            values=values_left + values_right,
            complexity=left.complexity + right.complexity + 1,
            feature_set=union_features,
        )
    )
    rows.append(
        ExpressionCandidate(
            name=f"({left.name} - {right.name})",
            values=values_left - values_right,
            complexity=left.complexity + right.complexity + 1,
            feature_set=union_features,
        )
    )
    rows.append(
        ExpressionCandidate(
            name=f"({left.name} * {right.name})",
            values=values_left * values_right,
            complexity=left.complexity + right.complexity + 2,
            feature_set=union_features,
        )
    )
    rows.append(
        ExpressionCandidate(
            name=f"({left.name} / (1e-6 + abs({right.name})))",
            values=values_left / (1e-6 + np.abs(values_right)),
            complexity=left.complexity + right.complexity + 2,
            feature_set=union_features,
        )
    )
    return rows


def _score_expressions(
    expressions: list[ExpressionCandidate],
    target_values: np.ndarray,
    *,
    target: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for expression in expressions:
        values = expression.values
        if len(values) != len(target_values):
            continue
        if not np.all(np.isfinite(values)) or np.std(values) <= 1e-9:
            continue
        design = np.column_stack([np.ones(len(values)), values])
        intercept, coefficient = np.linalg.lstsq(design, target_values, rcond=None)[0]
        predicted = intercept + coefficient * values
        rows.append(
            {
                "target": target,
                "expression": expression.name,
                "formula": f"{target} = {intercept:.4f} + {coefficient:.4f} * {expression.name}",
                "model_type": "symbolic_linear",
                "feature_set": ", ".join(expression.feature_set),
                "r2": float(_r2_score(target_values, predicted)),
                "observations": int(len(values)),
                "complexity": int(expression.complexity),
                "term_count": 1,
            }
        )
    rows.sort(key=lambda row: (float(row["r2"]), -int(row["complexity"])), reverse=True)
    return rows


def _score_multiterm_laws(
    basis: list[ExpressionCandidate],
    target_values: np.ndarray,
    *,
    target: str,
    max_terms: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    limited = basis[: max(6, max_terms * 3)]
    for term_count in range(2, max_terms + 1):
        for combo in combinations(limited, term_count):
            matrix = np.column_stack([candidate.values for candidate in combo])
            if not np.all(np.isfinite(matrix)):
                continue
            if np.linalg.matrix_rank(matrix) < min(term_count, matrix.shape[1]):
                continue
            design = np.column_stack([np.ones(len(target_values)), matrix])
            coefficients = np.linalg.lstsq(design, target_values, rcond=None)[0]
            predicted = design @ coefficients
            terms = [
                f"{coefficients[index + 1]:.4f} * {candidate.name}"
                for index, candidate in enumerate(combo)
            ]
            rows.append(
                {
                    "target": target,
                    "expression": " + ".join(candidate.name for candidate in combo),
                    "formula": f"{target} = {coefficients[0]:.4f} + " + " + ".join(terms),
                    "model_type": "symbolic_multiterm",
                    "feature_set": ", ".join(sorted({feature for candidate in combo for feature in candidate.feature_set})),
                    "r2": float(_r2_score(target_values, predicted)),
                    "observations": int(len(target_values)),
                    "complexity": int(sum(candidate.complexity for candidate in combo) + term_count),
                    "term_count": int(term_count),
                }
            )
    rows.sort(key=lambda row: (float(row["r2"]), -int(row["complexity"])), reverse=True)
    return rows[:40]


def _r2_score(actual: np.ndarray, predicted: np.ndarray) -> float:
    total = float(np.sum((actual - actual.mean()) ** 2))
    if total <= 1e-12:
        return 1.0
    residual = float(np.sum((actual - predicted) ** 2))
    return 1.0 - residual / total


def _empty_symbolic_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "target",
            "expression",
            "formula",
            "model_type",
            "feature_set",
            "r2",
            "observations",
            "complexity",
            "term_count",
        ]
    )
