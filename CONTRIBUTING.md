# Contributing

Thanks for improving OpenSquilla. Keep pull requests small, focused, and covered by tests that outside contributors can run without private access.

## Branch Targets

Open regular feature and bug-fix pull requests against `dev`. The `dev` branch is the shared integration line for the next release.

Open pull requests against `main` only for release candidates, release stabilization, or urgent hotfixes that start from the current published line. If a pull request was opened against `main` by mistake, retarget it to `dev` before review.

## Default Checks

Install development dependencies:

```powershell
uv sync --extra dev --extra recommended
```

Run the public quality gate before opening a pull request:

```powershell
uv run ruff check src tests
uv run pytest -q
uv build --wheel
```

Default tests must be offline, deterministic, credential-free, and safe for forks. Do not add network, provider, browser, or channel requirements to the default pull request path.

## Test Expectations

Add or update public regression tests for behavior changes and bug fixes. Prefer focused unit or integration tests unless the behavior crosses the gateway, browser UI, provider, or channel boundary.

Live checks are maintainer-only gates. The `Live Release E2E` workflow covers real provider, browser, and optional channel smoke tests with GitHub secrets and explicit opt-in inputs.

## Private Materials

Private test suites, release red-team prompts, real provider transcripts, real channel identifiers, local paths, credentials, and AI session artifacts must not be committed.

Local maintainer-only files may live under `tests/_private/` or `.omx/private-golden/`; both are excluded from the public tree and default pytest collection.

## Security Reports

Do not include vulnerability details, exploit steps, credentials, or provider tokens in public issues. Use the process in `SECURITY.md` for suspected vulnerabilities.

## Community Standards

Keep discussion technical, specific, and respectful. The expected conduct for issues, pull requests, and maintainer decisions is documented in `CODE_OF_CONDUCT.md`.
