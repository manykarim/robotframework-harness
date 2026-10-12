## Context

See proposal.md (Why). Current state:

- **Repository:** `manykarim/robotframework-harness` is public. The workflows are `ci.yml` (tests on 3 OSes × 4
  Pythons), `docs.yml` (strict build, reference check, offline link check; no deploy), `evidence.yml` and `eval.yml`
  (manual). There is no release workflow, Pages is not enabled, and no environments exist.
- **Versions:** `0.9.0` in `src/rf_harness/__init__.py`, `plugins/rf-harness/.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json`. `scripts/check_versions.py` requires all three to be equal.
- **Package:** `uv build` builds the sdist, then the wheel from that sdist. The hatch hook bundles
  `plugins/rf-harness/` into `rf_harness/_assets/`; CI already checks the wheel for `SKILL.md`.
- **PyPI:** the name `robotframework-harness` was free on 2026-10-11. Trusted publishing for a new project needs a
  "pending publisher" registered by the owner on pypi.org (and on test.pypi.org for the dry run).

## Goals / Non-Goals

**Goals:**
- Every release goes through one command, a tag push. Verification, publishing, the GitHub release and the `stable`
  tag all follow from it.
- No long-lived credentials: OIDC trusted publishing only.
- Each irreversible publish has a human approval point.
- The docs are always live from `main`.

**Non-Goals:**
- Uploading the transcript release assets (separate decision).
- Automatic version bumping or changelog generation.
- Publishing to conda or other indexes.
- Re-running the live release gate in the release workflow. It is a manual prerequisite, recorded in evidence
  (round 8 for v1).

## Decisions

### D1. One `release.yml`, triggered by version tags, with gated jobs

