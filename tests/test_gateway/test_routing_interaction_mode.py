from __future__ import annotations

from types import SimpleNamespace

from opensquilla.channels.types import IncomingMessage
from opensquilla.gateway.routing import (
    build_channel_route_envelope,
    build_cli_route_envelope,
    build_cron_route_envelope,
    build_subagent_route_envelope,
    build_web_route_envelope,
    tool_context_from_envelope,
)
from opensquilla.gateway.boot import _task_runtime_envelope_owner
from opensquilla.tools.policy import ToolSurfaceCapabilities, resolve_runtime_tool_surface
from opensquilla.tools.types import CallerKind, InteractionMode


def test_route_envelopes_assign_expected_interaction_modes() -> None:
    channel_msg = IncomingMessage(sender_id="u1", channel_id="c1", content="hi")
    cron_job = SimpleNamespace(id="job-1", name="demo")

    cases = [
        (
            build_cli_route_envelope(session_key="agent:main:cli"),
            CallerKind.CLI,
            InteractionMode.INTERACTIVE,
        ),
        (
            build_cli_route_envelope(
                session_key="agent:main:auto",
                interaction_mode=InteractionMode.UNATTENDED,
            ),
            CallerKind.CLI,
            InteractionMode.UNATTENDED,
        ),
        (
            build_web_route_envelope(session_key="agent:main:web"),
            CallerKind.WEB,
            InteractionMode.INTERACTIVE,
        ),
        (
            build_channel_route_envelope(
                channel_msg,
                session_key="telegram:dm:u1",
                session_prefix="telegram",
            ),
            CallerKind.CHANNEL,
            InteractionMode.UNATTENDED,
        ),
        (
            build_cron_route_envelope(cron_job, session_key="cron:job-1"),
            CallerKind.CRON,
            InteractionMode.UNATTENDED,
        ),
        (
            build_subagent_route_envelope(
                session_key="subagent:parent:child",
                parent_session_key="agent:main:parent",
            ),
            CallerKind.SUBAGENT,
            InteractionMode.UNATTENDED,
        ),
    ]

    for envelope, expected_kind, expected_mode in cases:
        ctx = tool_context_from_envelope(envelope)
        assert ctx.caller_kind is expected_kind
        assert ctx.interaction_mode is expected_mode


def test_unattended_cli_denies_runtime_dependent_tools_but_keeps_session_reads() -> None:
    envelope = build_cli_route_envelope(
        session_key="agent:main:auto",
        interaction_mode=InteractionMode.UNATTENDED,
    )

    ctx = resolve_runtime_tool_surface(
        tool_context_from_envelope(envelope, is_owner=True),
        capabilities=ToolSurfaceCapabilities(session_manager=True),
    )

    assert "sessions_spawn" in ctx.denied_tools
    assert "gateway" in ctx.denied_tools
    assert "sessions_list" not in ctx.denied_tools
    assert "sessions_history" not in ctx.denied_tools
    assert "session_status" not in ctx.denied_tools


def test_owner_cron_route_carries_owner_principal_for_task_runtime() -> None:
    cron_job = SimpleNamespace(id="job-owner", name="owner", creator_is_owner=True)

    envelope = build_cron_route_envelope(cron_job, session_key="cron:job-owner")

    assert envelope.metadata["principal_is_owner"] is True
    assert _task_runtime_envelope_owner(envelope) is True


def test_owner_cron_route_uses_owner_grade_tool_boundary() -> None:
    cron_job = SimpleNamespace(id="job-owner", name="owner", creator_is_owner=True)
    envelope = build_cron_route_envelope(cron_job, session_key="cron:job-owner")

    ctx = tool_context_from_envelope(
        envelope,
        is_owner=_task_runtime_envelope_owner(envelope),
    )

    assert ctx.caller_kind is CallerKind.CRON
    assert ctx.is_owner is True
    assert ctx.allowed_tools is None
    assert "exec_command" not in ctx.denied_tools
    assert "write_file" not in ctx.denied_tools


def test_non_owner_cron_route_keeps_restricted_tool_boundary() -> None:
    cron_job = SimpleNamespace(id="job-user", name="user")
    envelope = build_cron_route_envelope(cron_job, session_key="cron:job-user")

    ctx = tool_context_from_envelope(envelope)

    assert ctx.caller_kind is CallerKind.CRON
    assert ctx.is_owner is False
    assert ctx.allowed_tools is not None
    assert "exec_command" not in ctx.allowed_tools
    assert "exec_command" in ctx.denied_tools
