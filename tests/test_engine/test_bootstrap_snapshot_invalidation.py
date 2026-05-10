from __future__ import annotations

from types import SimpleNamespace

from opensquilla.bootstrap_types import BootstrapFileReport
from opensquilla.engine.runtime import BootstrapSnapshot, TurnRunner
from opensquilla.identity.workspace import filter_workspace_filenames_for_session
from opensquilla.tools.types import ToolContext


def test_bootstrap_write_evicts_only_matching_agent_snapshots() -> None:
    runner = TurnRunner(provider_selector=None)
    report = [BootstrapFileReport(filename="USER.md", raw_chars=4, injected_chars=4)]
    runner._bootstrap_snapshots[("main", "session-a", "full")] = BootstrapSnapshot(
        workspace_files={"USER.md": "main"},
        report=report,
    )
    runner._bootstrap_snapshots[("main", "session-b", "minimal")] = BootstrapSnapshot(
        workspace_files={"USER.md": "main"},
        report=report,
    )
    runner._bootstrap_snapshots[("other", "session-a", "full")] = BootstrapSnapshot(
        workspace_files={"USER.md": "other"},
        report=report,
    )
    runner._memory_snapshots[("main", "session-a")] = object()  # type: ignore[assignment]

    runner._handle_bootstrap_source_write("main", "USER.md")

    assert ("main", "session-a", "full") not in runner._bootstrap_snapshots
    assert ("main", "session-b", "minimal") not in runner._bootstrap_snapshots
    assert ("other", "session-a", "full") in runner._bootstrap_snapshots
    assert ("main", "session-a") in runner._memory_snapshots
    assert "USER.md" not in filter_workspace_filenames_for_session(None, "subagent:worker")


def test_runtime_write_callbacks_are_composed() -> None:
    runner = TurnRunner(provider_selector=None)
    memory_calls: list[tuple[str, str]] = []
    bootstrap_calls: list[tuple[str, str]] = []
    ctx = ToolContext(
        agent_id="main",
        on_memory_source_write=lambda agent_id, path: memory_calls.append((agent_id, path)),
        on_bootstrap_source_write=lambda agent_id, path: bootstrap_calls.append((agent_id, path)),
    )
    runner._bootstrap_snapshots[("main", "session-a", "full")] = BootstrapSnapshot(
        workspace_files={"USER.md": "main"},
        report=[],
    )

    updated = runner._with_runtime_write_callbacks(ctx, "main")

    assert updated.on_memory_source_write is not None
    assert updated.on_bootstrap_source_write is not None
    updated.on_memory_source_write("main", "MEMORY.md")
    updated.on_bootstrap_source_write("main", "USER.md")

    assert memory_calls == [("main", "MEMORY.md")]
    assert bootstrap_calls == [("main", "USER.md")]
    assert ("main", "session-a", "full") not in runner._bootstrap_snapshots


def test_unattended_bootstrap_context_skips_only_bootstrap_md(tmp_path) -> None:
    for filename in (
        "AGENTS.md",
        "SOUL.md",
        "IDENTITY.md",
        "TOOLS.md",
        "USER.md",
        "BOOTSTRAP.md",
    ):
        (tmp_path / filename).write_text(f"{filename} body\n", encoding="utf-8")
    (tmp_path / "IDENTITY.md").write_text("name: Test Agent\n", encoding="utf-8")
    runner = TurnRunner(
        provider_selector=None,
        config=SimpleNamespace(
            workspace_dir=str(tmp_path),
            memory=SimpleNamespace(source="workspace"),
            tools=SimpleNamespace(profile=None),
        ),
    )
    metadata: dict[str, object] = {}

    runner._assemble_prompt(
        "main",
        [],
        session_key="agent:main:auto",
        prompt_metadata=metadata,
        bootstrap_context_mode="unattended",
    )

    report = metadata["bootstrap_files"]
    filenames = {item.filename for item in report}  # type: ignore[attr-defined]
    assert "BOOTSTRAP.md" not in filenames
    assert {"AGENTS.md", "SOUL.md", "IDENTITY.md", "TOOLS.md", "USER.md"} <= filenames


def test_stateless_bootstrap_context_skips_persona_memory_and_bootstrap(tmp_path) -> None:
    for filename in (
        "AGENTS.md",
        "SOUL.md",
        "IDENTITY.md",
        "TOOLS.md",
        "USER.md",
        "MEMORY.md",
        "HEARTBEAT.md",
        "BOOTSTRAP.md",
    ):
        (tmp_path / filename).write_text(f"{filename} body\n", encoding="utf-8")
    runner = TurnRunner(
        provider_selector=None,
        config=SimpleNamespace(
            workspace_dir=str(tmp_path),
            memory=SimpleNamespace(source="workspace"),
            tools=SimpleNamespace(profile=None),
        ),
    )
    metadata: dict[str, object] = {}

    runner._assemble_prompt(
        "main",
        [],
        session_key="agent:main:auto",
        prompt_metadata=metadata,
        bootstrap_context_mode="stateless",
    )

    report = metadata["bootstrap_files"]
    filenames = {item.filename for item in report}  # type: ignore[attr-defined]
    assert filenames == {"TOOLS.md"}
    assert metadata["memory_md_present"] is False


def test_stateless_keep_project_rules_preserves_only_agents_md(tmp_path) -> None:
    for filename in (
        "AGENTS.md",
        "SOUL.md",
        "IDENTITY.md",
        "TOOLS.md",
        "USER.md",
        "MEMORY.md",
        "HEARTBEAT.md",
        "BOOTSTRAP.md",
    ):
        (tmp_path / filename).write_text(f"{filename} body\n", encoding="utf-8")
    runner = TurnRunner(
        provider_selector=None,
        config=SimpleNamespace(
            workspace_dir=str(tmp_path),
            memory=SimpleNamespace(source="workspace"),
            tools=SimpleNamespace(profile=None),
        ),
    )
    metadata: dict[str, object] = {}

    runner._assemble_prompt(
        "main",
        [],
        session_key="agent:main:auto",
        prompt_metadata=metadata,
        bootstrap_context_mode="stateless_keep_project_rules",
    )

    report = metadata["bootstrap_files"]
    filenames = {item.filename for item in report}  # type: ignore[attr-defined]
    assert filenames == {"AGENTS.md", "TOOLS.md"}
    assert metadata["memory_md_present"] is False


def test_full_and_unattended_bootstrap_snapshots_use_distinct_keys(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    (tmp_path / "BOOTSTRAP.md").write_text("bootstrap\n", encoding="utf-8")
    runner = TurnRunner(
        provider_selector=None,
        config=SimpleNamespace(
            workspace_dir=str(tmp_path),
            memory=SimpleNamespace(source="workspace"),
            tools=SimpleNamespace(profile=None),
        ),
    )
    session_key = "agent:main:auto"

    runner._assemble_prompt("main", [], session_key=session_key)
    runner._assemble_prompt(
        "main",
        [],
        session_key=session_key,
        bootstrap_context_mode="unattended",
    )

    assert ("main", session_key, "full") in runner._bootstrap_snapshots
    assert ("main", session_key, "unattended") in runner._bootstrap_snapshots
    full_snapshot = runner._bootstrap_snapshots[("main", session_key, "full")]
    unattended_snapshot = runner._bootstrap_snapshots[("main", session_key, "unattended")]
    assert "BOOTSTRAP.md" in full_snapshot.workspace_files
    assert (
        "BOOTSTRAP.md"
        not in unattended_snapshot.workspace_files
    )
