"""Channel message attachment and transcript IO helpers."""

from __future__ import annotations

import inspect
from typing import Any

import structlog

from opensquilla.channels.types import IncomingMessage
from opensquilla.gateway.attachment_ingest import AttachmentIngestResult, ingest_attachments
from opensquilla.paths import media_root_from_config

log = structlog.get_logger(__name__)


async def read_transcript_rows(session_manager: Any, session_key: str) -> list[Any]:
    read_transcript = getattr(session_manager, "read_transcript", None)
    if not callable(read_transcript):
        return []
    try:
        rows = await read_transcript(session_key)
    except Exception:
        log.warning("channel_dispatch.read_transcript_failed", session_key=session_key)
        return []
    return list(rows or [])


async def transcript_watermark(session_manager: Any, session_key: str) -> int:
    return len(await read_transcript_rows(session_manager, session_key))


def dump_attachment(attachment: Any) -> dict[str, Any] | None:
    if isinstance(attachment, dict):
        return dict(attachment)
    model_dump = getattr(attachment, "model_dump", None)
    if callable(model_dump):
        # Keep Pydantic's Python-mode default so bytes remain bytes for shared ingest.
        dumped = model_dump()
        return dict(dumped) if isinstance(dumped, dict) else None
    return None


async def materialize_channel_attachments(channel: Any, attachments: list[Any]) -> list[Any]:
    resolver = getattr(channel, "resolve_inbound_attachment", None)
    if not callable(resolver):
        return list(attachments or [])

    materialized: list[Any] = []
    for attachment in attachments or []:
        try:
            resolved = resolver(attachment)
            if inspect.isawaitable(resolved):
                resolved = await resolved
            materialized.append(resolved if resolved is not None else attachment)
        except Exception as exc:  # noqa: BLE001 - failure degrades via shared ingest marker
            item = dump_attachment(attachment) or {"name": "attachment"}
            item["_ingest_error"] = str(exc)
            materialized.append(item)
    return materialized


async def ingest_channel_message_attachments(
    *,
    channel: Any,
    msg: IncomingMessage,
) -> AttachmentIngestResult:
    materialized = await materialize_channel_attachments(
        channel,
        list(getattr(msg, "attachments", []) or []),
    )
    result = await ingest_attachments(
        msg.content,
        materialized,
        failure_mode="mark",
        mark_bytes_as_staged=True,
    )
    for failure in result.failures:
        log.warning(
            "channel.attachment_ingest_failed",
            channel=getattr(channel, "channel_id", None) or type(channel).__name__,
            attachment_index=failure.index,
            attachment_name=failure.name,
            reason=failure.reason,
            detail=failure.detail,
        )
    return result


async def append_channel_user_message(
    *,
    session_manager: Any,
    session_key: str,
    text: str,
    attachments: list[dict[str, Any]],
    config: Any,
) -> tuple[Any, str]:
    if attachments:
        from opensquilla.gateway.transcripts import build_transcript_attachment_envelope

        stamped_text = text
        if hasattr(session_manager, "stamp_user_text"):
            stamped = session_manager.stamp_user_text(text)
            if isinstance(stamped, str):
                stamped_text = stamped

        attachments_cfg = getattr(config, "attachments", None)
        persist_enabled = bool(getattr(attachments_cfg, "persist_transcripts", True))
        media_root = media_root_from_config(config)
        disk_budget = getattr(attachments_cfg, "transcript_disk_budget_bytes", None)
        session_id = session_key.split(":")[-1] or session_key
        envelope, _writes = build_transcript_attachment_envelope(
            text=stamped_text,
            attachments=attachments,
            session_id=session_id,
            media_root=media_root,
            persist_enabled=persist_enabled,
            disk_budget_bytes=disk_budget if isinstance(disk_budget, int) else None,
        )
        persisted = await session_manager.append_message(session_key, role="user", content=envelope)
        return persisted, stamped_text

    persisted = await session_manager.append_message(session_key, role="user", content=text)
    if persisted is not None and isinstance(persisted.content, str):
        return persisted, persisted.content
    return persisted, text


async def latest_assistant_text_after(
    session_manager: Any,
    session_key: str,
    start_index: int,
) -> str:
    rows = await read_transcript_rows(session_manager, session_key)
    for row in reversed(rows[start_index:]):
        role = row.get("role") if isinstance(row, dict) else getattr(row, "role", None)
        content = row.get("content") if isinstance(row, dict) else getattr(row, "content", None)
        if role == "assistant" and isinstance(content, str) and content:
            return content
    return ""
