"""CLI commands for migration from external agent runtimes."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import typer

from opensquilla.cli.ui import console
from opensquilla.migration.hermes import (
    MIGRATION_OPTIONS as HERMES_MIGRATION_OPTIONS,
)
from opensquilla.migration.hermes import (
    MIGRATION_PRESETS as HERMES_MIGRATION_PRESETS,
)
from opensquilla.migration.hermes import (
    SKILL_CONFLICT_MODES as HERMES_SKILL_CONFLICT_MODES,
)
from opensquilla.migration.hermes import (
    HermesMigrationOptions,
    HermesMigrator,
)
from opensquilla.migration.openclaw import (
    PERSONA_CONFLICT_MODES,
)
from opensquilla.migration.openclaw import (
    MIGRATION_OPTIONS,
    MIGRATION_PRESETS,
    SKILL_CONFLICT_MODES,
    MigrationOptions,
    OpenClawMigrator,
)

migrate_app = typer.Typer(help="Migration helpers for external agent runtimes.")


def _split_csv(values: list[str] | None) -> tuple[str, ...]:
    parsed: list[str] = []
    for value in values or []:
        for part in value.split(","):
            normalized = part.strip()
            if normalized:
                parsed.append(normalized)
    return tuple(parsed)


def _reject_invalid_options(
    *,
    preset: str,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    skill_conflict: str,
    persona_conflict: str | None = None,
) -> None:
    if preset not in MIGRATION_PRESETS:
        typer.echo(f"Unknown migration preset: {preset}")
        raise typer.Exit(2)
    unknown_include = sorted(set(include) - MIGRATION_OPTIONS)
    if unknown_include:
        typer.echo(f"Unknown migration option in include: {', '.join(unknown_include)}")
        raise typer.Exit(2)
    unknown_exclude = sorted(set(exclude) - MIGRATION_OPTIONS)
    if unknown_exclude:
        typer.echo(f"Unknown migration option in exclude: {', '.join(unknown_exclude)}")
        raise typer.Exit(2)
    if skill_conflict not in SKILL_CONFLICT_MODES:
        typer.echo(f"Unknown skill conflict behavior: {skill_conflict}")
        raise typer.Exit(2)
    if persona_conflict is not None and persona_conflict not in PERSONA_CONFLICT_MODES:
        typer.echo(f"Unknown persona conflict behavior: {persona_conflict}")
        raise typer.Exit(2)


def _reject_invalid_hermes_options(
    *,
    preset: str,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    skill_conflict: str,
) -> None:
    if preset not in HERMES_MIGRATION_PRESETS:
        typer.echo(f"Unknown Hermes migration preset: {preset}")
        raise typer.Exit(2)
    unknown_include = sorted(set(include) - HERMES_MIGRATION_OPTIONS)
    if unknown_include:
        typer.echo(f"Unknown Hermes migration option in include: {', '.join(unknown_include)}")
        raise typer.Exit(2)
    unknown_exclude = sorted(set(exclude) - HERMES_MIGRATION_OPTIONS)
    if unknown_exclude:
        typer.echo(f"Unknown Hermes migration option in exclude: {', '.join(unknown_exclude)}")
        raise typer.Exit(2)
    if skill_conflict not in HERMES_SKILL_CONFLICT_MODES:
        typer.echo(f"Unknown Hermes skill conflict behavior: {skill_conflict}")
        raise typer.Exit(2)


@migrate_app.command("openclaw")
def migrate_openclaw(
    source: Path = typer.Option(
        Path.home() / ".openclaw",
        "--source",
        help="OpenClaw home directory.",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="OpenSquilla config path to write or preview.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the migration. Without this flag, only a dry-run report is produced.",
    ),
    migrate_secrets: bool = typer.Option(
        False,
        "--migrate-secrets",
        help="Copy recognized secrets. Defaults to false.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite target workspace files after making item-level backups.",
    ),
    preset: str = typer.Option(
        "full",
        "--preset",
        help="Migration preset: user-data or full.",
    ),
    include: list[str] | None = typer.Option(
        None,
        "--include",
        help="Comma-separated migration option ids to include.",
    ),
    exclude: list[str] | None = typer.Option(
        None,
        "--exclude",
        help="Comma-separated migration option ids to exclude.",
    ),
    skill_conflict: str = typer.Option(
        "skip",
        "--skill-conflict",
        help="Skill conflict behavior: skip, overwrite, or rename.",
    ),
    persona_conflict: str = typer.Option(
        "prompt",
        "--persona-conflict",
        help=(
            "How to resolve SOUL/USER/AGENTS conflicts when the destination "
            "already holds real user content: prompt (interactive, default), "
            "use-opensquilla, use-openclaw, merge, or skip."
        ),
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Migrate OpenClaw state into OpenSquilla-native files."""

    include_options = _split_csv(include)
    exclude_options = _split_csv(exclude)
    _reject_invalid_options(
        preset=preset,
        include=include_options,
        exclude=exclude_options,
        skill_conflict=skill_conflict,
        persona_conflict=persona_conflict,
    )
    options = MigrationOptions(
        source=source,
        config_path=config,
        apply=apply,
        migrate_secrets=migrate_secrets,
        overwrite=overwrite,
        preset=preset,
        include=include_options,
        exclude=exclude_options,
        skill_conflict=skill_conflict,  # type: ignore[arg-type]
        persona_conflict=persona_conflict,  # type: ignore[arg-type]
    )
    if json_output:
        with contextlib.redirect_stdout(io.StringIO()):
            report = OpenClawMigrator(options).migrate()
    else:
        report = OpenClawMigrator(options).migrate()
    has_error = any(item.get("status") == "error" for item in report.get("items", []))
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False))
    else:
        mode = "applied" if apply else "dry-run"
        console.print(f"[green]OpenClaw migration complete[/green] ({mode})")
        console.print(f"[dim]Report:[/dim] {report['output_dir']}")
    if has_error:
        raise typer.Exit(1)


