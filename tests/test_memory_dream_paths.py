from __future__ import annotations

from types import SimpleNamespace

from opensquilla.memory.dream import Dream


def _dream(workspace):
    return Dream(
        workspace=workspace,
        provider=object(),
        model="test",
        tool_registry=None,
        session_lock=None,
        config=SimpleNamespace(max_batch_size=10, input_slimming="off"),
    )


def test_dream_uses_workspace_root_memory_md_for_curated_memory(tmp_path):
    root_memory = tmp_path / "MEMORY.md"
    nested_memory_dir = tmp_path / "memory"
    nested_memory = nested_memory_dir / "MEMORY.md"
    candidate = nested_memory_dir / "candidate.md"
    root_memory.write_text("root curated marker", encoding="utf-8")
    nested_memory_dir.mkdir()
    nested_memory.write_text("nested stale marker", encoding="utf-8")
    candidate.write_text("candidate note", encoding="utf-8")

    dream = _dream(tmp_path)
    prompt, _chars, _phase = dream._phase1_prompt([candidate])

    assert dream.memory_md == root_memory
    assert "root curated marker" in prompt
    assert "nested stale marker" not in prompt
