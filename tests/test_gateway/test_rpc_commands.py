from __future__ import annotations

import asyncio

from opensquilla.gateway.rpc import RpcContext, get_dispatcher


async def _list_for_surface(surface: str) -> dict:
    result = await get_dispatcher().dispatch(
        "r1",
        "commands.list_for_surface",
        {"surface": surface},
        RpcContext(conn_id="test"),
    )
    assert result.error is None, result.error
    assert result.payload is not None
    return result.payload


def test_commands_list_for_surface_accepts_legacy_web_alias() -> None:
    payload = asyncio.run(_list_for_surface("web"))

    assert payload["surface"] == "web_chat"


def test_web_catalog_includes_usage_rpc_execution() -> None:
    payload = asyncio.run(_list_for_surface("web"))
    usage = next(cmd for cmd in payload["commands"] if cmd["name"] == "/usage")

    assert usage["rpc_method"] == "usage.status"
    assert usage["execution"] == {
        "kind": "rpc",
        "action": "usage.status",
        "rpc_method": "usage.status",
    }


def test_cli_gateway_catalog_serializes_argument_choices() -> None:
    payload = asyncio.run(_list_for_surface("cli_gateway"))
    permissions = next(cmd for cmd in payload["commands"] if cmd["name"] == "/permissions")

    assert permissions["argument_choices"] == [
        {
            "value": "off",
            "description": "Sandboxed exec; approvals return to prompt mode.",
        },
        {"value": "on", "description": "Host exec, approvals required."},
        {
            "value": "bypass",
            "description": (
                "Host exec, approvals auto-granted; sensitive paths still blocked."
            ),
        },
        {
            "value": "full",
            "description": "Host exec, approvals skipped; sensitive paths bypassed.",
        },
        {"value": "status", "description": "Show current permissions mode."},
    ]


def test_channel_catalog_serialization_omits_rpc_params() -> None:
    payload = asyncio.run(_list_for_surface("channel"))

    assert payload["surface"] == "channel"
    assert all("rpc_params" not in cmd for cmd in payload["commands"])
    assert all("rpc_params" not in cmd.get("execution", {}) for cmd in payload["commands"])
