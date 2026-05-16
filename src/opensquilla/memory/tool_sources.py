"""Memory source read/delete operations used by memory tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opensquilla.memory.runtime import ResolvedMemoryAgent
from opensquilla.memory.source_paths import (
    is_memory_archive_path,
    is_memory_source_path,
    private_archive_error,
)

_MEMORY_GET_MAX_CHARS = 8000


class MemorySourceError(RuntimeError):
    """Raised when a memory source operation should return a tool-facing error."""


def read_memory_source(
    agent: ResolvedMemoryAgent,
    path: str,
    *,
    from_line: int | None = None,
    lines: int | None = None,
    allow_archive: bool = False,
    max_chars: int = _MEMORY_GET_MAX_CHARS,
) -> str:
    file_path = _validated_source_path(agent, path, allow_archive=allow_archive)
    if not file_path.exists():
        raise MemorySourceError(f"Error: {path} not found.")

    content = file_path.read_text(encoding="utf-8", errors="replace")
    if from_line is not None or lines is not None:
        all_lines = content.splitlines()
        start = max(0, (from_line - 1)) if from_line else 0
        end = (start + lines) if lines else len(all_lines)
        content = "\n".join(all_lines[start:end])
    full_len = len(content)
    if full_len > max_chars:
        return content[:max_chars] + f"\n\n... (truncated: showing {max_chars}/{full_len} chars)"
    return content


async def delete_memory_source(
    agent: ResolvedMemoryAgent,
    path: str,
    *,
    allow_archive: bool = False,
) -> str:
    file_path = _validated_source_path(agent, path, allow_archive=allow_archive)
    if not file_path.exists():
        raise MemorySourceError(f"Error: {path} not found.")

    workspace_dir = _workspace_path(agent)
    file_path.unlink()
    index_path = file_path.resolve().relative_to(workspace_dir.resolve()).as_posix()
    await _store_remove_file(agent.store, index_path)
    return index_path


def _validated_source_path(
    agent: ResolvedMemoryAgent,
    path: str,
    *,
    allow_archive: bool,
) -> Path:
    workspace_dir = _workspace_path(agent)
    file_path = workspace_dir / path
    try:
        file_path.resolve().relative_to(workspace_dir.resolve())
    except ValueError as exc:
        raise MemorySourceError("Error: path traversal not allowed.") from exc

    if is_memory_archive_path(path) and not allow_archive:
        raise MemorySourceError(private_archive_error())
    if not is_memory_source_path(path, allow_archive=allow_archive):
        raise MemorySourceError(
            "Error: path is not a memory source file. Use MEMORY.md or memory/*.md."
        )
    return file_path


def _workspace_path(agent: ResolvedMemoryAgent) -> Path:
    if not agent.workspace_dir:
        raise MemorySourceError("Error: workspace directory not configured.")
    return Path(agent.workspace_dir)


async def _store_remove_file(store: Any, path: str) -> None:
    await store.remove_file(path)
