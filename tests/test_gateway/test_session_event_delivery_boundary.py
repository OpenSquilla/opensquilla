from __future__ import annotations

from typing import Any

import pytest

from opensquilla.gateway.event_bridge import EventBridge
from opensquilla.gateway.session_event_delivery import (
    buffer_session_event,
    deliver_session_event,
)
from opensquilla.gateway.session_streams import SessionStreamRegistry


class _FakeConn:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def send_event(self, event_name: str, payload: dict[str, Any]) -> None:
        self.events.append((event_name, payload))


class _FakeRegistry:
    def __init__(self, conns: dict[str, _FakeConn]) -> None:
        self._conns = conns

    def get(self, conn_id: str) -> _FakeConn | None:
        return self._conns.get(conn_id)


class _FakeSubMgr:
    def __init__(self, *, message_ids: set[str], session_ids: set[str] | None = None) -> None:
        self._message_ids = message_ids
        self._session_ids = session_ids or set()

    def get_message_subscribers(self, session_key: str) -> set[str]:
        return set(self._message_ids) if session_key == "agent:main:event-boundary" else set()

    def get_session_subscribers(self) -> set[str]:
        return set(self._session_ids)


def test_buffer_session_event_records_only_session_events_with_session_key_and_stream_seq() -> None:
    registry = SessionStreamRegistry(max_events_per_session=5)
    key = "agent:main:event-boundary"

    session_payload = buffer_session_event(
        key,
        "session.event.text_delta",
        {"text": "hello"},
        stream_registry=registry,
    )
    changed_payload = buffer_session_event(
        key,
        "sessions.changed",
        {"reason": "turn_complete"},
        stream_registry=registry,
    )

    assert session_payload == {"text": "hello", "session_key": key, "stream_seq": 1}
    assert changed_payload == {"reason": "turn_complete"}
    assert registry.current_seq(key) == 1


@pytest.mark.asyncio
async def test_deliver_session_event_buffers_session_events_for_message_subscribers() -> None:
    key = "agent:main:event-boundary"
    message_conn = _FakeConn()
    session_conn = _FakeConn()
    registry = SessionStreamRegistry(max_events_per_session=5)

    await deliver_session_event(
        subscription_manager=_FakeSubMgr(
            message_ids={"message-conn"},
            session_ids={"session-conn"},
        ),
        connection_registry=_FakeRegistry(
            {"message-conn": message_conn, "session-conn": session_conn}
        ),
        session_key=key,
        event_name="session.event.done",
        payload={"reason": "stop"},
        stream_registry=registry,
    )

    assert message_conn.events == [
        (
            "session.event.done",
            {"reason": "stop", "session_key": key, "stream_seq": 1},
        )
    ]
    assert session_conn.events == []
    assert registry.current_seq(key) == 1


@pytest.mark.asyncio
async def test_deliver_session_event_sends_sessions_changed_to_both_subscriber_groups() -> None:
    key = "agent:main:event-boundary"
    message_conn = _FakeConn()
    session_conn = _FakeConn()
    registry = SessionStreamRegistry(max_events_per_session=5)

    await deliver_session_event(
        subscription_manager=_FakeSubMgr(
            message_ids={"message-conn"},
            session_ids={"session-conn"},
        ),
        connection_registry=_FakeRegistry(
            {"message-conn": message_conn, "session-conn": session_conn}
        ),
        session_key=key,
        event_name="sessions.changed",
        payload={"key": key, "reason": "turn_complete"},
        stream_registry=registry,
    )

    expected = ("sessions.changed", {"key": key, "reason": "turn_complete"})
    assert message_conn.events == [expected]
    assert session_conn.events == [expected]
    assert registry.current_seq(key) == 0


@pytest.mark.asyncio
async def test_event_bridge_emit_delegates_to_shared_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_deliver_session_event(**kwargs: Any) -> None:
        calls.append(kwargs)

    import opensquilla.gateway.session_event_delivery as delivery

    monkeypatch.setattr(delivery, "deliver_session_event", fake_deliver_session_event)

    subs = _FakeSubMgr(message_ids={"message-conn"})
    registry = _FakeRegistry({"message-conn": _FakeConn()})
    bridge = EventBridge(subs, registry)

    await bridge.emit(
        "agent:main:event-boundary",
        "session.event.text_delta",
        {"text": "hello"},
    )

    assert len(calls) == 1
    assert calls[0]["subscription_manager"] is subs
    assert calls[0]["connection_registry"] is registry
    assert calls[0]["session_key"] == "agent:main:event-boundary"
    assert calls[0]["event_name"] == "session.event.text_delta"
    assert calls[0]["payload"] == {"text": "hello"}
