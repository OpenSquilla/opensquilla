"""Gateway-owned provider RPC payload adapters."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, cast

from opensquilla.provider.model_listing import ProviderModelRow, list_provider_model_rows
from opensquilla.provider.runtime_status import (
    ProviderModelProbe,
    ProviderStatusReport,
    ProviderStatusRow,
    ProviderStatusSpec,
    build_provider_status_report,
)


def _provider_model_probe_to_wire(probe: ProviderModelProbe) -> dict[str, Any]:
    return {
        "attempted": probe.attempted,
        "status": probe.status,
        "count": probe.count,
        "error": probe.error,
    }


def _provider_status_row_to_wire(row: ProviderStatusRow) -> dict[str, Any]:
    return {
        "providerId": row.provider_id,
        "active": row.active,
        "configured": row.configured,
        "buildable": row.buildable,
        "model": row.model,
        "requiresApiKey": row.requires_api_key,
        "apiKeyConfigured": row.api_key_configured,
        "baseUrlConfigured": row.base_url_configured,
        "error": row.error,
        "modelProbe": _provider_model_probe_to_wire(row.model_probe),
    }


def _provider_status_report_to_wire(report: ProviderStatusReport) -> dict[str, Any]:
    rows = [_provider_status_row_to_wire(row) for row in report.rows]
    return {"activeProvider": report.active_provider, "providers": rows, "count": len(rows)}


async def build_provider_status_payload(
    specs: Iterable[ProviderStatusSpec],
    *,
    provider_selector: Any | None,
    config: Any | None,
    provider_filter: str | None = None,
    probe_models: bool = False,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the provider status payload exposed by Gateway RPC surfaces."""

    report = await build_provider_status_report(
        specs,
        provider_selector=provider_selector,
        config=config,
        provider_filter=provider_filter,
        probe_models=probe_models,
        environ=environ,
    )
    return _provider_status_report_to_wire(report)


def _provider_status_rpc_params(params: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise ValueError("params must be an object")
    return params


async def build_provider_status_rpc_payload(
    specs: Iterable[ProviderStatusSpec],
    params: Mapping[str, Any] | None,
    *,
    provider_selector: Any | None,
    config: Any | None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the provider status RPC payload from request params."""

    raw = _provider_status_rpc_params(params)
    provider_filter = raw.get("provider")
    return await build_provider_status_payload(
        specs,
        provider_selector=provider_selector,
        config=config,
        provider_filter=str(provider_filter) if provider_filter else None,
        probe_models=bool(raw.get("probeModels", False)),
        environ=environ,
    )


def _models_list_rpc_params(params: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise ValueError("params must be an object")
    return params


async def list_provider_models_rpc_payload(
    provider_selector: Any | None,
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the RPC wire payload for a provider model listing request."""

    raw = _models_list_rpc_params(params)
    rows = await list_provider_model_rows(
        provider_selector,
        provider_filter=cast(str | None, raw.get("provider")),
        capabilities_filter=cast(list[str] | None, raw.get("capabilities")),
    )
    return [_model_row_to_wire(row) for row in rows]


def _model_row_to_wire(row: ProviderModelRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "contextWindow": row.context_window,
        "capabilities": list(row.capabilities),
        "pricing": {
            "inputPer1k": row.input_cost_per_1k,
            "outputPer1k": row.output_cost_per_1k,
        },
    }
