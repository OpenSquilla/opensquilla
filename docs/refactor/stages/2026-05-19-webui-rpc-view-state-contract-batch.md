# Web UI RPC View State Contract Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` for same-thread workers or `superpowers:executing-plans` if same-thread agents become unavailable. Each worker must also use `superpowers:test-driven-development` and record RED/GREEN evidence. This stage must record concrete Superpowers evidence, not only intent.

**Goal:** Refactor Web UI RPC/access/view-state contracts into clearer behavior-compatible boundaries while preserving static asset load order, browser RPC/HTTP access, chat rendering, control views, and public Gateway RPC contracts.

**Architecture:** Use one active child integration worktree and independent worker branches/worktrees for disjoint Web UI subdomains. Keep `chat.js` owned by one worker because it is the largest conflict hotspot. The main thread owns stage planning, worker dispatch, diff review, child/integration gates, merge records, and cleanup.

**Tech Stack:** Python 3.12+, static Web UI JavaScript/CSS, Starlette Gateway template/RPC contracts, pytest static contract tests, Ruff, mypy, full `scripts/refactor_gate.sh`.

---

## Stage

- Name: webui-rpc-view-state-contract-batch
- Date: 2026-05-19
- Integration branch: `codex/refactor-architecture`
- Child branch: `codex/refactor-webui-rpc-view-state-contract-batch`
- Child worktree: `../opensquilla-refactor-active`
- Owner: Codex main thread for architecture, Superpowers evidence, worker dispatch, review, merge integration, full gates, stage record, and cleanup. Same-thread `spawn_agent` healthcheck succeeded with agent `019e3c2b-a31a-7771-9047-e7d6a314f2dd`.

## Goal

Refactor the Web UI surface as one coarse batch:

- keep Web UI RPC and HTTP access single-sourced through `WebUiRpc` and `WebUiHttp`;
- keep chat run-state, artifacts, attachment, stream reconciliation, savings animation, and markdown rendering behavior stable;
- keep shared UI primitives and control views stable while reducing repeated status/state rendering logic;
- keep static asset load order, public RPC names/scopes, and Gateway session payload contracts stable.

## Current-state audit

- Current HEAD: `9b60c51`.
- Worktree status: clean before creating this stage plan.
- AGENTS.md files in scope:
  - `AGENTS.md`
  - `src/opensquilla/identity/templates/bootstrap/AGENTS.md` exists but is outside this stage's file scope.
- Files inspected:
  - `AGENTS.md`
  - `docs/refactor/stage-template.md`
  - `docs/refactor/stages/2026-05-18-webui-rpc-access-boundary.md`
  - `docs/refactor/stages/2026-05-18-webui-http-access-boundary.md`
  - `docs/refactor/stages/2026-05-19-knowledge-services-rpc-cli-boundary-batch.md`
  - `src/opensquilla/gateway/templates/index.html`
  - `src/opensquilla/gateway/static/js/rpc.js`
  - `src/opensquilla/gateway/static/js/rpc_access.js`
  - `src/opensquilla/gateway/static/js/http_access.js`
  - `src/opensquilla/gateway/static/js/app.js`
  - `src/opensquilla/gateway/static/js/approval_monitor.js`
  - `src/opensquilla/gateway/static/js/components.js`
  - `src/opensquilla/gateway/static/js/components/savings-fx.js`
  - `src/opensquilla/gateway/static/js/components/token-widget.js`
  - `src/opensquilla/gateway/static/js/views/*.js`
  - `src/opensquilla/gateway/static/css/**/*.css`
  - `src/opensquilla/gateway/rpc_sessions.py`
- Symbols or command surfaces inspected:
  - Web UI asset load order for RPC/HTTP/access modules.
  - Direct `fetch(` and `App.getRpc()` static boundaries.
  - Chat artifact rendering, run-state tracking, stream reconciliation, subagent completion rendering, and attachment upload contracts.
  - Shared `window.UI` helpers for session status chips, drawers, and comboboxes.
  - Control views for agents, sessions, overview, usage, logs, config, channels, setup, cron, and skills.
