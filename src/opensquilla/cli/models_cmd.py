"""Model catalog CLI commands."""

from __future__ import annotations

import typer

from opensquilla.cli.models_workflows import list_models_for_cli

app = typer.Typer(help="Inspect available models.")


@app.command("list")
def models_list(
    provider: str | None = typer.Option(None, "--provider", help="Provider filter"),
    capability: list[str] | None = typer.Option(
        None, "--capability", "-c", help="Required capability"
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """List available models from the running gateway."""
    list_models_for_cli(
        provider=provider,
        capabilities=capability,
        json_output=json_output,
    )
