from __future__ import annotations

from pathlib import Path

from opensquilla.engine.tool_result_store import ToolResultStore


def test_tool_result_store_preserves_metadata_for_repeated_content(tmp_path: Path) -> None:
    store = ToolResultStore(tmp_path)

    first = store.write("same output", tool_use_id="tool-1", tool_name="fetch")
    second = store.write("same output", tool_use_id="tool-2", tool_name="execute_code")

    assert first.handle != second.handle
    assert store.read(first.handle).tool_use_id == "tool-1"
    assert store.read(first.handle).tool_name == "fetch"
    assert store.read(second.handle).tool_use_id == "tool-2"
    assert store.read(second.handle).tool_name == "execute_code"
