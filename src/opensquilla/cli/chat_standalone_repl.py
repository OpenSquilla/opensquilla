"""Standalone TurnRunner chat REPL orchestration."""

from __future__ import annotations

import asyncio
import getpass
import inspect
import os
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from opensquilla.cli import chat_approval_prompts as _chat_approval_prompts
from opensquilla.cli import chat_stream_presenters
from opensquilla.cli import chat_stream_support as _chat_stream_support
from opensquilla.cli.chat_input_builders import (
    _image_prompt_and_attachments,
    _image_prompt_from_command,
)
from opensquilla.cli.chat_standalone_image_workflows import handle_standalone_image_command
from opensquilla.cli.chat_standalone_model_cost_workflows import (
    handle_standalone_cost_command,
    handle_standalone_model_command,
)
from opensquilla.cli.chat_standalone_path_workflows import handle_standalone_path_command
from opensquilla.cli.chat_standalone_session_workflows import (
    handle_standalone_clear_command,
    handle_standalone_compact_command,
    handle_standalone_new_command,
)
from opensquilla.cli.chat_standalone_slash_routes import match_standalone_slash_route
from opensquilla.cli.chat_standalone_status_workflows import (
    handle_standalone_models_command,
    handle_standalone_status_command,
)
from opensquilla.cli.chat_standalone_transcript_rewrite import (
    flush_before_standalone_rewrite,
)
from opensquilla.cli.chat_standalone_utility_route_workflows import (
    handle_standalone_utility_route_command,
)
from opensquilla.cli.repl.commands import is_exit_command, render_help_table
from opensquilla.cli.repl.session_state import ChatSessionState
from opensquilla.cli.repl.stream import StreamingRenderer, TurnResult, UsageSummary
from opensquilla.cli.ui import console, error_panel

_timeout_exception_message = _chat_stream_support._timeout_exception_message
_turn_stream_error_message = _chat_stream_support._turn_stream_error_message
_wrap_cli_turn_stream = _chat_stream_support._wrap_cli_turn_stream
_maybe_handle_approval = _chat_approval_prompts.maybe_handle_approval
_local_approval_resolver = _chat_approval_prompts.local_approval_resolver

AsyncOrSyncCallable = Callable[..., Any]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _clear_current_cancel() -> None:
    task = asyncio.current_task()
    if task is not None and hasattr(task, "uncancel"):
        task.uncancel()


def _cli_sender_id() -> str:
    raw = os.environ.get("USER")
    if raw and raw.strip():
        return raw.strip()
    try:
        return getpass.getuser() or "cli-user"
    except Exception:
        return "cli-user"


def _resolve_compaction_provider(
    provider_selector: Any,
    model_override: str | None = None,
) -> Any | None:
    if provider_selector is None:
        return None
    selector = provider_selector
    clone = getattr(provider_selector, "clone", None)
    if callable(clone):
        try:
            selector = clone()
        except Exception:  # noqa: BLE001
            selector = provider_selector
    if model_override and selector is not provider_selector:
        override = getattr(selector, "override_model", None)
        if callable(override):
            try:
                override(model_override)
            except Exception:  # noqa: BLE001
                pass
    resolver = getattr(selector, "resolve", None)
    if not callable(resolver):
        return None
    try:
        return resolver()
    except Exception:  # noqa: BLE001
        return None


