"""Stream wrappers for runtime event streams.

Async-generator wrappers:
  - repair_json_stream   — fix malformed JSON in tool-use arguments
  - idle_timeout_stream  — raise TimeoutError when no event arrives within N seconds
  - trim_tool_names_stream — strip whitespace from tool names
  - heartbeat_stream — emit non-persistent run heartbeats while upstream is quiet

Use wrap_stream() to compose the wrappers in one call.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import re
import time
from collections.abc import AsyncIterator
from typing import Any, cast

from opensquilla.runtime.events import RunHeartbeatEvent

# ---------------------------------------------------------------------------
# JSON repair helpers
# ---------------------------------------------------------------------------


def _repair_json(s: str) -> str:
    """Best-effort repair of partially-formed JSON strings.

    Fixes:
    1. Trailing commas before } or ]  — ``{"k": "v",}`` → ``{"k": "v"}``
    2. Whitespace-only keys            — strips leading/trailing spaces in keys
    3. Unclosed braces / brackets      — appends missing closing chars
    """
    if not s or not s.strip():
        return s

    # 1. Remove trailing commas before closing braces/brackets
    s = re.sub(r",\s*([}\]])", r"\1", s)

    # 2. Strip whitespace from object keys  ("  key  ": …)
    s = re.sub(r'"(\s+)(.*?)(\s+)"(\s*:)', lambda m: f'"{m.group(2)}"{m.group(4)}', s)

    # 3. Close unclosed structures
    stack: list[str] = []
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()

    # Append missing closers in reverse order
    s = s + "".join(reversed(stack))

    return s


# ---------------------------------------------------------------------------
# Wrapper 1: JSON repair
# ---------------------------------------------------------------------------


async def repair_json_stream(
    stream: AsyncIterator[Any],
) -> AsyncIterator[Any]:
    """Yield events unchanged except ToolUseStartEvent whose tool_name carries
    repaired JSON — and any future event that grows an ``arguments`` str field."""
    async for event in stream:
        # ToolUseStartEvent does not carry arguments (those arrive as deltas),
        # but downstream code may attach them; handle generically via hasattr.
        arguments = getattr(event, "arguments", None)
        if isinstance(arguments, str):
            setattr(event, "arguments", _repair_json(arguments))
        yield event


# ---------------------------------------------------------------------------
# Wrapper 2: Idle timeout
# ---------------------------------------------------------------------------


async def idle_timeout_stream(
    stream: AsyncIterator[Any],
    timeout: float = 30.0,
) -> AsyncIterator[Any]:
    """Raise ``TimeoutError`` if no event arrives within *timeout* seconds."""
    # Obtain the underlying __anext__ coroutine so we can wrap it with asyncio.wait_for
    aiter = stream.__aiter__()
    while True:
        try:
            event = await asyncio.wait_for(aiter.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            return
        except TimeoutError as exc:
            raise TimeoutError(f"Stream idle for more than {timeout}s") from exc
        yield event


# ---------------------------------------------------------------------------
# Wrapper 3: Run heartbeat while waiting
# ---------------------------------------------------------------------------


async def heartbeat_stream(
    stream: AsyncIterator[Any],
    *,
    interval: float = 15.0,
    phase: str = "agent",
    message: str = "Still working",
) -> AsyncIterator[Any]:
    """Emit ``RunHeartbeatEvent`` while waiting for the next upstream event.

    This wrapper does not cancel the pending upstream ``__anext__`` call when
    the heartbeat interval elapses. If the upstream stream is also wrapped by
    ``idle_timeout_stream``, the real timeout still propagates once reached.
    """
    if interval <= 0:
        async for event in stream:
            yield event
        return

    aiter = stream.__aiter__()
    started = time.monotonic()
    last_event_at = started
    pending: asyncio.Task[Any] | None = asyncio.create_task(_next_event(aiter))

    try:
        while pending is not None:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if pending in done:
                try:
                    event = pending.result()
                except StopAsyncIteration:
                    return
                last_event_at = time.monotonic()
                yield event
                pending = asyncio.create_task(_next_event(aiter))
                continue

            now = time.monotonic()
            yield RunHeartbeatEvent(
                phase=phase,
                elapsed_ms=int((now - started) * 1000),
                idle_ms=int((now - last_event_at) * 1000),
                message=message,
            )
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending


async def _next_event(aiter: AsyncIterator[Any]) -> Any:
    return cast(Any, await aiter.__anext__())


# ---------------------------------------------------------------------------
# Wrapper 4: Tool-name trim
# ---------------------------------------------------------------------------


async def trim_tool_names_stream(
    stream: AsyncIterator[Any],
) -> AsyncIterator[Any]:
    """Strip leading/trailing whitespace from tool names in ToolUseStartEvent."""
    async for event in stream:
        tool_name = getattr(event, "tool_name", None)
        if getattr(event, "kind", "") == "tool_use_start" and isinstance(tool_name, str):
            stripped = tool_name.strip()
            if stripped != tool_name:
                if dataclasses.is_dataclass(event) and not isinstance(event, type):
                    event = dataclasses.replace(event, tool_name=stripped)
                else:
                    setattr(event, "tool_name", stripped)
        yield event


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------


def wrap_stream(
    stream: AsyncIterator[Any],
    *,
    repair_json: bool = True,
    idle_timeout: float | None = 30.0,
    heartbeat_interval: float | None = None,
    heartbeat_phase: str = "agent",
    heartbeat_message: str = "Still working",
    trim_names: bool = True,
) -> AsyncIterator[Any]:
    """Compose stream wrappers around *stream*.

    Args:
        stream:       Source async iterator of AgentEvent.
        repair_json:  Enable JSON-repair wrapper (default True).
        idle_timeout: Seconds before TimeoutError; None disables (default 30.0).
        heartbeat_interval: Seconds between quiet-stream heartbeat events;
            None disables.
        trim_names:   Enable tool-name trim wrapper (default True).
    """
    if repair_json:
        stream = repair_json_stream(stream)
    if trim_names:
        stream = trim_tool_names_stream(stream)
    if idle_timeout is not None:
        stream = idle_timeout_stream(stream, idle_timeout)
    if heartbeat_interval is not None:
        stream = heartbeat_stream(
            stream,
            interval=heartbeat_interval,
            phase=heartbeat_phase,
            message=heartbeat_message,
        )
    return stream
