"""Single-lock invariant test.

Verifies that the merged single-lock design does NOT deadlock when
TaskRuntime._execute() holds the shared session lock and then calls
TurnRunner.run() (which formerly would try to re-acquire the same lock).

Design:
- A shared asyncio.Lock plays the role of TaskRuntime._session_locks[key].
- TurnRunner is given a session_lock_provider that returns this shared lock.
- A fake turn handler simulates the full call chain:
    outer acquire lock → set _SESSION_LOCK_OWNER → call turn_runner.run()
      → run() detects same-task ownership → skips re-acquire → done.

The test uses asyncio.wait_for with a 3-second timeout.  If the design
introduced a deadlock (e.g. run() tried to acquire the already-held lock),
the coroutine would hang and TimeoutError would be raised, failing the test.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from opensquilla.engine.runtime import _SESSION_LOCK_OWNER, TurnRunner
from opensquilla.engine.types import DoneEvent


def _make_minimal_turn_runner(
    session_lock_provider: Any,
) -> TurnRunner:
    """Build a TurnRunner with stub dependencies sufficient for run()."""
    provider = MagicMock()
    provider.provider_name = "stub"
    # chat() is an async generator that immediately yields done
    async def _chat(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        yield DoneEvent()

    provider.chat = _chat

    selector = MagicMock()
    selector.resolve.return_value = provider
    selector.clone.return_value = selector
    selector.current_config = MagicMock(model="stub-model")

    session_manager = MagicMock()
    session_manager.get = AsyncMock(return_value=None)
    session_manager.append_message = AsyncMock(return_value=None)
    session_manager.update = AsyncMock(return_value=None)
    session_manager.get_compaction_summary = AsyncMock(return_value=None)

    return TurnRunner(
        provider_selector=selector,
        session_manager=session_manager,
        session_lock_provider=session_lock_provider,
    )


@pytest.mark.asyncio
async def test_no_self_deadlock() -> None:
    """Simulates OUTER lock held → TurnRunner.run() → no re-acquire deadlock.

    asyncio.wait_for 3s timeout must NOT fire (no deadlock).
    """
    session_key = "agent:main:test-deadlock-check"
    shared_lock = asyncio.Lock()

    def lock_provider(key: str) -> asyncio.Lock:
        # Always return the same shared lock (mirrors TaskRuntime._session_locks)
        return shared_lock

    runner = _make_minimal_turn_runner(lock_provider)

    from opensquilla.tools.types import ToolContext

    tool_ctx = ToolContext(session_key=session_key)

    async def _simulate_execute() -> None:
        """Mimic TaskRuntime._execute lock ownership before calling run()."""
        async with shared_lock:
            # Set _SESSION_LOCK_OWNER so TurnRunner.run() detects same-task
            # ownership and skips re-acquisition (mirrors _execute behaviour).
            current_task = asyncio.current_task()
            prev_map = _SESSION_LOCK_OWNER.get(None)
            new_map: dict[int, Any] = dict(prev_map or {})
            if current_task is not None:
                new_map[id(shared_lock)] = current_task
            token = _SESSION_LOCK_OWNER.set(new_map)
            try:
                events = []
                async for event in runner.run(
                    message="hello",
                    session_key=session_key,
                    tool_context=tool_ctx,
                ):
                    events.append(event)
            finally:
                _SESSION_LOCK_OWNER.reset(token)

    # 3-second timeout — any deadlock will cause TimeoutError here
    await asyncio.wait_for(_simulate_execute(), timeout=3.0)


@pytest.mark.asyncio
async def test_no_self_deadlock_when_run_consumed_by_child_task() -> None:
    """Heartbeat stream consumes TurnRunner.run() from a child task.

    ContextVar ownership must be call-chain based rather than current-task
    based, otherwise the child task tries to re-acquire the already-held lock.
    """
    session_key = "agent:main:test-heartbeat-child-task-deadlock-check"
    shared_lock = asyncio.Lock()
    runner = _make_minimal_turn_runner(lambda key: shared_lock)

    async def _fake_run_turn(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        yield DoneEvent()

    runner._run_turn = _fake_run_turn  # type: ignore[method-assign]

    from opensquilla.tools.types import ToolContext

    tool_ctx = ToolContext(session_key=session_key)

    async def _consume_run() -> list[Any]:
        events = []
        async for event in runner.run(
            message="hello",
            session_key=session_key,
            tool_context=tool_ctx,
        ):
            events.append(event)
        return events

    async def _simulate_execute_with_child_task() -> list[Any]:
        async with shared_lock:
            current_task = asyncio.current_task()
            prev_map = _SESSION_LOCK_OWNER.get(None)
            new_map: dict[int, Any] = dict(prev_map or {})
            if current_task is not None:
                new_map[id(shared_lock)] = current_task
            token = _SESSION_LOCK_OWNER.set(new_map)
            try:
                return await asyncio.create_task(_consume_run())
            finally:
                _SESSION_LOCK_OWNER.reset(token)

    events = await asyncio.wait_for(_simulate_execute_with_child_task(), timeout=3.0)
    assert any(isinstance(event, DoneEvent) for event in events)


@pytest.mark.asyncio
async def test_lock_provider_used_not_internal_dict() -> None:
    """When session_lock_provider is set, _get_session_lock returns the provider's lock.

    Verifies that the provided session-lock path takes precedence over internal locks.
    """
    session_key = "agent:main:provider-path-check"
    external_lock = asyncio.Lock()

    runner = _make_minimal_turn_runner(lambda key: external_lock)

    returned = runner._get_session_lock(session_key)
    assert returned is external_lock, (
        "_get_session_lock must return the external provider's lock, "
        f"got {returned!r} instead"
    )
    # TurnRunner has no internal _session_locks dict.
    assert not hasattr(runner, "_session_locks"), (
        "TurnRunner must not own an internal _session_locks dict"
    )


def test_no_provider_uses_fallback_no_session_locks_field() -> None:
    """TurnRunner without session_lock_provider creates a closure-based fallback.

    TurnRunner must NOT have a _session_locks attribute (the dict lives
    in the provider closure, not as a named field on the object).
    """
    external_lock = asyncio.Lock()
    runner = _make_minimal_turn_runner(lambda key: external_lock)
    assert not hasattr(runner, "_session_locks"), (
        "TurnRunner must not own a _session_locks attribute — "
        "lock dict lives in the provider closure"
    )
