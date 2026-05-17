"""CLI workflows for model catalog commands."""

from __future__ import annotations

from opensquilla.cli.models_gateway_queries import list_models_from_gateway
from opensquilla.cli.models_presenters import emit_model_rows


def list_models_for_cli(
    *,
    provider: str | None,
    capabilities: list[str] | None,
    json_output: bool,
) -> None:
    """Load and emit available model catalog rows for the CLI."""

    rows = list_models_from_gateway(
        provider=provider,
        capabilities=capabilities,
        json_output=json_output,
    )
    emit_model_rows(rows, json_output=json_output)