- Tests inspected:
  - `tests/test_gateway/test_webui_rpc_access_static.py`
  - `tests/test_gateway/test_webui_http_access_static.py`
  - `tests/test_gateway/test_chat_view_static.py`
  - `tests/test_gateway/test_chat_static_assets.py`
  - `tests/test_gateway/test_agents_view_static.py`
  - `tests/test_gateway/test_status_helper_static.py`
  - `tests/test_gateway/test_usage_view_static.py`
  - `tests/test_gateway/test_logs_view_static.py`
  - `tests/test_gateway/test_static_onboarding_views.py`
  - `tests/test_gateway/test_cron_view_static.py`
  - `tests/test_gateway_static_skills_view.py`
  - `tests/test_gateway/test_token_widget_static.py`
  - `tests/test_gateway/test_rpc_public_surface_baseline.py`
  - `tests/test_gateway/test_rpc_sessions.py`
  - `tests/test_gateway/test_rpc_sessions_attachments.py`
- Existing boundary pattern this stage follows:
  - Web UI views must access RPC only through `window.WebUiRpc`; no view should call `App.getRpc()`.
  - Browser HTTP/fetch/auth handling must live in `window.WebUiHttp`; no direct `fetch(` outside `http_access.js`.
  - Static tests lock contract strings because there is no JS unit harness for the v1 Web UI.
  - Shared status/primitive helpers live under `window.UI`.

## Superpowers evidence

- `superpowers:using-git-worktrees`:
  - Evidence: read the skill; verified previous temporary refactor worktrees were removed; created fixed active child worktree at `../opensquilla-refactor-active` on branch `codex/refactor-webui-rpc-view-state-contract-batch`.
- `superpowers:writing-plans`:
  - Evidence: read the skill; created this stage plan before worker implementation; plan includes exact files, worker ownership, TDD commands, full gates, merge review, and cleanup.
- `superpowers:test-driven-development`:
  - Evidence: read the skill; every worker must write a failing static boundary/behavior contract first and record expected RED failure before implementation.
- `superpowers:verification-before-completion`:
  - Evidence: read the skill; stage cannot be claimed complete until focused worker tests, touched-file checks, child `scripts/refactor_gate.sh`, integration `scripts/refactor_gate.sh`, and cleanup audit are recorded.
- `superpowers:dispatching-parallel-agents` / `superpowers:subagent-driven-development`:
  - Evidence: read the skills; same-thread `spawn_agent` healthcheck succeeded with agent `019e3c2b-a31a-7771-9047-e7d6a314f2dd`; this stage will dispatch independent worker agents with separate branches/worktrees.
- Parallelism decision:
  - Use multi-agent, multi-branch parallel execution because the selected Web UI subdomains have disjoint primary files.
  - Keep `chat.js` and `chat.css` owned by one worker only.
  - If same-thread spawning fails later, use `scripts/refactor_external_agent.sh` fixed worker slots before sequential fallback.
- Historical evidence note:
  - The user explicitly required every large refactor substage to use and record Superpowers. Treat missing per-worker evidence as a stage-record gap.

## Boundary decision

- Module batch:
  - `webui-rpc-view-state-contract-batch`
- Responsibilities moving out or clarifying:
  - Web UI transport/access contract ownership around RPC/HTTP/auth and static load order.
  - Chat view-state rendering sub-boundaries for artifacts, run state, attachment state, stream reconciliation, and savings effects.
  - Shared UI helper ownership for status chips, drawers, comboboxes, token widgets, and repeated control-view rendering.
  - Control view RPC/view-state contracts across overview, sessions, agents, usage, logs, config, setup, channels, cron, and skills.
- Responsibilities staying in place:
  - Public RPC method names/scopes and Gateway payload shapes.
  - Existing template script load order except deliberate boundary additions with tests.
  - Existing chat behavior and user-visible copy.
  - Existing static view CSS class names unless tests are updated for a behavior-preserving rename.
