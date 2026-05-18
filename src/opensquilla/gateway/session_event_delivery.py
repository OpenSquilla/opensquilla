"""Shared session event buffering and subscriber delivery helpers."""

from __future__ import annotations

from typing import Any

import structlog

from opensquilla.gateway.session_streams import SessionStreamRegistry, get_session_streams

log = structlog.get_logger(__name__)


def buffer_session_event(
    session_key: str,
    event_name: str,
    payload: dict[str, Any] | None,
    *,
    stream_registry: SessionStreamRegistry | None = None,
) -> dict[str, Any]:
    """Buffer replayable session events and return the payload to send."""
    if event_name.startswith("session.event."):
        registry = stream_registry or get_session_streams()
        return registry.record(session_key, event_name, payload)
    return dict(payload or {})


async def deliver_session_event(
    *,
    subscription_manager: Any,
    connection_registry: Any,
    session_key: str,
    event_name: str,
    payload: dict[str, Any] | None,
    stream_registry: SessionStreamRegistry | None = None,
    logger: Any | None = None,
) -> None:
    """Send a session-scoped event to matching websocket subscribers."""
    if subscription_manager is None:
        return

    active_logger = logger or log
    send_payload = buffer_session_event(
        session_key,
        event_name,
        payload,
        stream_registry=stream_registry,
    )

    conn_ids = subscription_manager.get_message_subscribers(session_key)
    if event_name.startswith("sessions."):
        conn_ids = conn_ids | subscription_manager.get_session_subscribers()

    for conn_id in conn_ids:
        conn = connection_registry.get(conn_id)
        if conn is not None:
            try:
                await conn.send_event(event_name, send_payload)
            except Exception:
                active_logger.warning(
                    "session_event_delivery.send_failed",
                    conn_id=conn_id,
                    event=event_name,
                )
