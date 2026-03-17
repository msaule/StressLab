"""Early-warning indicators for systemic collapse."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stresslab.models import EarlyWarningSummary


def compute_early_warning_signals(
    queue_frame: pd.DataFrame,
    *,
    failure_triggered: bool,
) -> dict[str, float]:
    """Extract variance/autocorrelation style indicators from queue traces."""

    if queue_frame.empty or "time" not in queue_frame.columns or "queue_length" not in queue_frame.columns:
        return {
            "variance_increase": 0.0,
            "autocorrelation_increase": 0.0,
            "recovery_lag": 0.0,
            "failure_triggered": float(failure_triggered),
        }
    aggregated = (
        queue_frame.groupby("time", as_index=False)["queue_length"].sum().sort_values("time").reset_index(drop=True)
    )
    if len(aggregated) < 6:
        return {
            "variance_increase": 0.0,
            "autocorrelation_increase": 0.0,
            "recovery_lag": 0.0,
            "failure_triggered": float(failure_triggered),
        }
    split_index = max(2, len(aggregated) // 2)
    early = aggregated.iloc[:split_index]["queue_length"].astype(float).to_numpy()
    late = aggregated.iloc[split_index:]["queue_length"].astype(float).to_numpy()
    early_variance = float(np.var(early))
    late_variance = float(np.var(late))
    variance_increase = (late_variance + 1e-9) / (early_variance + 1e-9) - 1.0
    early_autocorr = _lag_one_autocorrelation(early)
    late_autocorr = _lag_one_autocorrelation(late)
    recovery_lag = _recovery_lag(aggregated["queue_length"].astype(float).to_numpy())
    return {
        "variance_increase": float(variance_increase),
        "autocorrelation_increase": float(late_autocorr - early_autocorr),
        "recovery_lag": float(recovery_lag),
        "failure_triggered": float(failure_triggered),
    }


def summarize_early_warning_dataset(frame: pd.DataFrame) -> EarlyWarningSummary:
    """Aggregate early-warning indicators across a campaign dataset."""

    if frame.empty:
        return EarlyWarningSummary(total_case_count=0, collapse_case_count=0)
    subset = frame.copy()
    if "failure_triggered" in subset.columns:
        collapse_cases = subset[subset["failure_triggered"].astype(float) > 0.0]
    else:
        collapse_cases = subset
    return EarlyWarningSummary(
        mean_variance_increase=float(subset.get("variance_increase", pd.Series([0.0])).mean()),
        mean_autocorrelation_increase=float(subset.get("autocorrelation_increase", pd.Series([0.0])).mean()),
        mean_recovery_lag=float(subset.get("recovery_lag", pd.Series([0.0])).mean()),
        collapse_case_count=int(len(collapse_cases)),
        total_case_count=int(len(subset)),
    )


def summarize_early_warning_trends(frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize early-warning separation between collapse and non-collapse cases."""

    if frame.empty:
        return pd.DataFrame(columns=["metric", "collapse_mean", "stable_mean", "separation"])
    subset = frame.copy()
    subset["failure_triggered"] = subset.get("failure_triggered", pd.Series([0.0] * len(subset))).astype(float)
    collapse = subset[subset["failure_triggered"] > 0.0]
    stable = subset[subset["failure_triggered"] <= 0.0]
    rows = []
    for metric in ["variance_increase", "autocorrelation_increase", "recovery_lag"]:
        collapse_mean = float(collapse.get(metric, pd.Series([0.0])).mean()) if not collapse.empty else 0.0
        stable_mean = float(stable.get(metric, pd.Series([0.0])).mean()) if not stable.empty else 0.0
        rows.append(
            {
                "metric": metric,
                "collapse_mean": collapse_mean,
                "stable_mean": stable_mean,
                "separation": collapse_mean - stable_mean,
            }
        )
    return pd.DataFrame(rows).sort_values("separation", ascending=False).reset_index(drop=True)


def _lag_one_autocorrelation(values: np.ndarray) -> float:
    if len(values) < 3:
        return 0.0
    left = values[:-1]
    right = values[1:]
    if np.std(left) <= 1e-9 or np.std(right) <= 1e-9:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def _recovery_lag(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    median = float(np.median(values))
    longest_run = 0
    current_run = 0
    for value in values:
        if value > median:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    return float(longest_run)
