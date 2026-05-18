"""Session read-query helpers shared by Gateway adapters."""

from __future__ import annotations

from typing import Any

import structlog

from opensquilla.session.keys import canonicalize_session_key

log = structlog.get_logger(__name__)


async def list_task_rows(ctx: Any, storage: Any | None, session_key: str) -> list[Any]:
    task_runtime = getattr(ctx, "task_runtime", None)
    if task_runtime is not None:
        runtime_list = getattr(task_runtime, "list", None)
        if callable(runtime_list):
            try:
                return list(await runtime_list(session_key=session_key))
            except Exception:
                log.warning("sessions.task_runtime_state_failed", session_key=session_key)

    if storage is None:
        return []
    storage_list = getattr(storage, "list_agent_tasks", None)
    if not callable(storage_list):
        return []
    try:
        return list(await storage_list(session_key=session_key))
    except Exception:
        log.warning("sessions.agent_task_storage_state_failed", session_key=session_key)
        return []


async def list_task_rows_by_session(
    ctx: Any,
    storage: Any | None,
    session_keys: list[str],
) -> dict[str, list[Any]]:
    keys = [canonicalize_session_key(key) for key in session_keys]
    if not keys:
        return {}

    if storage is not None:
        storage_batch = getattr(storage, "list_agent_tasks_for_sessions", None)
        if callable(storage_batch):
            try:
                grouped = await storage_batch(keys)
                return {key: list(grouped.get(key, [])) for key in keys}
            except Exception:
                log.warning("sessions.agent_task_storage_batch_state_failed")

    return {key: await list_task_rows(ctx, storage, key) for key in keys}


async def resolve_session_node(storage: Any, key: str) -> Any:
    session = await storage.get_session(key)
    if session is not None:
        return session

    sessions = await storage.list_sessions(limit=500)
    matches: list[Any] = []
    for candidate in sessions:
        values = [
            getattr(candidate, "session_key", ""),
            getattr(candidate, "session_id", ""),
            getattr(candidate, "display_name", "") or "",
            getattr(candidate, "derived_title", "") or "",
        ]
        if any(str(value) == key or str(value).startswith(key) for value in values if value):
            matches.append(candidate)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        candidates = ", ".join(str(getattr(match, "session_key", "")) for match in matches[:5])
        raise ValueError(f"Ambiguous session id {key!r}; matches: {candidates}")
    raise KeyError(f"Session not found: {key}")


__all__ = [
    "list_task_rows",
    "list_task_rows_by_session",
    "resolve_session_node",
]
