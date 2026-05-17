"""Presentation helpers for gateway-backed skill CLI commands."""

from __future__ import annotations

from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from opensquilla.cli.output import print_json
from opensquilla.cli.ui import console


def emit_gateway_skill_view(
    payload: dict[str, Any],
    *,
    fallback_name: str,
    json_output: bool,
) -> None:
    """Emit one gateway skill payload."""

    if json_output:
        print_json(payload)
        return

    table = Table(title=f"Skill: {payload.get('name', fallback_name)}")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    for key in (
        "name",
        "layer",
        "eligible",
        "description",
        "file_path",
        "base_dir",
        "homepage",
    ):
        value = payload.get(key)
        if value not in (None, ""):
            table.add_row(key, str(value))
    console.print(table)
    content = str(payload.get("content") or "")
    if content:
        preview = content if len(content) <= 1200 else content[:1200] + "\n..."
        console.print(Panel(preview, title="Content", expand=False))


def emit_gateway_skill_update(payload: Any, *, json_output: bool) -> None:
    """Emit a gateway skill update payload and raise on failed rows."""

    results = payload.get("results", []) if isinstance(payload, dict) else []
    failures = [row for row in results if isinstance(row, dict) and not row.get("success", False)]
    top_level_failure = isinstance(payload, dict) and payload.get("success") is False
    if json_output:
        print_json(payload)
    else:
        table = Table(title="Skill updates")
        table.add_column("Name", style="cyan")
        table.add_column("Status")
        table.add_column("Message")
        for row in results:
            if not isinstance(row, dict):
                continue
            ok = bool(row.get("success", False))
            table.add_row(
                str(row.get("name") or ""),
                "[green]ok[/]" if ok else "[red]failed[/]",
                str(row.get("message") or ""),
            )
        console.print(table)
        message = payload.get("message") if isinstance(payload, dict) else None
        if message:
            console.print(str(message))
    if failures or top_level_failure:
        raise typer.Exit(1)
