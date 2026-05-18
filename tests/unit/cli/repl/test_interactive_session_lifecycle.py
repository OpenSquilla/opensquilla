"""Lifecycle tests for `interactive_session()`.

Drives the long-lived `prompt_toolkit.Application` headlessly through a
pipe-input / DummyOutput pair so the asserts run without a TTY.
"""

from __future__ import annotations

import asyncio

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from opensquilla.cli.repl import prompt as prompt_module
from opensquilla.cli.repl.app import ChatApplication
from opensquilla.cli.repl.prompt import interactive_session


@pytest.mark.asyncio
async def test_interactive_session_yields_submitted_lines() -> None:
    """Two newline-terminated payloads on the pipe surface as two lines."""
    with create_pipe_input() as pipe:
        async with interactive_session(input=pipe, output=DummyOutput()) as handle:
            pipe.send_text("hello\n")
            first = await asyncio.wait_for(handle.next_line(), timeout=2.0)
            pipe.send_text("world\n")
            second = await asyncio.wait_for(handle.next_line(), timeout=2.0)

    assert first == "hello"
    assert second == "world"


@pytest.mark.asyncio
async def test_interactive_session_ctrl_d_returns_none() -> None:
    """Ctrl-D (\x04) surfaces as `None` from `next_line()`."""
    with create_pipe_input() as pipe:
        async with interactive_session(input=pipe, output=DummyOutput()) as handle:
            pipe.send_text("\x04")
            result = await asyncio.wait_for(handle.next_line(), timeout=2.0)

    assert result is None


@pytest.mark.asyncio
async def test_set_toolbar_mutates_shared_context() -> None:
    """`set_toolbar` writes into `_toolbar_context` and shows up in the
    bottom-toolbar HTML on the next call."""
    previous_status = prompt_module._toolbar_context.get("status")
    previous_model = prompt_module._toolbar_context.get("model")
    previous_suppress = prompt_module._toolbar_context.get("suppress")
    try:
        with create_pipe_input() as pipe:
            async with interactive_session(
                input=pipe,
                output=DummyOutput(),
                model="provider/some-model",
            ) as handle:
                handle.set_toolbar("status", "thinking…")
                # Sanity: shared dict carries the value the handle wrote.
                assert prompt_module._toolbar_context["status"] == "thinking…"
                # The bottom-toolbar callable reads the same dict on every
                # redraw. The themed callable renders `model` chip; assert
                # the model survives the round-trip through the handle.
                html = prompt_module._bottom_toolbar()
                assert "some-model" in html.value
    finally:
        prompt_module._toolbar_context["status"] = previous_status
        prompt_module._toolbar_context["model"] = previous_model
        prompt_module._toolbar_context["suppress"] = previous_suppress


@pytest.mark.asyncio
async def test_chat_application_submit_iter_round_trips_lines() -> None:
    """`ChatApplication.submit_iter()` yields each submitted line in order."""
    with create_pipe_input() as pipe:
        async with interactive_session(input=pipe, output=DummyOutput()) as handle:
            inner: ChatApplication = handle.application

            async def collect() -> list[str]:
                collected: list[str] = []
                async for line in inner.submit_iter():
                    collected.append(line)
                    if len(collected) == 2:
                        return collected
                return collected

            collector = asyncio.create_task(collect())
            pipe.send_text("alpha\n")
            pipe.send_text("beta\n")
            lines = await asyncio.wait_for(collector, timeout=2.0)

    assert lines == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_patch_stdout_restored_after_context_exit() -> None:
    """`patch_stdout` wraps the Application lifetime and unwraps on exit.

    We check `sys.stdout` identity before vs after the context manager; if
    `patch_stdout` did not unwind, the restored stream would still be the
    `StdoutProxy` wrapper.
    """
    import sys

    before = sys.stdout
    with create_pipe_input() as pipe:
        async with interactive_session(input=pipe, output=DummyOutput()):
            # During the context: stdout is wrapped (patch_stdout active).
            assert sys.stdout is not before
        # After exit: original stdout restored.
        assert sys.stdout is before