@migrate_app.command("hermes")
def migrate_hermes(
    source: Path | None = typer.Option(
        None,
        "--source",
        help="Hermes home directory.",
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Hermes profile name under ~/.hermes/profiles.",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="OpenSquilla config path to write or preview.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the migration. Without this flag, only a dry-run report is produced.",
    ),
    migrate_secrets: bool = typer.Option(
        False,
        "--migrate-secrets",
        help="Copy recognized secrets. Defaults to false.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite target workspace files after making item-level backups.",
    ),
    preset: str = typer.Option(
        "full",
        "--preset",
        help="Migration preset: user-data or full.",
    ),
    include: list[str] | None = typer.Option(
        None,
        "--include",
        help="Comma-separated migration option ids to include.",
    ),
    exclude: list[str] | None = typer.Option(
        None,
        "--exclude",
        help="Comma-separated migration option ids to exclude.",
    ),
    skill_conflict: str = typer.Option(
        "skip",
        "--skill-conflict",
        help="Skill conflict behavior: skip, overwrite, or rename.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Migrate Hermes Agent state into OpenSquilla-native files."""

    include_options = _split_csv(include)
    exclude_options = _split_csv(exclude)
    _reject_invalid_hermes_options(
        preset=preset,
        include=include_options,
        exclude=exclude_options,
        skill_conflict=skill_conflict,
    )
    options = HermesMigrationOptions(
        source=source,
        profile=profile,
        config_path=config,
        apply=apply,
        migrate_secrets=migrate_secrets,
        overwrite=overwrite,
        preset=preset,
        include=include_options,
        exclude=exclude_options,
        skill_conflict=skill_conflict,  # type: ignore[arg-type]
    )
    if json_output:
        with contextlib.redirect_stdout(io.StringIO()):
            report = HermesMigrator(options).migrate()
    else:
        report = HermesMigrator(options).migrate()
    has_error = any(item.get("status") == "error" for item in report.get("items", []))
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False))
    else:
        mode = "applied" if apply else "dry-run"
        console.print(f"[green]Hermes migration complete[/green] ({mode})")
        console.print(f"[dim]Report:[/dim] {report['output_dir']}")
    if has_error:
        raise typer.Exit(1)
