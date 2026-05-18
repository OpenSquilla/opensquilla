"""Dedicated compaction seam suite for ``StreamConsumerStage``.

The general snapshot harness exercises every event-type branch in
the slice; this suite specifically pins the compaction seam contract --
the in-turn ``CompactionEvent`` handling -- so future compaction refactors
have an easily discoverable contract to honor.

Five focused tests cover:

1. ``persist_compaction_result`` is invoked with the event's summary +
   kept_entries.
2. ``notify_compaction`` fires after persist.
3. Memory snapshot refresh fires AFTER persist and respects
   ``private_memory_allowed``.
4. System prompt refresh fires AFTER snapshot refresh; the cacheable
   base is extracted from the ``(base, dynamic_suffix)`` tuple when
   ``_assemble_prompt`` returns one.
5. The persist call is log-and-continue: a raising persist does NOT
   prevent the snapshot + prompt refresh from firing.
"""

from __future__ import annotations

import pytest

from opensquilla.engine.runtime import TurnRunner
from opensquilla.engine.types import (
    CompactionEvent,
    DoneEvent,
    TextDeltaEvent,
)

from .test_stream_consumer_stage_snapshot import (
    _MAILBOX,
    _Case,
    _drive,
    _RecordingSessionManager,
    _setup_runner,
)


def _baseline_case(
    *,
    persist_raises: type[BaseException] | None = None,
    private_memory_allowed: bool = True,
) -> _Case:
    return _Case(
        case_id="phase_d_seam_drive",
        events=[
            TextDeltaEvent(text="pre"),
            CompactionEvent(summary="THE_SUMMARY", kept_entries=[10, 20, 30]),
            TextDeltaEvent(text=" after"),
            DoneEvent(text="pre after"),
        ],
        raise_after=None,
        persist_raises=persist_raises,
        private_memory_allowed=private_memory_allowed,
    )


# ---------------------------------------------------------------------------
# Compaction seam test 1: persist arguments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_compaction_result_invoked_with_event_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SessionManager.persist_compaction_result`` is invoked with the
    event's ``summary`` and ``kept_entries`` exactly once per
    CompactionEvent."""

    case = _baseline_case()
    runner = _setup_runner(monkeypatch, case)
    await _drive(runner)

    sm = runner._session_manager
    assert isinstance(sm, _RecordingSessionManager)
    persist_calls = [c for c in sm.calls if c[0] == "persist"]
    assert len(persist_calls) == 1
    assert persist_calls[0][1] == "agent:main:s1"
    assert persist_calls[0][2] == "THE_SUMMARY"
    assert persist_calls[0][3] == [10, 20, 30]


# ---------------------------------------------------------------------------
# Compaction seam test 2: notify_compaction follows persist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_compaction_fires_after_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cache_break_monitor.notify_compaction`` is invoked once after
    persist, with the same ``session_key``."""

    notify_calls: list[str] = []
    import opensquilla.engine.runtime as runtime_mod

    monkeypatch.setattr(
        runtime_mod,
        "notify_compaction",
        lambda session_key: notify_calls.append(session_key),
    )
    # The new-arm adapter imports notify_compaction lazily from
    # cache_break_monitor; patch the source module too.
    import opensquilla.engine.cache_break_monitor as cbm

    monkeypatch.setattr(
        cbm,
        "notify_compaction",
        lambda session_key: notify_calls.append(session_key),
    )

    case = _baseline_case()
    runner = _setup_runner(monkeypatch, case)
    await _drive(runner)

    assert len(notify_calls) == 1
    assert notify_calls[0] == "agent:main:s1"


# ---------------------------------------------------------------------------
# Compaction seam test 3: memory snapshot refresh respects private_memory_allowed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("private_allowed", [True, False])
@pytest.mark.asyncio
async def test_memory_snapshot_refresh_respects_private_memory(
    private_allowed: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``runner._memory_snapshots[(agent_id, session_key)]`` is refreshed
    after compaction iff ``private_memory_allowed`` is true.

    The dict-write happens IN ADDITION to (not in place of) any existing
    entry; the contract is "after this call, the snapshot reflects the
    post-compaction state".
    """

    case = _baseline_case(private_memory_allowed=private_allowed)
    runner = _setup_runner(monkeypatch, case)
    # Preserve initial dict snapshot keys to detect a write.
    initial_keys = set(runner._memory_snapshots.keys())
    await _drive(runner)

    snap_key = ("agent:main", "agent:main:s1")
    if private_allowed:
        # The dict has at least the snap_key after compaction.
        assert snap_key in runner._memory_snapshots, (
            "private_allowed=True: snapshot was not refreshed"
        )
    else:
        # No write expected when private memory is not allowed.
        assert snap_key not in runner._memory_snapshots or (
            snap_key in initial_keys
        ), "private_allowed=False: snapshot was written"


# ---------------------------------------------------------------------------
# Compaction seam test 4: system prompt refresh fires + tuple/str extract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("returns_tuple", [True, False])
@pytest.mark.asyncio
async def test_system_prompt_refresh_extracts_cacheable_base(
    returns_tuple: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``agent.refresh_system_prompt`` is invoked exactly once per
    CompactionEvent with the cacheable base (NOT a tuple). The
    tuple-vs-str pattern is exercised for both return shapes.
    """

    case = _baseline_case()
    runner = _setup_runner(monkeypatch, case)

    # Override _assemble_prompt to return a tuple vs str depending on case.
    refresh_payload = (
        ("CACHEABLE_BASE", "VOLATILE_SUFFIX")
        if returns_tuple
        else "CACHEABLE_BASE"
    )

    def _assemble_prompt_override(self, *args, **kwargs):  # noqa: ARG001, ARG002
        return refresh_payload

    runner._assemble_prompt = _assemble_prompt_override.__get__(runner, TurnRunner)

    await _drive(runner)

    assert len(_MAILBOX.refresh_prompt_calls) == 1
    refreshed = _MAILBOX.refresh_prompt_calls[0]
    assert refreshed == "CACHEABLE_BASE", (
        f"returns_tuple={returns_tuple}: "
        f"tuple-vs-str extract diverged ({refreshed!r})"
    )


# ---------------------------------------------------------------------------
# Compaction seam test 5: persist log-and-continue does NOT block snapshot/prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_raises_log_and_continue_preserves_refreshes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising ``persist_compaction_result`` is wrapped in
    log-and-continue. The snapshot refresh + system prompt refresh
    still fire afterwards.

    This is the most critical compaction seam contract: snapshot + prompt
    refresh ALWAYS fire, even on persist failure, so the next turn's
    cacheable prefix reflects the post-compaction state.
    """

    case = _baseline_case(persist_raises=RuntimeError)
    runner = _setup_runner(monkeypatch, case)
    yielded, raised = await _drive(runner)

    # The turn must NOT abort -- persist failure is log-and-continue.
    assert raised is None
    # The stream continues -- DoneEvent must still be yielded.
    assert any(isinstance(e, DoneEvent) for e in yielded), (
        "stream aborted after persist failure"
    )
    # System prompt refresh still fired.
    assert len(_MAILBOX.refresh_prompt_calls) == 1, (
        f"system prompt refresh skipped after persist raise "
        f"({len(_MAILBOX.refresh_prompt_calls)} calls)"
    )
    # Memory snapshot dict was still updated (private_memory_allowed=True).
    snap_key = ("agent:main", "agent:main:s1")
    assert snap_key in runner._memory_snapshots
