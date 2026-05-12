from __future__ import annotations

import json
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from opensquilla.cli.main import app

runner = CliRunner()


def _make_source(root: Path) -> Path:
    source = root / ".openclaw"
    workspace = source / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "SOUL.md").write_text("soul\n", encoding="utf-8")
    (workspace / "MEMORY.md").write_text("memory\n", encoding="utf-8")
    (source / "openclaw.json").write_text(
        json.dumps({"agents": {"defaults": {"model": "deepseek-chat"}}}),
        encoding="utf-8",
    )
    return source


def test_migrate_openclaw_json_dry_run(tmp_path: Path, monkeypatch) -> None:
    source = _make_source(tmp_path)
    home = tmp_path / "opensquilla-home"
    target = tmp_path / "config.toml"
    monkeypatch.setenv("OPENSQUILLA_STATE_DIR", str(home))

    result = runner.invoke(
        app,
        [
            "migrate",
            "openclaw",
            "--source",
            str(source),
            "--config",
            str(target),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["apply"] is False
    assert not target.exists()
    assert any(item["status"] == "planned" for item in payload["items"])


def test_migrate_openclaw_apply_writes_config_and_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = _make_source(tmp_path)
    home = tmp_path / "opensquilla-home"
    target = tmp_path / "config.toml"
    monkeypatch.setenv("OPENSQUILLA_STATE_DIR", str(home))

    result = runner.invoke(
        app,
        [
            "migrate",
            "openclaw",
            "--source",
            str(source),
            "--config",
            str(target),
            "--apply",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "OpenClaw migration complete" in result.stdout
    assert (home / "workspace" / "SOUL.md").read_text(encoding="utf-8") == "soul\n"
    config = tomllib.loads(target.read_text(encoding="utf-8"))
    assert config["llm"]["model"] == "deepseek-chat"


def test_migrate_openclaw_missing_source_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "migrate",
            "openclaw",
            "--source",
            str(tmp_path / "missing"),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["items"][0]["status"] == "error"


def test_migrate_openclaw_exclude_skips_workspace_item(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = _make_source(tmp_path)
    home = tmp_path / "opensquilla-home"
    target = tmp_path / "config.toml"
    monkeypatch.setenv("OPENSQUILLA_STATE_DIR", str(home))

    result = runner.invoke(
        app,
        [
            "migrate",
            "openclaw",
            "--source",
            str(source),
            "--config",
            str(target),
            "--apply",
            "--exclude",
            "soul",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert not (home / "workspace" / "SOUL.md").exists()
    config = tomllib.loads(target.read_text(encoding="utf-8"))
    assert config["llm"]["model"] == "deepseek-chat"


def test_migrate_openclaw_rejects_unknown_include(tmp_path: Path) -> None:
    source = _make_source(tmp_path)

    result = runner.invoke(
        app,
        [
            "migrate",
            "openclaw",
            "--source",
            str(source),
            "--include",
            "not-a-real-option",
        ],
    )

    assert result.exit_code != 0
    assert "Unknown migration option" in result.stdout


def test_migrate_openclaw_rejects_unknown_preset(tmp_path: Path) -> None:
    source = _make_source(tmp_path)

    result = runner.invoke(
        app,
        [
            "migrate",
            "openclaw",
            "--source",
            str(source),
            "--preset",
            "everything",
        ],
    )

    assert result.exit_code != 0
    assert "Unknown migration preset" in result.stdout


def test_migrate_openclaw_rejects_unknown_skill_conflict(tmp_path: Path) -> None:
    source = _make_source(tmp_path)

    result = runner.invoke(
        app,
        [
            "migrate",
            "openclaw",
            "--source",
            str(source),
            "--skill-conflict",
            "merge",
        ],
    )

    assert result.exit_code != 0
    assert "Unknown skill conflict behavior" in result.stdout
