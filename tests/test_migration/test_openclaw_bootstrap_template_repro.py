"""Repro: opensquilla bootstrap-template MEMORY.md blocks openclaw migration.

When opensquilla initializes a workspace (via ``ensure_agent_workspace``) it
seeds bootstrap templates for ``SOUL.md`` / ``USER.md`` / ``AGENTS.md`` /
``MEMORY.md``. These are placeholder docs (5-line comments). Before the fix
the openclaw migrator's ``_write_text_target`` hit the conflict gate on
every one of them, silently dropping every workspace file the user actually
wanted migrated — including the real reason the user invoked the migration,
their daily memory.

The fix detects "destination still holds the pristine bootstrap template"
and treats it as overwrite-safe (item-level backup + replace), with an
explicit ``details.replaced_bootstrap_template`` flag in the report.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from opensquilla.identity.bootstrap import ensure_agent_workspace
from opensquilla.migration.openclaw import MigrationOptions, OpenClawMigrator


def _make_openclaw_source(root: Path) -> Path:
    source = root / ".openclaw"
    workspace = source / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "SOUL.md").write_text("openclaw real soul\n", encoding="utf-8")
    (workspace / "USER.md").write_text("openclaw real user\n", encoding="utf-8")
    (workspace / "AGENTS.md").write_text("openclaw agents guide\n", encoding="utf-8")
    (workspace / "MEMORY.md").write_text("openclaw long-term memory\n", encoding="utf-8")
    (workspace / "memory").mkdir()
    (workspace / "memory" / "2026-05-04.md").write_text(
        "real daily entry that needs to survive migration\n",
        encoding="utf-8",
    )
    (source / "openclaw.json").write_text("{}", encoding="utf-8")
    return source


def test_pristine_bootstrap_templates_do_not_block_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _make_openclaw_source(tmp_path)
    home = tmp_path / "opensquilla-home"
    monkeypatch.setenv("OPENSQUILLA_STATE_DIR", str(home))
    ensure_agent_workspace(home / "workspace")
    # Confirm the templates were seeded (precondition for the bug).
    for filename in ("SOUL.md", "USER.md", "AGENTS.md", "MEMORY.md"):
        assert (home / "workspace" / filename).is_file()

    report = OpenClawMigrator(
        MigrationOptions(source=source, config_path=tmp_path / "cfg.toml", apply=True)
    ).migrate()

    statuses = {item["kind"]: item["status"] for item in report["items"]}
    for kind in ("soul", "user-profile", "workspace-agents", "memory"):
        assert statuses.get(kind) == "migrated", (
            f"kind={kind} expected migrated, got {statuses.get(kind)!r}. "
            f"items: {[i for i in report['items'] if i['kind']==kind]}"
        )

    # Bootstrap-template replacement is announced via the details flag so the
    # report makes the special case visible rather than silent.
    for kind in ("soul", "user-profile", "workspace-agents", "memory"):
        item = next(i for i in report["items"] if i["kind"] == kind)
        assert item["details"].get("replaced_bootstrap_template") is True, (
            f"kind={kind} did not record replaced_bootstrap_template: {item}"
        )

    # The migrated content actually landed and the daily memory is in MEMORY.md.
    memory_text = (home / "workspace" / "MEMORY.md").read_text(encoding="utf-8")
    assert "real daily entry that needs to survive migration" in memory_text

    soul_text = (home / "workspace" / "SOUL.md").read_text(encoding="utf-8")
    # rebrand: openclaw -> opensquilla in workspace prose.
    assert "opensquilla real soul" in soul_text
    assert "openclaw" not in soul_text.lower()

    # Item-level backups of the pristine templates exist for rollback.
    backups = sorted((home / "workspace").glob("*.backup.*"))
    backup_basenames = {b.name.split(".backup.")[0] for b in backups}
    assert {"SOUL.md", "USER.md", "MEMORY.md", "AGENTS.md"} <= backup_basenames


def test_user_edited_workspace_file_still_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # User who has truly edited their MEMORY.md should still get a conflict
    # record, not have their content silently overwritten. Only the pristine
    # template gets the override-safe treatment.
    source = _make_openclaw_source(tmp_path)
    home = tmp_path / "opensquilla-home"
    monkeypatch.setenv("OPENSQUILLA_STATE_DIR", str(home))
    ensure_agent_workspace(home / "workspace")
    (home / "workspace" / "MEMORY.md").write_text(
        "# My real, edited memory\n\nThis is not the template.\n",
        encoding="utf-8",
    )

    report = OpenClawMigrator(
        MigrationOptions(source=source, config_path=tmp_path / "cfg.toml", apply=True)
    ).migrate()

    memory_item = next(i for i in report["items"] if i["kind"] == "memory")
    assert memory_item["status"] == "conflict"
    assert memory_item["reason"] == "target exists"
    # Confirm the user content really was preserved.
    assert (
        "This is not the template."
        in (home / "workspace" / "MEMORY.md").read_text(encoding="utf-8")
    )


def test_template_detection_is_robust_to_trailing_whitespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stray trailing newline or platform EOL artifact should not disqualify
    # the destination from being treated as the pristine template.
    source = _make_openclaw_source(tmp_path)
    home = tmp_path / "opensquilla-home"
    monkeypatch.setenv("OPENSQUILLA_STATE_DIR", str(home))
    ensure_agent_workspace(home / "workspace")
    memory_path = home / "workspace" / "MEMORY.md"
    original = memory_path.read_text(encoding="utf-8")
    memory_path.write_text(original.rstrip() + "\n\n\n", encoding="utf-8")

    report = OpenClawMigrator(
        MigrationOptions(source=source, config_path=tmp_path / "cfg.toml", apply=True)
    ).migrate()

    memory_item = next(i for i in report["items"] if i["kind"] == "memory")
    assert memory_item["status"] == "migrated"
    assert memory_item["details"]["replaced_bootstrap_template"] is True
