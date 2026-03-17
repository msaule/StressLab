"""Synthetic system generation for StressLab discovery campaigns."""

from stresslab.generator.synthetic import (
    SUPPORTED_TOPOLOGIES,
    SyntheticGenerationConfig,
    build_generation_artifacts,
    generate_spec_records,
    generate_system_spec,
)

__all__ = [
    "SUPPORTED_TOPOLOGIES",
    "SyntheticGenerationConfig",
    "build_generation_artifacts",
    "generate_spec_records",
    "generate_system_spec",
]
