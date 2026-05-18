"""Equivalence harness — policy-pipeline self-comparison.

Both control and candidate are :func:`opensquilla.tools.dispatch.build_tool_handler`
(the policy pipeline). This is a determinism/infrastructure smoke-test: two
independent factory calls must produce byte-for-byte identical results for every
corpus case. Any shared mutable state, contextvar leak, or non-deterministic
ordering will surface here.

The legacy dispatch module was removed. The permanent behavioural contract
lives in:
  - test_dispatch_corpus_snapshots.py  (golden envelopes)
  - test_dispatch_properties.py         (idempotence, ordering invariants)
  - test_dispatch_legacy_coverage.py    (line coverage gate, now targets dispatch.py)
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
import structlog.testing
from laboratory import Experiment
from test_tools.dispatch_corpus import ALL_CASES, CorpusCase  # noqa: E402

from opensquilla.tool_boundary import ToolResult
from opensquilla.tools.dispatch import build_tool_handler as _build_candidate

# Both sides use the policy-pipeline factory.
from opensquilla.tools.dispatch import build_tool_handler as _build_control
from opensquilla.tools.types import ToolContext, current_tool_context

# -----------------------------------------------------------------------
# Envelope comparator
# -----------------------------------------------------------------------

def _parse_content(content: Any) -> dict[str, Any] | str:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except (TypeError, ValueError):
            return content
    return content


def _envelope_eq(a: ToolResult, b: ToolResult) -> bool:
    """Compare two ToolResult envelopes for dispatch-contract equivalence."""
    from opensquilla.execution_status import normalize_execution_status

    if type(a) is not type(b):
        return False
    if a.tool_use_id != b.tool_use_id:
        return False
    if a.tool_name != b.tool_name:
        return False
    if a.is_error != b.is_error:
        return False
    a_es = (
        normalize_execution_status(a.execution_status)
        if a.execution_status is not None
        else None
    )
    b_es = (
        normalize_execution_status(b.execution_status)
        if b.execution_status is not None
        else None
    )
    if a_es != b_es:
        return False
    if _parse_content(a.content) != _parse_content(b.content):
        return False
    if a.artifacts != b.artifacts:
        return False
    return True


# -----------------------------------------------------------------------
# Log record normaliser
# -----------------------------------------------------------------------

def _normalise_log_records(records: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    result: set[tuple[str, str, str]] = set()
    for rec in records:
        result.add((rec.get("_logger", ""), rec.get("log_level", ""), rec.get("event", "")))
    return result


# -----------------------------------------------------------------------
# Side-effect capture helper
# -----------------------------------------------------------------------

class _DispatchRun:
    def __init__(self) -> None:
        self.result: ToolResult | None = None
        self.artifact_snapshot: list[dict[str, Any]] = []
        self.log_records: set[tuple[str, str, str]] = set()


async def _run_one_side(
    build_fn: Any,
    case: CorpusCase,
    ctx: ToolContext | None,
    registry: Any,
) -> _DispatchRun:
    run = _DispatchRun()
    handler = build_fn(
        registry,
        ctx,
        known_skill_names=set(case.known_skill_names) if case.known_skill_names else None,
    )
    token = current_tool_context.set(None)
    try:
        with structlog.testing.capture_logs() as logs:
            run.result = await handler(case.tool_call)
        run.log_records = _normalise_log_records(logs)
        run.artifact_snapshot = list(ctx.published_artifacts) if ctx is not None else []
    finally:
        current_tool_context.reset(token)
    return run


# -----------------------------------------------------------------------
# Experiment subclass
# -----------------------------------------------------------------------

class _MismatchRecorder:
    def __init__(self) -> None:
        self.mismatches: list[str] = []


class _DispatchExperiment(Experiment):
    def __init__(self, name: str, recorder: _MismatchRecorder) -> None:
        super().__init__(name=name, raise_on_mismatch=False)
        self._recorder = recorder

    def compare(self, control: Any, candidate: Any) -> bool:  # type: ignore[override]
        ctrl_run: _DispatchRun = control.value
        cand_run: _DispatchRun = candidate.value
        if ctrl_run.result is None or cand_run.result is None:
            self._recorder.mismatches.append("One side returned None result")
            return False
        if not _envelope_eq(ctrl_run.result, cand_run.result):
            self._recorder.mismatches.append(
                f"Envelope mismatch: is_error={ctrl_run.result.is_error} vs "
                f"{cand_run.result.is_error}, "
                f"content={_parse_content(ctrl_run.result.content)!r} vs "
                f"{_parse_content(cand_run.result.content)!r}"
            )
            return False
        if ctrl_run.artifact_snapshot != cand_run.artifact_snapshot:
            self._recorder.mismatches.append(
                f"Artifact mismatch: {ctrl_run.artifact_snapshot!r} vs "
                f"{cand_run.artifact_snapshot!r}"
            )
            return False
        if ctrl_run.log_records != cand_run.log_records:
            self._recorder.mismatches.append(
                f"Log record mismatch: {ctrl_run.log_records!r} vs "
                f"{cand_run.log_records!r}"
            )
            return False
        return True

    def publish(self, result: Any) -> None:  # type: ignore[override]
        pass


# -----------------------------------------------------------------------
# Async harness runner
# -----------------------------------------------------------------------

async def _run_equivalence(case: CorpusCase) -> _MismatchRecorder:
    recorder = _MismatchRecorder()
    ctrl_ctx = copy.deepcopy(case.ctx_factory())
    cand_ctx = copy.deepcopy(case.ctx_factory())
    ctrl_registry = case.registry_factory()
    cand_registry = case.registry_factory()
    if case.setup is not None:
        case.setup()
    try:
        ctrl_run = await _run_one_side(_build_control, case, ctrl_ctx, ctrl_registry)
        cand_run = await _run_one_side(_build_candidate, case, cand_ctx, cand_registry)
    finally:
        if case.teardown is not None:
            case.teardown()
    experiment = _DispatchExperiment(name=case.name, recorder=recorder)
    experiment.control(lambda: ctrl_run)
    experiment.candidate(lambda: cand_run)
    experiment.conduct(randomize=False)
    ctx_val = current_tool_context.get()
    if ctx_val is not None and case.contextvar_must_be_none_after:
        recorder.mismatches.append(
            f"Contextvar leak after dispatch: current_tool_context.get() = {ctx_val!r}"
        )
    return recorder


# -----------------------------------------------------------------------
# Parametrised test
# -----------------------------------------------------------------------

@pytest.mark.parametrize("case", ALL_CASES, ids=[c.name for c in ALL_CASES])
@pytest.mark.asyncio
async def test_dispatch_equivalence_corpus(case: CorpusCase) -> None:
    """Self-comparison: two independent factory calls must produce identical results."""
    recorder = await _run_equivalence(case)
    assert not recorder.mismatches, (
        f"Equivalence failures for case '{case.name}':\n"
        + "\n".join(f"  - {m}" for m in recorder.mismatches)
    )
