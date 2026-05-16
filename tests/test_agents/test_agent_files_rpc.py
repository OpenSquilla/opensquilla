from __future__ import annotations

import pytest

from opensquilla.agents.files_rpc import (
    AgentFilesUnavailableError,
    agent_files_get_rpc_payload,
    agent_files_list_rpc_payload,
    agent_files_set_rpc_payload,
)
from opensquilla.gateway.config import GatewayConfig


class _Registry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def list_agent_files(self, agent_id: str):
        self.calls.append(("list", (agent_id,)))
        return [{"name": "MEMORY.md", "status": "present"}]

    async def get_agent_file(self, agent_id: str, name: str):
        self.calls.append(("get", (agent_id, name)))
        return {"name": name, "content": "notes"}

    async def set_agent_file(self, agent_id: str, name: str, content: object):
        self.calls.append(("set", (agent_id, name, content)))
        return {"name": name, "path": name, "size": len(str(content))}


@pytest.mark.asyncio
async def test_agent_files_rpc_payloads_delegate_to_registry_with_normalized_agent_id() -> None:
    registry = _Registry()

    listed = await agent_files_list_rpc_payload(
        {"agentId": "Ops"},
        agent_registry=registry,
        config=None,
    )
    got = await agent_files_get_rpc_payload(
        {"agentId": "Ops", "name": "MEMORY.md"},
        agent_registry=registry,
        config=None,
    )
    written = await agent_files_set_rpc_payload(
        {"agentId": "Ops", "name": "MEMORY.md", "content": "notes"},
        agent_registry=registry,
        config=None,
    )

    assert listed == {"files": [{"name": "MEMORY.md", "status": "present"}]}
    assert got == {"name": "MEMORY.md", "content": "notes"}
    assert written == {"name": "MEMORY.md", "path": "MEMORY.md", "size": 5}
    assert registry.calls == [
        ("list", ("ops",)),
        ("get", ("ops", "MEMORY.md")),
        ("set", ("ops", "MEMORY.md", "notes")),
    ]


@pytest.mark.asyncio
async def test_agent_files_rpc_payloads_own_workspace_fallback_wire_shape(tmp_path) -> None:
    config = GatewayConfig(workspace_dir=str(tmp_path / "workspace"))

    written = await agent_files_set_rpc_payload(
        {"agentId": "main", "name": "MEMORY.md", "content": "notes"},
        agent_registry=None,
        config=config,
    )
    got = await agent_files_get_rpc_payload(
        {"agentId": "main", "name": "MEMORY.md"},
        agent_registry=None,
        config=config,
    )
    listed = await agent_files_list_rpc_payload(
        {"agentId": "main"},
        agent_registry=None,
        config=config,
    )

    assert written == {"name": "MEMORY.md", "path": "MEMORY.md", "size": 5}
    assert got == {"name": "MEMORY.md", "content": "notes"}
    memory_entry = next(row for row in listed["files"] if row["name"] == "MEMORY.md")
    assert memory_entry["status"] == "present"
    assert memory_entry["size"] == 5


@pytest.mark.asyncio
async def test_agent_files_rpc_payloads_report_unavailable_without_registry_or_workspace() -> None:
    with pytest.raises(AgentFilesUnavailableError, match="Agent registry not available"):
        await agent_files_list_rpc_payload(
            {"agentId": "main"},
            agent_registry=None,
            config=GatewayConfig(workspace_dir=None),
        )
