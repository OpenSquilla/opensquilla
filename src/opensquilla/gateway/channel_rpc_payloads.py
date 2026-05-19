"""Gateway-owned channel management RPC payload adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opensquilla.channels.status_report import (
    ChannelStatusReport,
    ChannelStatusRow,
    build_channel_status_report,
)


async def channel_status_rpc_payload(
    config: Any | None,
    channel_manager: Any | None,
) -> dict[str, Any]:
    """Build the channels.status RPC wire payload."""

    report = await build_channel_status_report(config, channel_manager)
    return _channel_status_report_to_wire(report)


async def channel_logout_rpc_payload(
    params: Mapping[str, Any] | None,
    channel_manager: Any | None,
) -> dict[str, Any]:
    """Stop a channel and build the channels.logout RPC wire payload."""

    channel_name = _channel_name_param(params)
    manager = _require_channel(channel_manager, channel_name)
    await manager.stop_channel(channel_name)
    return {"status": "disconnected", "channel": channel_name}


async def channel_restart_rpc_payload(
    params: Mapping[str, Any] | None,
    channel_manager: Any | None,
) -> dict[str, Any]:
    """Restart a channel and build the channels.restart RPC wire payload."""

    channel_name = _channel_name_param(params)
    manager = _require_channel(channel_manager, channel_name)
    await manager.restart_channel(channel_name)
    return {"status": "restarted", "channel": channel_name}


def _channel_status_report_to_wire(report: ChannelStatusReport) -> dict[str, Any]:
    return {"channels": [_channel_status_row_to_wire(row) for row in report.rows]}


def _channel_status_row_to_wire(row: ChannelStatusRow) -> dict[str, Any]:
    return {
        "name": row.name,
        "connected": row.connected,
        "status": row.status,
        "bot_user_id": row.bot_user_id,
        "connected_since": row.connected_since,
        "restart_attempts": row.restart_attempts,
        "type": row.channel_type,
        "enabled": row.enabled,
        "configured": row.configured,
    }


def _channel_name_param(params: Mapping[str, Any] | None) -> str:
    channel_name = None
    if isinstance(params, Mapping):
        channel_name = params.get("channel") or params.get("name")
    if not channel_name:
        raise ValueError("channel name required")
    return str(channel_name)


def _require_channel(channel_manager: Any | None, channel_name: str) -> Any:
    if channel_manager is None or channel_manager.get(channel_name) is None:
        raise KeyError(f"Channel not found: {channel_name}")
    return channel_manager