- New module/file responsibility:
  - Workers may add focused static helper modules under `src/opensquilla/gateway/static/js/` only when a RED test proves ownership and load order is updated.
  - Workers may add focused Python static tests under `tests/test_gateway/` for import/load-order/string-contract checks.
- Public behavior that must not change:
  - `WebUiRpc` and `WebUiHttp` public methods and load order.
  - Chat upload/download auth, artifact previews, markdown rendering, interrupt marks, run-state pills, task terminal mappings, session switching, and savings animation semantics.
  - Agents/sessions drawer/combobox behavior, status chips, usage exports/charts/model breakdown, logs/config copy, setup/channel/cron/skills static contracts.
  - Public RPC method names/scopes in `tests/test_gateway/test_rpc_public_surface_baseline.py`.
- Files explicitly out of scope:
  - Provider runtime/model routing.
  - Knowledge services code completed in the previous batch.
  - Tools/sandbox/security surfaces.
  - Large visual redesign or CSS theme overhaul.

## Parallel Worker Ownership

- Worker `webui-transport-access` owns:
  - `src/opensquilla/gateway/templates/index.html`
  - `src/opensquilla/gateway/static/js/rpc.js`
  - `src/opensquilla/gateway/static/js/rpc_access.js`
  - `src/opensquilla/gateway/static/js/http_access.js`
  - `src/opensquilla/gateway/static/js/app.js`
  - `src/opensquilla/gateway/static/js/approval_monitor.js`
  - Tests:
    - `tests/test_gateway/test_webui_rpc_access_static.py`
    - `tests/test_gateway/test_webui_http_access_static.py`
    - selected non-chat assertions in `tests/test_gateway/test_chat_static_assets.py` only if required for HTTP/auth access.
- Worker `webui-chat-state` owns:
  - `src/opensquilla/gateway/static/js/views/chat.js`
  - `src/opensquilla/gateway/static/css/views/chat.css`
  - `src/opensquilla/gateway/static/js/components/savings-fx.js`
  - Tests:
    - `tests/test_gateway/test_chat_view_static.py`
    - `tests/test_gateway/test_chat_static_assets.py`
- Worker `webui-control-views` owns:
  - `src/opensquilla/gateway/static/js/components.js`
  - `src/opensquilla/gateway/static/css/components.css`
  - `src/opensquilla/gateway/static/js/views/agents.js`
  - `src/opensquilla/gateway/static/css/views/agents.css`
  - `src/opensquilla/gateway/static/js/views/sessions.js`
  - `src/opensquilla/gateway/static/css/views/sessions.css`
  - `src/opensquilla/gateway/static/js/views/overview.js`
  - `src/opensquilla/gateway/static/js/views/usage.js`
  - `src/opensquilla/gateway/static/css/views/usage.css`
  - `src/opensquilla/gateway/static/js/views/logs.js`
  - `src/opensquilla/gateway/static/js/views/config.js`
  - Tests:
    - `tests/test_gateway/test_agents_view_static.py`
    - `tests/test_gateway/test_status_helper_static.py`
    - `tests/test_gateway/test_usage_view_static.py`
    - `tests/test_gateway/test_logs_view_static.py`
- Worker `webui-setup-domain-views` owns:
  - `src/opensquilla/gateway/static/js/views/setup.js`
  - `src/opensquilla/gateway/static/css/views/setup.css`
  - `src/opensquilla/gateway/static/js/views/channels.js`
  - `src/opensquilla/gateway/static/css/views/channels.css`
  - `src/opensquilla/gateway/static/js/views/cron.js`
  - `src/opensquilla/gateway/static/css/views/cron.css`
  - `src/opensquilla/gateway/static/js/views/skills.js`
  - `src/opensquilla/gateway/static/css/views/skills.css`
  - Tests:
    - `tests/test_gateway/test_static_onboarding_views.py`
    - `tests/test_gateway/test_cron_view_static.py`
    - `tests/test_gateway_static_skills_view.py`

