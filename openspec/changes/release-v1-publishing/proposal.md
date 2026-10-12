## Why

The harness passed its v1 release gate: evidence round 8, rf-harness 0.82 vs the v3.2 prototype's 0.82 in the same
window. The repository is public. But users still cannot use the main quick start: `uvx robotframework-harness
install` needs a PyPI release, the docs are only Markdown in the repository, and no tag exists for teams to pin.

This change completes the open publishing part of task 8.2 of `bootstrap-ai-engineering-harness`. The release process
must be repeatable and token-free, so every future release works the same way.

## What Changes

- **Docs on GitHub Pages.**
  - The MkDocs site is deployed from `main` to `https://manykarim.github.io/robotframework-harness/` by the docs
    workflow.
  - Pages is enabled with the GitHub Actions source.
  - `site_url` is set in `mkdocs.yml`.
- **PyPI trusted publishing.**
  - A new release workflow publishes `robotframework-harness` (wheel and sdist) to PyPI through OIDC trusted
    publishing. No API token is stored anywhere.
  - Publishing runs through a protected GitHub environment `pypi`.
  - A `testpypi` environment allows a dry run with a release-candidate tag before the first real release.
- **Version 1.0.0 and tags.**
  - The package, `plugin.json` and `marketplace.json` versions go to `1.0.0`.
  - Release notes are added.
  - Tag `v1.0.0` triggers the release. After a successful publish, the moving `stable` tag points at it, as the
    marketplace pinning in the docs describes.
- **Verified artifacts.**
  - Before anything is published, the release workflow checks that the tag matches all three versions. It also runs
    the test suite, the generated-reference check and the evidence checks.
  - The wheel must contain the bundled plugin assets, and the built artifacts must pass a metadata check.
  - A GitHub release is created with the wheel and sdist attached.
- **After the release:** an install from PyPI on a clean environment, a marketplace install pinned to `v1.0.0`, and the
  live docs URL are checked.

Out of scope: attaching the transcript archives (about 92 MB) to the release. The tooling exists
(`evidence/pack_transcripts.py`). Uploading them is a separate decision.

## Capabilities

### New Capabilities

- `release-publishing`: how a version is released. Covers version and tag consistency, the pre-publish verification,
  token-free PyPI publishing through protected environments with a TestPyPI dry run, the GitHub release with
  artifacts, the moving `stable` tag, and docs deployment to GitHub Pages.

### Modified Capabilities

None. The tag-pinning behaviour for users is already specified by `marketplace-distribution` in change
`bootstrap-ai-engineering-harness`, which is not archived yet. This change only adds the process that produces those
tags.

## Impact

- New `.github/workflows/release.yml`. `docs.yml` gains a Pages deploy job on `main`.
- `mkdocs.yml` gets `site_url`. The versions change to `1.0.0` in `src/rf_harness/__init__.py`,
  `plugins/rf-harness/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. Release notes go in
  `docs/releases/1.0.0.md`.
- Repository settings: Pages (source: GitHub Actions); environments `pypi` and `testpypi`, with `pypi` limited to
  `v*` tags.
- **Owner actions outside the repository:** the PyPI and TestPyPI "pending trusted publisher" registration needs the
  owner's PyPI account.
- Outward-facing, irreversible steps need the owner's explicit go-ahead when they run:
  - pushing the release tags;
  - the first PyPI publish (PyPI never allows reusing a version number).
