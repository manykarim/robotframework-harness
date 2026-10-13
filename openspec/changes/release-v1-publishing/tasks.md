## 1. Version handling and release notes

- [x] 1.1 Extend `scripts/check_versions.py`:
  - compare the release part (strip `rcN`, `aN`, `bN`, `.devN` from the package version);
  - add `--tag vX`, which also requires the package version to equal the tag exactly.

  Verify with tests: a matching final, a matching rc, a mismatched tag, and plugin/marketplace drift each give the
  expected exit code.
- [x] 1.2 Write `docs/releases/1.0.0.md` and add it to the docs nav. Content: what it is, install, agents and
  versions, evidence headline (rounds 7 and 8), known limits, upgrade notes. Verify that the strict docs build passes
  and that every number on the page has a claim (`check_claims --check-sources`).

## 2. GitHub Pages

- [x] 2.1 Add `site_url: https://manykarim.github.io/robotframework-harness/` to `mkdocs.yml`, and a Pages
  upload + `deploy` job to `docs.yml` (only `main` pushes and manual dispatch; PRs build only). Verify that
  actionlint is clean and that the local strict build passes.
- [ ] 2.2 Enable Pages with the GitHub Actions source (`gh api -X POST repos/manykarim/robotframework-harness/pages -f
  build_type=workflow`) and run the docs workflow on `main`. Verify that
  `https://manykarim.github.io/robotframework-harness/` returns 200 and shows the home page, and that one evidence link
  resolves to the repository.

## 3. Release workflow

- [x] 3.1 Write `.github/workflows/release.yml` per design D1: jobs verify / test / build / publish-testpypi /
  publish-pypi / github-release / move-stable; tag filters for final and rc tags; per-job permissions;
  `concurrency: release`; artifact hand-over from build to publish. Verify that actionlint is clean.
- [x] 3.2 Make the build job check the wheel content (`_assets/skills/rf-harness/SKILL.md`, `_assets/bin/rfh-launch`,
  `_assets/hooks/hooks.json`) and run `uvx twine check dist/*`. Verify locally by running the same commands on
  `uv build` output.
- [x] 3.3 Create the environments `pypi` (tags `v*`, required reviewer manykarim) and `testpypi` (tags `v*rc*`), and a
  tag ruleset blocking updates and deletions of `refs/tags/v*`. Verify with `gh api` that the environments, branch
  policies, reviewer and ruleset exist.
- [x] 3.4 Check that no PyPI token exists in repository secrets or workflow files. Verify that `gh secret list` and a
  grep over `.github/` show no `PYPI`/`pypi-` token.

## 4. Owner steps (outside the repository)

- [x] 4.1 The owner registers the pending trusted publisher on test.pypi.org and pypi.org with the values in design D4. _(Done 2026-10-13: owner confirmed the pending publishers on test.pypi.org and pypi.org.)_
  Verify by the owner's confirmation (screenshots are not needed), recorded in this task.

## 5. Dry run on TestPyPI (owner go-ahead before the tag push)

- [x] 5.1 Set the package version to `1.0.0rc1` (plugin and marketplace stay `1.0.0`), commit, and push tag _(Done: release run published 1.0.0rc1 wheel + sdist to TestPyPI; publish-pypi, github-release and move-stable skipped; no `stable` tag, no GitHub release.)_
  `v1.0.0rc1`. Verify that the release workflow publishes to TestPyPI only, `stable` does not move, and no GitHub
  release is created.
- [x] 5.2 Install from TestPyPI in a clean environment: _(Done: clean uvx install from TestPyPI prints `rf-harness 1.0.0rc1` / plugin 1.0.0; `install --dry-run` plans the Claude Code files.)_
  `uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ robotframework-harness==1.0.0rc1 version`,
  plus `install --dry-run` in a temporary project. Verify that it prints `rf-harness 1.0.0rc1` and the planned files.

## 6. Release v1.0.0 (owner go-ahead before the tag push and environment approval)

- [ ] 6.1 Set the package version to `1.0.0`, commit, and push tag `v1.0.0`. The owner approves the `pypi`
  environment. Verify that PyPI shows `robotframework-harness 1.0.0` with the wheel and sdist, the GitHub release
  `v1.0.0` has both files and the notes, and `stable` points at the `v1.0.0` commit.
- [ ] 6.2 Post-release checks:
  - `uvx robotframework-harness@1.0.0 install --dry-run --agent claude-code` in a clean project;
  - a Claude Code marketplace install pinned to `v1.0.0` with an isolated `CLAUDE_CONFIG_DIR`;
  - the docs URL.

  Verify that all three succeed, and record the results in the release notes' verification section.
- [ ] 6.3 Mark task 8.2 of `bootstrap-ai-engineering-harness` complete, noting that transcript assets are out of scope.
  Verify that `openspec validate --strict` passes for both changes.
