"""Admin tools: cron scheduler and gateway control."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Protocol

import structlog

from opensquilla.scheduler.payloads import (
    SYSTEM_EVENT_KIND,
    make_agent_turn_payload,
    make_system_event_payload,
)
from opensquilla.scheduler.types import (
    DeliveryConfig,
    DeliveryMode,
    ReplyTargetSnapshot,
    SessionTarget,
)
from opensquilla.tools.registry import tool
from opensquilla.tools.types import ToolError

log = structlog.get_logger(__name__)

_VALID_CRON_ACTIONS = ("list", "add", "remove", "run")


# ---------------------------------------------------------------------------
# Cron prompt injection scanner
# ---------------------------------------------------------------------------

# Hard-block patterns — always rejected
_HARD_BLOCK_PATTERNS: list[re.Pattern[str]] = [
    # Invisible unicode characters
    re.compile(r"[\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff]"),
    # Exfiltration via curl/wget with variable interpolation
    re.compile(r"(curl|wget)\s+.*(\{\{|\\$[\w{])", re.IGNORECASE),
    # Destructive system commands
    re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r"mkfs\.", re.IGNORECASE),
    re.compile(r":(){ :\|:& };:", re.IGNORECASE),  # fork bomb
]

# Soft-block patterns — logged as warning, still rejected
_SOFT_BLOCK_PATTERNS: list[re.Pattern[str]] = [
    # Instruction injection
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior", re.IGNORECASE),
    # SQL destructive
    re.compile(r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE)\b", re.IGNORECASE),
]


def _scan_cron_prompt(task: str) -> tuple[bool, str]:
    """Scan a cron task prompt for injection/exfiltration patterns.

    Returns (blocked: bool, reason: str). If blocked is True, the prompt
    should be rejected.
    """
    # Check for invisible unicode characters
    for char in task:
        cat = unicodedata.category(char)
        if cat in ("Cf", "Mn", "Cc") and char not in ("\n", "\r", "\t"):
            log.warning("cron_prompt_blocked", pattern="invisible_unicode", char=repr(char))
            return True, f"Blocked: invisible unicode character detected ({repr(char)})"

    # Hard-block patterns
    for pattern in _HARD_BLOCK_PATTERNS:
        if pattern.search(task):
            log.warning("cron_prompt_blocked", pattern=pattern.pattern)
            return True, f"Blocked: dangerous pattern detected ({pattern.pattern})"

    # Soft-block patterns
    for pattern in _SOFT_BLOCK_PATTERNS:
        if pattern.search(task):
            log.warning("cron_prompt_blocked", pattern=pattern.pattern, severity="soft")
            return True, f"Blocked: potential injection pattern ({pattern.pattern})"

    return False, ""


_VALID_GATEWAY_ACTIONS = ("restart", "config_get", "config_set")


class _SchedulerProtocol(Protocol):
    async def list_jobs(self) -> list[Any]: ...

    async def add_job(
        self,
        name: str,
        schedule_raw: str | None = None,
        handler_key: str = "agent_run",
        payload: dict[Any, Any] | None = None,
        session_target: SessionTarget = SessionTarget.ISOLATED,
        session_key: str = "",
        timeout_seconds: float = 600.0,
        wake_mode: str = "now",
        max_retries: int = 3,
        origin_session_key: str = "",
        cron_expr: str | None = None,
        delivery: DeliveryConfig | None = None,
        tool_policy: dict[str, Any] | None = None,
    ) -> Any: ...

    async def update_job(self, job_id: str, **patch: Any) -> Any: ...

    async def remove_job(self, job_id: str) -> bool: ...

    async def run_job_now(self, job_id: str) -> Any: ...


# Setter-injected dependencies (gateway boot calls these)
_scheduler: _SchedulerProtocol | None = None
_gateway_config = None


def set_scheduler(engine: _SchedulerProtocol) -> None:
    """Inject the SchedulerEngine (called from gateway boot)."""
    global _scheduler
    _scheduler = engine


def set_gateway_config(config: object) -> None:
    """Inject the GatewayConfig (called from gateway boot)."""
    global _gateway_config
    _gateway_config = config


def scheduler_available() -> bool:
    return _scheduler is not None


def gateway_config_available() -> bool:
    return _gateway_config is not None


# ---------------------------------------------------------------------------
# cron
# ---------------------------------------------------------------------------


def _owns_cron_job(job: Any, sender_id: str, session_key: str) -> bool:
    """Caller-ownership test for non-owner cron actions.

    Prefer the stable channel sender_id; fall back to session_key for jobs
    created before sender_id tracking existed (or for non-channel sessions).
    """
    job_sender = (getattr(job, "creator_sender_id", "") or "")
    job_session = (getattr(job, "creator_session_key", "") or "")
    if sender_id and job_sender:
        return job_sender == sender_id
    if session_key and job_session:
        return job_session == session_key
    return False


@tool(
    name="cron",
    description=(
        "Create, list, remove, or trigger scheduled cron jobs. "
        "Use this tool (NOT exec_command or background_process) for any recurring/timed "
        "task scheduling or reminders. For reminders such as '每分钟提醒我喝水', use "
        "job_kind=system_event and session_target=main. For recurring background "
        "agent tasks such as 'every morning summarize yesterday's emails', use "
        "job_kind=agent_turn with session_target=isolated. "
        "Channel users can create reminders and tasks bound to the calling channel; "
        "list / remove / run only affect jobs the caller created."
    ),
    params={
        "action": {
            "type": "string",
            "description": "Action: list, add, remove, run",
        },
        "schedule": {
            "type": "string",
            "description": (
                "Schedule: cron expr, natural language ('every 30m', '2h'), Chinese "
                "reminders ('每分钟', '每5分钟', '45分钟后', '每天9点'), or ISO timestamp"
            ),
        },
        "task": {
            "type": "string",
            "description": "Message to execute on trigger (required for add)",
        },
        "job_kind": {
            "type": "string",
            "description": "system_event for reminders, agent_turn for background agent tasks.",
            "enum": ["system_event", "agent_turn"],
        },
        "session_target": {
            "type": "string",
            "description": (
                "Target session mode for add. Use main for reminders and isolated/session"
                " for agent_turn jobs."
            ),
            "enum": ["main", "isolated", "session"],
        },
        "target_session_key": {
            "type": "string",
            "description": "Named session key when session_target=session.",
        },
        "job_id": {
            "type": "string",
            "description": "Job ID (required for remove and run)",
        },
        "agent_id": {
            "type": "string",
            "description": "Agent to run the task as (for add)",
            "default": "main",
        },
        "wake_mode": {
            "type": "string",
            "description": (
                "Main-session heartbeat mode: now runs one "
                "heartbeat immediately; next-heartbeat only queues a wake."
            ),
            "enum": ["now", "next-heartbeat"],
            "default": "now",
        },
        "tool_policy": {
            "type": "object",
            "description": (
                "Optional per-job cron tool policy with profile, allow, also_allow, and deny."
            ),
        },
        "tz": {
            "type": "string",
            "description": (
                "Optional IANA timezone (e.g. 'America/Los_Angeles', 'Asia/Shanghai'). "
                "Applies to cron expressions; '0 9 * * *' with tz='America/Los_Angeles' "
                "fires at 09:00 LA wall time. Empty string keeps the legacy UTC behaviour."
            ),
        },
    },
    required=["action"],
    owner_only=False,
)
async def cron(
    action: str,
    schedule: str | None = None,
    task: str | None = None,
    job_kind: str = "system_event",
    session_target: str = "main",
    target_session_key: str | None = None,
    job_id: str | None = None,
    agent_id: str = "main",
    wake_mode: str = "now",
    tool_policy: dict[str, Any] | None = None,
    tz: str = "",
) -> str:
    if action not in _VALID_CRON_ACTIONS:
        raise ToolError(f"Invalid action: {action}. Must be list|add|remove|run")

    if action == "add" and (not schedule or not task):
        raise ToolError("'schedule' and 'task' required for add")
    if action in ("remove", "run") and not job_id:
        raise ToolError(f"'job_id' required for {action}")

    # Dispatch to injected scheduler
    if _scheduler is None:
        raise ToolError("Scheduler not available")

    sched = _scheduler

    # Resolve caller context. Owner-context calls (loopback CLI, owner WebUI,
    # channel_admin_senders) pass through unchanged. Non-owner channel callers
    # get caller-scoped list / remove / run filtering and have target_session_key
    # / tool_policy blocked (privilege escalation knobs the model should not
    # synthesise on a normal channel turn).
    from opensquilla.tools.types import current_tool_context

    ctx = current_tool_context.get()
    is_owner_caller = bool(getattr(ctx, "is_owner", False)) if ctx is not None else True
    caller_session_key = (
        ctx.session_key if ctx is not None and ctx.session_key else ""
    )
    caller_sender_id = (
        ctx.sender_id if ctx is not None and getattr(ctx, "sender_id", "") else ""
    )

    if not is_owner_caller:
        if not caller_session_key:
            raise ToolError(
                "cron requires a session context for non-owner callers; "
                "call from a channel-bound session"
            )
        if action == "add":
            if target_session_key:
                raise ToolError(
                    "target_session_key is reserved for owner callers; "
                    "non-owner reminders are scoped to your current session"
                )
            if tool_policy:
                raise ToolError(
                    "tool_policy is reserved for owner callers"
                )

    if action == "list":
        jobs = await sched.list_jobs()
        if not is_owner_caller:
            jobs = [
                j
                for j in jobs
                if _owns_cron_job(j, caller_sender_id, caller_session_key)
            ]
        items = [
            {
                "job_id": j.id,
                "name": j.name,
                "cron_expr": j.cron_expr,
                "status": j.status.value if hasattr(j.status, "value") else str(j.status),
            }
            for j in jobs
        ]
        return json.dumps({"action": "list", "jobs": items})

    if action == "add":
        assert schedule is not None
        assert task is not None
        wake_mode = str(wake_mode or "now").strip().lower()

        # Scan prompt for injection/exfiltration before scheduling
        blocked, reason = _scan_cron_prompt(task)
        if blocked:
            raise ToolError(reason)

        if job_kind not in ("system_event", "agent_turn"):
            raise ToolError("job_kind must be system_event or agent_turn")
        if session_target not in ("main", "isolated", "session"):
            raise ToolError("session_target must be main, isolated, or session")
        if job_kind == "system_event" and session_target != "main":
            raise ToolError("system_event jobs must use session_target=main")
        if job_kind == "agent_turn" and session_target == "main":
            raise ToolError("agent_turn jobs cannot use session_target=main")
        if session_target == "session" and not target_session_key:
            raise ToolError("target_session_key is required when session_target=session")
        if wake_mode not in ("now", "next-heartbeat"):
            raise ToolError("wake_mode must be now or next-heartbeat")

        # Auto-detect delivery target from session storage.
        delivery = None
        if caller_session_key:
            try:
                from opensquilla.scheduler.delivery import infer_delivery
                from opensquilla.tools.builtin.sessions import _get_session_manager

                mgr = _get_session_manager()
                storage = getattr(mgr, "_storage", mgr)
                inferred = await infer_delivery(
                    session_storage=storage,
                    session_key=caller_session_key,
                    user_overrides=None,
                )
                if (
                    inferred.mode == DeliveryMode.ORIGIN
                    and inferred.channel_name
                    and inferred.originating_reply_target is None
                ):
                    inferred.originating_reply_target = ReplyTargetSnapshot(
                        channel_name=inferred.channel_name,
                        channel_type=inferred.channel_name,
                        to=inferred.channel_id,
                        account_id=inferred.account_id,
                        thread_id=inferred.thread_id,
                    )
                if session_target == "main":
                    # Main heartbeat ignores the channel mode (persistence forces
                    # NONE for main) but uses the snapshot to pin the reply target.
                    if inferred.originating_reply_target is not None:
                        delivery = DeliveryConfig(
                            mode=DeliveryMode.NONE,
                            originating_reply_target=inferred.originating_reply_target,
                        )
                else:
                    delivery = inferred
            except Exception:
                pass

        # Snapshot fallback: when session storage did not yield a channel-
        # routable target (fresh session before last_channel was written), build
        # one from the live ToolContext so the first cron call still binds.
        if (
            ctx is not None
            and getattr(ctx, "channel_kind", None)
            and getattr(delivery, "originating_reply_target", None) is None
        ):
            snapshot = ReplyTargetSnapshot(
                channel_name=ctx.channel_kind or "",
                channel_type=ctx.channel_kind or "",
                to=ctx.channel_id or "",
            )
            if delivery is None:
                delivery = DeliveryConfig(
                    mode=DeliveryMode.NONE,
                    originating_reply_target=snapshot,
                )
            else:
                delivery.originating_reply_target = snapshot

        payload = (
            make_system_event_payload(task, agent_id)
            if job_kind == SYSTEM_EVENT_KIND
            else make_agent_turn_payload(task, agent_id)
        )
        job = await sched.add_job(
            name=task or "cron-tool-job",
            schedule_raw=schedule,
            handler_key="system_event" if job_kind == SYSTEM_EVENT_KIND else "agent_run",
            payload=payload,
            session_target=SessionTarget(session_target),
            session_key=target_session_key or "",
            wake_mode=wake_mode,
            delivery=delivery,
            origin_session_key=caller_session_key,
            tool_policy=tool_policy,
            tz=tz or "",
            creator_session_key=caller_session_key,
            creator_sender_id=caller_sender_id,
        )
        # Populate ws_topic
        if job.delivery and not job.delivery.ws_topic:
            job.delivery.ws_topic = f"cron:{job.id}"
            try:
                await sched.update_job(job.id, delivery=job.delivery)
            except Exception:
                pass  # best-effort
        return json.dumps(
            {
                "action": "add",
                "job_id": job.id,
                "schedule": schedule,
                "task": task,
                "payload_kind": job_kind,
                "session_target": session_target,
                "wake_mode": wake_mode,
                "tz": tz or "",
                "status": "scheduled",
            }
        )

    if action == "remove":
        assert job_id is not None
        if not is_owner_caller:
            target_job = await sched.get_job(job_id)
            if target_job is None:
                raise ToolError(f"Job not found: {job_id}")
            if not _owns_cron_job(target_job, caller_sender_id, caller_session_key):
                raise ToolError(
                    "permission denied: you can only remove cron jobs you created"
                )
        removed = await sched.remove_job(job_id)
        if not removed:
            raise ToolError(f"Job not found: {job_id}")
        return json.dumps({"action": "remove", "job_id": job_id, "status": "removed"})

    # run
    assert job_id is not None
    if not is_owner_caller:
        target_job = await sched.get_job(job_id)
        if target_job is None:
            raise ToolError(f"Job not found: {job_id}")
        if not _owns_cron_job(target_job, caller_sender_id, caller_session_key):
            raise ToolError(
                "permission denied: you can only run cron jobs you created"
            )
    result = await sched.run_job_now(job_id)
    status = getattr(result, "status", "")
    status_str = status.value if hasattr(status, "value") else str(status)
    execution = getattr(result, "execution", None)
    run_payload: dict[str, Any] = {
        "action": "run",
        "job_id": job_id,
        "status": status_str,
    }
    if execution is not None:
        run_payload["success"] = execution.success
        run_payload["summary"] = execution.summary
        run_payload["error"] = execution.error
    else:
        run_payload["success"] = False
        run_payload["reason"] = getattr(result, "reason", "") or status_str
        run_payload["error"] = getattr(result, "error", None)
        current_status = getattr(result, "current_status", "")
        if current_status:
            run_payload["current_status"] = current_status
        backoff_until = getattr(result, "backoff_until", None)
        if backoff_until is not None:
            run_payload["backoff_until"] = backoff_until.isoformat()
    return json.dumps(
        run_payload
    )


# ---------------------------------------------------------------------------
# gateway
# ---------------------------------------------------------------------------


@tool(
    name="gateway",
    description="Gateway control: restart and configuration management.",
    params={
        "action": {
            "type": "string",
            "description": "Action: restart, config_get, config_set",
        },
        "key": {
            "type": "string",
            "description": "Config key path (required for config_get and config_set)",
        },
        "value": {
            "type": "string",
            "description": "Config value as JSON string (required for config_set)",
        },
    },
    required=["action"],
    owner_only=True,
)
async def gateway(
    action: str,
    key: str | None = None,
    value: str | None = None,
) -> str:
    if action not in _VALID_GATEWAY_ACTIONS:
        raise ToolError(f"Invalid action: {action}. Must be restart|config_get|config_set")

    if action in ("config_get", "config_set") and not key:
        raise ToolError(f"'key' required for {action}")
    if action == "config_set" and value is None:
        raise ToolError("'value' required for config_set")

    # Parse JSON value for config_set
    parsed_value = None
    if action == "config_set":
        assert value is not None
        try:
            parsed_value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            raise ToolError("'value' must be valid JSON")

    if _gateway_config is None:
        raise ToolError("Gateway config not available")

    config = _gateway_config

    if action == "restart":
        raise ToolError("Gateway restart not supported via tool")

    if action == "config_get":
        assert key is not None
        cfg_dict = config.to_toml_dict() if hasattr(config, "to_toml_dict") else {}
        # Navigate dot-path key
        parts = key.split(".")
        val = cfg_dict
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                val = None
                break
        if val is None:
            raise ToolError(f"Config key not found: {key}")
        return json.dumps({"action": "config_get", "key": key, "value": val})

    # config_set
    if hasattr(config, "patch"):
        await config.patch({key: parsed_value})
        return json.dumps(
            {
                "action": "config_set",
                "key": key,
                "value": parsed_value,
            }
        )
    raise ToolError("Config modification not supported")
