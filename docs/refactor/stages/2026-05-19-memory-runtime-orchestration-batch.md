# Memory Runtime Orchestration Batch

> For agentic workers: REQUIRED SUB-SKILL: use
> `superpowers:writing-plans` before implementation. Use
> `superpowers:test-driven-development` for code or executable behavior and
> `superpowers:verification-before-completion` before claiming completion.

## Stage

- Name: memory-runtime-orchestration-batch
- Date: 2026-05-19
- Integration branch: `codex/refactor-architecture`
- Child branch: `codex/refactor-memory-runtime-orchestration-batch`
- Child worktree: `../opensquilla-refactor-active`
- Owner: Codex main thread for architecture boundary, worker dispatch, review,
  conflict resolution, child/integration gates, stage records, and cleanup.

## Goal

Refactor two memory-domain runtime orchestration surfaces in one cohesive,
behavior-compatible batch:

- memory tool runtime surface: move tool-facing runtime resolution, archive
  policy, write notification, and memory tool result orchestration into
  `opensquilla.memory`;
- memory gateway runtime assembly: move gateway boot memory-manager view
  materialization and memory tool registration orchestration into
  `opensquilla.memory`, while preserving fail-open boot behavior.

Do not touch engine/session flush hot paths in this batch. They require a later
exclusive stage because they share turn/session locking and transcript mutation
state.

## Current-state audit

- Current integration HEAD before child creation: `366f064`.
- Worktree status before child creation: clean.
- Integration preflight:
  `scripts/refactor_preflight.sh --expect-branch codex/refactor-architecture`
  passed at `366f064`.
- Child preflight:
  `scripts/refactor_preflight.sh --expect-branch codex/refactor-memory-runtime-orchestration-batch`
  passed at `366f064`.
- AGENTS.md files in scope:
  - `AGENTS.md`
  - `src/opensquilla/identity/templates/bootstrap/AGENTS.md` exists but is
    outside this stage's touched scope.
- Files inspected:
  - `docs/refactor/overall-plan.md`
  - `docs/refactor/stage-template.md`
  - `docs/refactor/stages/2026-05-19-search-skills-runtime-boundary-batch.md`
  - `docs/refactor/stages/2026-05-19-session-lifecycle-flush-boundary.md`
  - `docs/refactor/stages/2026-05-19-session-lifecycle-memory-preservation-boundary.md`
  - `src/opensquilla/memory/runtime.py`
  - `src/opensquilla/memory/manager.py`
  - `src/opensquilla/memory/session_flush.py`
  - `src/opensquilla/memory/__init__.py`
  - `src/opensquilla/tools/builtin/memory_tools.py`
  - `src/opensquilla/gateway/boot.py`
  - `src/opensquilla/engine/runtime.py` via audit agent only
  - `src/opensquilla/engine/agent.py` via audit agent only
  - `src/opensquilla/session/lifecycle_memory.py`
  - `src/opensquilla/session/lifecycle_flush.py`
- Tests inspected or baselined:
  - `tests/test_memory_tool_runtime.py`
  - `tests/test_memory_tool_sources.py`
  - `tests/test_memory_tool_search.py`
  - `tests/test_memory_tool_writes.py`
  - `tests/test_memory_source_rpc.py`
  - `tests/test_memory_flush.py`
  - `tests/test_gateway/test_router_boot.py`
  - `tests/test_engine/test_preflight_compaction.py`
  - `tests/test_engine/test_t3_upgrade_compaction.py`
  - `tests/test_session/test_session_lifecycle_memory.py`
  - `tests/test_session/test_session_lifecycle_flush.py`
- Baseline focused command:
  - `uv run --extra dev pytest tests/test_memory_tool_runtime.py tests/test_memory_tool_sources.py tests/test_memory_tool_search.py tests/test_memory_tool_writes.py tests/test_memory_source_rpc.py tests/test_memory_flush.py tests/test_gateway/test_router_boot.py tests/test_engine/test_preflight_compaction.py tests/test_engine/test_t3_upgrade_compaction.py tests/test_session/test_session_lifecycle_memory.py tests/test_session/test_session_lifecycle_flush.py -q`
  - Result before implementation: `120 passed`.
- Existing boundary pattern this stage follows:
  - Domain modules own runtime/payload/resource semantics.
  - Gateway and tool modules remain thin adapters.
  - Public tool names, params, descriptions, exposure defaults, CLI/RPC keys,
    and public imports remain behavior-compatible.

