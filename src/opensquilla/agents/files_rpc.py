"""RPC payload builders for agent workspace files."""

from __future__ import annotations

from typing import Any, cast

from opensquilla.agents.workspace_files import (
    list_workspace_agent_files,
    read_workspace_agent_file,
    validate_workspace_file_extension,
    validate_workspace_file_name,
    workspace_file_root_for_config,
    write_workspace_agent_file,
)
from opensquilla.session.keys import normalize_agent_id


class AgentFilesUnavailableError(RuntimeError):
    """Raised when neither registry nor workspace fallback can serve files."""


def _workspace_root_or_unavailable(config: Any | None, agent_id: str):
    root = workspace_file_root_for_config(config, agent_id)
    if root is None:
        raise AgentFilesUnavailableError("Agent registry not available")
    return root


async def agent_files_list_rpc_payload(
    params: dict | None,
    *,
    agent_registry: Any | None,
    config: Any | None,
) -> dict[str, Any]:
    """Build the RPC wire payload for ``agents.files.list``."""

    if not isinstance(params, dict) or "agentId" not in params:
        raise ValueError("params.agentId is required")

    agent_id = normalize_agent_id(params["agentId"])

    if agent_registry is None:
        root = _workspace_root_or_unavailable(config, agent_id)
        return {"files": list_workspace_agent_files(root)}
    files = await agent_registry.list_agent_files(agent_id)
    return {"files": files}


async def agent_files_get_rpc_payload(
    params: dict | None,
    *,
    agent_registry: Any | None,
    config: Any | None,
) -> dict[str, Any]:
    """Build the RPC wire payload for ``agents.files.get``."""

    if not isinstance(params, dict):
        raise ValueError("params required: agentId, name")
    if "agentId" not in params:
        raise ValueError("params.agentId is required")
    if "name" not in params:
        raise ValueError("params.name is required")

    agent_id = normalize_agent_id(params["agentId"])
    name = validate_workspace_file_name(params["name"])

    if agent_registry is None:
        root = _workspace_root_or_unavailable(config, agent_id)
        safe_name, content = read_workspace_agent_file(root, name)
        return {"name": safe_name, "content": content}
    content = await agent_registry.get_agent_file(agent_id, name)
    return cast(dict[str, Any], content)


async def agent_files_set_rpc_payload(
    params: dict | None,
    *,
    agent_registry: Any | None,
    config: Any | None,
) -> dict[str, Any]:
    """Build the RPC wire payload for ``agents.files.set``."""

    if not isinstance(params, dict):
        raise ValueError("params required: agentId, name, content")
    if "agentId" not in params:
        raise ValueError("params.agentId is required")
    if "name" not in params:
        raise ValueError("params.name is required")
    if "content" not in params:
        raise ValueError("params.content is required")

    agent_id = normalize_agent_id(params["agentId"])
    name = validate_workspace_file_name(params["name"])
    validate_workspace_file_extension(name)
    content = params["content"]

    if agent_registry is None:
        root = _workspace_root_or_unavailable(config, agent_id)
        return write_workspace_agent_file(root, name, content)
    result = await agent_registry.set_agent_file(agent_id, name, content)
    return cast(dict[str, Any], result)


__all__ = [
    "AgentFilesUnavailableError",
    "agent_files_get_rpc_payload",
    "agent_files_list_rpc_payload",
    "agent_files_set_rpc_payload",
]
