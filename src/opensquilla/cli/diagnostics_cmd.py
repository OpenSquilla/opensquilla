"""Diagnostics CLI commands."""

from __future__ import annotations

import typer

from opensquilla.cli.diagnostics_workflows import (
    disable_diagnostics_for_cli,
    enable_diagnostics_for_cli,
    show_diagnostics_status_for_cli,
)

diagnostics_app = typer.Typer(help="Manage runtime diagnostics logging.")


@diagnostics_app.command("status")
def diagnostics_status(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Show effective diagnostics and raw-capture state."""
    show_diagnostics_status_for_cli(json_output=json_output)


@diagnostics_app.command("on")
def diagnostics_on(
    raw: bool = typer.Option(False, "--raw", help="Also enable raw turn-call capture."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Enable runtime diagnostics; --raw also enables raw turn-call capture."""
    enable_diagnostics_for_cli(raw=raw, json_output=json_output)


@diagnostics_app.command("off")
def diagnostics_off(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Disable runtime diagnostics and runtime raw capture."""
    disable_diagnostics_for_cli(json_output=json_output)
