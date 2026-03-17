"""Phase-transition style detection from discovery datasets."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stresslab.models import PhaseTransitionResult


def detect_phase_transition(
    frame: pd.DataFrame,
    *,
    feature: str = "utilization",
    outcome: str = "collapse_probability",
    bins: int = 12,
) -> tuple[PhaseTransitionResult, pd.DataFrame]:
    """Detect a coarse critical threshold from aggregate system behavior."""

    if frame.empty or feature not in frame.columns or outcome not in frame.columns:
        return PhaseTransitionResult(feature=feature, outcome=outcome), pd.DataFrame(
            columns=[feature, outcome, "system_count"]
        )
    subset = frame[[feature, outcome]].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if len(subset) < 4:
        return PhaseTransitionResult(feature=feature, outcome=outcome), subset
    quantiles = np.linspace(0.0, 1.0, min(bins, len(subset)) + 1)
    edges = sorted(set(float(subset[feature].quantile(q)) for q in quantiles))
    if len(edges) < 3:
        grouped = subset.assign(system_count=1.0)
        grouped = grouped.groupby(feature, as_index=False).agg({outcome: "mean", "system_count": "sum"})
        return PhaseTransitionResult(feature=feature, outcome=outcome), grouped
    subset = subset.assign(
        bin=pd.cut(
            subset[feature],
            bins=edges,
            include_lowest=True,
            duplicates="drop",
        )
    )
    grouped = subset.groupby("bin", observed=False).agg(
        feature_mean=(feature, "mean"),
        outcome_mean=(outcome, "mean"),
        system_count=(outcome, "size"),
    ).reset_index(drop=True)
    grouped = grouped.rename(columns={"feature_mean": feature, "outcome_mean": outcome})
    if len(grouped) < 2:
        return PhaseTransitionResult(feature=feature, outcome=outcome), grouped
    deltas = np.abs(np.diff(grouped[outcome].to_numpy(dtype=float)))
    best_index = int(np.argmax(deltas))
    threshold = float(np.mean(grouped[feature].iloc[best_index : best_index + 2]))
    pre_mean = float(grouped[outcome].iloc[: best_index + 1].mean())
    post_mean = float(grouped[outcome].iloc[best_index + 1 :].mean())
    result = PhaseTransitionResult(
        feature=feature,
        outcome=outcome,
        critical_threshold=threshold,
        discontinuity_score=float(deltas[best_index]),
        pre_transition_mean=pre_mean,
        post_transition_mean=post_mean,
    )
    return result, grouped


def bootstrap_phase_transition(
    frame: pd.DataFrame,
    *,
    feature: str = "utilization",
    outcome: str = "collapse_probability",
    bins: int = 12,
    bootstrap_samples: int = 64,
    seed: int = 17,
) -> pd.DataFrame:
    """Estimate threshold stability by bootstrapping the detected critical point."""

    if frame.empty or feature not in frame.columns or outcome not in frame.columns:
        return pd.DataFrame(columns=["sample_id", "critical_threshold", "discontinuity_score"])
    subset = frame[[feature, outcome]].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if len(subset) < 5:
        return pd.DataFrame(columns=["sample_id", "critical_threshold", "discontinuity_score"])
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float]] = []
    for sample_id in range(bootstrap_samples):
        sampled = subset.sample(n=len(subset), replace=True, random_state=int(rng.integers(0, 10_000_000)))
        result, _ = detect_phase_transition(sampled, feature=feature, outcome=outcome, bins=bins)
        rows.append(
            {
                "sample_id": float(sample_id),
                "critical_threshold": float(result.critical_threshold or 0.0),
                "discontinuity_score": float(result.discontinuity_score or 0.0),
            }
        )
    return pd.DataFrame(rows)
