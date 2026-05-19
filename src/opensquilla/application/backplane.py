"""Application-facing contract backplane.

The backplane is a lightweight composition seam for ports from
``opensquilla.contracts``. It lets application use cases depend on stable
contracts without importing concrete tool, session, provider, channel, or
memory implementations.
"""

from __future__ import annotations

from dataclasses import dataclass

from opensquilla.contracts import (
    ChannelIngressPort,
    IncomingMessage,
    MemoryPort,
    MemoryQuery,
    MemoryResult,
    ProviderFactoryPort,
    ProviderPort,
    SessionRecord,
    SessionStorePort,
    ToolContext,
    ToolPolicyPort,
    ToolRegistryPort,
    ToolSpec,
)


@dataclass(frozen=True)
class ContractBackplane:
    """Optional contract-port bundle for application-layer composition.

    Concrete subsystems stay outside the application package. Callers inject
    whichever ports are available, and helper methods fan out through the
    contracts package rather than through Gateway/Engine/Provider internals.
    """

    tool_registry: ToolRegistryPort | None = None
    tool_policy: ToolPolicyPort | None = None
    session_store: SessionStorePort | None = None
    provider_factory: ProviderFactoryPort | None = None
    channel_ingress: ChannelIngressPort | None = None
    memory: MemoryPort | None = None

    def list_tool_specs(self, context: ToolContext | None = None) -> list[ToolSpec]:
        """Return contract tool specs, filtered by the optional policy port."""

        if self.tool_registry is None:
            return []
        specs = self.tool_registry.list_specs(context)
        if self.tool_policy is None or context is None:
            return specs
        return self.tool_policy.filter_tools(specs, context)

    async def get_session(self, session_key: str) -> SessionRecord | None:
        """Read a session through the contract store port when available."""

        if self.session_store is None:
            return None
        return await self.session_store.get_session(session_key)

    async def search_memory(
        self,
        text: str,
        *,
        agent_id: str = "main",
        limit: int = 5,
    ) -> list[MemoryResult]:
        """Search memory through the contract port when available."""

        if self.memory is None:
            return []
        return await self.memory.search(MemoryQuery(text=text, agent_id=agent_id, limit=limit))

    async def save_memory(
        self,
        *,
        agent_id: str,
        text: str,
        metadata: dict[str, object] | None = None,
    ) -> str | None:
        """Save memory through the contract port when available."""

        if self.memory is None:
            return None
        return await self.memory.save(agent_id=agent_id, text=text, metadata=metadata)

    def build_provider(self, provider_id: str, config: dict[str, object]) -> ProviderPort | None:
        """Build a provider through the contract factory port when available."""

        if self.provider_factory is None:
            return None
        return self.provider_factory.build_provider(provider_id, config)

    async def handle_channel_message(
        self,
        channel_name: str,
        message: IncomingMessage,
    ) -> None:
        """Dispatch a normalized incoming channel message through the channel port."""

        if self.channel_ingress is None:
            return
        await self.channel_ingress.handle_incoming(channel_name, message)


__all__ = ["ContractBackplane"]
