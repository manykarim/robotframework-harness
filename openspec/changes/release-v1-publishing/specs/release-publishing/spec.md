## Purpose

Defines how a version of robotframework-harness is released: verified before anything leaves the repository, published to PyPI without stored credentials, tagged for pinning, and documented on a live site.

## ADDED Requirements

### Requirement: A release tag must match every version declaration

A release SHALL be triggered by pushing a tag `v<version>`. Before any build or publish step, the release workflow SHALL
verify that `<version>` equals:
- the package version (`rf_harness.__version__`);
- the plugin manifest version;
- the marketplace entry version.

A mismatch MUST fail the workflow and publish nothing.

#### Scenario: mismatched tag is rejected

- **WHEN** tag `v1.0.1` is pushed while the package version is still `1.0.0`
- **THEN** the release workflow fails in its first job, and nothing is built, published or tagged `stable`

### Requirement: Artifacts are verified before publishing

The release workflow SHALL run these checks on the tagged commit, and SHALL publish only if all pass:
- the test suite;
- the generated-reference check;
- the evidence checks (checksums, scrub, claims);
- a build of the wheel and sdist;
- a check that the wheel contains the bundled plugin assets (`rf_harness/_assets/skills/rf-harness/SKILL.md`, the
  hook launcher, the hook definitions);
- a check that both artifacts pass a package metadata check.

The published files MUST be exactly the files that were built and checked in that run.

#### Scenario: a wheel without plugin assets is not published

- **WHEN** the built wheel lacks `rf_harness/_assets/skills/rf-harness/SKILL.md`
- **THEN** the workflow fails before the publish job, and PyPI receives nothing

### Requirement: Publishing uses trusted publishing through protected environments

The workflow SHALL publish to PyPI through OIDC trusted publishing. No PyPI API token MUST exist in repository secrets
or workflow files. The publish job SHALL run in a GitHub environment named `pypi`, which accepts only `v*` tags. A
separate `testpypi` environment SHALL allow publishing a release candidate (`v<version>rc<n>`) to TestPyPI only. A
release-candidate tag MUST NOT publish to PyPI.

#### Scenario: release candidate goes to TestPyPI only

- **WHEN** tag `v1.0.0rc1` is pushed with matching versions
- **THEN** the artifacts are published to TestPyPI, nothing is published to PyPI, and the `stable` tag does not move

#### Scenario: no stored token

- **WHEN** the repository secrets and workflow files are inspected
- **THEN** no PyPI or TestPyPI API token is present, and the publish step relies on the job's OIDC identity

### Requirement: A final release creates a GitHub release and moves the stable tag

After a successful PyPI publish of a final version, the workflow SHALL:
- create a GitHub release for the tag with the release notes, the wheel and the sdist attached;
- point the `stable` tag at the released commit.

Version tags MUST never be moved or deleted.

#### Scenario: v1.0.0 release

- **WHEN** tag `v1.0.0` is published successfully
- **THEN** a GitHub release `v1.0.0` exists with both artifacts and notes, `stable` points at the `v1.0.0` commit, and `uvx robotframework-harness@1.0.0 version` prints `rf-harness 1.0.0`

### Requirement: The documentation site is deployed from main

The docs workflow SHALL build the documentation strictly, including the reference and link checks, and SHALL deploy it
to GitHub Pages on every push to `main` that changes the docs. The site MUST declare its public URL, so that canonical
and root-relative links resolve. Pull requests SHALL build and check the docs without deploying.

#### Scenario: docs change goes live

- **WHEN** a commit that changes `docs/` is pushed to `main`
- **THEN** the site at `https://manykarim.github.io/robotframework-harness/` shows the change after the workflow completes

#### Scenario: pull request does not deploy

- **WHEN** a pull request changes `docs/`
- **THEN** the docs are built and checked, and nothing is deployed
