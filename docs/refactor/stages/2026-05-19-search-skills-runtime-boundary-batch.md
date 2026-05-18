# Search Skills Runtime Boundary Batch

> For agentic workers: REQUIRED SUB-SKILL: use
> `superpowers:writing-plans` before implementation. Use
> `superpowers:test-driven-development` for code or executable behavior and
> `superpowers:verification-before-completion` before claiming completion.

## Stage

- Name: search-skills-runtime-boundary-batch
- Date: 2026-05-19
- Integration branch: `codex/refactor-architecture`
- Child branch: `codex/refactor-search-skills-runtime-boundary-batch`
- Child worktree: `../opensquilla-refactor-active`
- Owner: Codex main thread for architecture, worker dispatch, review,
  integration merge, full gates, stage records, and cleanup. Same-thread
  `spawn_agent` was available for the audit phase.

## Goal

Refactor two independent runtime-facing module families in one coarse batch:

- search runtime/config sync: make `opensquilla.search` own provider bootstrap,
  runtime configuration sync, query/status execution, and RPC payload adaptation
  while keeping gateway and tool surfaces thin;
- skills runtime facade: make `opensquilla.skills` own loaded-skill inventory,
  status rows, resource/view reads, and dependency preview argv construction
  while keeping CLI and tool surfaces thin.

Do not change public RPC method names, CLI output shape, tool names,
search provider fallback behavior, skill loader namespace/provenance behavior,
or bundled skill assets.

## Current-state audit

- Current HEAD: `9bfdb07`.
- Worktree status: clean before child creation.
- AGENTS.md files in scope:
  - `AGENTS.md`
  - `src/opensquilla/identity/templates/bootstrap/AGENTS.md` exists but is
    outside this stage's touched scope.
- Files inspected:
  - `docs/refactor/overall-plan.md`
  - `docs/refactor/stage-template.md`
  - `docs/refactor/stages/2026-05-19-knowledge-services-rpc-cli-boundary-batch.md`
  - `docs/refactor/stages/2026-05-19-tools-gateway-runtime-surface-batch.md`
  - `src/opensquilla/search/runtime.py`
  - `src/opensquilla/search/execution.py`
  - `src/opensquilla/search/rpc_payload.py`
  - `src/opensquilla/gateway/boot.py`
  - `src/opensquilla/gateway/rpc_onboarding_search.py`
  - `src/opensquilla/gateway/rpc_search.py`
  - `src/opensquilla/tools/builtin/web.py`
  - `src/opensquilla/skills/rpc_payload.py`
  - `src/opensquilla/cli/skills_rows.py`
  - `src/opensquilla/tools/builtin/skill_tools.py`
  - `src/opensquilla/skills/resources.py`
- Tests inspected:
  - `tests/test_search/test_search_runtime_boundary.py`
  - `tests/test_search/test_search_execution.py`
  - `tests/test_skills_runtime_boundary.py`
  - `tests/test_skills_rpc_payload.py`
  - `tests/test_skills_hub_deps.py`
  - `tests/test_skills_default_prompt_contract.py`
- Existing boundary pattern this stage follows:
  - Domain modules own runtime/payload/resource semantics.
  - Gateway, CLI, and tool modules remain thin adapters.
  - Compatibility wrappers stay in place when public imports or tools rely on
    old names.

## Superpowers evidence

- `superpowers:using-git-worktrees`:
  - Evidence: read the skill; verified integration was a linked worktree on
    `codex/refactor-architecture`; created fixed child worktree
    `../opensquilla-refactor-active` on branch
    `codex/refactor-search-skills-runtime-boundary-batch`.
- `superpowers:writing-plans`:
  - Evidence: read the skill; wrote this stage plan before production edits.
- `superpowers:test-driven-development`:
  - Evidence: read the skill; each worker must add a RED boundary/behavior test
    before implementation and record expected failure.
- `superpowers:verification-before-completion`:
  - Evidence: read the skill; this stage cannot be claimed complete until
    focused tests, touched-file checks, child `scripts/refactor_gate.sh`,
    integration `scripts/refactor_gate.sh`, and cleanup audit are recorded.
- Parallelism decision:
  - `superpowers:dispatching-parallel-agents` used for three read-only audits:
    search, memory, and skills.
  - `superpowers:subagent-driven-development` applies for the implementation
    phase: dispatch Search and Skills workers in parallel with disjoint file
    ownership.
  - `spawn_agent` probe: audit agents spawned successfully.
  - External worker fallback: use `scripts/refactor_external_agent.sh` only if
    same-thread worker spawning fails or a thread limit blocks progress.
