"""Tests for C3 fix: no split-brain lock on rapid re-enqueue after terminal.

AC-C3-1: session locks are retained at terminal.
AC-C3-2: rapid enqueue -> terminal -> re-enqueue for same session_key never
          allows two tasks to run concurrently (max_concurrent_per_session == 1).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from opensquilla.gateway.routing import RouteEnvelope, SourceKind
from opensquilla.gateway.task_runtime import TaskRuntime
from opensquilla.session.models import AgentTaskRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_envelope(session_key: str = "agent-1::sess-1") -> RouteEnvelope:
    return RouteEnvelope(
        source_kind=SourceKind.WEB,
        source_name="test",
        agent_id="agent-1",
        session_key=session_key,
        input_provenance={"kind": "test"},
    )


def _make_storage() -> Any:
    storage = MagicMock()
    task_db: dict[str, AgentTaskRecord] = {}

    async def create(record: AgentTaskRecord) -> None:
        task_db[record.task_id] = record

    async def update(task_id: str, **kwargs: Any) -> None:
        rec = task_db.get(task_id)
        if rec is None:
            return
        for k, v in kwargs.items():
            if hasattr(rec, k):
                object.__setattr__(rec, k, v)

    async def get(task_id: str) -> AgentTaskRecord | None:
        return task_db.get(task_id)

    async def list_tasks(**_: Any) -> list[AgentTaskRecord]:
        return list(task_db.values())

    storage.create_agent_task = create
    storage.update_agent_task = update
    storage.get_agent_task = get
    storage.list_agent_tasks = list_tasks
    return storage


# ---------------------------------------------------------------------------
# AC-C3-1: session locks are retained at terminal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_locks_never_popped_at_terminal() -> None:
    """After a task reaches terminal state, the session lock key remains observable."""
    async def _instant(_run: Any) -> None:
        pass

    rt = TaskRuntime(
        storage=_make_storage(),
        turn_handler=_instant,
        max_concurrency=4,
    )
    env = _make_envelope("agent-1::sess-c3")
    handle = await rt.enqueue(env, "msg")
    await rt.wait(handle.task_id, timeout=5.0)

    snapshot = rt.snapshot_runtime_state()
    assert env.session_key in snapshot.session_lock_keys, (
        "session locks should retain the entry after terminal (C3 fix)"
    )


# ---------------------------------------------------------------------------
# AC-C3-2: no split-brain under rapid enqueue -> terminal -> re-enqueue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rapid_enqueue_after_terminal_no_split_brain() -> None:
    """Loop 100 times: enqueue -> wait for terminal -> immediately re-enqueue.

    At no point should two tasks for the same session run concurrently.
    max_concurrent_per_session must always be 1.
    """
    iterations = 100
    session_key = "agent-1::sess-rapid"
    env = _make_envelope(session_key)

    concurrent_count = 0
    max_concurrent = 0
    count_lock = asyncio.Lock()

    async def _handler(_run: Any) -> None:
        nonlocal concurrent_count, max_concurrent
        async with count_lock:
            concurrent_count += 1
            if concurrent_count > max_concurrent:
                max_concurrent = concurrent_count
        # Small yield to allow other tasks to slip in if the lock is broken.
        await asyncio.sleep(0)
        async with count_lock:
            concurrent_count -= 1

    rt = TaskRuntime(
        storage=_make_storage(),
        turn_handler=_handler,
        max_concurrency=4,
        max_pending_per_session=None,
    )

    for _ in range(iterations):
        handle = await rt.enqueue(env, "msg")
        await rt.wait(handle.task_id, timeout=5.0)
        # Yield to event loop so any in-flight concurrent task could manifest.
        await asyncio.sleep(0)

    assert max_concurrent == 1, (
        f"Split-brain detected: max concurrent tasks for same session = {max_concurrent} "
        f"(expected 1)"
    )
