"""Session-domain persistence facade over low-level storage."""

from __future__ import annotations

from opensquilla.session.models import SessionNode, SessionSummary, TranscriptEntry
from opensquilla.session.storage import SessionStorage


class SessionPersistenceRepository:
    """Repository boundary for session rows, transcripts, and summaries.

    The repository deliberately delegates to ``SessionStorage`` for SQLite
    schema, migrations, transactions, and serialization. It gives higher-level
    session services a domain-named persistence boundary without changing
    durable row shape or public session-key behavior.
    """

    def __init__(self, storage: SessionStorage) -> None:
        self._storage = storage

    async def save_session(self, node: SessionNode) -> None:
        await self._storage.upsert_session(node)

    async def get_session(self, session_key: str) -> SessionNode | None:
        return await self._storage.get_session(session_key)

    async def list_sessions(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
        spawned_by: str | None = None,
    ) -> list[SessionNode]:
        return await self._storage.list_sessions(
            agent_id=agent_id,
            status=status,
            limit=limit,
            offset=offset,
            spawned_by=spawned_by,
        )

    async def delete_session(self, session_key: str) -> None:
        await self._storage.delete_session(session_key)

    async def prune_stale_sessions(self, before_ms: int) -> int:
        return await self._storage.prune_stale_sessions(before_ms)

    async def count_sessions(self) -> int:
        return await self._storage.count_sessions()

    async def append_transcript_entry(
        self,
        entry: TranscriptEntry,
        *,
        expected_epoch: int | None = None,
    ) -> None:
        await self._storage.append_transcript_entry(entry, expected_epoch=expected_epoch)

    async def get_transcript(
        self,
        session_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TranscriptEntry]:
        return await self._storage.get_transcript(session_id, limit=limit, offset=offset)

    async def count_transcript_entries(self, session_id: str) -> int:
        return await self._storage.count_transcript_entries(session_id)

    async def delete_transcript(self, session_id: str) -> None:
        await self._storage.delete_transcript(session_id)

    async def delete_transcript_entry(self, session_id: str, message_id: str) -> bool:
        return await self._storage.delete_transcript_entry(session_id, message_id)

    async def get_recent_transcript(self, session_id: str, n: int) -> list[TranscriptEntry]:
        return await self._storage.get_recent_transcript(session_id, n)

    async def save_summary(self, summary: SessionSummary) -> SessionSummary:
        return await self._storage.save_summary(summary)

    async def delete_summaries(self, session_id: str) -> None:
        await self._storage.delete_summaries(session_id)

    async def get_all_summaries(self, session_id: str) -> list[SessionSummary]:
        return await self._storage.get_all_summaries(session_id)

    async def rewrite_compacted_session(
        self,
        *,
        node: SessionNode,
        summary: SessionSummary | None,
        entries: list[TranscriptEntry],
    ) -> None:
        await self._storage.rewrite_compacted_session(
            node=node,
            summary=summary,
            entries=entries,
        )