Workers are not alone in the codebase. Each worker must preserve other workers' edits, avoid shared-file changes outside ownership, and not revert unrelated changes. If a worker needs a shared file outside ownership, it must stop and report instead of editing it.

## TDD Red/Green

- Failing test commands:
  - Transport/access: `uv run --extra dev pytest tests/test_gateway/test_webui_rpc_access_static.py tests/test_gateway/test_webui_http_access_static.py -q`
  - Chat: `uv run --extra dev pytest tests/test_gateway/test_chat_view_static.py tests/test_gateway/test_chat_static_assets.py -q`
  - Control views: `uv run --extra dev pytest tests/test_gateway/test_agents_view_static.py tests/test_gateway/test_status_helper_static.py tests/test_gateway/test_usage_view_static.py tests/test_gateway/test_logs_view_static.py -q`
  - Setup/domain views: `uv run --extra dev pytest tests/test_gateway/test_static_onboarding_views.py tests/test_gateway/test_cron_view_static.py tests/test_gateway_static_skills_view.py -q`
- Expected red failures:
  - New static boundary tests fail because a helper module, load-order contract, view-state helper, or ownership string does not exist yet.
  - If a worker only clarifies an existing boundary, it must add an AST/text boundary assertion that fails on current ownership before implementation.
- Behavior compatibility coverage:
  - Worker suites above.
  - `tests/test_gateway/test_rpc_public_surface_baseline.py` and session RPC tests if a worker touches Gateway RPC contracts.
- Module-batch implementation:
  - Move or clarify one coherent ownership boundary per worker.
  - Preserve static load order and user-facing copy.
  - Keep worker changes within ownership.
- Focused green command:
  - `uv run --extra dev pytest tests/test_gateway/test_webui_rpc_access_static.py tests/test_gateway/test_webui_http_access_static.py tests/test_gateway/test_chat_view_static.py tests/test_gateway/test_chat_static_assets.py tests/test_gateway/test_agents_view_static.py tests/test_gateway/test_status_helper_static.py tests/test_gateway/test_usage_view_static.py tests/test_gateway/test_logs_view_static.py tests/test_gateway/test_static_onboarding_views.py tests/test_gateway/test_cron_view_static.py tests/test_gateway_static_skills_view.py tests/test_gateway/test_token_widget_static.py tests/test_gateway/test_rpc_public_surface_baseline.py -q`
- Additional touched-file checks:
  - `uv run --extra dev ruff check tests/test_gateway/test_webui_rpc_access_static.py tests/test_gateway/test_webui_http_access_static.py tests/test_gateway/test_chat_view_static.py tests/test_gateway/test_chat_static_assets.py tests/test_gateway/test_agents_view_static.py tests/test_gateway/test_status_helper_static.py tests/test_gateway/test_usage_view_static.py tests/test_gateway/test_logs_view_static.py tests/test_gateway/test_static_onboarding_views.py tests/test_gateway/test_cron_view_static.py tests/test_gateway_static_skills_view.py tests/test_gateway/test_token_widget_static.py`
  - `git diff --check`

## Files

- Create:
  - Worker-specific static helper modules and static boundary tests as justified by RED tests.
- Modify:
  - This stage file.
  - Worker-owned files listed in Parallel Worker Ownership.
- Test:
  - Worker tests listed in Parallel Worker Ownership.
- Documentation:
  - This stage file records Superpowers, TDD, merge, gate, and cleanup evidence.

## Detailed Superpowers Implementation Plan

### Task 1: Baseline, Evidence, and Stage Plan

- [x] Run `scripts/refactor_preflight.sh --expect-branch codex/refactor-architecture` from integration.
- [x] Confirm `spawn_agent` status.
  - Observed: same-thread healthcheck succeeded.
- [x] Read required Superpowers skills:
  - `superpowers:using-superpowers`
  - `superpowers:using-git-worktrees`
  - `superpowers:writing-plans`
  - `superpowers:dispatching-parallel-agents`
  - `superpowers:test-driven-development`
  - `superpowers:verification-before-completion`
