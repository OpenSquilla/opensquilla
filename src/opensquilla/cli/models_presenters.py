"""CLI presenters for model catalog output."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from opensquilla.cli.output import print_json
from opensquilla.cli.ui import console


def emit_model_rows(
    rows: list[dict[str, Any]],
    *,
    json_output: bool,
) -> None:
    """Emit model catalog rows."""

    if json_output:
        print_json(rows)
        return

    table = Table(title="Models", show_header=True, header_style="bold cyan")
    table.add_column("ID")
    table.add_column("Provider")
    table.add_column("Context", justify="right")
    table.add_column("Capabilities")
    table.add_column("Input/1k", justify="right")
    table.add_column("Output/1k", justify="right")
    for row in rows:
        pricing = row.get("pricing") or {}
        table.add_row(
            str(row.get("id") or ""),
            str(row.get("provider") or ""),
            str(row.get("contextWindow") or ""),
            ", ".join(str(value) for value in row.get("capabilities") or []),
            str(pricing.get("inputPer1k") or ""),
            str(pricing.get("outputPer1k") or ""),
        )
    console.print(table)