```
on: push tags v[0-9]+.[0-9]+.[0-9]+ and v[0-9]+.[0-9]+.[0-9]+rc[0-9]+

verify   tag == package version; plugin + marketplace == release part; CHANGELOG entry exists
test     uv run pytest -m "not browser"; gen_reference --check; evidence: checksums, scrub, claims
build    uv build -> dist/*; wheel contains _assets SKILL.md + bin/rfh-launch + hooks/hooks.json;
         `uvx twine check dist/*`; upload dist as a workflow artifact
publish-testpypi   (rc tags only)    environment testpypi, pypa/gh-action-pypi-publish, repository-url TestPyPI
publish-pypi       (final tags only) environment pypi,     pypa/gh-action-pypi-publish
github-release     (final tags only) gh release create v<version> dist/* --notes-file docs/releases/<version>.md
move-stable        (final tags only) git tag -f stable <sha>; git push -f origin refs/tags/stable
```

- Publish jobs download the exact `dist/` artifact of the build job. Nothing is rebuilt after verification.
- Permissions are least-privilege per job:
  - `id-token: write` only on the publish jobs;
  - `contents: write` only on github-release and move-stable.
- Alternatives considered:
  - **Publishing from a laptop with an API token:** a stored secret, and not reproducible.
  - **One job that does everything:** too broad permissions, and it can't pause for approval before publishing.

### D2. Version rules for final and candidate releases

- **Final:** tag `v1.0.0`; all three files say `1.0.0`.
- **Candidate:** tag `v1.0.0rc1`; the package says `1.0.0rc1`; `plugin.json` and `marketplace.json` keep `1.0.0`.
  Plugin manifests expect a plain release version, and candidates are only for the PyPI dry run.
- `scripts/check_versions.py` therefore compares the **release part**: it strips `rcN`, `aN`, `bN` and `.devN` from
  the package version. A new `--tag vX` option additionally requires the package version to equal the tag exactly.
  CI keeps using the release-part check.

### D3. Protected environments as the approval point

- **`pypi`:** deployment limited to tags matching `v*`, required reviewer `manykarim`. Each real publish waits for one
  click in GitHub, which is the owner's go-ahead.
- **`testpypi`:** tags matching `v*rc*`, no reviewer.
- **Tag ruleset on `refs/tags/v*`:** blocks updates and deletions, so published versions can't be moved. `stable` stays
  movable, but only the release workflow moves it.
- Alternative considered: no reviewer. Rejected for the first releases; it can be relaxed later.

### D4. Trusted publisher registration (owner, once per index)

| field | PyPI (pypi.org → Publishing → pending publisher) | TestPyPI (test.pypi.org) |
|---|---|---|
| PyPI project name | `robotframework-harness` | `robotframework-harness` |
| owner | `manykarim` | `manykarim` |
| repository | `robotframework-harness` | `robotframework-harness` |
| workflow | `release.yml` | `release.yml` |
| environment | `pypi` | `testpypi` |

A pending publisher does not reserve the name until the first upload. The dry run and the real release should follow
soon after registration.

### D5. Docs deployment from the docs workflow

- `docs.yml` keeps its build-and-check job for pushes and pull requests. On pushes to `main` it also uploads the site
  (`actions/upload-pages-artifact`).
- A `deploy` job then runs only for `main`: `actions/deploy-pages`, environment `github-pages`, permissions
  `pages: write` and `id-token: write`.
- Pages is enabled once with the "GitHub Actions" source:
  `gh api -X POST repos/manykarim/robotframework-harness/pages -f build_type=workflow`.
- `mkdocs.yml` gets `site_url: https://manykarim.github.io/robotframework-harness/`.
- A docs deploy also triggers on `workflow_dispatch`, so the site can be republished without a commit.

### D6. Release notes as a docs page

`docs/releases/1.0.0.md` (also in the docs navigation) serves as the GitHub release body. It covers:
- what the harness is and the install commands;
- supported agents and verified versions;
- the evidence headline (rounds 7 and 8);
- known limits (desktop opt-in, Windows not through the live gate, VS Code verified only via doctor);
- upgrade notes for research-prototype users.

`verify` fails when the file for the tagged version is missing.

### D7. Order of the first release

1. Merge the workflow, docs and version-check changes; enable Pages and check the site.
2. The owner registers both pending publishers (D4). Environments and the tag ruleset are created.
3. Set the package version to `1.0.0rc1` and push tag `v1.0.0rc1` (with the owner's go-ahead). It publishes to TestPyPI.
   Check `uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/
   robotframework-harness==1.0.0rc1 version`.
4. Set the package version to `1.0.0` and push tag `v1.0.0` (with the owner's go-ahead). The owner approves the `pypi`
   environment. The workflow publishes to PyPI, creates the GitHub release and moves `stable`.
5. Post-release checks:
   - `uvx robotframework-harness install --dry-run` in a clean project;
   - a marketplace install pinned to `v1.0.0`, with an isolated Claude config dir;
   - the docs URL answers.

## Risks / Trade-offs

- [PyPI never allows re-uploading a version] → the TestPyPI dry run with an rc tag, verification before publish, and
  manual approval in the `pypi` environment.
- [Someone registers the name first, or PyPI rejects it as too similar to an existing project] → publish soon after
  the pending-publisher registration. If PyPI rejects the name, the fallback `robotframework-agentharness` (free on
  2026-10-11) needs a follow-up change: package name, docs and installer commands.
- [The build backend emits a metadata version the publish toolchain rejects] → found during implementation: hatchling
  1.30+ (except 1.31) writes `Metadata-Version: 2.5`, and twine 6.2 (used by the PyPI publish action) rejects it.
  The build backend is pinned to `hatchling>=1.27,<1.30` (2.4, with PEP 639 license-files), and the build job runs
  `twine check --strict`.
- [`uv build` from the sdist loses the assets] → the build job checks the wheel content. The hatch hook already
  handles sdist → wheel.
- [Root-relative links break on the project Pages path] → `site_url`. The link check already excludes the generated
  404 page.
- [A `stable` force-push races with a concurrent release] → `concurrency: release` on the workflow. Only final tags
  move `stable`.
- [Marketplace pins need agent support for refs] → the docs already show `#v1.0.0` / `--ref`. The post-release check
  covers Claude Code.

## Migration Plan

- Additive: new workflow, docs job and settings; the version bump is the only behaviour change for users.
- Rollback for a bad release: PyPI yank (not delete), mark the GitHub release as pre-release or delete it, and point
  `stable` back to the previous tag. Version tags are never moved.
