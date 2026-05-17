"""Presenters for interactive chat slash-command output."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from opensquilla.cli.ui import console


def emit_chat_sessions_table(rows: list[dict[str, Any]]) -> None:
    """Emit the gateway chat session list."""

    table = Table(title="Sessions", show_header=True, header_style="bold cyan")
    table.add_column("Key")
    table.add_column("Status")
    table.add_column("Model")
    table.add_column("Messages", justify="right")
    for row in rows:
        table.add_row(
            str(row.get("key") or row.get("session_key") or ""),
            str(row.get("status") or ""),
            str(row.get("model") or ""),
            str(row.get("message_count") or row.get("entry_count") or 0),
        )
    console.print(table)


def emit_chat_models_table(rows: list[dict[str, Any]]) -> None:
    """Emit the gateway chat model list."""

    table = Table(title="Models", show_header=True, header_style="bold cyan")
    table.add_column("ID")
    table.add_column("Provider")
    table.add_column("Context", justify="right")
    table.add_column("Capabilities")
    for row in rows:
        table.add_row(
            str(row.get("id") or ""),
            str(row.get("provider") or ""),
            str(row.get("contextWindow") or ""),
            ", ".join(str(value) for value in row.get("capabilities") or []),
        )
    console.print(table)
