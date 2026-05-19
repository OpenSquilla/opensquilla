"""Boundary tests for standalone chat REPL orchestration."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from opensquilla.cli import chat_standalone_repl
from opensquilla.cli.repl.stream import TurnResult, UsageSummary


class _FakeSessionManager:
    def __init__(self) -> None:
        self.get_or_create_calls: list[tuple[str, str]] = []

    async def get_or_create(self, session_key: str, agent_id: str = "main") -> object:
        self.get_or_create_calls.append((session_key, agent_id))
        return SimpleNamespace(session_key=session_key, agent_id=agent_id)


class _FakeServices:
    def __init__(self, *, workspace_dir: str | None = None) -> None:
        self.config = SimpleNamespace(workspace_dir=workspace_dir, workspace_strict=None)
        self.session_manager = _FakeSessionManager()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _prompt_from(values: list[str | None]):
    inputs = iter(values)

    async def prompt_user(label: str) -> str | None:
        return next(inputs)

    return prompt_user


async def _build_services(services: _FakeServices) -> _FakeServices:
    return services


def _build_route_envelope(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _tool_context_from_envelope(envelope: SimpleNamespace, **kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(
        session_key=envelope.session_key,
        channel_id=envelope.channel_id,
        sender_id=envelope.sender_id,
        source_name=envelope.source_name,
        is_owner=kwargs["is_owner"],
        workspace_dir=kwargs["workspace_dir"],
        workspace_strict=kwargs["workspace_strict"],
    )


def test_module_boundary_does_not_import_chat_cmd() -> None:
    source_path = Path(chat_standalone_repl.__file__ or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "opensquilla.cli.chat_cmd"
            if node.module == "opensquilla.cli":
                assert all(alias.name != "chat_cmd" for alias in node.names)
        elif isinstance(node, ast.Import):
            assert all(alias.name != "opensquilla.cli.chat_cmd" for alias in node.names)


@pytest.mark.asyncio
async def test_timeout_is_forwarded_to_stream_response() -> None:
    services = _FakeServices()
    runner = object()
    calls: list[dict[str, object]] = []

    async def stream_response(
        turn_runner: object,
        session_key: str,
        tool_context: object,
        message: str,
        **kwargs: object,
    ) -> TurnResult:
        calls.append(
            {
                "turn_runner": turn_runner,
                "session_key": session_key,
                "tool_context": tool_context,
                "message": message,
                "kwargs": kwargs,
            }
        )
        return TurnResult(
            text="reply",
            usage=UsageSummary(input_tokens=1, output_tokens=2),
        )

    await chat_standalone_repl.run_standalone_repl(
        "openrouter/test",
        "standalone:test",
        timeout=7.25,
        build_services_fn=lambda: _build_services(services),
        build_turn_runner_from_services_fn=lambda svc: runner,
        prompt_user_fn=_prompt_from(["hello", "/quit"]),
        stream_response=stream_response,
        build_cli_route_envelope_fn=_build_route_envelope,
        tool_context_from_envelope_fn=_tool_context_from_envelope,
        cli_sender_id_fn=lambda: "sender",
        resolve_workspace_strict_fn=lambda **kwargs: False,
    )

    assert calls == [
        {
            "turn_runner": runner,
            "session_key": "standalone:test",
            "tool_context": _tool_context_from_envelope(
                _build_route_envelope(
                    session_key="standalone:test",
                    agent_id="main",
                    channel_id="cli:chat",
                    sender_id="sender",
                    source_name="chat",
                ),
                is_owner=True,
                workspace_dir=None,
                workspace_strict=False,
            ),
            "message": "hello",
            "kwargs": {
                "model": "openrouter/test",
                "svc": services,
                "timeout": 7.25,
            },
        }
    ]


@pytest.mark.asyncio
async def test_workspace_options_are_reflected_in_tool_context(tmp_path: Path) -> None:
    services = _FakeServices(workspace_dir="/config/workspace")
    captured_contexts: list[SimpleNamespace] = []

    async def stream_response(
        turn_runner: object,
        session_key: str,
        tool_context: object,
        message: str,
        **kwargs: object,
    ) -> TurnResult:
        captured_contexts.append(tool_context)
        return TurnResult(text="reply")

    await chat_standalone_repl.run_standalone_repl(
        "openrouter/test",
        "standalone:test",
        workspace=str(tmp_path),
        workspace_strict=True,
        build_services_fn=lambda: _build_services(services),
        build_turn_runner_from_services_fn=lambda svc: object(),
        prompt_user_fn=_prompt_from(["hello", "/quit"]),
        stream_response=stream_response,
        build_cli_route_envelope_fn=_build_route_envelope,
        tool_context_from_envelope_fn=_tool_context_from_envelope,
        cli_sender_id_fn=lambda: "sender",
        resolve_workspace_strict_fn=lambda **kwargs: kwargs["cli_value"],
    )

    assert captured_contexts[0].workspace_dir == str(tmp_path)
    assert captured_contexts[0].workspace_strict is True
    assert captured_contexts[0].channel_id == "cli:chat"
    assert captured_contexts[0].sender_id == "sender"
    assert captured_contexts[0].source_name == "chat"
    assert captured_contexts[0].is_owner is True


@pytest.mark.asyncio
async def test_services_are_closed_in_finally() -> None:
    services = _FakeServices()

    async def prompt_user(label: str) -> str:
        raise KeyboardInterrupt

    await chat_standalone_repl.run_standalone_repl(
        "openrouter/test",
        "standalone:test",
        build_services_fn=lambda: _build_services(services),
        build_turn_runner_from_services_fn=lambda svc: object(),
        prompt_user_fn=prompt_user,
        build_cli_route_envelope_fn=_build_route_envelope,
        tool_context_from_envelope_fn=_tool_context_from_envelope,
        cli_sender_id_fn=lambda: "sender",
        resolve_workspace_strict_fn=lambda **kwargs: False,
    )

    assert services.closed is True


@pytest.mark.asyncio
async def test_new_rebuilds_state_and_tool_context() -> None:
    services = _FakeServices()
    contexts: list[SimpleNamespace] = []
    stream_calls: list[tuple[str, SimpleNamespace]] = []

    def tool_context_from_envelope(envelope: SimpleNamespace, **kwargs: object) -> SimpleNamespace:
        ctx = _tool_context_from_envelope(envelope, **kwargs)
        contexts.append(ctx)
        return ctx

    async def stream_response(
        turn_runner: object,
        session_key: str,
        tool_context: object,
        message: str,
        **kwargs: object,
    ) -> TurnResult:
        stream_calls.append((session_key, tool_context))
        return TurnResult(text="reply")

    await chat_standalone_repl.run_standalone_repl(
        "openrouter/test",
        "standalone:initial",
        build_services_fn=lambda: _build_services(services),
        build_turn_runner_from_services_fn=lambda svc: object(),
        prompt_user_fn=_prompt_from(["/new scratch", "after new", "/quit"]),
        stream_response=stream_response,
        build_cli_route_envelope_fn=_build_route_envelope,
        tool_context_from_envelope_fn=tool_context_from_envelope,
        cli_sender_id_fn=lambda: "sender",
        resolve_workspace_strict_fn=lambda **kwargs: False,
    )

    assert services.session_manager.get_or_create_calls[0] == ("standalone:initial", "main")
    new_session_key = services.session_manager.get_or_create_calls[1][0]
    assert new_session_key.startswith("agent:main:standalone:")
    assert stream_calls == [(new_session_key, contexts[1])]
    assert contexts[0].session_key == "standalone:initial"
    assert contexts[1].session_key == new_session_key


@pytest.mark.asyncio
async def test_injected_dependencies_cover_future_facade_compatibility() -> None:
    services = _FakeServices()
    runner = SimpleNamespace(name="turn-runner")
    route_calls: list[dict[str, object]] = []

    def build_route_envelope(**kwargs: object) -> SimpleNamespace:
        route_calls.append(dict(kwargs))
        return _build_route_envelope(**kwargs)

    async def stream_response(
        turn_runner: object,
        session_key: str,
        tool_context: object,
        message: str,
        **kwargs: object,
    ) -> TurnResult:
        assert turn_runner is runner
        assert session_key == "standalone:test"
        assert tool_context.sender_id == "facade-sender"
        assert message == "hello"
        assert kwargs["model"] == "openrouter/test"
        assert kwargs["svc"] is services
        return TurnResult(text="reply")

    await chat_standalone_repl.run_standalone_repl(
        "openrouter/test",
        "standalone:test",
        build_services_fn=lambda: _build_services(services),
        build_turn_runner_from_services_fn=lambda svc: runner,
        prompt_user_fn=_prompt_from(["hello", "/quit"]),
        stream_response=stream_response,
        build_cli_route_envelope_fn=build_route_envelope,
        tool_context_from_envelope_fn=_tool_context_from_envelope,
        cli_sender_id_fn=lambda: "facade-sender",
        resolve_workspace_strict_fn=lambda **kwargs: False,
    )

    assert route_calls == [
        {
            "session_key": "standalone:test",
            "agent_id": "main",
            "channel_id": "cli:chat",
            "sender_id": "facade-sender",
            "source_name": "chat",
        }
    ]
