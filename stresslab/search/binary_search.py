"""Binary search helpers for minimum-failure discovery."""

from __future__ import annotations


def binary_threshold_search(
    evaluate,
    *,
    low: float = 0.0,
    high: float = 1.0,
    iterations: int = 20,
) -> tuple[float, object | None]:
    """Binary search for the smallest scale that triggers failure."""

    best_scale = None
    best_result = None
    left = low
    right = high
    for _ in range(iterations):
        mid = 0.5 * (left + right)
        result = evaluate(mid)
        if result.failure_triggered:
            best_scale = mid
            best_result = result
            right = mid
        else:
            left = mid
    if best_scale is None:
        return high, None
    return best_scale, best_result
