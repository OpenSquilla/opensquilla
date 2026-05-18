"""prompt-toolkit backed input for the chat REPL."""

from __future__ import annotations

import asyncio
import re
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, FuzzyCompleter, WordCompleter
from prompt_toolkit.formatted_text import HTML, AnyFormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style

from opensquilla.cli.repl.commands import slash_words
from opensquilla.cli.ui import (
    ACCENT,
    ACCENT_DEEP,
    ACCENT_INK,
    ACCENT_SOFT,
    console,
)
from opensquilla.engine.commands import DEFAULT_REGISTRY, Surface, parse_surface
from opensquilla.paths import state_dir

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from prompt_toolkit.input.base import Input
    from prompt_toolkit.output.base import Output

    from opensquilla.cli.repl.app import ChatApplication


@dataclass(frozen=True)
class PromptConfig:
    force_plain: bool = False


_session: PromptSession[str] | None = None
_sessions: dict[Surface, PromptSession[str]] = {}
_toolbar_context: dict[str, str | None] = {
    "model": None,
    "session_id": None,
    "suppress": None,
    # Free-form transient status string surfaced in the bottom toolbar
    # (e.g. "thinking…" before the first streamed chunk lands). Mutated
    # by StreamingRenderer; cleared on the first chunk or on close.
    "status": None,
}


def _key_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("c-c")
    def _clear_input(event) -> None:
        event.app.current_buffer.reset()

    return bindings


def _history_path() -> str:
    path = state_dir("history", "chat")
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _build_meta_dict(surface: Surface) -> dict[str, str]:
    """Build word→description mapping from the command registry for a surface."""
    meta: dict[str, str] = {}
    for cmd in DEFAULT_REGISTRY.for_surface(surface):
        for word in cmd.words():
            meta[word] = cmd.description
    return meta


class _SlashCompleter(Completer):
    """Fuzzy completer that only fires when the buffer starts with '/'."""

    def __init__(self, surface: Surface) -> None:
        words = slash_words(surface)
        meta_dict = _build_meta_dict(surface)
        inner = WordCompleter(words, meta_dict=meta_dict, ignore_case=True, WORD=True)
        self._fuzzy = FuzzyCompleter(inner)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        yield from self._fuzzy.get_completions(document, complete_event)


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_PROMPT_STYLE = Style.from_dict({
    "completion-menu.completion": f"bg:{ACCENT_INK} {ACCENT_SOFT}",
    "completion-menu.completion.current": f"bg:{ACCENT} {ACCENT_INK} bold",
    "completion-menu.meta.completion": f"bg:{ACCENT_INK} {ACCENT_DEEP} italic",
    "completion-menu.meta.completion.current": f"bg:{ACCENT} {ACCENT_INK} italic",
    "completion-menu.multi-column-meta": f"bg:{ACCENT_INK} {ACCENT_DEEP}",
    "scrollbar.background": f"bg:{ACCENT_INK}",
    "scrollbar.button": f"bg:{ACCENT_DEEP}",
})


_PREFIX_RE = re.compile(r"^\[(?P<model>.+?) (?P<mode>\w+)\] (?P<role>\w+) > $")


def _bottom_toolbar() -> HTML:
    if _toolbar_context.get("suppress"):
        return HTML("")
    model = _toolbar_context.get("model") or ""
    session_id = _toolbar_context.get("session_id") or ""
    status = _toolbar_context.get("status") or ""

    model_short = model.rsplit("/", 1)[-1] if model else ""
    session_short = session_id.rsplit(":", 1)[-1] if session_id else session_id

    blocks: list[str] = []
    if model_short:
        blocks.append(
            f"<b><style bg='{ACCENT}' fg='{ACCENT_INK}'> {_html_escape(model_short)} </style></b>"
        )
    if session_short:
        blocks.append(
            f"<style bg='{ACCENT_INK}' fg='{ACCENT_SOFT}'> {_html_escape(session_short)} </style>"
        )
    if status:
        # Transient status block (e.g. "thinking…" before the first chunk).
        # Uses the ACCENT_DEEP bg + ACCENT_INK fg pair so it visually pairs
        # with the existing `/help` block on the right while being clearly
        # distinct from the model/session chips.
        blocks.append(
            f"<style bg='{ACCENT_DEEP}' fg='{ACCENT_INK}'> {_html_escape(status)} </style>"
        )
    blocks.append(f"<style bg='{ACCENT_INK}' fg='{ACCENT}'> ⏎ send </style>")
    blocks.append(f"<b><style bg='{ACCENT_SOFT}' fg='{ACCENT_INK}'> /help </style></b>")
    return HTML("".join(blocks))


