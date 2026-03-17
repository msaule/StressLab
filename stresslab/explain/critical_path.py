"""Critical path summaries."""

from __future__ import annotations


def critical_path(result) -> list[str]:
    """Return a best-effort ordered list of degraded nodes."""

    ranked = sorted(
        result.node_metrics.items(),
        key=lambda item: item[1].get("queue_integral", 0.0),
        reverse=True,
    )
    return [node_id for node_id, _ in ranked[:5]]
