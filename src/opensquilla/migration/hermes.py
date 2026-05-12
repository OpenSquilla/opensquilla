"""Hermes Agent to OpenSquilla migration."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from opensquilla.paths import default_opensquilla_home

SKILL_IMPORT_DIRNAME = "hermes-imports"
SECRET_REDACTION = "[redacted]"
SKILL_CONFLICT_MODES = {"skip", "overwrite", "rename"}
MAX_SKILL_FILE_BYTES = 256_000
MAX_MEMORY_CHARS = 80_000
MEMORY_OVERFLOW_DIR = "memory-overflow"

USER_DATA_OPTIONS = {"soul", "memory", "user-profile", "skills", "workspace-files"}
RUNTIME_CONFIG_OPTIONS = {
    "model-config",
    "provider-keys",
    "search-config",
    "telegram-settings",
    "discord-settings",
    "slack-settings",
    "mcp-servers",
    "tools-config",
    "archive",
    "browser-config",
    "session-config",
    "cron-jobs",
    "plugins-config",
    "gateway-config",
    "memory-backend",
    "approvals-config",
    "logging-config",
}
MIGRATION_OPTIONS = USER_DATA_OPTIONS | RUNTIME_CONFIG_OPTIONS
MIGRATION_PRESETS = {"user-data": USER_DATA_OPTIONS, "full": MIGRATION_OPTIONS}


@dataclass(frozen=True)
class HermesMigrationOptions:
    source: Path | str | None = None
    profile: str | None = None
    config_path: Path | str | None = None
    apply: bool = False
    migrate_secrets: bool = False
    overwrite: bool = False
    preset: str = "full"
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    skill_conflict: Literal["skip", "overwrite", "rename"] = "skip"


@dataclass
class ItemResult:
    kind: str
    source: str | None
    destination: str | None
    status: str
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _as_path(value: Path | str | None) -> Path | None:
    if value is None:
        return None
    return Path(value).expanduser()


def _is_valid_hermes_home(path: Path) -> bool:
    return any(
        (path / name).exists()
        for name in ("config.yaml", ".env", "SOUL.md", "memories", "skills")
    )


class HermesMigrator:
    def __init__(self, options: HermesMigrationOptions) -> None:
        self.options = options
        self.source = self._resolve_source()
        self.home = default_opensquilla_home()
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        self.output_dir = self.home / "migration" / "hermes" / timestamp
        self.items: list[ItemResult] = []

    def _resolve_source(self) -> Path:
        explicit = _as_path(self.options.source)
        if explicit is not None:
            return explicit

        env_home = os.environ.get("HERMES_HOME")
        root = Path(env_home).expanduser() if env_home else Path.home() / ".hermes"
        if self.options.profile:
            return root / "profiles" / self.options.profile
        return root

    def migrate(self) -> dict[str, Any]:
        if not _is_valid_hermes_home(self.source):
            self._record("source", self.source, None, "error", "not a Hermes home")
            return self._report()
        selected = self._selected_options()
        self._plan_user_data(selected)
        self._write_reports()
        return self._report()

    def _selected_options(self) -> set[str]:
        selected = set(MIGRATION_PRESETS.get(self.options.preset, MIGRATION_PRESETS["full"]))
        selected.update(self.options.include)
        selected.difference_update(self.options.exclude)
        return selected

    def _workspace_dir(self) -> Path:
        return self.home / "workspace"

    def _plan_user_data(self, selected: set[str]) -> None:
        if "soul" in selected:
            self._plan_file("soul", self.source / "SOUL.md", self._workspace_dir() / "SOUL.md")
        if "memory" in selected:
            self._plan_file(
                "memory",
                self.source / "memories" / "MEMORY.md",
                self._workspace_dir() / "MEMORY.md",
            )
        if "user-profile" in selected:
            self._plan_file(
                "user-profile",
                self.source / "memories" / "USER.md",
                self._workspace_dir() / "USER.md",
            )
        if "skills" in selected:
            self._plan_skills()

    def _plan_file(self, kind: str, source: Path, destination: Path) -> None:
        if not source.exists():
            self._record(kind, source, destination, "skipped", "source missing")
            return
        status = "migrated" if self.options.apply else "planned"
        if self.options.apply:
            self._write_text_merge(source, destination)
        self._record(
            kind,
            source,
            destination,
            status,
        )

    def _plan_skills(self) -> None:
        skills_dir = self.source / "skills"
        destination_root = self.home / "skills" / SKILL_IMPORT_DIRNAME
        if not skills_dir.exists():
            self._record("skills", skills_dir, destination_root, "skipped", "source missing")
            return
        for skill_dir in sorted(path for path in skills_dir.iterdir() if path.is_dir()):
            target = destination_root / skill_dir.name
            status = "migrated" if self.options.apply else "planned"
            reason = ""
            if self.options.apply:
                copied = self._copy_skill_dir(skill_dir, target)
                if copied is None:
                    status = "skipped"
                    reason = "target exists"
                else:
                    target = copied
            self._record("skills", skill_dir, target, status, reason)

    def _write_text_merge(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_text = source.read_text(encoding="utf-8-sig")
        if destination.exists() and not self.options.overwrite:
            existing = destination.read_text(encoding="utf-8")
            if source_text.strip() in existing:
                return
            destination.write_text(
                existing.rstrip() + "\n\n" + source_text.lstrip(), encoding="utf-8"
            )
            return
        destination.write_text(source_text, encoding="utf-8")

    def _copy_skill_dir(self, source: Path, destination: Path) -> Path | None:
        target = destination
        if target.exists():
            if self.options.skill_conflict == "skip":
                return None
            if self.options.skill_conflict == "rename":
                index = 1
                while target.exists():
                    target = destination.with_name(f"{destination.name}-imported-{index}")
                    index += 1
            elif self.options.skill_conflict == "overwrite":
                shutil.rmtree(target)
        shutil.copytree(source, target)
        return target

    def _write_reports(self) -> None:
        if not self.options.apply:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        report = self._report()
        (self.output_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        counts: dict[str, int] = {}
        for item in report["items"]:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        lines = ["# Hermes Migration Summary", ""]
        lines.extend(f"- {key}: {value}" for key, value in sorted(counts.items()))
        (self.output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _record(
        self,
        kind: str,
        source: Path | str | None,
        destination: Path | str | None,
        status: str,
        reason: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.items.append(
            ItemResult(
                kind=kind,
                source=str(source) if source is not None else None,
                destination=str(destination) if destination is not None else None,
                status=status,
                reason=reason,
                details=details or {},
            )
        )

    def _report(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "target_home": str(self.home),
            "output_dir": str(self.output_dir),
            "apply": self.options.apply,
            "items": [asdict(item) for item in self.items],
        }