def _format_prefix(prefix: str) -> AnyFormattedText:
    match = _PREFIX_RE.match(prefix)
    if not match:
        return prefix
    model_alias = _html_escape(match["model"])
    mode = _html_escape(match["mode"])
    role = _html_escape(match["role"])
    return HTML(
        f"<style fg='{ACCENT_DEEP}'>[</style>"
        f"<b><style fg='{ACCENT}'>{model_alias}</style></b>"
        f"<style fg='{ACCENT_SOFT}'> {mode}</style>"
        f"<style fg='{ACCENT_DEEP}'>]</style> "
        f"<b><style fg='{ACCENT}'>{role}</style></b>"
        f"<style fg='{ACCENT_DEEP}'> &gt; </style>"
    )


def _chrome_top(label: str = "you") -> None:
    console.print()
    console.rule(label, style="dim", characters="─", align="left")


def _chrome_bottom() -> None:
    console.print()


def _prompt_session(surface: Surface | str = Surface.CLI_GATEWAY) -> PromptSession[str]:
    global _session
    parsed = parse_surface(surface) if isinstance(surface, str) else surface
    if parsed not in _sessions:
        _sessions[parsed] = PromptSession(
            history=FileHistory(_history_path()),
            completer=_SlashCompleter(parsed),
            complete_while_typing=True,
            complete_in_thread=True,
            complete_style=CompleteStyle.MULTI_COLUMN,
            enable_history_search=True,
            key_bindings=_key_bindings(),
            bottom_toolbar=_bottom_toolbar,
            style=_PROMPT_STYLE,
        )
    if parsed == Surface.CLI_GATEWAY:
        _session = _sessions[parsed]
    return _sessions[parsed]


async def prompt_user(
    prefix: str = "[you] ",
    *,
    config: PromptConfig | None = None,
    surface: Surface | str = Surface.CLI_GATEWAY,
    model: str | None = None,
    session_id: str | None = None,
    chrome: bool = True,
) -> str | None:
    """Read one prompt line, using prompt-toolkit for real terminals.

    Set ``chrome=False`` to skip the top rule and bottom toolbar (used by
    approval prompts so they don't masquerade as chat-turn input).
    """
    cfg = config or PromptConfig()
    if cfg.force_plain or not sys.stdin.isatty() or not sys.stdout.isatty():
        loop = asyncio.get_running_loop()

        def _readline() -> str | None:
            sys.stdout.write(prefix)
            sys.stdout.flush()
            line = sys.stdin.readline()
            if line == "":
                return None
            return line.rstrip("\n")

        return await loop.run_in_executor(None, _readline)

    previous_suppress = _toolbar_context.get("suppress")
    if chrome:
        _toolbar_context["model"] = model
        _toolbar_context["session_id"] = session_id
        _toolbar_context["suppress"] = None
        _chrome_top("you")
    else:
        _toolbar_context["suppress"] = "1"

    try:
        with patch_stdout():
            return await _prompt_session(surface).prompt_async(_format_prefix(prefix))
    except EOFError:
        return None
    finally:
        if chrome:
            _chrome_bottom()
        else:
            _toolbar_context["suppress"] = previous_suppress


