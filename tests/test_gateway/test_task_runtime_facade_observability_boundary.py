"""Boundary tests for TaskRuntime test-observability facade access."""

from __future__ import annotations

import ast
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from opensquilla.gateway.routing import RouteEnvelope, SourceKind
from opensquilla.gateway.task_runtime import TaskRuntime
from opensquilla.session.models import AgentTaskRecord

PRIVATE_RUNTIME_ATTRS = {
    "_tasks",
    "_pending_by_session",
    "_running_by_session",
    "_last_envelope_by_session",
    "_runtime_state",
    "_session_locks",
}

REPO_ROOT = Path(__file__).resolve().parents[2]
BEHAVIOR_TESTS = (
    "tests/test_gateway/test_task_runtime_terminal_cleanup.py",
    "tests/test_gateway/test_task_runtime_execution_boundary.py",
    "tests/test_gateway/test_no_split_brain_lock.py",
)


def _make_envelope(session_key: str = "agent-1::facade-boundary") -> RouteEnvelope:
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
        for key, value in kwargs.items():
            if hasattr(rec, key):
                object.__setattr__(rec, key, value)

    async def get(task_id: str) -> AgentTaskRecord | None:
        return task_db.get(task_id)

    async def list_tasks(**_: Any) -> list[AgentTaskRecord]:
        return list(task_db.values())

    storage.create_agent_task = create
    storage.update_agent_task = update
    storage.get_agent_task = get
    storage.list_agent_tasks = list_tasks
    return storage


def _make_runtime(
    turn_handler: Callable[..., Awaitable[Any]] | None = None,
) -> TaskRuntime:
    async def _default_handler(_run: Any) -> None:
        pass

    return TaskRuntime(
        storage=_make_storage(),
        turn_handler=turn_handler or _default_handler,
    )


def _private_runtime_attr_reads(path: str) -> list[tuple[int, str]]:
    tree = ast.parse((REPO_ROOT / path).read_text())
    return [
        (node.lineno, node.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in PRIVATE_RUNTIME_ATTRS
    ]


@pytest.mark.asyncio
async def test_snapshot_runtime_state_exposes_read_only_observability_facade() -> None:
    runtime = _make_runtime()
    envelope = _make_envelope()
    lock = runtime._get_session_lock_for_turn(envelope.session_key)
    await lock.acquire()

    try:
        handle = await runtime.enqueue(envelope, "hello")
        snapshot = runtime.snapshot_runtime_state()

        assert handle.task_id in snapshot.task_ids
        assert envelope.session_key in snapshot.pending_session_keys
        assert envelope.session_key in snapshot.session_lock_keys
        assert snapshot.tasks_count == 1
        with pytest.raises(AttributeError):
            snapshot.task_ids.add(handle.task_id)  # type: ignore[attr-defined]
    finally:
        lock.release()
        await runtime.wait(handle.task_id, timeout=2.0)

    terminal_snapshot = runtime.snapshot_runtime_state()
    assert handle.task_id not in terminal_snapshot.task_ids
    assert envelope.session_key not in terminal_snapshot.pending_session_keys
    assert envelope.session_key not in terminal_snapshot.running_session_keys
    assert envelope.session_key not in terminal_snapshot.last_envelope_session_keys
    assert envelope.session_key in terminal_snapshot.session_lock_keys


def test_real_task_runtime_behavior_tests_use_snapshot_facade_for_private_state() -> None:
    violations = {
        path: _private_runtime_attr_reads(path)
        for path in BEHAVIOR_TESTS
        if _private_runtime_attr_reads(path)
    }

    assert violations == {}
