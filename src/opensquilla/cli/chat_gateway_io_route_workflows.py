"""Gateway local I/O slash-route executor for interactive chat."""

from __future__ import annotations

from collections.abc import Sequence

from opensquilla.cli.chat_gateway_file_workflows import (
    AsyncFilePromptBuilder,
    GatewayUploadClient,
    handle_gateway_file_command,
)
from opensquilla.cli.chat_gateway_path_workflows import (
    GatewayLocalCheck,
    PathPromptBuilder,
    StreamResponse,
    handle_gateway_path_command,
)
from opensquilla.cli.repl.session_state import ChatSessionState

GATEWAY_IO_ROUTE_NAMES = frozenset({"path", "file"})


async def handle_gateway_io_route_command(
    route_name: str,
    command: str,
    parts: Sequence[str],
    state: ChatSessionState,
    *,
    client: GatewayUploadClient,
    elevated_state: dict[str, str | None],
    stream_response: StreamResponse,
    path_prompt_and_attachments: PathPromptBuilder,
    gateway_client_is_local: GatewayLocalCheck,
    remote_gateway_message: str,
    async_file_prompt_and_attachments: AsyncFilePromptBuilder,
) -> bool:
    """Handle gateway slash routes for local path/file inputs."""

    if route_name == "path":
        await handle_gateway_path_command(
            command,
            parts,
            state,
            client=client,
            elevated_state=elevated_state,
            stream_response=stream_response,
            path_prompt_and_attachments=path_prompt_and_attachments,
            gateway_client_is_local=gateway_client_is_local,
            remote_gateway_message=remote_gateway_message,
        )
        return True

    if route_name == "file":
        await handle_gateway_file_command(
            command,
            parts,
            state,
            client=client,
            elevated_state=elevated_state,
            stream_response=stream_response,
            async_file_prompt_and_attachments=async_file_prompt_and_attachments,
        )
        return True

    return False
