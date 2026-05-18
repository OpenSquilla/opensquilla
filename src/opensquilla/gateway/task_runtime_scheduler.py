"""Fair slot accounting for the in-process task runtime."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any


class TaskRuntimeScheduler:
    """Own global/subagent concurrency and per-agent round-robin state."""

    def __init__(self, *, max_concurrency: int, subagent_reserved_slots: int) -> None:
        self.max_concurrency = max_concurrency
        self.subagent_reserved_slots = subagent_reserved_slots
        # In-flight counters track tasks that have actually acquired a slot.
        # They drive the reserved-slot fairness gate for subagent runs.
        self.global_in_flight = 0
        self.subagent_in_flight = 0
        # Lazily constructed so the runtime can be instantiated outside an
        # event loop (some tests do this); the Condition is bound to the
        # running loop the first time a subagent waits on a slot.
        self.slot_cond: asyncio.Condition | None = None
        # Per-agent-id fair-queuing state (true round-robin).
        #
        # ``agent_session_rr[agent_id]`` is a deque of session_keys that have
        # active (pending or running) tasks for that agent.  When a task needs a
        # slot it must be at the front of its agent's deque; after acquiring the
        # slot the deque entry rotates to the tail so the next session goes next.
        # When a session has no more pending/running tasks it is removed by
        # ``remove_inactive_session``.
        self.agent_session_rr: dict[str, deque[str]] = {}
        self.agent_active_sessions: dict[str, set[str]] = {}
        self.agent_in_flight: dict[str, int] = {}
        self.fair_cond: asyncio.Condition | None = None

    def enroll(self, task: Any) -> None:
        """Register a task's session in the per-agent round-robin queue."""
        agent_id = task.envelope.agent_id
        session_key = task.envelope.session_key
        if agent_id not in self.agent_session_rr:
            self.agent_session_rr[agent_id] = deque()
            self.agent_active_sessions[agent_id] = set()
        active = self.agent_active_sessions[agent_id]
        rr = self.agent_session_rr[agent_id]
        if session_key not in active:
            active.add(session_key)
            rr.append(session_key)

    def remove_inactive_session(self, task: Any, *, has_session_work: bool) -> None:
        """Drop a session from RR state after its last pending/running task."""
        if has_session_work:
            return
        session_key = task.envelope.session_key
        agent_id = task.envelope.agent_id
        active = self.agent_active_sessions.get(agent_id)
        if active is None:
            return
        active.discard(session_key)
        rr = self.agent_session_rr.get(agent_id)
        if rr is not None:
            try:
                rr.remove(session_key)
            except ValueError:
                pass
        if not active:
            self.agent_active_sessions.pop(agent_id, None)
            self.agent_session_rr.pop(agent_id, None)

    def _ensure_slot_cond(self) -> asyncio.Condition:
        if self.slot_cond is None:
            self.slot_cond = asyncio.Condition()
        return self.slot_cond

    def _ensure_fair_cond(self) -> asyncio.Condition:
        if self.fair_cond is None:
            self.fair_cond = asyncio.Condition()
        return self.fair_cond

    async def wait_for_subagent_slot(self, task: Any) -> None:
        """Wait until a subagent can run without consuming reserved capacity."""
        if task.run_kind != "subagent" or self.subagent_reserved_slots <= 0:
            return
        cond = self._ensure_slot_cond()
        async with cond:
            while self.max_concurrency - self.global_in_flight <= self.subagent_reserved_slots:
                await cond.wait()

    async def acquire_fair_slot(
        self,
        task: Any,
        *,
        mark_running: Callable[[Any], Awaitable[None]],
        emit_metric: Callable[..., None],
    ) -> None:
        """Acquire one global slot with per-agent_id round-robin enrollment."""
        cond = self._ensure_fair_cond()
        agent_id = task.envelope.agent_id
        session_key = task.envelope.session_key

        async with cond:
            while True:
                if self.global_in_flight >= self.max_concurrency:
                    await cond.wait()
                    continue
                idle_slots = self.max_concurrency - self.global_in_flight
                rr = self.agent_session_rr.get(agent_id)
                if idle_slots == 1 and rr and len(rr) > 1 and rr[0] != session_key:
                    await cond.wait()
                    continue
                if rr and rr[0] == session_key:
                    rr.rotate(-1)
                self.global_in_flight += 1
                if task.run_kind == "subagent":
                    self.subagent_in_flight += 1
                self.agent_in_flight[agent_id] = self.agent_in_flight.get(agent_id, 0) + 1
                task.acquired_slot = True
                break

        await mark_running(task)
        emit_metric(
            "in_flight_turns_total",
            value=1,
            session_key=task.envelope.session_key,
        )

    async def release_slot(self, task: Any) -> None:
        if task.acquired_slot:
            self.global_in_flight = max(0, self.global_in_flight - 1)
            if task.run_kind == "subagent":
                self.subagent_in_flight = max(0, self.subagent_in_flight - 1)
            agent_id = task.envelope.agent_id
            new_count = max(0, self.agent_in_flight.get(agent_id, 0) - 1)
            if new_count == 0:
                self.agent_in_flight.pop(agent_id, None)
            else:
                self.agent_in_flight[agent_id] = new_count
            task.acquired_slot = False
        # Wake all tasks waiting for a slot: both the subagent-reserved gate
        # and the fair-queuing gate.
        if self.slot_cond is not None:
            async with self.slot_cond:
                self.slot_cond.notify_all()
        if self.fair_cond is not None:
            async with self.fair_cond:
                self.fair_cond.notify_all()