- Historical evidence note:
  - Do not infer Superpowers usage from older stages. This stage records only
    current command/log evidence.

## Boundary decision

- Module batch:
  - Search runtime/config sync boundary.
  - Skills runtime facade boundary.
- Responsibilities moving out:
  - Search provider/env/runtime sync duplicated in gateway boot and onboarding
    search RPC.
  - Search RPC compatibility re-exports from `search.execution`.
  - Loaded-skill row/status/resource/dependency lookup duplicated in CLI and
    tool layers.
- Responsibilities staying in place:
  - Search provider implementations under `search/providers`.
  - Search RPC method registration in `gateway/rpc_search.py`.
  - Skill hub/community operation internals under `skills/hub`.
  - Skill mutation tools and workspace-layer write behavior in
    `tools/builtin/skill_tools.py`.
- New module/file responsibility:
  - Search may add a search-domain sync/config helper if RED tests prove the
    gateway/onboarding duplication.
  - Skills may add `skills/runtime_facade.py` or `skills/runtime_services.py`
    for loaded-skill inventory/status/view/dependency helpers.
- Public behavior that must not change:
  - `search.provider`, `search.status`, `search.query`, and onboarding search
    RPC wire keys.
  - DuckDuckGo/Brave provider fallback, diagnostics, proxy, env proxy, and
    sensitive-query redaction behavior.
  - `skill_list`, `skill_view`, `install_skill_deps`, and skills CLI row JSON
    shape.
  - Skill layer/provenance namespace behavior, dependency install argv safety,
    resource traversal rejection, and bundled skill contents.
- Files explicitly out of scope:
  - `src/opensquilla/memory/**`
  - `src/opensquilla/engine/**`
  - `src/opensquilla/session/**`
  - `src/opensquilla/skills/retrieval/**`
  - `src/opensquilla/skills/hub/**` except import-only adapters if unavoidable
  - `src/opensquilla/search/providers/**`
  - Web UI static redesign or browser behavior.

## Worker ownership

### Worker A: Search Runtime Config Sync

- Owns:
  - `src/opensquilla/search/runtime.py`
  - `src/opensquilla/search/execution.py`
  - `src/opensquilla/search/rpc_payload.py`
  - `src/opensquilla/search/__init__.py`
  - `src/opensquilla/gateway/boot.py` search-provider block only
  - `src/opensquilla/gateway/rpc_onboarding_search.py`
  - `src/opensquilla/gateway/rpc_search.py`
  - `src/opensquilla/tools/builtin/web.py` search compatibility wrappers only
  - `tests/test_search/**`
  - targeted gateway RPC domain/product tests
- Must not edit:
  - `src/opensquilla/skills/**`
  - `src/opensquilla/memory/**`
  - `src/opensquilla/search/providers/**`
  - non-search blocks in `gateway/boot.py`
- RED tests:
  - `gateway.boot` and `gateway.rpc_onboarding_search` delegate search runtime
    configuration to a search-domain helper instead of importing
    `configure_search` directly.
  - helper preserves Brave auto-select, explicit provider config, API key env,
    proxy, env proxy, fallback policy, and diagnostics.
  - `search.execution` no longer imports/re-exports RPC payload helpers.
- Focused GREEN:
  - `uv run --extra dev pytest tests/test_search tests/test_gateway/test_rpc_domain_modules.py tests/test_gateway/test_rpc_product_cli_gaps.py -q`

### Worker B: Skills Runtime Facade

- Owns:
  - `src/opensquilla/skills/runtime_facade.py` or
    `src/opensquilla/skills/runtime_services.py`
  - `src/opensquilla/skills/rpc_payload.py`
  - `src/opensquilla/skills/__init__.py` only if exporting the new boundary
  - `src/opensquilla/cli/skills_rows.py`
  - `src/opensquilla/tools/builtin/skill_tools.py` loaded-skill list/view/deps
    helpers only
  - `tests/test_skills_runtime_boundary.py`
  - `tests/test_skills_rpc_payload.py`
  - `tests/test_skills_hub_deps.py`
  - `tests/test_skills_default_prompt_contract.py`
  - optional new `tests/test_skills_runtime_facade.py`
- Must not edit:
  - `src/opensquilla/search/**`
  - `src/opensquilla/memory/**`
  - `src/opensquilla/skills/retrieval/**`
  - `src/opensquilla/skills/hub/**`
  - bundled skill content
