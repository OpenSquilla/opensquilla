"""RPC handlers for the models domain."""

from __future__ import annotations

from typing import Any

from opensquilla.gateway.provider_rpc_payloads import list_provider_models_rpc_payload
from opensquilla.gateway.rpc import RpcContext, get_dispatcher

_d = get_dispatcher()


@_d.method("models.list", scope="operator.read")
async def _handle_models_list(params: dict | None, ctx: RpcContext) -> list[dict[str, Any]]:
    return await list_provider_models_rpc_payload(ctx.provider_selector, params)
