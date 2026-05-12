from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from opensquilla.migration.hermes import HermesMigrationOptions, HermesMigrator


def _make_hermes_home(root: Path) -> Path:
    home = root / ".hermes"
    home.mkdir(parents=True)
    (home / "config.yaml").write_text("model:\n  provider: openrouter\n", encoding="utf-8")
    return home


def test_source_detection_prefers_explicit_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = _make_hermes_home(tmp_path / "explicit")
    env_home = _make_hermes_home(tmp_path / "env")
    monkeypatch.setenv("HERMES_HOME", str(env_home))

    migrator = HermesMigrator(HermesMigrationOptions(source=explicit))

    assert migrator.source == explicit


def test_source_detection_uses_hermes_home_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_home = _make_hermes_home(tmp_path / "env")
    monkeypatch.setenv("HERMES_HOME", str(env_home))

    migrator = HermesMigrator(HermesMigrationOptions())

    assert migrator.source == env_home


def test_source_detection_uses_profile_under_root_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_hermes_home(tmp_path)
    profile = root / "profiles" / "work"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text("model:\n  provider: anthropic\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(root))

    migrator = HermesMigrator(HermesMigrationOptions(profile="work"))

    assert migrator.source == profile


def test_dry_run_plans_user_data_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _make_hermes_home(tmp_path)
    (source / "SOUL.md").write_text("Hermes soul\n", encoding="utf-8")
    memories = source / "memories"
    memories.mkdir()
    (memories / "MEMORY.md").write_text("memory line\n", encoding="utf-8")
    (memories / "USER.md").write_text("user profile\n", encoding="utf-8")
    (source / "skills" / "demo").mkdir(parents=True)
    (source / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo\n---\nBody\n",
        encoding="utf-8",
    )
    home = tmp_path / "opensquilla-home"
    monkeypatch.setenv("OPENSQUILLA_STATE_DIR", str(home))

    report = HermesMigrator(HermesMigrationOptions(source=source, apply=False)).migrate()

    statuses = {(item["kind"], item["status"]) for item in report["items"]}
    assert ("soul", "planned") in statuses
    assert ("memory", "planned") in statuses
    assert ("user-profile", "planned") in statuses
    assert ("skills", "planned") in statuses
    assert not (home / "workspace" / "SOUL.md").exists()
    assert not (home / "skills" / "hermes-imports").exists()


def test_apply_migrates_user_data_and_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _make_hermes_home(tmp_path)
    (source / "SOUL.md").write_text("Hermes soul\n", encoding="utf-8")
    memories = source / "memories"
    memories.mkdir()
    (memories / "MEMORY.md").write_text("memory line\n", encoding="utf-8")
    (memories / "USER.md").write_text("user profile\n", encoding="utf-8")
    skill = source / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo\n---\nBody\n", encoding="utf-8"
    )
    home = tmp_path / "opensquilla-home"
    monkeypatch.setenv("OPENSQUILLA_STATE_DIR", str(home))

    report = HermesMigrator(HermesMigrationOptions(source=source, apply=True)).migrate()

    assert (home / "workspace" / "SOUL.md").read_text(encoding="utf-8") == "Hermes soul\n"
    assert "memory line" in (home / "workspace" / "MEMORY.md").read_text(encoding="utf-8")
    assert (home / "workspace" / "USER.md").read_text(encoding="utf-8") == "user profile\n"
    assert (home / "skills" / "hermes-imports" / "demo" / "SKILL.md").is_file()
    assert (Path(report["output_dir"]) / "report.json").is_file()
    assert (Path(report["output_dir"]) / "summary.md").is_file()