## Superpowers evidence

- `superpowers:using-git-worktrees`:
  - Evidence: read the skill; verified clean integration worktree on
    `codex/refactor-architecture`; created fixed child worktree
    `../opensquilla-refactor-active` on branch
    `codex/refactor-memory-runtime-orchestration-batch`.
- `superpowers:writing-plans`:
  - Evidence: read the skill; wrote this stage plan before production edits.
- `superpowers:test-driven-development`:
  - Evidence: read the skill; each implementation worker must add RED boundary
    or behavior tests and record the expected failure before production edits.
- `superpowers:verification-before-completion`:
  - Evidence: read the skill; this stage cannot be claimed complete until
    focused tests, touched-file checks, child `scripts/refactor_gate.sh`,
    integration `scripts/refactor_gate.sh`, and cleanup audit are recorded.
- Parallelism decision:
  - `superpowers:dispatching-parallel-agents` used for three read-only audits:
    memory tool runtime surface, gateway boot/runtime assembly, and
    engine/session hot paths.
  - `superpowers:subagent-driven-development` applies for implementation:
    dispatch Memory Tool Surface and Memory Gateway Runtime workers in parallel
    with disjoint file ownership.
  - `spawn_agent` probe: availability probe returned `spawn_agent available`.
  - External worker fallback: not needed unless same-thread worker spawning
    fails during implementation.
- Historical evidence note:
  - Do not infer Superpowers usage from older stages. This stage records only
    current command/log evidence.

## Boundary decision

- Module batch:
  - Memory tool runtime surface.
  - Memory gateway runtime assembly.
- Responsibilities moving out:
  - Tool-facing runtime resolution, archive allowance, default save path,
    write notification, and `ToolError` translation currently embedded in
    `tools/builtin/memory_tools.py`.
  - Gateway boot's inline memory manager view derivation, memory watcher list
    materialization, `_on_memory_write` callback construction, and memory tool
    registration orchestration.
- Responsibilities staying in place:
  - Tool registry decorators and public tool specs stay in
    `tools/builtin/memory_tools.py`.
  - Low-level memory source read/delete/search/write helpers stay in existing
    `opensquilla.memory.tool_*` modules.
  - `build_memory_managers` construction internals stay in
    `opensquilla.memory.manager`.
  - Engine/session preflight, T3 upgrade, background flush, lifecycle
    reset/compact locking, and `memory.session_flush` internals stay out of
    scope.
- New module/file responsibility:
  - `src/opensquilla/memory/tool_surface.py` owns memory tool runtime surface
    calls.
  - `src/opensquilla/memory/gateway_runtime.py` owns memory runtime bundle/view
    materialization and boot-time memory tool registration orchestration.
- Public behavior that must not change:
  - `create_memory_tools(...)` signature and single-store backward
    compatibility.
  - Tool names, params, descriptions, exposure defaults, result strings, and
    error strings for `memory_search`, `memory_save`, `memory_get`, and
    `memory_delete`.
  - `memory_search` max-result clamping and `SearchIntent.TOOL`.
  - `memory_get` `from` alias behavior and private archive errors.
  - `memory_save` default `memory/YYYY-MM-DD.md`, append default, integrity
    response, threat blocking, rollback behavior, and snapshot refresh callback.
  - `memory_delete` success/error strings and index removal.
  - Runtime resolution semantics: normalized agent id, `main` fallback,
    state/workspace source modes, context workspace override, and invalid
    `memory_source` errors.
  - Gateway memory setup remains fail-open and logs
    `build_services.memory_tools_failed` on setup errors.
  - Memory config defaults and memory RPC source payloads remain unchanged.
- Files explicitly out of scope:
  - `src/opensquilla/engine/**`
  - `src/opensquilla/session/**`
  - `src/opensquilla/memory/session_flush.py`
  - `src/opensquilla/gateway/rpc_session_lifecycle.py`
  - `src/opensquilla/gateway/websocket.py`
  - `src/opensquilla/gateway/app.py`
  - provider, channel, scheduler, search, skills, CLI, and Web UI internals.

## Worker ownership

### Worker A: Memory Tool Surface

