from __future__ import annotations

import pytest

from opensquilla.memory.sync_manager import MemorySyncManager


class NoopStore:
    def __init__(self) -> None:
        self.indexed: list[str] = []
        self.removed: list[str] = []

    async def index_file(self, *, path: str, content: str, source: object) -> int:
        self.indexed.append(path)
        return 1

    async def remove_file(self, path: str) -> None:
        self.removed.append(path)
        return None


def test_sync_manager_scans_archive_as_curated_memory_subdir(tmp_path):
    workspace = tmp_path / "workspace"
    memory = workspace / "memory"
    archive = memory / "archive"
    hidden = memory / ".private"
    archive.mkdir(parents=True)
    hidden.mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("root\n", encoding="utf-8")
    (memory / "a.md").write_text("a\n", encoding="utf-8")
    (memory / ".hidden.md").write_text("hidden file\n", encoding="utf-8")
    (archive / "x.md").write_text("archive is curated if user-created\n", encoding="utf-8")
    (hidden / "x.md").write_text("hidden\n", encoding="utf-8")

    manager = MemorySyncManager(
        store=NoopStore(),
        workspace_dir=workspace,
        memory_dir=memory,
    )

    assert sorted(manager._scan_files()) == [
        "MEMORY.md",
        "memory/a.md",
        "memory/archive/x.md",
    ]


@pytest.mark.asyncio
async def test_sync_force_rescans_unchanged_memory_sources(tmp_path):
    workspace = tmp_path / "workspace"
    memory = workspace / "memory"
    memory.mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("root\n", encoding="utf-8")
    (memory / "a.md").write_text("a\n", encoding="utf-8")
    store = NoopStore()
    manager = MemorySyncManager(store=store, workspace_dir=workspace, memory_dir=memory)

    await manager.sync(reason="manual")
    first_indexed = list(store.indexed)
    await manager.sync(reason="manual")
    second_indexed = store.indexed[len(first_indexed) :]
    await manager.sync(reason="manual", force=True)
    forced_indexed = store.indexed[len(first_indexed) + len(second_indexed) :]

    assert sorted(first_indexed) == ["MEMORY.md", "memory/a.md"]
    assert second_indexed == []
    assert sorted(forced_indexed) == ["MEMORY.md", "memory/a.md"]


@pytest.mark.asyncio
async def test_sync_force_overrides_search_clean_fast_path(tmp_path):
    workspace = tmp_path / "workspace"
    memory = workspace / "memory"
    memory.mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("root\n", encoding="utf-8")
    store = NoopStore()
    manager = MemorySyncManager(store=store, workspace_dir=workspace, memory_dir=memory)

    await manager.sync(reason="manual")
    first_count = len(store.indexed)
    sync_calls: list[dict[str, object]] = []

    async def fake_do_file_sync(**kwargs: object) -> set[str]:
        sync_calls.append(kwargs)
        return set()

    manager._do_file_sync = fake_do_file_sync  # type: ignore[method-assign]
    await manager.sync(reason="search")
    await manager.sync(reason="search:tool")
    await manager.sync(reason="search:admin")
    search_count = len(store.indexed)
    await manager.sync(reason="search:tool", force=True)

    assert first_count == 1
    assert search_count == first_count
    assert sync_calls == [{"force": True}]
