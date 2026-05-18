"""CLI footer renders per-turn-only metrics; session totals reach via state.usage."""

from __future__ import annotations

import pytest

from opensquilla.cli.repl.stream import StreamingRenderer, UsageCounter, UsageSummary
from opensquilla.engine.usage import SessionTotalsSnapshot


@pytest.fixture
def renderer():
    return StreamingRenderer()


def _usage(session_totals=None):
    return UsageSummary(
        model="gpt-test",
        input_tokens=11,
        output_tokens=22,
        cached_tokens=3,
        reasoning_tokens=4,
        cost_usd=0.000123,
        session_totals=session_totals,
    )


def test_footer_renders_per_turn_only_with_snapshot(renderer):
    snap = SessionTotalsSnapshot(input_tokens=100, output_tokens=200, cost_usd=0.5)
    footer = renderer.footer(_usage(session_totals=snap), elapsed=1.5)
    assert "11 in / 22 out" in footer       # per-turn
    assert "4 think" in footer
    assert "4 reasoning" not in footer
    assert "100" not in footer               # NOT session-total in footer
    assert "$0.000123" in footer
    assert "∑" not in footer            # cumulative segment fully removed


def test_footer_renders_per_turn_only_without_snapshot(renderer):
    footer = renderer.footer(_usage(session_totals=None), elapsed=1.5)
    assert "11 in / 22 out" in footer
    assert "$0.000123" in footer
    assert "∑" not in footer


def test_usage_counter_apply_overwrites_from_snapshot():
    counter = UsageCounter(input_tokens=50, output_tokens=99)
    snap = SessionTotalsSnapshot(
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=3,
        cost_usd=0.5,
    )
    counter.apply(_usage(session_totals=snap))
    assert counter.input_tokens == 10  # overwrote, not summed
    assert counter.output_tokens == 20


def test_usage_counter_apply_accumulates_without_snapshot():
    counter = UsageCounter(input_tokens=50, output_tokens=99)
    counter.apply(_usage(session_totals=None))
    assert counter.input_tokens == 50 + 11
    assert counter.output_tokens == 99 + 22
