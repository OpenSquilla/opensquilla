"""sessionTarget=current fail-soft fallback.

OpenSquilla preserves CURRENT in storage and resolves the bound key at
fire-time using stored ``session_key``/``origin_session_key`` (see existing
RPC tests). This file covers the creation-time guard: when CURRENT is
requested but neither binding is present (e.g. headless CLI use),
SchedulerOps.add silently falls back to ISOLATED instead of raising.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opensquilla.scheduler.ops import SchedulerOps
from opensquilla.scheduler.payloads import make_agent_turn_payload
from opensquilla.scheduler.persistence import JobStore
from opensquilla.scheduler.types import SessionTarget


async def test_current_target_with_no_binding_falls_back_to_isolated(tmp_path: Path) -> None:
    db = tmp_path / "cron.db"
    store = JobStore(str(db))
    await store.open()
    try:
        ops = SchedulerOps(store)
        job = await ops.add(
            name="headless",
            schedule_raw="*/5 * * * *",
            handler_key="agent_run",
            payload=make_agent_turn_payload("brief"),
            session_target=SessionTarget.CURRENT,
            # No session_key, no origin_session_key
        )
        assert job.session_target == SessionTarget.ISOLATED
    finally:
        await store.close()


async def test_current_target_with_origin_session_key_preserves_current(tmp_path: Path) -> None:
    """When origin_session_key is provided, CURRENT is preserved (existing semantic)."""
    db = tmp_path / "cron.db"
    store = JobStore(str(db))
    await store.open()
    try:
        ops = SchedulerOps(store)
        job = await ops.add(
            name="bound",
            schedule_raw="*/5 * * * *",
            handler_key="agent_run",
            payload=make_agent_turn_payload("brief"),
            session_target=SessionTarget.CURRENT,
            origin_session_key="agent:main:webchat:abc",
        )
        assert job.session_target == SessionTarget.CURRENT
        assert job.session_key == "agent:main:webchat:abc"
        assert job.origin_session_key == "agent:main:webchat:abc"
    finally:
        await store.close()


async def test_current_target_with_session_key_preserves_current(tmp_path: Path) -> None:
    """When session_key is provided directly, CURRENT is preserved."""
    db = tmp_path / "cron.db"
    store = JobStore(str(db))
    await store.open()
    try:
        ops = SchedulerOps(store)
        job = await ops.add(
            name="bound",
            schedule_raw="*/5 * * * *",
            handler_key="agent_run",
            payload=make_agent_turn_payload("brief"),
            session_target=SessionTarget.CURRENT,
            session_key="agent:main:webchat:abc",
            origin_session_key="agent:main:webchat:abc",
        )
        assert job.session_target == SessionTarget.CURRENT
        assert job.session_key == "agent:main:webchat:abc"
    finally:
        await store.close()


async def test_isolated_target_unaffected(tmp_path: Path) -> None:
    """Sanity: explicit ISOLATED target is unchanged."""
    db = tmp_path / "cron.db"
    store = JobStore(str(db))
    await store.open()
    try:
        ops = SchedulerOps(store)
        job = await ops.add(
            name="iso",
            schedule_raw="*/5 * * * *",
            handler_key="agent_run",
            payload=make_agent_turn_payload("brief"),
            session_target=SessionTarget.ISOLATED,
        )
        assert job.session_target == SessionTarget.ISOLATED
    finally:
        await store.close()