async def run_standalone_repl(
    model: str | None,
    session_id: str | None,
    workspace: str | None = None,
    workspace_strict: bool | None = None,
    timeout: float | None = None,
    *,
    build_services_fn: AsyncOrSyncCallable | None = None,
    build_turn_runner_from_services_fn: AsyncOrSyncCallable | None = None,
    prompt_user_fn: Callable[[str], Awaitable[str | None]] | None = None,
    stream_response: AsyncOrSyncCallable | None = None,
    run_image_command: AsyncOrSyncCallable | None = None,
    image_prompt_from_command: Callable[[str], str] | None = None,
    cli_sender_id_fn: Callable[[], str] | None = None,
    flush_before_rewrite: AsyncOrSyncCallable | None = None,
    resolve_compaction_provider: AsyncOrSyncCallable | None = None,
    console_obj: Any | None = None,
    build_cli_route_envelope_fn: AsyncOrSyncCallable | None = None,
    tool_context_from_envelope_fn: AsyncOrSyncCallable | None = None,
    resolve_workspace_strict_fn: AsyncOrSyncCallable | None = None,
) -> None:
    """Interactive standalone REPL backed by TurnRunner."""

    if build_services_fn is None:
        from opensquilla.gateway import build_services

        build_services_fn = build_services
    if build_turn_runner_from_services_fn is None:
        from opensquilla.gateway import build_turn_runner_from_services

        build_turn_runner_from_services_fn = build_turn_runner_from_services
    if prompt_user_fn is None:
        from opensquilla.cli.repl.prompt import prompt_user

        prompt_user_fn = prompt_user
    if stream_response is None:
        stream_response = _stream_response_turnrunner
    if run_image_command is None:
        run_image_command = _handle_image_command_turnrunner
    if image_prompt_from_command is None:
        image_prompt_from_command = _image_prompt_from_command
    if cli_sender_id_fn is None:
        cli_sender_id_fn = _cli_sender_id
    if flush_before_rewrite is None:
        flush_before_rewrite = flush_before_standalone_rewrite
    if resolve_compaction_provider is None:
        resolve_compaction_provider = _resolve_compaction_provider
    if build_cli_route_envelope_fn is None:
        from opensquilla.gateway.routing import build_cli_route_envelope

        build_cli_route_envelope_fn = build_cli_route_envelope
    if tool_context_from_envelope_fn is None:
        from opensquilla.gateway.routing import tool_context_from_envelope

        tool_context_from_envelope_fn = tool_context_from_envelope
    if resolve_workspace_strict_fn is None:
        from opensquilla.cli.agent_cmd import _resolve_workspace_strict

        resolve_workspace_strict_fn = _resolve_workspace_strict

    output = console_obj or console
    svc = await _maybe_await(build_services_fn())
    try:
        session_manager = getattr(svc, "session_manager", None)
        if session_manager is None:
            raise RuntimeError("standalone chat requires session manager")

        session_key = session_id or f"agent:main:standalone:{uuid4().hex[:8]}"
        await session_manager.get_or_create(session_key, agent_id="main")
        active_workspace = workspace or getattr(getattr(svc, "config", None), "workspace_dir", None)
        effective_workspace_strict = await _maybe_await(
            resolve_workspace_strict_fn(
                cli_value=workspace_strict,
                config_value=getattr(getattr(svc, "config", None), "workspace_strict", None),
                entrypoint_default=bool(active_workspace),
            )
        )

        def build_tool_context(active_session_key: str) -> object:
            route_envelope = build_cli_route_envelope_fn(
                session_key=active_session_key,
                agent_id="main",
                channel_id="cli:chat",
                sender_id=cli_sender_id_fn(),
                source_name="chat",
            )
            return tool_context_from_envelope_fn(
                route_envelope,
                is_owner=True,
                workspace_dir=active_workspace,
                workspace_strict=effective_workspace_strict,
            )

        tool_ctx = build_tool_context(session_key)
        state = ChatSessionState(session_key=session_key, model=model)
        turn_runner = await _maybe_await(build_turn_runner_from_services_fn(svc))

        while True:
            try:
                user_input = await prompt_user_fn(state.prompt_state().label)
            except (EOFError, KeyboardInterrupt):
                output.print("\n[yellow]Goodbye.[/yellow]")
                break

            if user_input is None or is_exit_command(user_input):
                output.print("[yellow]Goodbye.[/yellow]")
                break

            stripped = user_input.strip()
            if not stripped:
                continue

            if stripped.startswith("/"):
                route_match = match_standalone_slash_route(stripped)
                if route_match is None:
                    output.print("[red]Unknown command.[/red] [dim]Use /help.[/dim]")
                    continue

                route_name = route_match.name
                parts = route_match.parts

                if route_name == "help":
                    output.print(render_help_table())
                    continue
                if route_name == "new":
                    session_key, tool_ctx, state = await handle_standalone_new_command(
                        parts,
                        session_manager=session_manager,
                        build_tool_context=build_tool_context,
                        model=model,
                    )
                    continue
                if route_name == "status":
                    handle_standalone_status_command(state)
                    continue
                if route_name == "models":
                    handle_standalone_models_command()
                    continue
                if route_name == "model":
                    updated_model = handle_standalone_model_command(parts, state)
                    if updated_model is not None:
                        model = updated_model
                    continue
                if route_name == "cost":
                    handle_standalone_cost_command(state)
                    continue
                if await handle_standalone_utility_route_command(
                    route_name,
                    stripped,
                    state,
                    config=getattr(svc, "config", None),
                ):
                    continue
                if route_name == "clear":
                    await handle_standalone_clear_command(
                        state,
                        services=svc,
                        flush_before_rewrite=flush_before_rewrite,
                    )
                    continue
                if route_name == "compact":
                    await handle_standalone_compact_command(
                        state,
                        services=svc,
                        model=model,
                        flush_before_rewrite=flush_before_rewrite,
                        resolve_compaction_provider=resolve_compaction_provider,
                    )
                    continue
                if route_name == "image":
                    await handle_standalone_image_command(
                        stripped,
                        parts,
                        state,
                        turn_runner=turn_runner,
                        tool_context=tool_ctx,
                        services=svc,
                        model=model,
                        timeout=timeout,
                        run_image_command=run_image_command,
                        image_prompt_from_command=image_prompt_from_command,
                    )
                    continue
                if route_name == "path":
                    await handle_standalone_path_command(
                        stripped,
                        parts,
                        state,
                        turn_runner=turn_runner,
                        tool_context=tool_ctx,
                        services=svc,
                        model=model,
                        timeout=timeout,
                        stream_response=stream_response,
                    )
                    continue
                output.print("[red]Unknown command.[/red] [dim]Use /help.[/dim]")
                continue

            result = await stream_response(
                turn_runner,
                session_key,
                tool_ctx,
                user_input,
                model=model,
                svc=svc,
                timeout=timeout,
            )
            state.transcript.add("user", user_input)
            state.transcript.add("assistant", result.text)
            state.usage.add(result.usage)
    finally:
        close = getattr(svc, "close", None)
        if callable(close):
            await _maybe_await(close())


