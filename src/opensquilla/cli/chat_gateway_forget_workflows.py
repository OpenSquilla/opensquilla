"""Gateway forget slash-command workflow for interactive chat."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from opensquilla.cli.ui import console

ForgetServerApprovals = Callable[[object | None, str | None], Awaitable[bool]]


async def handle_gateway_forget_command(
    command: str,
    *,
    client: object | None,
    forget_server_approvals: ForgetServerApprovals,
) -> bool:
    """Handle gateway approval-cache clearing commands."""
    parts = command.split(maxsplit=1)
    if len(parts) < 2:
        if await forget_server_approvals(client, None):
            console.print(
                "[cyan]All cached approvals cleared.[/cyan] Future destructive "
                "ops will prompt again."
            )
        return True

    target = parts[1].strip()
    if await forget_server_approvals(client, target):
        console.print(
            f"[cyan]Cached approval for[/cyan] {target} "
            "[cyan]cleared[/cyan] (if one existed)."
        )
    return True
