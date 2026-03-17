"""Queue helpers."""

from __future__ import annotations

from stresslab.des.node import Job, NodeState


def enqueue_job(node_state: NodeState, job: Job) -> bool:
    """Insert a job into the waiting queue if capacity allows."""

    if node_state.effective_buffer_capacity is not None and len(node_state.queue) >= node_state.effective_buffer_capacity:
        node_state.dropped_count += 1
        node_state.overflow_count += 1
        return False
    node_state.queue.append(job)
    node_state.max_queue_length = max(node_state.max_queue_length, len(node_state.queue))
    return True