async def _stream_response_turnrunner(
    turn_runner: object,
    session_key: str,
    tool_ctx: object,
    message: str,
    model: str | None = None,
    svc: object = None,
    timeout: float | None = None,
) -> TurnResult:
    """Stream TurnRunner response with Rich live display."""

    from opensquilla.engine.runtime import TurnRunner
    from opensquilla.engine.types import (
        ArtifactEvent,
        DoneEvent,
        ErrorEvent,
        RunHeartbeatEvent,
        TextDeltaEvent,
        ToolResultEvent,
        ToolUseStartEvent,
        WarningEvent,
    )
    from opensquilla.tools.types import ToolContext

    assert isinstance(turn_runner, TurnRunner)
    assert isinstance(tool_ctx, ToolContext)

    session_manager = getattr(svc, "session_manager", None) if svc is not None else None
    if session_manager is not None:
        persisted = await session_manager.append_message(
            session_key, role="user", content=message
        )
        if persisted is not None and isinstance(persisted.content, str):
            message = persisted.content

    resolver = _local_approval_resolver()
    usage: UsageSummary | None = None
    cancelled = False
    artifacts: list[dict[str, Any]] = []

    with StreamingRenderer() as renderer:
        try:
            stream = turn_runner.run(
                message, session_key, tool_context=tool_ctx, model=model, timeout=timeout
            )
            async for event in _wrap_cli_turn_stream(stream, svc):
                if isinstance(event, TextDeltaEvent):
                    renderer.append_text(event.text)
                elif isinstance(event, RunHeartbeatEvent):
                    renderer.pulse()
                elif isinstance(event, ToolUseStartEvent):
                    renderer.tool_call(event.tool_name)
                elif isinstance(event, ToolResultEvent):
                    await _maybe_handle_approval(event.result, renderer, resolver)
                elif isinstance(event, ArtifactEvent):
                    artifact = chat_stream_presenters.artifact_event_payload(event)
                    artifacts.append(artifact)
                    chat_stream_presenters.render_artifact_status(artifact, renderer)
                elif isinstance(event, WarningEvent):
                    console.print(f"[yellow]{event.message}[/yellow]")
                elif isinstance(event, ErrorEvent):
                    message_text = _turn_stream_error_message(event)
                    renderer.error(message_text)
                    return TurnResult(
                        text=renderer.buffer,
                        usage=usage,
                        error=message_text,
                        artifacts=artifacts,
                    )
                elif isinstance(event, DoneEvent):
                    usage = UsageSummary.from_done_event(event)
        except (KeyboardInterrupt, asyncio.CancelledError):
            _clear_current_cancel()
            cancelled = True
        except TimeoutError as exc:
            message_text = _timeout_exception_message(exc)
            renderer.error(message_text)
            return TurnResult(text=renderer.buffer, error=message_text)
        renderer.finalize(usage, cancelled=cancelled)
    return TurnResult(
        text=renderer.buffer,
        usage=usage,
        cancelled=cancelled,
        artifacts=artifacts,
    )


