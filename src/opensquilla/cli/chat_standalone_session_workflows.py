"""Standalone session slash-command workflows for interactive chat."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from uuid import uuid4

from opensquilla.cli.repl.session_state import ChatSessionState
from opensquilla.cli.ui import ACCENT, console


async def handle_standalone_new_command(
    parts: Sequence[str],
    *,
    session_manager: Any,
    build_tool_context: Callable[[str], object],
    model: str | None,
) -> tuple[str, object, ChatSessionState]:
    """Handle standalone chat /new by creating a fresh session and state."""

    session_key = f"agent:main:standalone:{uuid4().hex[:8]}"
    await session_manager.get_or_create(session_key, agent_id="main")
    tool_context = build_tool_context(session_key)
    state = ChatSessionState(session_key=session_key, model=model)
    title = parts[1].strip() if len(parts) > 1 else None
    label = f" ({title})" if title else ""
    console.print(f"[green]Started new session{label}:[/green] {session_key}")
    return session_key, tool_context, state


async def handle_standalone_clear_command(
    state: ChatSessionState,
    *,
    services: Any,
    flush_before_rewrite: Callable[..., Awaitable[bool]],
) -> bool:
    """Handle standalone chat /clear and /reset."""

    session_manager = getattr(services, "session_manager", None)
    if session_manager is not None:
        safe_to_reset = await flush_before_rewrite(
            services,
            state.session_key,
            operation="Reset",
        )
        if not safe_to_reset:
            return False
        await session_manager.truncate(state.session_key, max_messages=0)
    state.transcript.clear()
    state.usage.reset()
    console.print(f"[{ACCENT}]cleared[/] [dim]{state.session_key}[/dim]")
    return True
