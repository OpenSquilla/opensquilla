"""Output mutex + approval-suspend gate.

The output-lock contract pins the following invariants:

  - `ChatApplication.output_lock` is an `asyncio.Lock`.
  - The mirror Events `_approval_in_flight` and `_approval_idle` start in
    the idle-by-default state (`_approval_in_flight` cleared,
    `_approval_idle` set) and toggle inversely on `set_approval_in_flight`.
  - `write_through` blocks while an approval is in flight and unblocks
    immediately once `_approval_in_flight` clears.
  - The output lock guards write-and-flush only, NOT full Rich render:
    a long synthetic render running outside the lock MUST NOT delay a
    concurrent fast `write_through` beyond the microsecond write window.
"""

from __future__ import annotations

import asyncio
import io
import time

import pytest
from prompt_toolkit.input.base import DummyInput
from prompt_toolkit.output import DummyOutput

from opensquilla.cli import ui as cli_ui
from opensquilla.cli.repl.app import ChatApplication
from opensquilla.engine.commands import Surface


def _fresh_chat_app() -> ChatApplication:
    """Return a ChatApplication wired to DummyInput/DummyOutput for tests."""
    return ChatApplication(
        surface=Surface.CLI_GATEWAY,
        toolbar_context={
            "model": None,
            "session_id": None,
            "suppress": None,
            "status": None,
        },
        bottom_toolbar=lambda: "",
        style=None,
        input=DummyInput(),
        output=DummyOutput(),
    )


# --------------------------------------------------------------------------- #
# Lock / Event surface                                                        #
# --------------------------------------------------------------------------- #


def test_output_lock_is_asyncio_lock() -> None:
    """`chat_app.output_lock` MUST be an `asyncio.Lock` instance."""
    chat_app = _fresh_chat_app()
    assert isinstance(chat_app.output_lock, asyncio.Lock)


def test_approval_idle_event_starts_set() -> None:
    """At startup: `_approval_in_flight` cleared, `_approval_idle` set."""
    chat_app = _fresh_chat_app()
    assert chat_app._approval_in_flight.is_set() is False
    assert chat_app._approval_idle.is_set() is True


def test_approval_idle_toggles_inversely() -> None:
    """`set_approval_in_flight` keeps the mirror Events in lock-step."""
    chat_app = _fresh_chat_app()

    chat_app.set_approval_in_flight(True)
    assert chat_app._approval_in_flight.is_set() is True
    assert chat_app._approval_idle.is_set() is False

    chat_app.set_approval_in_flight(False)
    assert chat_app._approval_in_flight.is_set() is False
    assert chat_app._approval_idle.is_set() is True


# --------------------------------------------------------------------------- #
# Suspend-window gate                                                         #
# --------------------------------------------------------------------------- #


def test_write_through_respects_suspend_window(monkeypatch) -> None:
    """`write_through` MUST block while `_approval_in_flight` is set.

    Schedule a `write_through` as a task while the approval Event is set,
    confirm `wait_for` with a short timeout raises `TimeoutError` (the task
    is genuinely blocked), then clear the Event and assert the task drains
    promptly.
    """
    async def _drive() -> None:
        chat_app = _fresh_chat_app()
        buffer = io.StringIO()
        monkeypatch.setattr(cli_ui.console, "file", buffer, raising=True)

        chat_app.set_approval_in_flight(True)
        task = asyncio.create_task(chat_app.write_through("payload"))

        # Confirm the task does not finish during the suspend window.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.05)
        assert "payload" not in buffer.getvalue()

        chat_app.set_approval_in_flight(False)
        await asyncio.wait_for(task, timeout=1.0)
        assert buffer.getvalue() == "payload"

    asyncio.run(_drive())


def test_turn_completes_during_approval_does_not_print_until_resume(
    monkeypatch,
) -> None:
    """Mirror of the deferred approval test, now passing via the output lock.

    This is the same invariant as
    `test_write_through_respects_suspend_window` but framed as the
    end-to-end "turn finished a chunk during the approval window" path:
    the chunk MUST stay buffered (lock holder is parked on
    `wait_approval_idle`) until the inline approval session releases the
    suspend window.
    """
    async def _drive() -> None:
        chat_app = _fresh_chat_app()
        buffer = io.StringIO()
        monkeypatch.setattr(cli_ui.console, "file", buffer, raising=True)

        chat_app.set_approval_in_flight(True)
        task = asyncio.create_task(chat_app.write_through("CHUNK\n"))

        # Yield repeatedly so the task definitely enters write_through and
        # parks on the suspend gate inside the lock.
        for _ in range(10):
            await asyncio.sleep(0)
        assert "CHUNK" not in buffer.getvalue()

        chat_app.set_approval_in_flight(False)
        await asyncio.wait_for(task, timeout=1.0)
        assert "CHUNK\n" in buffer.getvalue()

    asyncio.run(_drive())


# --------------------------------------------------------------------------- #
# Input echo responsive under long render                                     #
# --------------------------------------------------------------------------- #


def test_input_echo_responsive_under_long_render(monkeypatch) -> None:
    """Lock-hold time MUST be bounded to the microsecond write window.

    The "long render" task simulates a 500ms Rich panel render *outside*
    the lock (the rendering happens in user code; the lock only protects
    the final write+flush). A concurrent fast `write_through` should
    acquire the lock and finish well within the long render's window. The
    threshold is generous (0.1s) to absorb scheduler jitter on CI.
    """
    async def _drive() -> None:
        chat_app = _fresh_chat_app()
        buffer = io.StringIO()
        monkeypatch.setattr(cli_ui.console, "file", buffer, raising=True)

        async def _long_render() -> None:
            # Simulate a Rich panel render that happens OUTSIDE the lock.
            # This is the output-lock contract: callers render into a StringIO
            # first, then acquire the lock only for the final write+flush.
            await asyncio.sleep(0.5)
            await chat_app.write_through("LONG\n")

        echo_elapsed: list[float] = []

        async def _fast_echo() -> None:
            start = time.monotonic()
            await chat_app.write_through("echo")
            echo_elapsed.append(time.monotonic() - start)

        # Give the long-render task a head start so it is already mid-sleep
        # when the fast echo races for the lock.
        long_task = asyncio.create_task(_long_render())
        await asyncio.sleep(0.01)
        echo_task = asyncio.create_task(_fast_echo())

        await asyncio.wait_for(echo_task, timeout=1.0)
        await asyncio.wait_for(long_task, timeout=2.0)

        # Fast echo MUST complete well before the long render finishes.
        assert echo_elapsed, "fast echo task did not record an elapsed sample"
        assert echo_elapsed[0] < 0.1, (
            f"fast echo blocked too long ({echo_elapsed[0]:.3f}s); "
            "output lock is holding through the render"
        )

        # Both writes must end up in the buffer.
        contents = buffer.getvalue()
        assert "echo" in contents
        assert "LONG\n" in contents

    asyncio.run(_drive())
