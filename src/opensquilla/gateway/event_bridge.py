"""EventBridge — emit session events to WebSocket subscribers without RpcContext.

Decouples channel dispatch event broadcasting from the RPC handler layer.
The gateway boot code creates an EventBridge and threads it through
ChannelManager → run_channel_dispatch.
"""

from __future__ import annotations

from typing import Any

import structlog

from opensquilla.gateway import session_event_delivery

log = structlog.get_logger(__name__)


class EventBridge:
    """Emit session events to WebSocket subscribers.

    Uses the same ``SubscriptionManager`` and ``ConnectionRegistry`` as
    the RPC path, but without requiring an ``RpcContext``.
    """

    def __init__(self, subscription_manager: Any, connection_registry: Any) -> None:
        self._subs = subscription_manager
        self._registry = connection_registry

    async def emit(
        self,
        session_key: str,
        event_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Broadcast an event to all WS connections subscribed to ``session_key``.

        Args:
            session_key: The session key to scope the broadcast.
            event_name: Event type (e.g. ``session.event.text_delta``,
                ``sessions.changed``).
            payload: Event payload dict.
        """
        if self._subs is None:
            return

        try:
            await session_event_delivery.deliver_session_event(
                subscription_manager=self._subs,
                connection_registry=self._registry,
                session_key=session_key,
                event_name=event_name,
                payload=payload,
                logger=log,
            )
        except Exception as exc:
            log.debug(
                "event_bridge.emit_failed",
                event_name=event_name,
                error_type=type(exc).__name__,
                error=str(exc),
            )
