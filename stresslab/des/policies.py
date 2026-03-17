"""Queue policies."""

from __future__ import annotations

from stresslab.des.node import Job, NodeState


def select_next_job(node_state: NodeState, class_priorities: dict[str, int]) -> Job | None:
    """Select the next job to start service."""

    if not node_state.queue:
        return None
    if node_state.spec.queue_policy == "fifo":
        return node_state.queue.pop(0)
    best_index = min(
        range(len(node_state.queue)),
        key=lambda idx: (class_priorities.get(node_state.queue[idx].class_id, 999), node_state.queue[idx].queue_sequence),
    )
    return node_state.queue.pop(best_index)
