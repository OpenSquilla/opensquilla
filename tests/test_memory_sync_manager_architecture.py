from __future__ import annotations

from opensquilla.memory.sync_manager import MemorySyncManager


class NoopStore:
    async def index_file(self, *, path: str, content: str, source: object) -> int:
        return 1

    async def remove_file(self, path: str) -> None:
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
