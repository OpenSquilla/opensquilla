"""Gateway control slash-route executor for interactive chat."""

from __future__ import annotations

from opensquilla.cli.chat_gateway_approvals_workflows import (
    handle_gateway_approvals_command,
)
from opensquilla.cli.chat_gateway_forget_workflows import handle_gateway_forget_command
from opensquilla.cli.chat_gateway_permissions_workflows import (
    ForgetServerApprovals,
    handle_gateway_permissions_command,
)
from opensquilla.cli.repl.session_state import ChatSessionState

GATEWAY_CONTROL_ROUTE_NAMES = frozenset({"permissions", "forget", "approvals"})


async def handle_gateway_control_route_command(
    route_name: str,
    command: str,
    state: ChatSessionState,
    elevated_state: dict[str, str | None],
    *,
    client: object,
    forget_server_approvals: ForgetServerApprovals,
) -> bool:
    """Handle gateway slash routes for permissions and approval cache controls."""

    if route_name == "permissions":
        await handle_gateway_permissions_command(
            command,
            state,
            elevated_state,
            client=client,
            forget_server_approvals=forget_server_approvals,
        )
        return True

    if route_name == "forget":
        await handle_gateway_forget_command(
            command,
            client=client,
            forget_server_approvals=forget_server_approvals,
        )
        return True

    if route_name == "approvals":
        await handle_gateway_approvals_command(command, client)
        return True

    return False
