"""Session-domain exceptions translated by Gateway adapters."""

from __future__ import annotations

from typing import Any

from opensquilla.session.rpc_payload import session_agent_not_found_details


class SessionAgentNotFoundError(Exception):
    """Raised when session creation targets an unknown agent."""

    code = "agent.not_found"

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.message = f"Agent '{agent_id}' does not exist"
        self.details: Any = session_agent_not_found_details(agent_id)
        super().__init__(self.message)


class SessionUnavailableError(RuntimeError):
    """Raised when a session capability is not available in the current process."""


__all__ = [
    "SessionAgentNotFoundError",
    "SessionUnavailableError",
]
