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
