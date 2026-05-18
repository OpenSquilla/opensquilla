from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from opensquilla.session import read_service

ROOT = Path(__file__).resolve().parents[2]
READ_SERVICE = ROOT / "src/opensquilla/session/read_service.py"


def _imports_from(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }


class _Runtime:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.calls: list[str | None] = []

    async def list(self, session_key: str | None = None) -> list[Any]:
        self.calls.append(session_key)
        return list(self.rows)


class _Storage:
    def __init__(
        self,
        *,
        rows: dict[str, list[Any]] | None = None,
        sessions: list[Any] | None = None,
    ) -> None:
        self.rows = rows or {}
        self.sessions = sessions or []
        self.list_agent_tasks_calls: list[str | None] = []
        self.list_agent_tasks_for_sessions_calls: list[tuple[str, ...]] = []

    async def list_agent_tasks(self, session_key: str | None = None) -> list[Any]:
        self.list_agent_tasks_calls.append(session_key)
        return list(self.rows.get(session_key or "", []))

    async def list_agent_tasks_for_sessions(self, session_keys: list[str]) -> dict[str, list[Any]]:
        self.list_agent_tasks_for_sessions_calls.append(tuple(session_keys))
        return {key: list(self.rows.get(key, [])) for key in session_keys}

    async def get_session(self, key: str) -> Any | None:
        for session in self.sessions:
            if session.session_key == key:
                return session
        return None

    async def list_sessions(self, limit: int | None = None) -> list[Any]:
        sessions = list(self.sessions)
        if limit is not None:
            return sessions[:limit]
        return sessions


def test_session_read_service_has_no_gateway_dependency() -> None:
    assert READ_SERVICE.is_file()
    assert not any(
        module.startswith("opensquilla.gateway") for module in _imports_from(READ_SERVICE)
    )


@pytest.mark.asyncio
async def test_list_task_rows_prefers_live_runtime_state() -> None:
    runtime_row = SimpleNamespace(task_id="live")
    storage_row = SimpleNamespace(task_id="stored")
    runtime = _Runtime([runtime_row])
    storage = _Storage(rows={"agent:main:one": [storage_row]})

    rows = await read_service.list_task_rows(
        SimpleNamespace(task_runtime=runtime),
        storage,
        "agent:main:one",
    )

    assert rows == [runtime_row]
    assert runtime.calls == ["agent:main:one"]
    assert storage.list_agent_tasks_calls == []


@pytest.mark.asyncio
async def test_list_task_rows_by_session_uses_storage_batch_path() -> None:
    one = SimpleNamespace(task_id="one")
    two = SimpleNamespace(task_id="two")
    storage = _Storage(
        rows={
            "agent:main:one": [one],
            "agent:main:two": [two],
        }
    )
    runtime = _Runtime([])

    rows = await read_service.list_task_rows_by_session(
        SimpleNamespace(task_runtime=runtime),
        storage,
        ["agent:main:one", "agent:main:two"],
    )

    assert rows == {"agent:main:one": [one], "agent:main:two": [two]}
    assert storage.list_agent_tasks_for_sessions_calls == [
        ("agent:main:one", "agent:main:two")
    ]
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_resolve_session_node_preserves_ambiguous_prefix_behavior() -> None:
    storage = _Storage(
        sessions=[
            SimpleNamespace(
                session_key="agent:default:abc123",
                session_id="abc123",
                display_name=None,
                derived_title=None,
            ),
            SimpleNamespace(
                session_key="agent:bench:abc999",
                session_id="abc999",
                display_name=None,
                derived_title=None,
            ),
        ]
    )

    with pytest.raises(ValueError, match="Ambiguous session id 'abc'; matches:"):
        await read_service.resolve_session_node(storage, "abc")