async def prompt_approval_inline(*, surface: Surface, approval_panel: str) -> str:
    """Inline approval: temporarily release the outer Application's
    terminal ownership via prompt-toolkit's ``in_terminal`` async context
    manager, run a fresh one-shot ``PromptSession`` as the sole owner of
    stdin/screen for the prompt, then resume the outer Application.

    The correct prompt-toolkit primitive for "pause this Application while
    something else owns the terminal, then resume" is ``in_terminal`` /
    ``run_in_terminal``. ``Application.suspend_to_background`` is the wrong
    tool — it sends SIGTSTP to the whole process group, the same effect as
    pressing Ctrl-Z in a shell. We want a temporary, scoped suspension that
    yields control back when the body completes, not a process-level stop
    that requires a shell ``fg`` to recover.

    The ``_approval_in_flight`` Event on the ``ChatApplication`` is set for
    the whole suspend window and cleared on resume so the output-lock
    acquirer can gate concurrent turn-task writes.
    """
    from prompt_toolkit.application.run_in_terminal import in_terminal

    chat_app = _chat_applications.get(surface)
    if chat_app is None:
        # No outer Application is running for this surface; run the fresh
        # one-shot session directly. This still avoids re-entering any
        # cached ``PromptSession`` so the legacy re-entry bug cannot recur.
        fresh = PromptSession(message=approval_panel)
        try:
            value = await fresh.prompt_async()
        except (EOFError, KeyboardInterrupt):
            return "d"
        return (value or "").strip().lower()

    chat_app.set_approval_in_flight(True)
    try:
        async with in_terminal():
            fresh = PromptSession(message=approval_panel)
            try:
                answer = await fresh.prompt_async()
            except (EOFError, KeyboardInterrupt):
                return "d"
            return (answer or "").strip().lower()
    finally:
        chat_app.set_approval_in_flight(False)


async def prompt_approval(
    prefix: str = "Decision [o/a/b/d]: ",
    *,
    surface: Surface = Surface.CLI_GATEWAY,
) -> str:
    """Thin wrapper that adapts the legacy prefix-style call to the
    inline approval path. Existing callers in ``chat_cmd.py`` keep
    working without source changes — they pass a prefix string and receive
    the lowercased answer.

    The default ``surface`` keeps legacy non-REPL callers (e.g. tool result
    handlers outside the new concurrent loop) on the gateway lookup path so
    no existing behavior changes. The new concurrent loop passes the active
    ``Surface`` explicitly so the standalone REPL hits its own
    ``ChatApplication`` instead of falling back to a bare ``PromptSession``.
    """
    return await prompt_approval_inline(
        surface=surface, approval_panel=prefix
    )


# ---------------------------------------------------------------------------- #
# Long-lived Application + interactive_session() context manager               #
# ---------------------------------------------------------------------------- #


_chat_applications: dict[Surface, ChatApplication] = {}


class InteractiveSessionHandle:
    """Handle returned by `interactive_session()`.

    Exposes the minimal contract concurrent chat callers need:
      - `await handle.next_line()` -> str | None  (None = Ctrl-D)
      - `handle.set_toolbar(key, value)`

    The handle wraps the underlying `ChatApplication`; the Application itself
    is intentionally not exposed to keep migration surface small.
    """

    def __init__(self, chat_app: ChatApplication) -> None:
        self._chat_app = chat_app

    async def next_line(self) -> str | None:
        return await self._chat_app.next_line()

    def set_toolbar(self, key: str, value: str | None) -> None:
        self._chat_app.set_toolbar(key, value)
        # Best-effort repaint; safe even when the Application has not yet
        # entered its run loop.
        try:
            self._chat_app.application.invalidate()
        except Exception:
            pass

    @property
    def application(self):  # type: ignore[no-untyped-def]
        """Expose the underlying ChatApplication for advanced callers / tests."""
        return self._chat_app


