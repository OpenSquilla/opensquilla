"""CLI presenters for diagnostics output."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from opensquilla.cli.output import print_json
from opensquilla.cli.ui import console


def emit_diagnostics_status(payload: dict[str, Any], *, json_output: bool) -> None:
    """Emit diagnostics state."""

    if json_output:
        print_json(payload)
        return

    raw = payload.get("raw_turn_call") or {}
    runtime = payload.get("runtime") or {}
    configured = payload.get("configured") or {}
    table = Table(title="Diagnostics", show_header=True)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("enabled", str(bool(payload.get("enabled"))).lower())
    table.add_row("detail", str(payload.get("detail") or "off"))
    table.add_row("raw", str(bool(raw.get("enabled"))).lower())
    table.add_row("raw source", str(raw.get("source") or "off"))
    table.add_row("runtime enabled", str(runtime.get("enabled")))
    table.add_row("runtime raw", str(bool(runtime.get("raw"))).lower())
    table.add_row(
        "config diagnostics_enabled",
        str(bool(configured.get("diagnostics_enabled"))).lower(),
    )
    if payload.get("warning"):
        table.add_row("warning", str(payload["warning"]))
    console.print(table)