- Owns:
  - create `src/opensquilla/memory/tool_surface.py`
  - `src/opensquilla/tools/builtin/memory_tools.py`
  - `src/opensquilla/memory/runtime.py` only if a tiny runtime helper is needed
  - `tests/test_memory_tool_runtime.py`
  - `tests/test_memory_tool_sources.py`
  - `tests/test_memory_tool_search.py`
  - `tests/test_memory_tool_writes.py`
  - `tests/test_tools/test_memory_profile_guidance.py`
  - `tests/test_tools/test_builtin_loader.py`
- Must not edit:
  - `src/opensquilla/gateway/**`
  - `src/opensquilla/engine/**`
  - `src/opensquilla/session/**`
  - `src/opensquilla/memory/manager.py`
  - `src/opensquilla/memory/session_flush.py`
- RED tests:
  - `memory_tools.py` no longer imports `apply_memory_writes`,
    `search_memory_tool`, `memory_get_tool_result`, or
    `memory_delete_tool_result` directly once `memory.tool_surface` exists.
  - Registered tools resolve through a memory-owned tool surface/facade while
    preserving current tool output.
  - Successful `memory_save` keeps default daily path, append mode, integrity
    response, indexing, and resolved-agent notification.
  - Archive allow/deny is mediated by the memory surface and preserves private
    archive errors.
- Focused GREEN:
  - `uv run --extra dev pytest tests/test_memory_tool_runtime.py tests/test_memory_tool_search.py tests/test_memory_tool_sources.py tests/test_memory_tool_writes.py tests/test_tools/test_memory_profile_guidance.py tests/test_tools/test_builtin_loader.py -q`

### Worker B: Memory Gateway Runtime

- Owns:
  - create `src/opensquilla/memory/gateway_runtime.py`
  - `src/opensquilla/gateway/boot.py` memory-manager/tool-registration block
    only
  - `tests/test_gateway/test_router_boot.py`
  - create `tests/test_memory_gateway_runtime.py`
  - `tests/test_gateway/test_config_memory_defaults.py`
  - `tests/test_gateway/test_rpc_config_memory_embedding.py` only for
    compatibility coverage, not config helper refactor
  - `tests/test_memory_manager_embedding_config.py`
  - `tests/test_memory_source_rpc.py`
  - `tests/test_session/test_session_lifecycle_memory.py`
- Must not edit:
  - `src/opensquilla/tools/builtin/memory_tools.py`
  - `src/opensquilla/engine/**`
  - `src/opensquilla/session/**`
  - `src/opensquilla/memory/session_flush.py`
  - non-memory blocks in `gateway/boot.py`
- RED tests:
  - `gateway.boot` delegates memory runtime assembly to a memory-domain helper
    instead of importing `create_memory_tools` or deriving legacy views inline.
  - Memory gateway runtime helper builds managers, stores, retrievers,
    sync-managers, watchers, turn-capture services, and registers the memory
    tools runtime with correct `memory_source` and `workspace_base`.
  - Gateway memory setup remains fail-open on helper failure.
- Focused GREEN:
  - `uv run --extra dev pytest tests/test_gateway/test_router_boot.py tests/test_gateway/test_config_memory_defaults.py tests/test_gateway/test_rpc_config_memory_embedding.py tests/test_memory_manager_embedding_config.py tests/test_memory_tool_runtime.py tests/test_memory_source_rpc.py tests/test_memory_tool_sources.py tests/test_tools/test_memory_profile_guidance.py tests/test_session/test_session_lifecycle_memory.py -q`

Workers are not alone in the codebase. Preserve edits made by the other worker,
do not revert unrelated changes, and stop rather than editing outside ownership.

## TDD red/green

- Baseline focused command:
  - `uv run --extra dev pytest tests/test_memory_tool_runtime.py tests/test_memory_tool_sources.py tests/test_memory_tool_search.py tests/test_memory_tool_writes.py tests/test_memory_source_rpc.py tests/test_memory_flush.py tests/test_gateway/test_router_boot.py tests/test_engine/test_preflight_compaction.py tests/test_engine/test_t3_upgrade_compaction.py tests/test_session/test_session_lifecycle_memory.py tests/test_session/test_session_lifecycle_flush.py -q`
  - Result before implementation: `120 passed`.
- Expected red failures:
  - Worker A fails because `opensquilla.memory.tool_surface` does not exist and
    `memory_tools.py` still owns runtime surface orchestration inline.
  - Worker B fails because `opensquilla.memory.gateway_runtime` does not exist
    and `gateway.boot` still owns memory runtime assembly inline.
