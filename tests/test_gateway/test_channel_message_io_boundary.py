from __future__ import annotations

import base64
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from opensquilla.channels.types import Attachment, IncomingMessage


def test_channel_message_io_exports_expected_boundary_helpers() -> None:
    from opensquilla.gateway import channel_message_io

    expected = {
        "materialize_channel_attachments",
        "ingest_channel_message_attachments",
        "append_channel_user_message",
        "latest_assistant_text_after",
        "transcript_watermark",
        "read_transcript_rows",
        "dump_attachment",
    }

    for name in expected:
        assert hasattr(channel_message_io, name), f"missing {name}"


def test_channel_dispatch_preserves_private_compatibility_aliases() -> None:
    from opensquilla.gateway import channel_dispatch, channel_message_io

    assert (
        channel_dispatch._materialize_channel_attachments
        is channel_message_io.materialize_channel_attachments
    )
    assert (
        channel_dispatch._ingest_channel_message_attachments
        is channel_message_io.ingest_channel_message_attachments
    )
    assert (
        channel_dispatch._append_channel_user_message
        is channel_message_io.append_channel_user_message
    )
    assert channel_dispatch._transcript_watermark is channel_message_io.transcript_watermark
    assert channel_dispatch._read_transcript_rows is channel_message_io.read_transcript_rows
    assert (
        channel_dispatch._latest_assistant_text_after
        is channel_message_io.latest_assistant_text_after
    )
    assert channel_dispatch._dump_attachment is channel_message_io.dump_attachment


def test_channel_dispatch_no_longer_owns_message_io_helper_definitions() -> None:
    import opensquilla.gateway.channel_dispatch as channel_dispatch

    source = inspect.getsource(channel_dispatch)

    moved_definitions = [
        "async def _read_transcript_rows(",
        "async def _transcript_watermark(",
        "def _dump_attachment(",
        "async def _materialize_channel_attachments(",
        "async def _ingest_channel_message_attachments(",
        "async def _append_channel_user_message(",
        "async def _latest_assistant_text_after(",
    ]
    for definition in moved_definitions:
        assert definition not in source


@pytest.mark.asyncio
async def test_materialized_attachment_resolution_matches_dispatch_behavior() -> None:
    from opensquilla.gateway.channel_message_io import ingest_channel_message_attachments

    class ResolvingChannel:
        channel_id = "test"

        async def resolve_inbound_attachment(self, attachment: Attachment) -> Attachment:
            return Attachment(
                name=attachment.name,
                mime_type=attachment.mime_type,
                data=b"hello",
                size=5,
            )

    msg = IncomingMessage(
        sender_id="u1",
        channel_id="c1",
        content="read",
        attachments=[
            Attachment(
                name="note.txt",
                mime_type="text/plain",
                url="https://example.test/note.txt",
            )
        ],
    )

    result = await ingest_channel_message_attachments(channel=ResolvingChannel(), msg=msg)

    assert result.text == "read"
    assert result.failures == []
    assert result.attachments == [
        {
            "name": "note.txt",
            "type": "text/plain",
            "data": base64.b64encode(b"hello").decode("ascii"),
            "_was_staged": True,
        }
    ]


class _RecordingSessionManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def stamp_user_text(self, text: str) -> str:
        return f"[user] {text}"

    async def append_message(self, session_key: str, *, role: str, content: Any) -> Any:
        self.calls.append({"session_key": session_key, "role": role, "content": content})
        return SimpleNamespace(content=content)


@pytest.mark.asyncio
async def test_append_channel_user_message_preserves_persisted_attachment_envelope(
    tmp_path: Path,
) -> None:
    from opensquilla.gateway.channel_message_io import append_channel_user_message

    manager = _RecordingSessionManager()
    attachment = {
        "name": "note.txt",
        "type": "text/plain",
        "data": base64.b64encode(b"hello").decode("ascii"),
        "_was_staged": True,
    }
    config = SimpleNamespace(
        attachments=SimpleNamespace(
            media_root=str(tmp_path),
            persist_transcripts=True,
            transcript_disk_budget_bytes=None,
        )
    )

    persisted, persisted_content = await append_channel_user_message(
        session_manager=manager,
        session_key="agent:main:session-1",
        text="read this",
        attachments=[attachment],
        config=config,
    )

    assert persisted is not None
    assert persisted_content == "[user] read this"
    assert manager.calls[-1]["role"] == "user"
    envelope = json.loads(manager.calls[-1]["content"])
    assert envelope["text"] == "[user] read this"
    assert envelope["attachments"] == [
        {
            "sha256_ref": envelope["attachments"][0]["sha256_ref"],
            "name": "note.txt",
            "mime": "text/plain",
            "size": 5,
        }
    ]
    material_path = (
        tmp_path / "transcripts" / "session-1" / envelope["attachments"][0]["sha256_ref"]
    )
    assert material_path.read_bytes() == b"hello"
