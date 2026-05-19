"""Tests for the context-overflow policy branches."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from opensquilla.gateway import context_overflow
from opensquilla.gateway.config import ContextOverflowPolicy, GatewayConfig
from opensquilla.gateway.context_overflow import (
    OverflowOutcome,
    apply_context_overflow_policy,
)
from opensquilla.gateway.rpc_chat import _enforce_context_overflow
from opensquilla.session.compaction import CompactionConfig


@dataclass
class _FakeEntry:
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    reasoning_content: str | None = None
    token_count: int | None = None


class _FakeSessionManager:
    """Minimal session-manager stub: tracks compact() calls + transcript."""

    def __init__(self, transcript: list[_FakeEntry]) -> None:
        self._transcript = list(transcript)
        self.compact_calls: list[tuple[str, int, object | None]] = []

    async def get_transcript(self, session_key: str) -> list[_FakeEntry]:
        return list(self._transcript)

    async def compact(self, session_key: str, budget: int, config=None) -> str:
        # Simulate a successful compaction: collapse history into a single
        # short summary entry so the next estimate fits easily.
        self.compact_calls.append((session_key, budget, config))
        self._transcript = [_FakeEntry(content="[summary]")]
        return "[summary]"


class _InsufficientCompactionSessionManager(_FakeSessionManager):
    async def compact(self, session_key: str, budget: int, config=None) -> str:
        self.compact_calls.append((session_key, budget, config))
        return "[summary]"


class _FailingCompactionSessionManager(_FakeSessionManager):
    async def compact(self, session_key: str, budget: int, config=None) -> str:
        self.compact_calls.append((session_key, budget, config))
        raise RuntimeError("compact boom")


class _LegacyCompactSessionManager(_FakeSessionManager):
    async def compact(self, session_key: str, budget: int) -> str:
        self.compact_calls.append((session_key, budget, None))
        self._transcript = [_FakeEntry(content="[summary]")]
        return "[summary]"


class _SummaryReadFailureSessionManager(_FakeSessionManager):
    async def get_summaries(self, session_key: str) -> list[Any]:
        raise RuntimeError(f"summary store unavailable for {session_key}")


class _FakeCompactionProvider:
    provider_name = "openai"

    def __init__(self) -> None:
        self._api_key = "overflow-provider-key"
        self._model = "provider/model"
        self._base_url = "https://openrouter.ai/api/v1"

    @property
    def model(self) -> str:
        return self._model


class _FakeSelectorClone:
    def __init__(self, provider: _FakeCompactionProvider) -> None:
        self.provider = provider
        self.override_calls: list[str] = []

    def override_model(self, model: str) -> None:
        self.override_calls.append(model)
        self.provider._model = model

    def resolve(self) -> _FakeCompactionProvider:
        return self.provider


class _FakeProviderSelector:
    def __init__(self) -> None:
        self.provider = _FakeCompactionProvider()
        self.clone_instance = _FakeSelectorClone(self.provider)
        self.override_calls: list[str] = []

    def clone(self) -> _FakeSelectorClone:
        return self.clone_instance

    def override_model(self, model: str) -> None:
        self.override_calls.append(model)

    def resolve(self) -> _FakeCompactionProvider:
        return self.provider


class _TurnCompactionMarker:
    def __init__(self, compacted: set[str] | None = None) -> None:
        self.compacted = set(compacted or set())
        self.mark_calls: list[str] = []
        self.clear_calls: list[str] = []

    def has_compacted_this_turn(self, session_key: str) -> bool:
        return session_key in self.compacted

    def mark_compacted_this_turn(self, session_key: str) -> None:
        self.mark_calls.append(session_key)
        self.compacted.add(session_key)

    def clear_compacted_this_turn(self, session_key: str) -> None:
        self.clear_calls.append(session_key)
        self.compacted.discard(session_key)


def _cfg(
    policy: ContextOverflowPolicy,
    budget: int = 20,
    *,
    flush_enabled: bool = False,
    flush_timeout_seconds: float = 5.0,
    flush_background_timeout_seconds: float = 60.0,
    flush_compaction_requires_safe_receipt: bool = False,
) -> GatewayConfig:
    return GatewayConfig(
        context_overflow_policy=policy,
        context_budget_tokens=budget,
        memory={
            "flush_enabled": flush_enabled,
            "flush_timeout_seconds": flush_timeout_seconds,
            "flush_background_timeout_seconds": flush_background_timeout_seconds,
            "flush_compaction_requires_safe_receipt": (
                flush_compaction_requires_safe_receipt
            ),
        },
    )


def _history(n_entries: int, chars_per_entry: int) -> list[_FakeEntry]:
    # estimate_tokens rounds chars/4, so ~4 chars ≈ 1 token.
    return [_FakeEntry(content="x" * chars_per_entry) for _ in range(n_entries)]


@pytest.mark.asyncio
async def test_default_policy_is_auto_summarize() -> None:
    """GatewayConfig default policy must be AUTO_SUMMARIZE per S4 AC."""

    cfg = GatewayConfig()
    assert cfg.context_overflow_policy == ContextOverflowPolicy.AUTO_SUMMARIZE
    assert cfg.context_budget_tokens == 100_000


@pytest.mark.asyncio
async def test_policy_enum_has_exactly_three_members() -> None:
    """Locks S4 AC: exactly three policy options, stable string values."""

    values = {m.value for m in ContextOverflowPolicy}
    assert values == {"auto_summarize", "hard_truncate", "refuse"}


@pytest.mark.asyncio
async def test_under_budget_is_noop() -> None:
    cfg = _cfg(ContextOverflowPolicy.REFUSE, budget=10_000)
    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="hi",
        transcript=_history(1, 4),
        session_key="s1",
    )
    assert outcome.over_budget is False
    assert outcome.refusal is None


@pytest.mark.asyncio
async def test_refuse_returns_stable_error_envelope() -> None:
    """REFUSE short-circuits with the documented error envelope."""

    cfg = _cfg(ContextOverflowPolicy.REFUSE, budget=5)
    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="hello",
        transcript=_history(4, 40),
        session_key="s-refuse",
    )
    assert outcome.over_budget is True
    assert outcome.refusal is not None
    env = outcome.refusal
    assert env["status"] == "error"
    assert env["error_class"] == "context_overflow"
    assert env["retry_allowed"] is False
    assert isinstance(env["user_message"], str) and env["user_message"]


@pytest.mark.asyncio
async def test_gateway_context_overflow_counts_tool_call_arguments() -> None:
    cfg = _cfg(ContextOverflowPolicy.REFUSE, budget=100)
    transcript = [
        _FakeEntry(
            content="small visible answer",
            token_count=1,
            tool_calls=[
                {
                    "type": "tool_use",
                    "tool_use_id": "write-stale",
                    "name": "write_file",
                    "input": {"path": "index.html", "content": "x" * 5000},
                }
            ],
        )
    ]

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="next",
        transcript=transcript,
        session_key="s-tool-payload",
    )

    assert outcome.over_budget is True
    assert outcome.refusal is not None
    assert outcome.estimated_tokens > cfg.context_budget_tokens


@pytest.mark.asyncio
async def test_gateway_context_overflow_counts_reasoning_content() -> None:
    cfg = _cfg(ContextOverflowPolicy.REFUSE, budget=100)
    transcript = [
        _FakeEntry(
            content="small visible answer",
            token_count=1,
            reasoning_content="reasoning " + ("r" * 5000),
        )
    ]

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="next",
        transcript=transcript,
        session_key="s-reasoning-payload",
    )

    assert outcome.over_budget is True
    assert outcome.refusal is not None
    assert outcome.estimated_tokens > cfg.context_budget_tokens


@pytest.mark.asyncio
async def test_hard_truncate_drops_oldest_history_until_fits() -> None:
    """HARD_TRUNCATE removes oldest entries one at a time to fit the budget."""

    cfg = _cfg(ContextOverflowPolicy.HARD_TRUNCATE, budget=10)
    transcript = _history(5, 40)  # 5 * 40 chars ≈ 50 tokens per estimate_tokens
    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=transcript,
        session_key="s-trunc",
    )
    assert outcome.over_budget is True
    assert outcome.truncated_entries > 0
    # Some entries were dropped; remaining history is shorter than input.
    assert len(outcome.trimmed_history) == len(transcript) - outcome.truncated_entries


@pytest.mark.asyncio
async def test_auto_summarize_invokes_compaction_and_retries_once() -> None:
    """AUTO_SUMMARIZE retries only after compacted payload is inside budget."""

    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _FakeSessionManager(_history(6, 40))
    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="s-auto",
        session_manager=sm,
    )
    assert outcome.over_budget is True
    assert outcome.summarized is True
    assert outcome.retried is True
    assert len(sm.compact_calls) == 1
    assert sm.compact_calls[0][0] == "s-auto"
    assert outcome.tokens_after is not None
    assert outcome.remaining_budget_tokens is not None
    assert outcome.tokens_after <= outcome.budget_tokens


@pytest.mark.asyncio
async def test_auto_summarize_emits_started_and_completed_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _FakeSessionManager(_history(6, 40))
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        context_overflow,
        "notify_compaction",
        lambda session_key, **payload: events.append((session_key, payload)),
    )

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="s-auto-events",
        session_manager=sm,
    )

    assert outcome.summarized is True
    assert [(key, payload["status"]) for key, payload in events] == [
        ("s-auto-events", "started"),
        ("s-auto-events", "completed"),
    ]
    assert all(payload["source"] == "automatic" for _, payload in events)
    assert all(payload["phase"] == "gateway_auto_summarize" for _, payload in events)


@pytest.mark.asyncio
async def test_auto_summarize_emits_failed_event_on_compaction_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _FailingCompactionSessionManager(_history(6, 40))
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        context_overflow,
        "notify_compaction",
        lambda session_key, **payload: events.append((session_key, payload)),
    )

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="s-auto-failed",
        session_manager=sm,
    )

    assert outcome.summarized is False
    assert outcome.reason == "compaction_failed"
    assert [payload["status"] for _, payload in events] == ["started", "failed"]
    assert "compact boom" in events[-1][1]["message"]


@pytest.mark.asyncio
async def test_auto_summarize_refuses_when_compaction_still_exceeds_budget() -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _InsufficientCompactionSessionManager(_history(6, 40))

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="s-insufficient",
        session_manager=sm,
    )

    assert outcome.over_budget is True
    assert outcome.summarized is False
    assert outcome.retried is False
    assert outcome.reason == "compaction_insufficient"
    assert outcome.refusal is not None
    assert outcome.refusal["error"]["reason"] == "compaction_insufficient"
    assert len(sm.compact_calls) == 1


@pytest.mark.asyncio
async def test_auto_summarize_refuses_when_summary_context_cannot_be_verified() -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _SummaryReadFailureSessionManager(_history(6, 40))

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="s-summary-fail",
        session_manager=sm,
    )

    assert outcome.over_budget is True
    assert outcome.summarized is False
    assert outcome.retried is False
    assert outcome.reason == "compaction_failed"
    assert outcome.refusal is not None
    assert outcome.refusal["error"]["reason"] == "compaction_failed"
    assert len(sm.compact_calls) == 1


@pytest.mark.asyncio
async def test_auto_summarize_compacts_after_degraded_flush_receipt() -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10, flush_enabled=True)
    sm = _FakeSessionManager(_history(6, 40))
    flush_service = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                mode="llm",
                integrity_ok=False,
                output_coverage_status="ok",
                missing_candidate_count=0,
                invalid_candidate_count=0,
                obligation_status="ok",
            )
        )
    )

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="agent:main:s-flush",
        session_manager=sm,
        flush_service=flush_service,
    )

    assert outcome.over_budget is True
    assert outcome.summarized is True
    assert outcome.retried is True
    assert outcome.reason is None
    assert outcome.refusal is None
    assert outcome.flush_receipt is not None
    assert outcome.lifecycle is not None
    assert outcome.lifecycle.flush_receipt is outcome.flush_receipt
    assert outcome.lifecycle.refused is False
    assert sm.compact_calls == [("agent:main:s-flush", 10, None)]


@pytest.mark.asyncio
async def test_auto_summarize_compacts_when_flush_service_is_missing() -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10, flush_enabled=True)
    sm = _FakeSessionManager(_history(6, 40))

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="agent:main:s-missing-flush",
        session_manager=sm,
    )

    assert outcome.over_budget is True
    assert outcome.summarized is True
    assert outcome.retried is True
    assert outcome.reason is None
    assert outcome.refusal is None
    assert sm.compact_calls == [("agent:main:s-missing-flush", 10, None)]


@pytest.mark.asyncio
async def test_auto_summarize_compacts_after_foreground_flush_grace_timeout() -> None:
    cfg = _cfg(
        ContextOverflowPolicy.AUTO_SUMMARIZE,
        budget=10,
        flush_enabled=True,
        flush_timeout_seconds=0.001,
        flush_background_timeout_seconds=42.0,
    )
    sm = _FakeSessionManager(_history(6, 40))
    flush_started = asyncio.Event()
    flush_release = asyncio.Event()

    async def _slow_flush(*args: Any, **kwargs: Any) -> Any:
        flush_started.set()
        await flush_release.wait()
        return SimpleNamespace(
            mode="llm",
            integrity_ok=True,
            output_coverage_status="ok",
            missing_candidate_count=0,
            invalid_candidate_count=0,
            obligation_status="ok",
            timeout_seconds=kwargs.get("timeout"),
        )

    flush_service = SimpleNamespace(execute=AsyncMock(side_effect=_slow_flush))

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="agent:main:s-slow-flush",
        session_manager=sm,
        flush_service=flush_service,
    )

    assert flush_started.is_set()
    assert outcome.over_budget is True
    assert outcome.summarized is True
    assert outcome.retried is True
    assert outcome.reason is None
    assert outcome.refusal is None
    assert sm.compact_calls == [("agent:main:s-slow-flush", 10, None)]
    assert flush_service.execute.await_args.kwargs["timeout"] == 42.0

    flush_release.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_auto_summarize_does_not_compact_twice_in_same_turn() -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _InsufficientCompactionSessionManager(_history(6, 40))
    marker = _TurnCompactionMarker({"s-once"})

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="s-once",
        session_manager=sm,
        compaction_marker=marker,
    )

    assert outcome.over_budget is True
    assert outcome.reason == "compaction_insufficient"
    assert sm.compact_calls == []


@pytest.mark.asyncio
async def test_failed_auto_summarize_does_not_mark_turn_compacted() -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _InsufficientCompactionSessionManager(_history(6, 40))
    marker = _TurnCompactionMarker()

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="s-failed",
        session_manager=sm,
        compaction_marker=marker,
    )

    assert outcome.reason == "compaction_insufficient"
    assert outcome.compacted_this_turn is False
    assert marker.mark_calls == []
    assert "s-failed" not in marker.compacted


@pytest.mark.asyncio
async def test_auto_summarize_forwards_compaction_config() -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _FakeSessionManager(_history(6, 40))
    compaction_config = CompactionConfig(api_key="key", model="model")

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="s-auto",
        session_manager=sm,
        compaction_config=compaction_config,
    )

    assert outcome.summarized is True
    assert sm.compact_calls == [("s-auto", 10, compaction_config)]


@pytest.mark.asyncio
async def test_auto_summarize_keeps_legacy_compact_manager_compatible() -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _LegacyCompactSessionManager(_history(6, 40))
    compaction_config = CompactionConfig(api_key="key", model="model")

    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=sm._transcript,
        session_key="s-auto",
        session_manager=sm,
        compaction_config=compaction_config,
    )

    assert outcome.summarized is True
    assert sm.compact_calls == [("s-auto", 10, None)]


@pytest.mark.asyncio
async def test_rpc_chat_auto_summarize_builds_provider_compaction_config() -> None:
    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    sm = _FakeSessionManager(_history(6, 40))
    sm._storage = SimpleNamespace(
        get_session=AsyncMock(
            return_value=SimpleNamespace(model="session/model", model_override="routed/model")
        )
    )
    selector = _FakeProviderSelector()
    ctx = SimpleNamespace(config=cfg, session_manager=sm, provider_selector=selector)

    refusal = await _enforce_context_overflow(ctx, "s-auto", "m")

    assert refusal is None
    config = sm.compact_calls[0][2]
    assert isinstance(config, CompactionConfig)
    assert config.api_key == "overflow-provider-key"
    assert config.model == "routed/model"
    assert config.base_url == "https://openrouter.ai/api/v1"
    assert selector.override_calls == []
    assert selector.clone_instance.override_calls == ["routed/model"]


@pytest.mark.asyncio
async def test_auto_summarize_without_session_manager_uses_proxy() -> None:
    """Without a session manager, AUTO degrades to drop-oldest proxy."""

    cfg = _cfg(ContextOverflowPolicy.AUTO_SUMMARIZE, budget=10)
    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="m",
        transcript=_history(6, 40),
        session_key="s-proxy",
        session_manager=None,
    )
    assert outcome.over_budget is True
    assert outcome.retried is True
    assert outcome.summarized is False
    assert outcome.truncated_entries > 0


@pytest.mark.asyncio
async def test_outcome_carries_diagnostic_counters() -> None:
    """The returned OverflowOutcome exposes estimated + budget for observability."""

    cfg = _cfg(ContextOverflowPolicy.REFUSE, budget=3)
    outcome = await apply_context_overflow_policy(
        config=cfg,
        message="hello",
        transcript=_history(2, 40),
        session_key="s-x",
    )
    assert isinstance(outcome, OverflowOutcome)
    assert outcome.estimated_tokens > outcome.budget_tokens
    assert outcome.budget_tokens == 3