- RED tests:
  - CLI skill rows delegate eligibility/status row construction to the skills
    runtime facade rather than importing eligibility directly.
  - skill tools delegate loaded-skill status/view/dependency preview helpers to
    the skills runtime facade while preserving public tool output.
  - facade preserves CLI row shape and skills RPC status/list/get shape.
- Focused GREEN:
  - `uv run --extra dev pytest tests/test_skills_runtime_boundary.py tests/test_skills_rpc_payload.py tests/test_skills_hub_deps.py tests/test_skills_default_prompt_contract.py tests/test_gateway_static_skills_view.py -q`

Workers are not alone in the codebase. Preserve edits made by the other worker,
do not revert unrelated changes, and stop rather than editing outside ownership.

## TDD red/green

- Baseline focused command:
  - `uv run --extra dev pytest tests/test_search tests/test_gateway/test_rpc_domain_modules.py tests/test_gateway/test_rpc_product_cli_gaps.py tests/test_skills_runtime_boundary.py tests/test_skills_rpc_payload.py tests/test_skills_hub_deps.py tests/test_skills_default_prompt_contract.py -q`
  - Result before implementation: `64 passed`.
- Expected red failures:
  - Search worker boundary tests fail because gateway boot/onboarding still call
    `configure_search` directly and `search.execution` still imports
    `search.rpc_payload`.
  - Skills worker boundary tests fail because CLI/tool layers still own loaded
    skill status/resource/dependency helper logic.
- Behavior compatibility coverage:
  - Search runtime, RPC, and CLI product gap tests.
  - Skills runtime, RPC payload, hub deps, default prompt, and static skills view
    tests.
- Combined focused GREEN:
  - `uv run --extra dev pytest tests/test_search tests/test_gateway/test_rpc_domain_modules.py tests/test_gateway/test_rpc_product_cli_gaps.py tests/test_skills_runtime_boundary.py tests/test_skills_rpc_payload.py tests/test_skills_hub_deps.py tests/test_skills_default_prompt_contract.py tests/test_gateway_static_skills_view.py -q`
- Additional touched-file checks:
  - `uv run --extra dev ruff check src/opensquilla/search src/opensquilla/skills src/opensquilla/cli/skills_rows.py src/opensquilla/tools/builtin/web.py src/opensquilla/tools/builtin/skill_tools.py src/opensquilla/gateway/rpc_search.py src/opensquilla/gateway/rpc_onboarding_search.py src/opensquilla/gateway/boot.py tests/test_search tests/test_skills_runtime_boundary.py tests/test_skills_rpc_payload.py tests/test_skills_hub_deps.py tests/test_skills_default_prompt_contract.py tests/test_gateway_static_skills_view.py`
  - `uv run --extra dev mypy src/opensquilla/search src/opensquilla/skills src/opensquilla/cli/skills_rows.py src/opensquilla/tools/builtin/web.py src/opensquilla/tools/builtin/skill_tools.py --show-error-codes`
  - `git diff --check`

## Files

- Create:
  - Worker-specific boundary modules only if RED tests justify them.
- Modify:
  - This stage record.
  - Worker-owned files listed above.
- Test:
  - Worker-focused tests listed above.
- Documentation:
  - This stage record.

## Steps

- [x] Run `scripts/refactor_preflight.sh --expect-branch codex/refactor-architecture`.
- [x] Create fixed child worktree `../opensquilla-refactor-active`.
- [x] Run child preflight.
- [x] Run baseline focused command and record result.
- [ ] Dispatch Search and Skills workers with explicit ownership and TDD RED/GREEN.
- [ ] Review each worker diff for public API compatibility and import cycles.
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

- Revert the integration merge commit if search runtime/provider behavior,
  search RPC payloads, skills CLI rows, skills tool outputs, skill resource
  reads, or dependency preview execution regress.
- Keep the child branch for diagnosis until a replacement slice is ready.
- Do not rewrite `main` or unrelated worktrees.

## Completion record

- Child commit:
- Integration merge:
- Verification evidence:
- Residual risk:
  - Memory runtime/flush orchestration is intentionally left for a later batch
    because it touches gateway boot plus engine/session lifecycle hot paths.
- Next recommended slice:
  - Memory runtime/flush orchestration boundary, selected from the audit
    evidence after this search+skills batch is merged, gated, and cleaned up.
