"""Gateway-backed model catalog queries for CLI workflows."""

from __future__ import annotations

from typing import Any, cast

from opensquilla.cli.gateway_rpc import run_gateway_sync


def list_models_from_gateway(
    *,
    provider: str | None,
    capabilities: list[str] | None,
    json_output: bool,
) -> list[dict[str, Any]]:
    """List available models from the running gateway."""

    async def _with_client(client: Any) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await client.list_models(provider=provider, capabilities=capabilities),
        )

    return cast(
        list[dict[str, Any]],
        run_gateway_sync(_with_client, json_output=json_output),
    )