- [x] Use Serena project activation and initial instructions.
- [x] Create fixed active worktree on `codex/refactor-webui-rpc-view-state-contract-batch`.
- [x] Write this stage plan before implementation.
- [ ] Commit this stage plan as the worker base.

### Task 2: Worker `webui-transport-access`

- [ ] Create an independent worker worktree/branch.
- [ ] Write RED static boundary tests for RPC/HTTP access ownership or load order.
- [ ] Run the worker RED command and record the expected failure.
- [ ] Implement one behavior-compatible transport/access boundary move.
- [ ] Run worker focused tests and touched-file checks.
- [ ] Commit with the required co-author trailer.

### Task 3: Worker `webui-chat-state`

- [ ] Create an independent worker worktree/branch.
- [ ] Write RED static boundary tests for chat view-state ownership.
- [ ] Run the worker RED command and record the expected failure.
- [ ] Implement one behavior-compatible chat view-state boundary move.
- [ ] Run worker focused tests and touched-file checks.
- [ ] Commit with the required co-author trailer.

### Task 4: Worker `webui-control-views`

- [ ] Create an independent worker worktree/branch.
- [ ] Write RED static boundary tests for shared UI/control-view ownership.
- [ ] Run the worker RED command and record the expected failure.
- [ ] Implement one behavior-compatible shared UI/control-view boundary move.
- [ ] Run worker focused tests and touched-file checks.
- [ ] Commit with the required co-author trailer.

### Task 5: Worker `webui-setup-domain-views`

- [ ] Create an independent worker worktree/branch.
- [ ] Write RED static boundary tests for setup/domain view ownership.
- [ ] Run the worker RED command and record the expected failure.
- [ ] Implement one behavior-compatible setup/domain view boundary move.
- [ ] Run worker focused tests and touched-file checks.
- [ ] Commit with the required co-author trailer.

### Task 6: Main Integration Review

- [ ] Wait for all worker branches and read summaries.
- [ ] Review each branch diff before merge.
- [ ] Merge worker branches into child branch one by one with `git merge --no-ff`.
- [ ] Resolve conflicts without reverting another worker's ownership.
- [ ] Run the focused batch green command.
- [ ] Run touched-file ruff and `git diff --check`.
- [ ] Run full child `scripts/refactor_gate.sh`.
- [ ] Commit stage-record update with the required co-author trailer.

### Task 7: Integration Branch Merge and Cleanup

- [ ] Merge child into integration with `git merge --no-ff codex/refactor-webui-rpc-view-state-contract-batch`.
- [ ] Run full integration `scripts/refactor_gate.sh`.
- [ ] Update this completion record with worker commits, child hash, integration hash, verification output, residual risk, and next recommended slice.
- [ ] Commit the stage record update on integration with the required co-author trailer.
- [ ] Remove `../opensquilla-refactor-active`.
- [ ] Remove worker worktrees created for this batch.
- [ ] Run `git worktree prune`.
- [ ] Verify no extra refactor worktree directories remain beyond `../opensquilla-refactor-integration`.

## Child Gate

- `uv run --extra dev ruff check src tests`
- `uv run --extra dev mypy src/opensquilla --show-error-codes`
- `git diff --check`
- `uv run --extra dev pytest`
- gateway smoke through `scripts/refactor_gate.sh`

## Integration Gate

- `uv run --extra dev ruff check src tests`
- `uv run --extra dev mypy src/opensquilla --show-error-codes`
- `git diff --check HEAD^ HEAD`
- `uv run --extra dev pytest`
- gateway smoke through `scripts/refactor_gate.sh`

## Rollback

- Revert the integration merge commit if Web UI RPC/HTTP access, chat behavior, static load order, or public RPC surface behavior regresses.
- Keep worker branches until a replacement slice is ready.
- Do not rewrite `main` or unrelated worktrees.

## Completion Record

- Worker commits:
- Child integration commits:
- Integration merge:
- Verification evidence:
- Residual risk:
- Next recommended slice:
