"""StressLab exceptions."""

from __future__ import annotations


class StressLabError(Exception):
    """Base exception for the project."""


class SpecValidationError(StressLabError):
    """Raised when a SystemSpec is invalid."""


class SimulationError(StressLabError):
    """Raised when a simulation cannot continue safely."""


class SearchError(StressLabError):
    """Raised when a search request is malformed or unsupported."""


class ReportError(StressLabError):
    """Raised when report generation fails."""