async def _handle_image_command_turnrunner(
    turn_runner: object,
    session_key: str,
    tool_ctx: object,
    command: str,
    model: str | None = None,
    svc: object = None,
    timeout: float | None = None,
) -> TurnResult:
    """Handle /image with TurnRunner attachments."""

    from opensquilla.engine.runtime import TurnRunner
    from opensquilla.engine.types import (
        DoneEvent,
        ErrorEvent,
        RunHeartbeatEvent,
        TextDeltaEvent,
        ToolUseStartEvent,
    )
    from opensquilla.tools.types import ToolContext

    assert isinstance(turn_runner, TurnRunner)
    assert isinstance(tool_ctx, ToolContext)

    try:
        prompt, attachments = _image_prompt_and_attachments(command)
    except ValueError as exc:
        console.print(error_panel(str(exc)))
        return TurnResult(error=str(exc))

    session_manager = getattr(svc, "session_manager", None) if svc is not None else None
    if session_manager is not None:
        persisted = await session_manager.append_message(
            session_key, role="user", content=prompt
        )
        if persisted is not None and isinstance(persisted.content, str):
            prompt = persisted.content

    usage: UsageSummary | None = None
    with StreamingRenderer() as renderer:
        try:
            stream = turn_runner.run(
                prompt,
                session_key,
                tool_context=tool_ctx,
                model=model,
                attachments=attachments,
                timeout=timeout,
            )
            async for event in _wrap_cli_turn_stream(stream, svc):
                if isinstance(event, TextDeltaEvent):
                    renderer.append_text(event.text)
                elif isinstance(event, RunHeartbeatEvent):
                    renderer.pulse()
                elif isinstance(event, ToolUseStartEvent):
                    renderer.tool_call(event.tool_name)
                elif isinstance(event, ErrorEvent):
                    message = _turn_stream_error_message(event)
                    renderer.error(message)
                    return TurnResult(text=renderer.buffer, usage=usage, error=message)
                elif isinstance(event, DoneEvent):
                    usage = UsageSummary.from_done_event(event)
        except TimeoutError as exc:
            message = _timeout_exception_message(exc)
            renderer.error(message)
            return TurnResult(text=renderer.buffer, error=message)
        renderer.finalize(usage)
    return TurnResult(text=renderer.buffer, usage=usage)
