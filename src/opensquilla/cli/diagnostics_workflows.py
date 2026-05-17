"""CLI workflows for diagnostics commands."""

from __future__ import annotations

from opensquilla.cli.diagnostics_gateway_queries import (
    load_diagnostics_status,
    set_diagnostics_enabled,
)
from opensquilla.cli.diagnostics_presenters import emit_diagnostics_status


def show_diagnostics_status_for_cli(*, json_output: bool) -> None:
    """Load and emit effective diagnostics state for the CLI."""

    payload = load_diagnostics_status(json_output=json_output)
    emit_diagnostics_status(payload, json_output=json_output)


def enable_diagnostics_for_cli(*, raw: bool, json_output: bool) -> None:
    """Enable runtime diagnostics and emit the resulting state."""

    payload = set_diagnostics_enabled(
        enabled=True,
        raw=raw,
        json_output=json_output,
    )
    emit_diagnostics_status(payload, json_output=json_output)


def disable_diagnostics_for_cli(*, json_output: bool) -> None:
    """Disable runtime diagnostics and emit the resulting state."""

    payload = set_diagnostics_enabled(
        enabled=False,
        json_output=json_output,
    )
    emit_diagnostics_status(payload, json_output=json_output)
