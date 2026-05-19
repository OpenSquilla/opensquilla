"""RPC payload helpers for agent-facing surfaces."""

from __future__ import annotations

from typing import Any


def agents_list_response(agents: list[Any] | None = None) -> dict[str, Any]:
    return {"agents": list(agents or [])}


def agent_id_error_details(agent_id: str) -> dict[str, Any]:
    return {"agentId": agent_id}


__all__ = [
    "agent_id_error_details",
    "agents_list_response",
]
