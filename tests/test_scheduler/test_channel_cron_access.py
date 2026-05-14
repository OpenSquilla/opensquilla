"""Channel-callable cron tool.

Drives the contract:
- A Feishu / Slack chat user can create reminders (system_event + main) AND
  background tasks (agent_turn + isolated) — both are normal use cases the
  model picks up from "提醒我喝水" / "每天早上总结邮件" style prompts.
- target_session_key and tool_policy are owner-only knobs; passing them as a
  non-owner is rejected with a clear ToolError (the model would only emit
  them deliberately, so silent drop would create false-success bugs).
- list / remove / run are scoped to the caller's identity (channel sender_id
  first, session_key fallback) for privacy. Owner-context callers see all.
- When session storage has not yet captured last_channel for a fresh chat,
  the tool synthesises a ReplyTargetSnapshot from the live ToolContext so the
  first cron call still binds delivery to the calling channel.
- No artificial active-job quota.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest

import opensquilla.tools.builtin.admin as admin_mod
from opensquilla.scheduler.types import (
    CronJob,
    DeliveryConfig,
    ReplyTargetSnapshot,
    SessionTarget,
)
from opensquilla.tools.builtin.admin import cron as cron_tool
from opensquilla.tools.registry import (
    _CHANNEL_DEFAULT_ALLOW,
    ToolProfile,
    profile_allows_tool,
)
from opensquilla.tools.types import (
    CallerKind,
    InteractionMode,
    ToolContext,
    current_tool_context,
)


@contextmanager
def _with_ctx(ctx: ToolContext):
    """Set/reset current_tool_context around a test body."""
    token = current_tool_context.set(ctx)
    try:
        yield
    finally:
        current_tool_context.reset(token)


# --- Tool visibility (channel-default profile) ---------------------------


def test_cron_visible_in_channel_default_profile() -> None:
    """Channel non-owner callers must see cron in the default tool profile."""
    assert "cron" in _CHANNEL_DEFAULT_ALLOW
    assert profile_allows_tool("cron", ToolProfile.CHANNEL_DEFAULT) is True


def test_cron_spec_is_not_owner_only() -> None:
    """Defense-in-depth dispatch must not block channel callers."""
    from opensquilla.tools.registry import _default_registry

    rt = _default_registry.get("cron")
    assert rt is not None, "cron tool not registered"
    assert rt.spec.owner_only is False


# --- Fakes ----------------------------------------------------------------


class _FakeScheduler:
    def __init__(self, jobs: list[CronJob] | None = None) -> None:
        self.jobs: list[CronJob] = list(jobs or [])
        self.add_calls: list[dict[str, Any]] = []

    async def list_jobs(self):
        return list(self.jobs)

    async def add_job(self, **kwargs):
        self.add_calls.append(kwargs)
        job = CronJob(
            id=f"job-{len(self.jobs) + 1}",
            name=kwargs["name"],
            cron_expr=kwargs["schedule_raw"],
            schedule_raw=kwargs["schedule_raw"],
            handler_key=kwargs["handler_key"],
            payload=kwargs["payload"],
            session_target=kwargs["session_target"],
            session_key=kwargs["session_key"],
            origin_session_key=kwargs.get("origin_session_key", ""),
            delivery=kwargs.get("delivery") or DeliveryConfig(),
            creator_session_key=kwargs.get("creator_session_key", "") or "",
            creator_sender_id=kwargs.get("creator_sender_id", "") or "",
        )
        self.jobs.append(job)
        return job

    async def update_job(self, job_id, **patch):
        for job in self.jobs:
            if job.id == job_id:
                for k, v in patch.items():
                    setattr(job, k, v)
                return job
        return None

    async def remove_job(self, job_id):
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j.id != job_id]
        return len(self.jobs) < before

    async def get_job(self, job_id):
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None

    async def run_job_now(self, job_id):
        from types import SimpleNamespace

        return SimpleNamespace(
            status=SimpleNamespace(value="accepted"),
            execution=SimpleNamespace(success=True, summary="ran", error=None),
        )


def _channel_ctx(
    session_key: str,
    sender_id: str = "feishu-user-1",
    channel_kind: str = "feishu",
    channel_id: str = "oc_chat_001",
) -> ToolContext:
    return ToolContext(
        is_owner=False,
        caller_kind=CallerKind.CHANNEL,
        interaction_mode=InteractionMode.INTERACTIVE,
        session_key=session_key,
        agent_id="main",
        channel_kind=channel_kind,
        channel_id=channel_id,
        sender_id=sender_id,
        source_kind="channel",
        source_name=channel_kind,
    )


def _owner_ctx(session_key: str = "agent:main:cli:owner") -> ToolContext:
    return ToolContext(
        is_owner=True,
        caller_kind=CallerKind.CLI,
        interaction_mode=InteractionMode.INTERACTIVE,
        session_key=session_key,
        agent_id="main",
    )


def _install_fake_infer(monkeypatch, snapshot: ReplyTargetSnapshot | None) -> None:
    """Patch infer_delivery so test calls do not hit real session storage."""
    from opensquilla.scheduler import delivery as delivery_mod
    from opensquilla.scheduler.types import DeliveryConfig as DC
    from opensquilla.scheduler.types import DeliveryMode as DM

    async def _stub(session_storage, session_key, user_overrides):
        if snapshot is None:
            return DC(mode=DM.NONE)
        return DC(
            mode=DM.ORIGIN,
            channel_name=snapshot.channel_name,
            channel_id=snapshot.to,
            account_id=snapshot.account_id,
            thread_id=snapshot.thread_id,
            originating_reply_target=snapshot,
        )

    monkeypatch.setattr(delivery_mod, "infer_delivery", _stub)
    from opensquilla.tools.builtin import sessions as sessions_mod

    monkeypatch.setattr(
        sessions_mod, "_get_session_manager", lambda: object(), raising=False
    )


@pytest.fixture
def fake_scheduler(monkeypatch):
    sched = _FakeScheduler()
    admin_mod.set_scheduler(sched)
    _install_fake_infer(
        monkeypatch,
        ReplyTargetSnapshot(
            channel_name="feishu",
            channel_type="feishu",
            to="oc_chat_001",
            account_id="",
            thread_id="",
        ),
    )
    yield sched
    admin_mod.set_scheduler(None)  # type: ignore[arg-type]


def _seed_job(
    fake_scheduler: _FakeScheduler,
    *,
    job_id: str,
    creator_session_key: str = "",
    creator_sender_id: str = "",
    name: str = "x",
) -> None:
    fake_scheduler.jobs.append(
        CronJob(
            id=job_id,
            name=name,
            cron_expr="*/5 * * * *",
            creator_session_key=creator_session_key,
            creator_sender_id=creator_sender_id,
        )
    )


# --- Happy path: channel user creates a reminder -------------------------


async def test_channel_user_can_add_reminder(fake_scheduler) -> None:
    """Feishu user: '每分钟提醒我喝水' → cron tool creates the job."""
    with _with_ctx(_channel_ctx("agent:main:feishu:user-1")):
        raw = await cron_tool(
            action="add",
            schedule="every 1m",
            task="提醒喝水",
            job_kind="system_event",
            session_target="main",
        )

    resp = json.loads(raw)
    assert resp["status"] == "scheduled"
    kwargs = fake_scheduler.add_calls[-1]
    assert kwargs["creator_sender_id"] == "feishu-user-1"
    assert kwargs["creator_session_key"] == "agent:main:feishu:user-1"
    assert kwargs["delivery"].originating_reply_target.to == "oc_chat_001"


async def test_channel_user_can_schedule_isolated_agent_turn(fake_scheduler) -> None:
    """'每天早上总结邮件' is a legitimate non-reminder cron use case (#3 relaxed).

    The cron-triggered turn runs under CRON_AGENT_ALLOW, so scheduling
    isolated does not escalate non-owner tool access.
    """
    with _with_ctx(_channel_ctx("agent:main:feishu:user-1")):
        raw = await cron_tool(
            action="add",
            schedule="0 9 * * *",
            task="总结昨日邮件",
            job_kind="agent_turn",
            session_target="isolated",
        )
    resp = json.loads(raw)
    assert resp["status"] == "scheduled"
    assert resp["session_target"] == "isolated"
    kwargs = fake_scheduler.add_calls[-1]
    assert kwargs["session_target"] == SessionTarget.ISOLATED
    assert kwargs["handler_key"] == "agent_run"


# --- Privilege-only parameters stay blocked (no UX impact on normal calls)


async def test_channel_user_cannot_inject_target_session_key(fake_scheduler) -> None:
    """Model never emits this on a normal turn; silent drop would mislead."""
    with _with_ctx(_channel_ctx("agent:main:feishu:user-1")):
        with pytest.raises(Exception, match="target_session_key"):
            await cron_tool(
                action="add",
                schedule="every 5m",
                task="leak",
                job_kind="agent_turn",
                session_target="session",
                target_session_key="agent:main:cli:owner",
            )


async def test_channel_user_cannot_use_tool_policy(fake_scheduler) -> None:
    with _with_ctx(_channel_ctx("agent:main:feishu:user-1")):
        with pytest.raises(Exception, match="tool_policy"):
            await cron_tool(
                action="add",
                schedule="every 5m",
                task="x",
                job_kind="system_event",
                session_target="main",
                tool_policy={"profile": "owner_full"},
            )


# --- Snapshot fallback from ctx -----------------------------------------


async def test_channel_user_without_session_snapshot_falls_back_to_ctx(monkeypatch) -> None:
    """If session storage has not captured last_channel yet, ctx.channel_*
    provides a usable snapshot — the first cron call from a fresh chat does
    NOT fail."""
    sched = _FakeScheduler()
    admin_mod.set_scheduler(sched)
    _install_fake_infer(monkeypatch, snapshot=None)

    ctx = _channel_ctx(
        "agent:main:feishu:fresh-user",
        sender_id="feishu-user-fresh",
        channel_id="oc_chat_fresh",
    )
    try:
        with _with_ctx(ctx):
            raw = await cron_tool(
                action="add",
                schedule="every 1m",
                task="hi",
                job_kind="system_event",
                session_target="main",
            )
    finally:
        admin_mod.set_scheduler(None)  # type: ignore[arg-type]

    assert json.loads(raw)["status"] == "scheduled"
    snap = sched.add_calls[-1]["delivery"].originating_reply_target
    assert snap.channel_name == "feishu"
    assert snap.to == "oc_chat_fresh"


# --- Cross-user privacy isolation ----------------------------------------


async def test_channel_user_list_shows_only_own_jobs(fake_scheduler) -> None:
    """List filter uses sender_id (preferred) then session_key (fallback)."""
    _seed_job(
        fake_scheduler,
        job_id="mine",
        creator_session_key="agent:main:feishu:user-1",
        creator_sender_id="feishu-user-1",
    )
    _seed_job(
        fake_scheduler,
        job_id="theirs",
        creator_session_key="agent:main:feishu:user-9",
        creator_sender_id="feishu-user-9",
    )
    _seed_job(fake_scheduler, job_id="owner-job")  # creator fields blank

    with _with_ctx(_channel_ctx("agent:main:feishu:user-1", sender_id="feishu-user-1")):
        raw = await cron_tool(action="list")

    ids = [j["job_id"] for j in json.loads(raw)["jobs"]]
    assert ids == ["mine"]


async def test_channel_user_list_falls_back_to_session_when_sender_missing(
    fake_scheduler,
) -> None:
    """Legacy jobs without creator_sender_id are matched on session_key."""
    _seed_job(
        fake_scheduler,
        job_id="legacy",
        creator_session_key="agent:main:feishu:user-1",
    )
    with _with_ctx(_channel_ctx("agent:main:feishu:user-1", sender_id="")):
        raw = await cron_tool(action="list")
    ids = [j["job_id"] for j in json.loads(raw)["jobs"]]
    assert ids == ["legacy"]


async def test_channel_user_cannot_remove_others_job(fake_scheduler) -> None:
    _seed_job(
        fake_scheduler,
        job_id="theirs",
        creator_session_key="agent:main:feishu:user-9",
        creator_sender_id="feishu-user-9",
    )
    with _with_ctx(_channel_ctx("agent:main:feishu:user-1")):
        with pytest.raises(Exception, match="permission denied"):
            await cron_tool(action="remove", job_id="theirs")


async def test_channel_user_cannot_run_others_job(fake_scheduler) -> None:
    _seed_job(
        fake_scheduler,
        job_id="theirs",
        creator_session_key="agent:main:feishu:user-9",
        creator_sender_id="feishu-user-9",
    )
    with _with_ctx(_channel_ctx("agent:main:feishu:user-1")):
        with pytest.raises(Exception, match="permission denied"):
            await cron_tool(action="run", job_id="theirs")


async def test_channel_user_can_remove_own_job(fake_scheduler) -> None:
    _seed_job(
        fake_scheduler,
        job_id="mine",
        creator_session_key="agent:main:feishu:user-1",
        creator_sender_id="feishu-user-1",
    )
    with _with_ctx(_channel_ctx("agent:main:feishu:user-1")):
        raw = await cron_tool(action="remove", job_id="mine")
    assert json.loads(raw)["status"] == "removed"


async def test_channel_user_can_run_own_job(fake_scheduler) -> None:
    _seed_job(
        fake_scheduler,
        job_id="mine",
        creator_session_key="agent:main:feishu:user-1",
        creator_sender_id="feishu-user-1",
    )
    with _with_ctx(_channel_ctx("agent:main:feishu:user-1")):
        raw = await cron_tool(action="run", job_id="mine")
    assert json.loads(raw)["action"] == "run"


# --- Owner path unchanged ------------------------------------------------


async def test_owner_path_unchanged(fake_scheduler) -> None:
    with _with_ctx(_owner_ctx()):
        raw = await cron_tool(
            action="add",
            schedule="0 9 * * *",
            task="Morning brief",
            job_kind="agent_turn",
            session_target="session",
            target_session_key="agent:main:custom:report-daily",
        )
    assert json.loads(raw)["status"] == "scheduled"


async def test_owner_can_list_all_jobs(fake_scheduler) -> None:
    _seed_job(fake_scheduler, job_id="ch1", creator_sender_id="feishu-user-1")
    _seed_job(fake_scheduler, job_id="own1")
    with _with_ctx(_owner_ctx()):
        raw = await cron_tool(action="list")
    ids = {j["job_id"] for j in json.loads(raw)["jobs"]}
    assert ids == {"ch1", "own1"}