def _get_or_create_chat_app(
    surface: Surface,
    *,
    input: Input | None = None,
    output: Output | None = None,
) -> ChatApplication:
    # Local import to avoid a circular dependency with app.py at module load
    # (app.py only imports from `opensquilla.engine.commands`).
    from opensquilla.cli.repl.app import ChatApplication

    completer = _SlashCompleter(surface)
    auto_suggest = AutoSuggestFromHistory()
    # LockedFileHistory serializes store_string calls across concurrent writers
    # (input task plus any auxiliary prompts), keeping the history file from
    # interleaving bytes on multi-thread or yielding I/O paths.
    from opensquilla.cli.repl.app import LockedFileHistory

    history = LockedFileHistory(_history_path())

    # Tests routinely pass a custom pipe input / DummyOutput pair; never cache
    # those because their lifecycle is bound to the test fixture.
    if input is not None or output is not None:
        return ChatApplication(
            surface=surface,
            toolbar_context=_toolbar_context,
            bottom_toolbar=_bottom_toolbar,
            style=_PROMPT_STYLE,
            input=input,
            output=output,
            completer=completer,
            auto_suggest=auto_suggest,
            history=history,
        )

    cached = _chat_applications.get(surface)
    if cached is None:
        cached = ChatApplication(
            surface=surface,
            toolbar_context=_toolbar_context,
            bottom_toolbar=_bottom_toolbar,
            style=_PROMPT_STYLE,
            completer=completer,
            auto_suggest=auto_suggest,
            history=history,
        )
        _chat_applications[surface] = cached
    return cached


@asynccontextmanager
async def interactive_session(
    *,
    surface: Surface | str = Surface.CLI_GATEWAY,
    model: str | None = None,
    session_id: str | None = None,
    input: Input | None = None,
    output: Output | None = None,
) -> AsyncIterator[InteractiveSessionHandle]:
    """Long-lived prompt-toolkit Application for this surface.

    Yields a handle exposing:
      - `await handle.next_line() -> str | None`  (None = Ctrl-D)
      - `handle.set_toolbar(key, value)`

    Wraps `patch_stdout(raw=True)` for the entire lifetime so any Rich output
    written via `console.print` / `console.file.write` appears above the
    persistent prompt instead of overwriting it. The underlying
    `prompt_toolkit.Application` is launched in a background task and torn
    down on context exit.

    Existing callers (`prompt_user`, `prompt_approval`) are NOT routed through
    this context manager.
    The toolbar state dict (`_toolbar_context`) is shared, so setting
    `model` / `session_id` here remains visible to the legacy
    `_bottom_toolbar` callable used by `prompt_user`.
    """
    parsed = parse_surface(surface) if isinstance(surface, str) else surface
    chat_app = _get_or_create_chat_app(parsed, input=input, output=output)

    # Toolbar context lives in `_toolbar_context`; mutate before launching so
    # the first redraw renders the right model / session_id chips.
    previous_model = _toolbar_context.get("model")
    previous_session = _toolbar_context.get("session_id")
    previous_suppress = _toolbar_context.get("suppress")
    if model is not None:
        _toolbar_context["model"] = model
    if session_id is not None:
        _toolbar_context["session_id"] = session_id
    _toolbar_context["suppress"] = None

    handle = InteractiveSessionHandle(chat_app)
    app_task: asyncio.Task[None] | None = None
    stdout_cm = patch_stdout(raw=True)

    try:
        stdout_cm.__enter__()
        app_task = asyncio.create_task(
            chat_app.application.run_async(),
            name=f"chat-application-{parsed.value if hasattr(parsed, 'value') else parsed}",
        )
        # Give the Application's run loop a chance to attach to the
        # input/output pair before the caller starts pushing keystrokes
        # through `create_pipe_input`.
        await asyncio.sleep(0)
        yield handle
    finally:
        # Tear down the Application before unwinding patch_stdout so the
        # outgoing screen state restores cleanly.
        if app_task is not None and not app_task.done():
            try:
                chat_app.application.exit()
            except Exception:
                pass
            try:
                await asyncio.wait_for(app_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                app_task.cancel()
            except Exception:
                # Application exit raised; swallow so context manager still
                # exits cleanly (the alternative is to mask the original
                # exception inside `async with`).
                pass

        try:
            stdout_cm.__exit__(None, None, None)
        except Exception:
            pass

        _toolbar_context["model"] = previous_model
        _toolbar_context["session_id"] = previous_session
        _toolbar_context["suppress"] = previous_suppress
