"""Theory-layer analysis for systemic fragility discovery."""

from stresslab.theory.early_warning import (
    compute_early_warning_signals,
    summarize_early_warning_dataset,
    summarize_early_warning_trends,
)
from stresslab.theory.features import extract_system_features
from stresslab.theory.fragility import fit_fragility_models
from stresslab.theory.metrics import (
    build_collapse_distribution,
    collapse_metrics_from_results,
)
from stresslab.theory.phase_transition import bootstrap_phase_transition, detect_phase_transition
from stresslab.theory.powerlaws import compare_tail_models, fit_power_law

__all__ = [
    "build_collapse_distribution",
    "bootstrap_phase_transition",
    "compare_tail_models",
    "collapse_metrics_from_results",
    "compute_early_warning_signals",
    "detect_phase_transition",
    "extract_system_features",
    "fit_fragility_models",
    "fit_power_law",
    "summarize_early_warning_dataset",
    "summarize_early_warning_trends",
]
