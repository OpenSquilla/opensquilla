from __future__ import annotations

import json
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from opensquilla.cli.main import app

runner = CliRunner()


def _write_hermes_home(root: Path) -> Path:
    source = root / ".hermes"
    source.mkdir(parents=True)
    (source / "config.yaml").write_text(
        "model:\n  provider: openrouter\n  model: openai/gpt-4o-mini\n",
        encoding="utf-8",
    )
    (source / "SOUL.md").write_text("Hermes soul\n", encoding="utf-8")
    return source


def test_cli_hermes_dry_run_json_does_not_write(tmp_path: Path, monkeypatch) -> None:
    source = _write_hermes_home(tmp_path)
    home = tmp_path / "opensquilla-home"
    config_path = tmp_path / "opensquilla.toml"
    monkeypatch.setenv("OPENSQUILLA_STATE_DIR", str(home))

    result = runner.invoke(
        app,
        ["migrate", "hermes", "--source", str(source), "--config", str(config_path), "--json"],
    )

    assert result.exit_code == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["apply"] is False
    assert not config_path.exists()
    assert not (home / "workspace" / "SOUL.md").exists()
