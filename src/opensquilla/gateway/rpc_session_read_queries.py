"""Gateway session read/query RPC handlers."""

from __future__ import annotations

import time

from opensquilla.gateway import rpc_session_events as _session_events
from opensquilla.gateway.rpc import RpcContext
from opensquilla.gateway.session_streams import get_session_streams
from opensquilla.session.keys import canonicalize_session_key
from opensquilla.session.management_service import require_session_key
from opensquilla.session.read_service import (
    list_task_rows,
    list_task_rows_by_session,
    resolve_session_node,
)
from opensquilla.session.rpc_payload import (
    messages_subscribe_response,
    session_list_response,
    session_list_row,
    session_preview_response,
    session_preview_row,
    session_resolve_response,
)
from opensquilla.session.services import get_session_storage


async def handle_sessions_list(params: dict | None, ctx: RpcContext) -> dict:
    """List all sessions."""
    now_ms = int(time.time() * 1000)

    if ctx.session_manager is None:
        return session_list_response(now_ms, [])

    storage = get_session_storage(ctx.session_manager)
    if storage is None:
        return session_list_response(now_ms, [])

    limit = (params or {}).get("limit", 50)
    sessions = await storage.list_sessions(limit=limit)
    task_rows_by_session = await list_task_rows_by_session(
        ctx,
        storage,
        [s.session_key for s in sessions],
    )

    result = []
    for s in sessions:
        entry_count = 0
        try:
            entry_count = await storage.count_transcript_entries(s.session_id)
        except Exception:
            pass

        task_rows = task_rows_by_session.get(canonicalize_session_key(s.session_key), [])
        result.append(
            session_list_row(
                s,
                entry_count=entry_count,
                task_rows=task_rows,
                now_ms=now_ms,
            )
        )

    return session_list_response(now_ms, result)


async def handle_sessions_subscribe(params: dict | None, ctx: RpcContext) -> None:
    subscription_mgr = getattr(ctx, "subscription_manager", None)
    if subscription_mgr is not None:
        subscription_mgr.subscribe_sessions(ctx.conn_id)
    return None


async def handle_sessions_unsubscribe(params: dict | None, ctx: RpcContext) -> None:
    subscription_mgr = getattr(ctx, "subscription_manager", None)
    if subscription_mgr is not None:
        subscription_mgr.unsubscribe_sessions(ctx.conn_id)
    return None


async def handle_sessions_messages_subscribe(params: dict | None, ctx: RpcContext) -> dict:
    key = require_session_key(params)
    subscription_mgr = getattr(ctx, "subscription_manager", None)
    if subscription_mgr is not None:
        subscription_mgr.subscribe_messages(ctx.conn_id, key)

    replay = get_session_streams().replay(key, _session_events.optional_stream_seq(params))
    replayed_count = 0
    if subscription_mgr is not None and replay.events:
        from opensquilla.gateway.websocket import get_registry

        conn = get_registry().get(ctx.conn_id)
        if conn is not None:
            for event in replay.events:
                await conn.send_event(event.event_name, event.payload)
                replayed_count += 1

    storage = get_session_storage(getattr(ctx, "session_manager", None))
    task_rows = await list_task_rows(ctx, storage, key)
    return messages_subscribe_response(
        key=key,
        subscribed=subscription_mgr is not None,
        replay=replay,
        replayed_count=replayed_count,
        task_rows=task_rows,
    )


async def handle_sessions_messages_unsubscribe(params: dict | None, ctx: RpcContext) -> None:
    key = require_session_key(params)
    subscription_mgr = getattr(ctx, "subscription_manager", None)
    if subscription_mgr is not None:
        subscription_mgr.unsubscribe_messages(ctx.conn_id, key)
    return None


async def handle_sessions_preview(params: dict | None, ctx: RpcContext) -> dict:
    keys = (params or {}).get("keys")
    limit = (params or {}).get("limit", 50)
    now_ms = int(time.time() * 1000)

    if ctx.session_manager is None:
        return session_preview_response(now_ms, [])

    storage = get_session_storage(ctx.session_manager)
    if storage is None:
        return session_preview_response(now_ms, [])

    if keys:
        sessions = []
        for k in keys:
            s = await storage.get_session(k)
            if s is not None:
                sessions.append(s)
    else:
        sessions = await storage.list_sessions(limit=limit)

    previews = []
    for s in sessions:
        transcript = []
        try:
            transcript = await storage.get_transcript(s.session_id, limit=-1)
        except Exception:
            pass
        previews.append(session_preview_row(s, transcript=transcript, now_ms=now_ms))

    return session_preview_response(now_ms, previews)


async def handle_sessions_resolve(params: dict | None, ctx: RpcContext) -> dict:
    key = require_session_key(params)

    if ctx.session_manager is None:
        raise KeyError("No session manager available")

    storage = get_session_storage(ctx.session_manager)
    if storage is None:
        raise KeyError("No session storage available")

    session = await resolve_session_node(storage, key)

    return session_resolve_response(session)
