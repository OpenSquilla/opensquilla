"""Gateway-backed session queries for CLI workflows."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, cast

from opensquilla.cli.gateway_rpc import run_gateway_sync
from opensquilla.cli.url_utils import normalize_gateway_url


@dataclass(frozen=True)
class SessionGatewayUnavailable:
    """Gateway connection failed before the resume lookup could run."""

    message: str


@dataclass(frozen=True)
class SessionGatewayActionFailed:
    """Gateway rejected the resume lookup."""

    message: str


SessionResumeResolution = str | SessionGatewayUnavailable | SessionGatewayActionFailed


def list_sessions_from_gateway(*, limit: int, json_output: bool) -> dict[str, Any]:
    """Load recent sessions from the running gateway."""

    async def _run(client: Any) -> dict[str, Any]:
        return cast(dict[str, Any], await client.list_sessions(limit=limit))

    return cast(dict[str, Any], run_gateway_sync(_run, json_output=json_output))


def _resolved_key(payload: dict[str, Any], fallback: str) -> str:
    value = payload.get("session_key") or payload.get("key") or fallback
    return str(value)


def load_session_preview_from_gateway(
    session_id: str,
    *,
    json_output: bool,
) -> dict[str, Any]:
    """Load resolved session metadata and preview from the running gateway."""

    async def _run(client: Any) -> dict[str, Any]:
        resolved = cast(dict[str, Any], await client.resolve_session(session_id))
        preview = cast(
            dict[str, Any],
            await client.preview_sessions(keys=[_resolved_key(resolved, session_id)]),
        )
        return {"resolved": resolved, "preview": preview}

    return cast(dict[str, Any], run_gateway_sync(_run, json_output=json_output))


def resolve_session_key_from_gateway(session_id: str) -> SessionResumeResolution:
    """Resolve a session key while preserving resume's legacy error behavior."""

    async def _run() -> SessionResumeResolution:
        from opensquilla.cli.gateway_client import GatewayClient, GatewayRPCError

        client = GatewayClient()
        try:
            await client.connect(
                normalize_gateway_url(
                    os.environ.get("OPENSQUILLA_GATEWAY_URL", "ws://localhost:18790/ws")
                )
            )
            resolved = cast(dict[str, Any], await client.resolve_session(session_id))
            return _resolved_key(resolved, session_id)
        except SystemExit as exc:
            return SessionGatewayUnavailable(str(exc))
        except GatewayRPCError as exc:
            return SessionGatewayActionFailed(str(exc))
        finally:
            await client.close()

    return asyncio.run(_run())


def abort_session_from_gateway(
    session_id: str,
    *,
    json_output: bool,
) -> dict[str, Any]:
    """Resolve and abort a session through the running gateway."""

    async def _run(client: Any) -> dict[str, Any]:
        resolved = cast(dict[str, Any], await client.resolve_session(session_id))
        key = _resolved_key(resolved, session_id)
        result = await client.abort_session(key)
        if isinstance(result, dict):
            return {"resolved": resolved, **result}
        return {"resolved": resolved, "result": result}

    return cast(dict[str, Any], run_gateway_sync(_run, json_output=json_output))


def delete_session_from_gateway(session_id: str) -> dict[str, Any]:
    """Resolve and delete a session through the running gateway."""

    async def _run(client: Any) -> dict[str, Any]:
        resolved = cast(dict[str, Any], await client.resolve_session(session_id))
        key = _resolved_key(resolved, session_id)
        result = await client.delete_sessions([key])
        if isinstance(result, dict):
            return result
        return {"result": result}

    return cast(dict[str, Any], run_gateway_sync(_run))
