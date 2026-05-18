"""LockedFileHistory serializes concurrent writers.

FileHistory.store_string opens, writes, and closes the
history file per call. With multiple writers (input task + auxiliary
prompts) we need a single-writer guard so distinct entries do not
interleave bytes in the file.
"""

from __future__ import annotations

import threading
from pathlib import Path

from prompt_toolkit.history import FileHistory

from opensquilla.cli.repl.app import LockedFileHistory


def test_locked_file_history_is_file_history_subclass() -> None:
    assert issubclass(LockedFileHistory, FileHistory)


def test_locked_file_history_owns_write_lock(tmp_path: Path) -> None:
    history = LockedFileHistory(str(tmp_path / "h"))
    assert isinstance(history._write_lock, type(threading.Lock()))


def test_concurrent_history_writes_dont_interleave(tmp_path: Path) -> None:
    """20 threads write distinct sentinel strings; assert every line is one
    complete sentinel.

    FileHistory stores entries as a `# YYYY-MM-DD HH:MM:SS.ffffff` timestamp
    line followed by one `+<text>` line per entry continuation. We assert the
    `+<sentinel>` lines exist for every sentinel and that none of them are
    truncated or fused with another sentinel.
    """
    history_path = tmp_path / "history"
    history = LockedFileHistory(str(history_path))

    # Distinct sentinels: each thread writes "sentinel-NN" where NN is a
    # zero-padded 2-digit index. The sentinels are long enough (≥10 bytes)
    # that a write split across two threads would be visibly garbled.
    sentinels = [f"sentinel-{i:02d}-end" for i in range(20)]

    def _writer(text: str) -> None:
        # Each thread also pads the call with a small busy loop so the
        # scheduler is more likely to interleave them.
        for _ in range(3):
            history.store_string(text)

    threads = [threading.Thread(target=_writer, args=(s,)) for s in sentinels]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    contents = history_path.read_text(encoding="utf-8")
    # Every `+...` line in FileHistory's format is a single complete sentinel.
    plus_lines = [
        line[1:] for line in contents.splitlines() if line.startswith("+")
    ]
    # 20 sentinels × 3 writes each = 60 lines
    assert len(plus_lines) == 60, (
        f"expected 60 '+sentinel' lines, got {len(plus_lines)}: {plus_lines[:5]}"
    )
    # Each line MUST equal one of the known sentinels — never a fused
    # combination like "sentinel-03-end" + "sentinel-17-end".
    sentinel_set = set(sentinels)
    for line in plus_lines:
        assert line in sentinel_set, f"corrupted line: {line!r}"


def test_locked_history_round_trips_via_prompt_buffer(tmp_path: Path) -> None:
    """Smoke: prompt-toolkit Buffer can read back what LockedFileHistory wrote."""
    history = LockedFileHistory(str(tmp_path / "h"))
    history.store_string("first command")
    history.store_string("second command")

    # FileHistory.load_history_strings is a sync generator yielding entries
    # in reverse insertion order.
    loaded = list(history.load_history_strings())
    assert "first command" in loaded
    assert "second command" in loaded
