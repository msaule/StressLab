"""Heavy-tail fitting helpers for cascade distributions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stresslab.models import PowerLawFitResult


def fit_power_law(values: pd.Series | list[float] | np.ndarray, *, metric: str = "cascade_size") -> PowerLawFitResult:
    """Fit a coarse power law to strictly positive observations."""

    series = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    series = series[series > 0]
    if series.empty:
        return PowerLawFitResult(metric=metric, sample_size=0)
    xmin = float(max(1.0, series.min()))
    clipped = series[series >= xmin]
    if clipped.empty:
        return PowerLawFitResult(metric=metric, sample_size=0)
    alpha = 1.0 + len(clipped) / max(float(np.log(clipped / xmin).sum()), 1e-9)
    empirical = clipped.sort_values().reset_index(drop=True)
    empirical_ccdf = 1.0 - (np.arange(len(empirical), dtype=float) + 1.0) / len(empirical)
    theoretical_ccdf = (empirical / xmin) ** (1.0 - alpha)
    ks_distance = float(np.max(np.abs(empirical_ccdf - theoretical_ccdf)))
    log_x = np.log(empirical.to_numpy(dtype=float))
    log_y = np.log(np.clip(empirical_ccdf.astype(float), 1e-9, None))
    if len(log_x) >= 2:
        design = np.column_stack([np.ones(len(log_x)), log_x])
        intercept, slope = np.linalg.lstsq(design, log_y, rcond=None)[0]
        predicted = intercept + slope * log_x
        total = float(np.sum((log_y - log_y.mean()) ** 2))
        residual = float(np.sum((log_y - predicted) ** 2))
        r2 = 1.0 - residual / max(total, 1e-9)
    else:
        r2 = 0.0
    return PowerLawFitResult(
        metric=metric,
        alpha=float(alpha),
        xmin=xmin,
        sample_size=int(len(clipped)),
        ks_distance=ks_distance,
        loglog_r2=float(r2),
    )


def compare_tail_models(
    values: pd.Series | list[float] | np.ndarray,
    *,
    metric: str = "cascade_size",
) -> pd.DataFrame:
    """Compare coarse power-law, exponential, and lognormal tail fits."""

    series = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    series = series[series > 0]
    if series.empty:
        return pd.DataFrame(columns=["metric", "model", "log_likelihood", "parameter_a", "parameter_b"])
    values_array = series.to_numpy(dtype=float)
    power_fit = fit_power_law(values_array, metric=metric)
    xmin = float(power_fit.xmin or max(values_array.min(), 1.0))
    clipped = values_array[values_array >= xmin]
    if clipped.size == 0:
        clipped = values_array
    scale = max(float(np.mean(clipped)), 1e-9)
    lambda_exp = 1.0 / scale
    log_likelihood_exp = float(np.sum(np.log(lambda_exp) - lambda_exp * clipped))
    log_values = np.log(clipped)
    mu = float(np.mean(log_values))
    sigma = max(float(np.std(log_values)), 1e-9)
    log_likelihood_lognormal = float(
        np.sum(
            -np.log(clipped * sigma * np.sqrt(2.0 * np.pi))
            - ((log_values - mu) ** 2) / (2.0 * sigma**2)
        )
    )
    alpha = float(power_fit.alpha or 0.0)
    if alpha > 1.0:
        log_likelihood_power = float(
            len(clipped) * np.log((alpha - 1.0) / xmin) - alpha * np.sum(np.log(clipped / xmin))
        )
    else:
        log_likelihood_power = float("-inf")
    rows = [
        {
            "metric": metric,
            "model": "power_law",
            "log_likelihood": log_likelihood_power,
            "parameter_a": alpha,
            "parameter_b": xmin,
        },
        {
            "metric": metric,
            "model": "exponential",
            "log_likelihood": log_likelihood_exp,
            "parameter_a": lambda_exp,
            "parameter_b": scale,
        },
        {
            "metric": metric,
            "model": "lognormal",
            "log_likelihood": log_likelihood_lognormal,
            "parameter_a": mu,
            "parameter_b": sigma,
        },
    ]
    return pd.DataFrame(rows).sort_values("log_likelihood", ascending=False).reset_index(drop=True)
