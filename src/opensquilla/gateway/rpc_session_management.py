"""RPC adapters for Gateway session create/patch management."""

from __future__ import annotations

from opensquilla.gateway.rpc import RpcContext, RpcHandlerError, RpcUnavailableError
from opensquilla.session.errors import SessionAgentNotFoundError, SessionUnavailableError
from opensquilla.session.management_service import create_session, patch_session


async def handle_sessions_create(params: dict | None, ctx: RpcContext) -> dict:
    try:
        return await create_session(params, ctx)
    except SessionAgentNotFoundError as exc:
        raise RpcHandlerError(exc.code, exc.message, details=exc.details) from exc
    except SessionUnavailableError as exc:
        raise RpcUnavailableError(str(exc)) from exc


async def handle_sessions_patch(params: dict | None, ctx: RpcContext) -> dict:
    try:
        return await patch_session(params, ctx)
    except SessionAgentNotFoundError as exc:
        raise RpcHandlerError(exc.code, exc.message, details=exc.details) from exc
    except SessionUnavailableError as exc:
        raise RpcUnavailableError(str(exc)) from exc
