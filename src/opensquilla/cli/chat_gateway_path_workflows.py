"""Gateway local path slash-command workflow for interactive chat."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from opensquilla.cli.repl.session_state import ChatSessionState
from opensquilla.cli.repl.stream import TurnResult
from opensquilla.cli.ui import console, error_panel

GatewayLocalCheck = Callable[[object], bool]
PathPromptBuilder = Callable[[str], tuple[str, list[dict[str, Any]]]]
StreamResponse = Callable[..., Awaitable[TurnResult]]


async def handle_gateway_path_command(
    command: str,
    parts: Sequence[str],
    state: ChatSessionState,
    *,
    client: object,
    elevated_state: dict[str, str | None],
    stream_response: StreamResponse,
    path_prompt_and_attachments: PathPromptBuilder,
    gateway_client_is_local: GatewayLocalCheck,
    remote_gateway_message: str,
) -> bool:
    """Handle gateway chat /path without uploading local file contents."""

    if len(parts) == 1 or not parts[1].strip():
        console.print("[red]Usage: /path <path> \\[prompt][/red]")
        return True

    if not gateway_client_is_local(client):
        console.print(error_panel(remote_gateway_message))
        return True

    try:
        prompt, attachments = path_prompt_and_attachments(command)
    except ValueError as exc:
        console.print(error_panel(str(exc)))
        return True

    result = await stream_response(
        client,
        state.session_key,
        prompt,
        elevated_state,
        attachments=attachments,
    )
    state.transcript.add("user", prompt)
    state.transcript.add("assistant", result.text)
    state.usage.add(result.usage)
    return True
