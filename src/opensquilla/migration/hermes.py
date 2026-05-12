"""Hermes Agent to OpenSquilla migration."""

from __future__ import annotations

import json
import os
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
