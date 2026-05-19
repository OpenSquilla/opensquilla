"""Memory source inspection helpers used by adapter surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from opensquilla.memory.source_paths import is_memory_archive_path, is_memory_source_path

MEMORY_SOURCE_MAX_SHOW_CHARS: Final[int] = 8000
MEMORY_SOURCE_MAX_SHOW_LINES: Final[int] = 500
MEMORY_SOURCE_MAX_SHOW_FILE_BYTES: Final[int] = 1024 * 1024


class MemorySourceInspectionError(ValueError):
    """Raised when a memory source inspection request is invalid."""


class MemorySourceNotFoundError(KeyError):
    """Raised when a validated memory source path does not exist."""


@dataclass(frozen=True, slots=True)
class MemorySourceRow:
    path: str
    size_bytes: int
    modified_at: str
    line_count: int


@dataclass(frozen=True, slots=True)
class MemorySourceContent:
    path: str
    from_line: int
    line_count: int
    truncated: bool
    content: str


def list_memory_source_rows(root: str | Path) -> list[MemorySourceRow]:
    resolved_root = Path(root).resolve()
    candidates: list[Path] = []
    memory_md = resolved_root / "MEMORY.md"
    if memory_md.is_file():
        candidates.append(memory_md)
    memory_dir = resolved_root / "memory"
    if memory_dir.is_dir():
        candidates.extend(path for path in memory_dir.rglob("*.md") if path.is_file())

    rows: list[MemorySourceRow] = []
    seen: set[str] = set()
    for file_path in candidates:
        try:
            resolved_file = file_path.resolve()
            rel = resolved_file.relative_to(resolved_root).as_posix()
        except ValueError:
            continue
        if rel in seen or not is_memory_source_path(rel, allow_archive=False):
            continue
        stat = resolved_file.stat()
        with resolved_file.open("r", encoding="utf-8", errors="replace") as handle:
            line_count = sum(1 for _ in handle)
        seen.add(rel)
        rows.append(
            MemorySourceRow(
                path=rel,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                line_count=line_count,
            )
        )
    return sorted(rows, key=lambda row: row.path)


def read_memory_source_content(
    root: str | Path,
    path: str,
    *,
    from_line: int | None = None,
    lines: int | None = None,
    allow_archive: bool = False,
    max_chars: int = MEMORY_SOURCE_MAX_SHOW_CHARS,
    max_file_bytes: int = MEMORY_SOURCE_MAX_SHOW_FILE_BYTES,
) -> MemorySourceContent:
    file_path = _validated_memory_source_path(root, path, allow_archive=allow_archive)
    if not file_path.is_file():
        raise MemorySourceNotFoundError(f"Memory source not found: {path}")

    if from_line is None and lines is None and file_path.stat().st_size > max_file_bytes:
        raise MemorySourceInspectionError("memory source is too large; request a line slice")

    content, selected_line_count, truncated = _read_memory_content(
        file_path,
        from_line=from_line,
        lines=lines,
        max_chars=max_chars,
    )

    return MemorySourceContent(
        path=path,
        from_line=int(from_line or 1),
        line_count=selected_line_count,
        truncated=truncated,
        content=content,
    )


def _validated_memory_source_path(
    root: str | Path,
    path: str,
    *,
    allow_archive: bool,
) -> Path:
    if not path.strip():
        raise MemorySourceInspectionError("params.path is required")
    if is_memory_archive_path(path) and not allow_archive:
        raise MemorySourceInspectionError("memory archive is private turn-capture storage")
    if not is_memory_source_path(path, allow_archive=allow_archive):
        raise MemorySourceInspectionError("params.path must be MEMORY.md or memory/*.md")

    resolved_root = Path(root).resolve()
    file_path = (resolved_root / path).resolve()
    try:
        file_path.relative_to(resolved_root)
    except ValueError as exc:
        raise MemorySourceInspectionError("path traversal is not allowed") from exc
    return file_path


def _read_memory_content(
    file_path: Path,
    *,
    from_line: int | None,
    lines: int | None,
    max_chars: int,
) -> tuple[str, int, bool]:
    if from_line is None and lines is None:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return (
            content[:max_chars],
            len(content.splitlines()),
            len(content) > max_chars,
        )

    start_line = int(from_line or 1)
    max_lines = int(lines) if lines is not None else None
    parts: list[str] = []
    char_count = 0
    selected_line_count = 0
    truncated = False

    with file_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            if line_no < start_line:
                continue
            if max_lines is not None and selected_line_count >= max_lines:
                break
            if char_count >= max_chars:
                truncated = True
                break

            text = line.rstrip("\r\n")
            piece = text if selected_line_count == 0 else f"\n{text}"
            remaining = max_chars - char_count
            if len(piece) > remaining:
                if remaining > 0:
                    parts.append(piece[:remaining])
                    selected_line_count += 1
                truncated = True
                break

            parts.append(piece)
            char_count += len(piece)
            selected_line_count += 1

    return "".join(parts), selected_line_count, truncated
