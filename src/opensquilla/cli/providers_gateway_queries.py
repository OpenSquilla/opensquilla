"""Gateway-backed provider queries for CLI workflows."""

from __future__ import annotations

from typing import Any, cast

from opensquilla.cli.gateway_rpc import run_gateway_sync


def provider_status_request_params(
    provider: str | None,
    *,
    probe_models: bool,
) -> dict[str, object]:
    """Build gateway request params for provider status diagnostics."""

    params: dict[str, object] = {"probeModels": probe_models}
    if provider:
        params["provider"] = provider
    return params


def load_provider_status(
    provider: str | None,
    *,
    probe_models: bool,
    json_output: bool,
) -> dict[str, Any]:
    """Load runtime provider diagnostics from the gateway."""

    params = provider_status_request_params(provider, probe_models=probe_models)

    async def _run(client):
        return await client.call("providers.status", params)

    return cast(dict[str, Any], run_gateway_sync(_run, json_output=json_output))
