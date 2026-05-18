"""Provider-specific onboarding RPC handlers."""

from __future__ import annotations

from typing import Any

from opensquilla.gateway.provider_runtime_sync import (
    sync_image_generation,
    sync_provider_selector,
)
from opensquilla.gateway.rpc import RpcContext, get_dispatcher
from opensquilla.gateway.rpc_onboarding import (
    _active_config,
    _apply_inplace,
    _persist,
    _require,
)

_d = get_dispatcher()


def _sync_running_provider_selector(ctx: RpcContext, config: Any) -> None:
    sync_provider_selector(ctx, getattr(ctx, "config", None) or config)


@_d.method("onboarding.provider.configure", scope="operator.admin")
async def _provider_configure(params: Any, ctx: RpcContext) -> dict[str, Any]:
    from opensquilla.onboarding.mutations import upsert_llm_provider

    provider_id = _require(params, "providerId")
    model = params.get("model", "") if isinstance(params, dict) else ""
    cfg = _active_config(ctx)
    res = upsert_llm_provider(
        cfg,
        provider_id=provider_id,
        model=model,
        api_key=params.get("apiKey", "") if isinstance(params, dict) else "",
        api_key_env=params.get("apiKeyEnv", "") if isinstance(params, dict) else "",
        base_url=params.get("baseUrl", "") if isinstance(params, dict) else "",
        proxy=params.get("proxy", "") if isinstance(params, dict) else "",
    )
    _apply_inplace(ctx, res.config)
    _sync_running_provider_selector(ctx, res.config)
    sync_image_generation(res.config)
    config_path = _persist(ctx, res.config, restart_required=res.restart_required)
    return {
        "changed": res.changed,
        "restartRequired": res.restart_required,
        "configPath": config_path,
        "entry": res.public_payload,
        "warnings": res.warnings,
    }


@_d.method("onboarding.imageGeneration.configure", scope="operator.admin")
async def _image_generation_configure(params: Any, ctx: RpcContext) -> dict[str, Any]:
    from opensquilla.onboarding.mutations import upsert_image_generation_provider

    provider_id = _require(params, "providerId")
    cfg = _active_config(ctx)
    res = upsert_image_generation_provider(
        cfg,
        provider_id=provider_id,
        primary=params.get("primary", "") if isinstance(params, dict) else "",
        api_key=params.get("apiKey", "") if isinstance(params, dict) else "",
        api_key_env=params.get("apiKeyEnv", "") if isinstance(params, dict) else "",
        base_url=params.get("baseUrl", "") if isinstance(params, dict) else "",
        enabled=params.get("enabled", True) if isinstance(params, dict) else True,
    )
    _apply_inplace(ctx, res.config)
    sync_image_generation(res.config)
    config_path = _persist(ctx, res.config, restart_required=res.restart_required)
    return {
        "changed": res.changed,
        "restartRequired": res.restart_required,
        "configPath": config_path,
        "entry": res.public_payload,
        "warnings": res.warnings,
    }
