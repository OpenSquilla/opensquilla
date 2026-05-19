"""TaskRuntime stream event emission helpers."""

from __future__ import annotations

import inspect
from dataclasses import asdict, is_dataclass
from typing import Any, cast

import structlog

from opensquilla.runtime.stream_wrappers import wrap_stream
from opensquilla.session.terminal_reply import build_terminal_reply

log = structlog.get_logger(__name__)


async def emit_task_runtime_stream_events(
    raw_stream: Any,
    session_key: str,
    event_emitter: Any,
    *,
    idle_timeout: float | None = 180.0,
    heartbeat_interval: float | None = None,
    stream_event_sink: Any = None,
) -> None:
    """Emit turn events and fail the task if the stream reports an error."""
    error_message: str | None = None
    async for event in wrap_stream(
        raw_stream,
        idle_timeout=idle_timeout,
        heartbeat_interval=heartbeat_interval,
        heartbeat_message="Agent run is still active",
    ):
        if stream_event_sink is not None:
            try:
                result = stream_event_sink(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                log.debug(
                    "task_runtime.stream_event_sink_failed",
                    session_key=session_key,
                    event_kind=getattr(event, "kind", event.__class__.__name__),
                    exc_info=True,
                )
        if is_dataclass(event) and not isinstance(event, type):
            event_dict = asdict(cast(Any, event))
        else:
            event_dict = {
                key: value
                for key, value in getattr(event, "__dict__", {}).items()
                if not key.startswith("_")
            }
        event_kind = event_dict.pop("kind", getattr(event, "kind", event.__class__.__name__))
        if event_kind == "error":
            raw_message = event_dict.get("message")
            error_message = (
                raw_message if isinstance(raw_message, str) and raw_message else "Agent error"
            )
            code = event_dict.get("code")
            code_text = str(code or "").lower()
            is_timeout = "timeout" in code_text or "stream idle" in error_message.lower()
            terminal_payload = {
                "status": "timeout" if is_timeout else "failed",
                "terminal_reason": "timeout" if is_timeout else "error",
                "error_class": code,
                "error_message": error_message,
            }
            terminal_message = build_terminal_reply(terminal_payload)
            event_dict["message"] = terminal_message
            event_dict["terminal_message"] = terminal_message
            event_dict["terminal_reason"] = terminal_payload["terminal_reason"]
            event_dict["error_message"] = error_message
        await event_emitter(
            session_key,
            f"session.event.{event_kind}",
            event_dict,
        )
        if event_kind == "error":
            message = event_dict.get("error_message")
            error_message = message if isinstance(message, str) and message else "Agent error"
    if error_message is not None:
        raise RuntimeError(error_message)