- Behavior compatibility coverage:
  - Memory tool runtime, search/source/write behavior, profile guidance, builtin
    loader, router boot, memory config defaults, memory source RPC, and session
    lifecycle memory tests.
- Combined focused GREEN:
  - `uv run --extra dev pytest tests/test_memory_tool_runtime.py tests/test_memory_tool_search.py tests/test_memory_tool_sources.py tests/test_memory_tool_writes.py tests/test_tools/test_memory_profile_guidance.py tests/test_tools/test_builtin_loader.py tests/test_gateway/test_router_boot.py tests/test_gateway/test_config_memory_defaults.py tests/test_gateway/test_rpc_config_memory_embedding.py tests/test_memory_manager_embedding_config.py tests/test_memory_source_rpc.py tests/test_session/test_session_lifecycle_memory.py -q`
- Additional touched-file checks:
  - `uv run --extra dev ruff check src/opensquilla/memory src/opensquilla/tools/builtin/memory_tools.py src/opensquilla/gateway/boot.py tests/test_memory_tool_runtime.py tests/test_memory_tool_search.py tests/test_memory_tool_sources.py tests/test_memory_tool_writes.py tests/test_memory_gateway_runtime.py tests/test_gateway/test_router_boot.py tests/test_tools/test_memory_profile_guidance.py tests/test_tools/test_builtin_loader.py`
  - `uv run --extra dev mypy src/opensquilla/memory src/opensquilla/tools/builtin/memory_tools.py src/opensquilla/gateway/boot.py --show-error-codes`
  - `git diff --check`

## Files

- Create:
  - `src/opensquilla/memory/tool_surface.py`
  - `src/opensquilla/memory/gateway_runtime.py`
  - `tests/test_memory_gateway_runtime.py`
- Modify:
  - `src/opensquilla/tools/builtin/memory_tools.py`
  - `src/opensquilla/gateway/boot.py`
  - worker-owned tests listed above
  - this stage record
- Test:
  - worker-focused tests listed above
- Documentation:
  - this stage record

## Steps

- [x] Run `scripts/refactor_preflight.sh --expect-branch codex/refactor-architecture`.
- [x] Create fixed child worktree `../opensquilla-refactor-active`.
- [x] Run child preflight.
- [x] Run baseline focused command and record result.
- [ ] Dispatch Memory Tool Surface and Memory Gateway Runtime workers with
      explicit ownership and TDD RED/GREEN.
- [ ] Review each worker diff for public API compatibility, import cycles, and
      ownership violations.
- [ ] Run combined focused GREEN.
- [ ] Run touched-file Ruff, mypy, and `git diff --check`.
- [ ] Run `scripts/refactor_gate.sh`.
- [ ] Commit with:

```text
Co-authored-by: Codex <noreply@openai.com>
```

- [ ] Merge child into integration with `git merge --no-ff`.
- [ ] Run `scripts/refactor_gate.sh` in integration.
- [ ] Record child hash, integration hash, verification, and next slice.
- [ ] Remove `../opensquilla-refactor-active`, run
      `git worktree prune`, and verify no extra refactor worktree directories
      remain beyond `../opensquilla-refactor-integration`.

## Child gate

- `uv run --extra dev ruff check src tests`
- `uv run --extra dev mypy src/opensquilla --show-error-codes`
- `git diff --check`
- `uv run --extra dev pytest`
- gateway smoke through `scripts/refactor_gate.sh`

## Integration gate

- `uv run --extra dev ruff check src tests`
- `uv run --extra dev mypy src/opensquilla --show-error-codes`
- `git diff --check HEAD^ HEAD`
- `uv run --extra dev pytest`
- gateway smoke through `scripts/refactor_gate.sh`

## Rollback

- Revert the integration merge commit if memory tools, memory source files,
  memory config defaults/RPC payloads, gateway boot memory setup, or session
  lifecycle memory behavior regress.
- Keep the child branch for diagnosis until a replacement slice is ready.
- Do not rewrite `main` or unrelated worktrees.

## Completion record

- Child commit:
- Integration merge:
- Verification evidence:
- Residual risk:
  - Engine/session flush hot paths intentionally remain out of scope because
    they require a later exclusive runtime/session lifecycle stage.
- Next recommended slice:
  - Exclusive runtime/session lifecycle memory flush stage, using the audit
    recommendations for preflight/T3/background flush/session-lock RED tests.
