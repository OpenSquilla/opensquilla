# OpenSquilla Releases

| Version | Tag | Date | Notes |
|---|---|---|---|
| 0.2.0rc1 | v0.2.0rc1 | 2026-05-19 | Second public preview |
| 0.1.0rc1 | v0.1.0rc1 | 2026-05-12 | First public preview |

Preview releases publish only versioned assets:

- `OpenSquilla-<version>-windows-x64-py312-recommended-portable.zip`
- `opensquilla-<version>-py3-none-any.whl`
- `SHA256SUMS`

Stable releases additionally publish version-independent aliases for
`/releases/latest/download/` URLs:

- `OpenSquilla-windows-x64-portable.zip`
- `opensquilla-latest-py3-none-any.whl`

GitHub source archives remain available for code review and developer
reference; source installs should use `git clone` plus Git LFS. Public
wheelhouse zips, macOS portable zips, and Linux portable zips are intentionally
not published for this preview. macOS and Linux users install the same
versioned wheel through the `uv tool install` command documented in the README.

Preview releases are GitHub pre-releases. Their README install commands must
use tag-pinned URLs such as:

- `https://github.com/opensquilla/opensquilla/releases/download/v0.2.0rc1/OpenSquilla-0.2.0rc1-windows-x64-py312-recommended-portable.zip`
- `https://github.com/opensquilla/opensquilla/releases/download/v0.2.0rc1/opensquilla-0.2.0rc1-py3-none-any.whl`

Stable releases may use the `/releases/latest/download/` aliases after a
non-pre-release GitHub Release exists.

## Preview tag SOP

1. Verify `git status` is clean.
2. Update `CHANGELOG.md`: move entries from `[Unreleased]` to `[0.2.0rc1] - <date>` section; reopen empty `[Unreleased]`.
3. Bump `pyproject.toml` to `0.2.0rc1`.
4. `git tag -a v0.2.0rc1 -m "OpenSquilla 0.2.0 Preview 1"`
5. `git push origin v0.2.0rc1` (this triggers `.github/workflows/wheelhouse-release.yml`)
6. Wait for the Windows release workflow → review the draft GitHub Release.
   Confirm it contains exactly the three preview assets listed above, plus
   GitHub's generated source archives, before publishing.
7. Confirm the draft GitHub Release is marked as a pre-release.
8. Publish the GitHub Release, then run the post-publish tag URL checks:

   ```sh
   curl --fail --head --location https://github.com/opensquilla/opensquilla/releases/download/v0.2.0rc1/OpenSquilla-0.2.0rc1-windows-x64-py312-recommended-portable.zip
   curl --fail --head --location https://github.com/opensquilla/opensquilla/releases/download/v0.2.0rc1/opensquilla-0.2.0rc1-py3-none-any.whl
   ```

9. For stable `0.2.0`, publish a non-pre-release GitHub Release and run the
   post-publish latest URL checks:

   ```sh
   curl --fail --head --location https://github.com/opensquilla/opensquilla/releases/latest/download/OpenSquilla-windows-x64-portable.zip
   curl --fail --head --location https://github.com/opensquilla/opensquilla/releases/latest/download/opensquilla-latest-py3-none-any.whl
   ```

10. For subsequent previews: bump `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, and the tag to `0.2.0rc2`, `v0.2.0rc2`, etc.

## GitHub-only release checks

These checks cannot be fully proven by local artifact generation:

- The tag exists on GitHub and matches `pyproject.toml`.
- The release workflow can fetch hydrated Git LFS router assets.
- Preview GitHub Releases contain the versioned assets and `SHA256SUMS` after
  `gh release upload --clobber`.
- Stable GitHub Releases contain the versioned assets, stable aliases, and
  `SHA256SUMS` after `gh release upload --clobber`.
- After a stable GitHub Release is published, the stable release URLs resolve:
  `.../releases/latest/download/OpenSquilla-windows-x64-portable.zip` and
  `.../releases/latest/download/opensquilla-latest-py3-none-any.whl`.
- After a preview GitHub Release is published, the tag-pinned release asset URLs
  resolve.
- Windows browser downloads may carry Mark-of-the-Web; SmartScreen,
  Smart App Control, enterprise policy, and unsigned binary reputation must be
  checked on a real Windows machine.

## Why the package version uses rc

Release zips are distributed as built artifacts, so the package filename,
manifest, zip name, and tag should describe the same preview build. PEP 440
accepts `0.2.0rc1`, while the public GitHub Release title can use the friendlier
name "OpenSquilla 0.2.0 Preview 1".
