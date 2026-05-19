"""Gateway-backed model catalog queries for CLI workflows."""

from __future__ import annotations

from typing import Any, TypedDict, cast

from opensquilla.cli.gateway_rpc import run_gateway_sync


class ModelListRequestParams(TypedDict):
    """Gateway model list request params owned by the CLI query boundary."""

    provider: str | None
    capabilities: list[str] | None


def model_list_request_params(
    *,
    provider: str | None,
    capabilities: list[str] | None,
) -> ModelListRequestParams:
    """Build gateway request params for model listing."""

    return {"provider": provider, "capabilities": capabilities}


def list_models_from_gateway(
    *,
    provider: str | None,
    capabilities: list[str] | None,
    json_output: bool,
) -> list[dict[str, Any]]:
    """List available models from the running gateway."""

    params = model_list_request_params(provider=provider, capabilities=capabilities)

    async def _with_client(client: Any) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await client.list_models(**params),
        )

    return cast(
        list[dict[str, Any]],
        run_gateway_sync(_with_client, json_output=json_output),
    )
