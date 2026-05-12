# OpenSquilla OpenClaw Migration vs Hermes

## Current Conclusion

OpenSquilla now performs an OpenClaw migration with OpenSquilla-native semantic
conversion. It is no longer only a copy-and-archive migration.

The current strategy is:

- Migrate directly into OpenSquilla-native config, workspace, skills, and env surfaces.
- Convert important OpenClaw semantics when OpenSquilla has a real native equivalent.
- Preserve original workspace text when branding conversion changes user-facing files.
- Write migration notes for partial or unsupported semantics.
- Avoid unsafe privilege widening, especially for channel sender policies.

Hermes still has broader long-tail behavior coverage. OpenSquilla is stricter:
it only writes behavior that OpenSquilla can actually enforce.

## Shared Coverage

Both OpenSquilla and Hermes support these OpenClaw migration behaviors:

- Dry-run by default.
- Explicit apply mode.
- Secrets are opt-in.
- Workspace/persona files are migrated.
- Memory is merged.
- Skills are imported from multiple OpenClaw-style roots.
- Model config supports string, object, and alias/catalog forms.
- Provider keys can come from `.env` and provider config.
- Sensitive runtime artifacts are skipped.
- Unsupported or unsafe material is preserved through archives or notes.
- Migration reports are emitted.

## OpenSquilla Native Semantics

OpenSquilla currently maps these OpenClaw semantics into native OpenSquilla
behavior:

- OpenClaw branding in workspace text:
  - `OpenClaw` -> `OpenSquilla`
  - `ClawdBot` / `MoltBot` -> `OpenSquilla`
  - `.openclaw` -> `.opensquilla`
- Original changed workspace files are archived under:
  - `archive/files/workspace-original/`
- `agents.defaults.model` supports:
  - plain string model id
  - object format such as `{ "primary": "..." }`
  - alias/catalog reverse lookup
- `agents.defaults.timeoutSeconds` maps to:
  - `agent_runtime_timeout_seconds`
- `agents.defaults.thinkingDefault` maps to:
  - `llm.thinking`
- `agents.defaults.compaction.mode` maps to:
  - `context_overflow_policy`
- `BRAVE_API_KEY` maps to:
  - `search_provider = "brave"`
  - `search_api_key_env = "BRAVE_API_KEY"`
- `adminUsers` / `admin_users` map to:
  - `channel_admin_senders`

## Safety Difference: Channel Policy

OpenSquilla intentionally does not map ordinary OpenClaw channel allowlists to
admin privilege.

These OpenClaw fields are treated as access policy and recorded in notes:

- `allowFrom`
- `allowedUsers`
- `allowed_users`
- `allowlist`

Only explicit admin fields are mapped to OpenSquilla admin senders:

- `adminUsers`
- `admin_users`

Reason: in OpenSquilla, `channel_admin_senders` can grant operator/owner
semantics. Treating a normal allowlist as admin users would be a privilege
escalation.

## OpenSquilla Notes Instead of Fake Config

OpenSquilla writes `MIGRATION_NOTES.md` and includes `notes` in dry-run JSON
reports for semantics that need review or cannot be safely mapped.

Current notes include cases such as:

- OpenClaw channel allowlists that are not admin senders.
- WhatsApp or Signal settings detected without a native migrated channel entry.
- TTS provider/voice/model config archived while assets are copied.
- MCP fields such as headers/auth/cwd/include/exclude when not natively mapped.
- Agent defaults such as verboseDefault, humanDelay, and userTimezone.

## Remaining Differences From Hermes

Hermes still covers more long-tail behavior automatically:

- WhatsApp migration.
- Signal migration.
- More complete TTS config mapping.
- More complete MCP advanced field mapping.
- More browser/session/approval/tool policy migration.
- More detailed memory parsing and structured merging.
- More complete post-migration guidance and cleanup flow.

OpenSquilla's current gap is not "no semantic conversion". The gap is long-tail
runtime behavior coverage.

## Verification Evidence

The OpenSquilla migration behavior is covered by these tests:

- `tests/test_migration/test_openclaw_migration.py`
- `tests/test_migration/test_openclaw_e2e.py`

The E2E test builds a realistic OpenClaw footprint, runs the `opensquilla migrate
openclaw` CLI, and verifies:

- Existing OpenSquilla config is preserved.
- Workspace files are migrated.
- Skills are imported and exposed through `skills.extra_dirs`.
- Secrets are redacted in reports.
- Provider/model/MCP/channel config is migrated where native.
- Unsupported config is archived.
- Sensitive runtime state is skipped.
- Unrelated OpenSquilla workspace and state files are not touched.

