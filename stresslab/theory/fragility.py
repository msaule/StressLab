"""Regression-style fitting for collapse-feature relationships."""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from stresslab.models import FragilityModelResult

DEFAULT_FEATURES = [
    "utilization",
    "capacity_slack",
    "redundancy_index",
    "coupling_strength",
    "centralization_index",
    "routing_entropy",
    "average_degree",
    "buffer_ratio",
    "mean_betweenness",
    "max_betweenness",
]
DEFAULT_TARGETS = [
    "collapse_probability",
    "fragility_index",
    "throughput_loss",
    "max_cascade_size",
    "failure_shock_budget",
]


def fit_fragility_models(
    frame: pd.DataFrame,
    *,
    features: list[str] | None = None,
    targets: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit simple linear/log/power models and return all fits plus top laws."""

    feature_columns = [column for column in (features or DEFAULT_FEATURES) if column in frame.columns]
    target_columns = [column for column in (targets or DEFAULT_TARGETS) if column in frame.columns]
    results: list[FragilityModelResult] = []
    for target in target_columns:
        y = _clean_series(frame[target])
        for feature in feature_columns:
            x = _clean_series(frame[feature])
            aligned = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
            if len(aligned) < 4:
                continue
            results.extend(_fit_univariate_models(feature=feature, target=target, aligned=aligned))
        for left, right in combinations(feature_columns[: min(6, len(feature_columns))], 2):
            aligned = frame[[left, right, target]].replace([np.inf, -np.inf], np.nan).dropna()
            if len(aligned) < 5:
                continue
            results.append(_fit_bivariate_linear(target=target, left=left, right=right, aligned=aligned))
    results_frame = pd.DataFrame([result.model_dump(mode="json") for result in results])
    if results_frame.empty:
        results_frame = pd.DataFrame(
            columns=[
                "target",
                "feature",
                "model_type",
                "coefficient",
                "intercept",
                "exponent",
                "r2",
                "observations",
                "formula",
            ]
        )
    else:
        results_frame = results_frame.sort_values(["r2", "observations"], ascending=[False, False])
    law_candidates = results_frame.dropna(subset=["r2"]).query("r2 >= 0.05").head(20).reset_index(drop=True)
    return results_frame, law_candidates


def _fit_univariate_models(*, feature: str, target: str, aligned: pd.DataFrame) -> list[FragilityModelResult]:
    x = aligned["x"].to_numpy(dtype=float)
    y = aligned["y"].to_numpy(dtype=float)
    return [
        _fit_linear_model(x=x, y=y, feature=feature, target=target, model_type="linear"),
        _fit_log_feature_model(x=x, y=y, feature=feature, target=target),
        _fit_power_law_relation(x=x, y=y, feature=feature, target=target),
    ]


def _fit_linear_model(
    *,
    x: np.ndarray,
    y: np.ndarray,
    feature: str,
    target: str,
    model_type: str,
) -> FragilityModelResult:
    design = np.column_stack([np.ones(len(x)), x])
    intercept, coefficient = np.linalg.lstsq(design, y, rcond=None)[0]
    predicted = intercept + coefficient * x
    r2 = _r2_score(y, predicted)
    return FragilityModelResult(
        target=target,
        feature=feature,
        model_type=model_type,
        coefficient=float(coefficient),
        intercept=float(intercept),
        r2=float(r2),
        observations=int(len(x)),
        formula=f"{target} = {intercept:.4f} + {coefficient:.4f} * {feature}",
    )


def _fit_log_feature_model(*, x: np.ndarray, y: np.ndarray, feature: str, target: str) -> FragilityModelResult:
    transformed = np.log1p(np.clip(x, 0.0, None))
    design = np.column_stack([np.ones(len(transformed)), transformed])
    intercept, coefficient = np.linalg.lstsq(design, y, rcond=None)[0]
    predicted = intercept + coefficient * transformed
    r2 = _r2_score(y, predicted)
    return FragilityModelResult(
        target=target,
        feature=feature,
        model_type="log",
        coefficient=float(coefficient),
        intercept=float(intercept),
        r2=float(r2),
        observations=int(len(x)),
        formula=f"{target} = {intercept:.4f} + {coefficient:.4f} * log1p({feature})",
    )


def _fit_power_law_relation(*, x: np.ndarray, y: np.ndarray, feature: str, target: str) -> FragilityModelResult:
    positive = (x > 0) & (y > 0)
    if int(positive.sum()) < 4:
        return FragilityModelResult(
            target=target,
            feature=feature,
            model_type="power_law",
            observations=int(positive.sum()),
        )
    log_x = np.log(x[positive])
    log_y = np.log(y[positive])
    design = np.column_stack([np.ones(len(log_x)), log_x])
    intercept_log, exponent = np.linalg.lstsq(design, log_y, rcond=None)[0]
    predicted_log = intercept_log + exponent * log_x
    r2 = _r2_score(log_y, predicted_log)
    coefficient = float(np.exp(intercept_log))
    return FragilityModelResult(
        target=target,
        feature=feature,
        model_type="power_law",
        coefficient=coefficient,
        exponent=float(exponent),
        intercept=float(intercept_log),
        r2=float(r2),
        observations=int(positive.sum()),
        formula=f"{target} = {coefficient:.4f} * {feature}^{float(exponent):.4f}",
    )


def _fit_bivariate_linear(
    *,
    target: str,
    left: str,
    right: str,
    aligned: pd.DataFrame,
) -> FragilityModelResult:
    design = np.column_stack(
        [
            np.ones(len(aligned)),
            aligned[left].to_numpy(dtype=float),
            aligned[right].to_numpy(dtype=float),
        ]
    )
    intercept, left_coef, right_coef = np.linalg.lstsq(
        design,
        aligned[target].to_numpy(dtype=float),
        rcond=None,
    )[0]
    predicted = intercept + left_coef * aligned[left].to_numpy(dtype=float) + right_coef * aligned[right].to_numpy(dtype=float)
    r2 = _r2_score(aligned[target].to_numpy(dtype=float), predicted)
    return FragilityModelResult(
        target=target,
        feature=f"{left}+{right}",
        model_type="multivariate_linear",
        coefficient=float(left_coef),
        intercept=float(intercept),
        exponent=float(right_coef),
        r2=float(r2),
        observations=int(len(aligned)),
        formula=f"{target} = {intercept:.4f} + {left_coef:.4f} * {left} + {right_coef:.4f} * {right}",
    )


def _clean_series(series: pd.Series) -> pd.Series:
    return series.astype(float).replace([np.inf, -np.inf], np.nan)


def _r2_score(actual: np.ndarray, predicted: np.ndarray) -> float:
    if len(actual) == 0:
        return 0.0
    total = float(np.sum((actual - actual.mean()) ** 2))
    if total <= 1e-12:
        return 1.0
    residual = float(np.sum((actual - predicted) ** 2))
    return 1.0 - residual / total
