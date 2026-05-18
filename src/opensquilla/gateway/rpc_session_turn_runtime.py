"""TaskRuntime enqueue boundary for session RPC sends."""

from __future__ import annotations

from typing import Any

import structlog

from opensquilla.engine.start_turn import start_turn_via_runtime
from opensquilla.gateway.rpc import RpcHandlerError
from opensquilla.session.rpc_payload import (
    session_send_accepted_response,
    session_send_queue_full_details,
    session_send_queue_full_dirty_details,
)

log = structlog.get_logger(__name__)


async def _evict_consumed_uploads(consumed_file_uuids: list[str]) -> None:
    if not consumed_file_uuids:
        return

    from opensquilla.gateway.uploads import get_upload_store

    store = get_upload_store()
    for file_uuid in consumed_file_uuids:
        try:
            await store.evict(file_uuid)
        except Exception:  # noqa: BLE001 - eviction is best-effort
            log.warning("uploads.evict_failed_post_turn uuid=%s", file_uuid[:8])


async def enqueue_session_turn_via_runtime(
    task_runtime: Any,
    *,
    route_envelope: Any,
    message_text: str,
    raw_attachments: list[dict[str, Any]],
    runtime_mode: str | None,
    run_kind: str,
    no_memory_capture: bool,
    semantic_message_text: str,
    session_manager: Any,
    session_key: str,
    persisted_entry: Any,
    consumed_file_uuids: list[str],
) -> dict[str, Any]:
    """Start a session turn through TaskRuntime and translate enqueue failures."""
    try:
        handle = await start_turn_via_runtime(
            task_runtime,
            route_envelope,
            message_text,
            attachments=raw_attachments,
            mode=runtime_mode,
            run_kind=run_kind,
            no_memory_capture=no_memory_capture,
            semantic_message=semantic_message_text,
        )
    except Exception as exc:
        from opensquilla.gateway.task_runtime import TaskQueueFullError

        if not isinstance(exc, TaskQueueFullError):
            raise

        orphan_id = getattr(persisted_entry, "message_id", None)
        rollback_ok = False
        if orphan_id and hasattr(session_manager, "remove_message"):
            try:
                rollback_ok = await session_manager.remove_message(session_key, orphan_id)
            except Exception as rb_exc:  # noqa: BLE001 - rollback is best-effort
                log.warning(
                    "sessions.send.rollback_failed",
                    session_key=session_key,
                    message_id=orphan_id,
                    error=str(rb_exc),
                )
                rollback_ok = False

        if rollback_ok:
            raise RpcHandlerError(
                "QUEUE_FULL",
                "The session task queue is full. Try again after queued work completes.",
                details=session_send_queue_full_details(
                    session_key=exc.session_key,
                    max_pending=exc.max_pending,
                    rollback_message_id=orphan_id,
                ),
                retryable=True,
            ) from exc
        raise RpcHandlerError(
            "QUEUE_FULL_DIRTY",
            (
                "The session task queue is full and the just-appended user "
                "turn could not be rolled back. The transcript now contains "
                "an orphan message; clients must dedup by orphan_message_id "
                "before retrying."
            ),
            details=session_send_queue_full_dirty_details(
                session_key=exc.session_key,
                max_pending=exc.max_pending,
                orphan_message_id=orphan_id,
            ),
            retryable=False,
        ) from exc

    await _evict_consumed_uploads(consumed_file_uuids)
    return session_send_accepted_response(session_key, task_id=handle.task_id)
