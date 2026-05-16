from __future__ import annotations

import pytest

from opensquilla.memory.source_inspection import (
    MEMORY_SOURCE_MAX_SHOW_CHARS,
    MemorySourceInspectionError,
    MemorySourceNotFoundError,
    list_memory_source_rows,
    read_memory_source_content,
)


def test_list_memory_source_rows_returns_public_sources_only(tmp_path) -> None:
    (tmp_path / "MEMORY.md").write_text("root\n", encoding="utf-8")
    memory_dir = tmp_path / "memory"
    archive_dir = memory_dir / "archive"
    hidden_dir = memory_dir / ".private"
    archive_dir.mkdir(parents=True)
    hidden_dir.mkdir(parents=True)
    (memory_dir / "a.md").write_text("one\ntwo\n", encoding="utf-8")
    (archive_dir / "x.md").write_text("private\n", encoding="utf-8")
    (hidden_dir / "x.md").write_text("hidden\n", encoding="utf-8")

    rows = list_memory_source_rows(tmp_path)

    assert [row.path for row in rows] == ["MEMORY.md", "memory/a.md"]
    assert rows[1].line_count == 2
    assert rows[1].size_bytes > 0
    assert rows[1].modified_at.endswith("+00:00")


def test_read_memory_source_content_returns_line_slices(tmp_path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "a.md").write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = read_memory_source_content(tmp_path, "memory/a.md", from_line=2, lines=1)

    assert result.path == "memory/a.md"
    assert result.from_line == 2
    assert result.line_count == 1
    assert result.truncated is False
    assert result.content == "two"


def test_read_memory_source_content_truncates_long_content(tmp_path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "long.md").write_text("x" * (MEMORY_SOURCE_MAX_SHOW_CHARS + 1), encoding="utf-8")

    result = read_memory_source_content(tmp_path, "memory/long.md")

    assert result.truncated is True
    assert len(result.content) == MEMORY_SOURCE_MAX_SHOW_CHARS


def test_read_memory_source_content_rejects_invalid_and_missing_sources(tmp_path) -> None:
    memory_dir = tmp_path / "memory" / "archive"
    memory_dir.mkdir(parents=True)
    (memory_dir / "x.md").write_text("private", encoding="utf-8")

    with pytest.raises(MemorySourceInspectionError, match="memory archive"):
        read_memory_source_content(tmp_path, "memory/archive/x.md")
    with pytest.raises(MemorySourceInspectionError, match="MEMORY.md"):
        read_memory_source_content(tmp_path, "../secret.md")
    with pytest.raises(MemorySourceNotFoundError, match="not found"):
        read_memory_source_content(tmp_path, "memory/missing.md")


def test_read_memory_source_content_allows_archive_when_configured(tmp_path) -> None:
    archive_dir = tmp_path / "memory" / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "x.md").write_text("private", encoding="utf-8")

    result = read_memory_source_content(tmp_path, "memory/archive/x.md", allow_archive=True)

    assert result.content == "private"
