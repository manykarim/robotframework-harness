## 1. Repository foundation

- [x] 1.1 Create the layout from design D1 with `LICENSE` (Apache-2.0), `README.md` (pitch, 3-line quick start, evidence headline with link), `pyproject.toml` (dist `robotframework-harness`, console scripts `robotframework-harness` and `rf-harness`, zero dependencies, extra `runtime`), a hatch build hook that bundles `plugins/rf-harness/` into `rf_harness/_assets`, and `.gitignore`. Verify `uv build` produces a wheel that contains `_assets/skills/rf-harness/SKILL.md`.
- [x] 1.2 Add CI (`.github/workflows/ci.yml`: ruff, mypy, pytest on Linux/macOS/Windows with Python 3.10–3.13) and a version-consistency check (plugin.json == package version). Verify CI passes on an empty test suite and fails when the versions differ.
- [x] 1.3 Create the **private** GitHub repository `manykarim/robotframework-ai-engineering` and push `main`. Verify `gh repo view` reports visibility PRIVATE.

## 2. Runtime port from v3.2 (harness-live-session, harness-failure-feedback, harness-keyword-knowledge, harness-static-quality)

- [ ] 2.1 Port `rfharness32` into `rf_harness.runtime` (design D5): `RFH32_` → `RFH_` via the `config.py` registry, markers `[rfh]`, state dir `.rf/`, robotcode access only through `robotcode_adapter.py`. Verify that `python -m rf_harness.runtime.hook` handles a session-start payload and that a grep finds no `rfharness3`, `RFH3` or `hook32` strings.
- [ ] 2.2 Port the 224-check simulation suite to `tests/simulation/` (Browser + chromium, run in CI on Linux). Verify ≥ 221/224 pass, with the scenario-D pre-tool lint timing check marked as a tolerated flake with a retry, and the v3.2 scenario L (covered `label:has(#id)` target, read-streak nudge) green.
- [ ] 2.3 Add robotcode adapter contract tests (`BaseInterpreter`/`run_repl` embedding, libdoc, analyzer) pinned to `robotcode>=2.7,<2.8`. Verify they pass against robotcode 2.7.x.
- [x] 2.4 Vendor the desktop safety, isolation and focus guards into `rf_harness.runtime.desktop` with attribution, and add parity tests replaying recorded rf-mcp guard decisions. Desktop live steps stay refused unless `RFH_DESKTOP=1`. Verify the parity tests pass and an active-desktop input step is refused by default.

## 3. Plugin and marketplace (marketplace-distribution)

- [ ] 3.1 Write `plugins/rf-harness/`: `plugin.json`, the `rf-harness` skill (from hookpkg32 SKILL.md and references, fixture-free), `hooks/hooks.json`, and `variants/codex` and `variants/opencode`. Verify `claude plugin validate .` passes and the fixture-leak scan from the evaluation finds nothing.
- [x] 3.2 Implement `bin/rfh-launch` (stdlib only): interpreter discovery (design D3 order), version-compatibility check, exec of the runtime, fail-open setup hint. Verify with unit tests for each discovery branch, a missing-runtime case (one hint line, exit 0) and launcher overhead under 50 ms median.
- [ ] 3.3 Add `.claude-plugin/marketplace.json`, then install the plugin from a local checkout in Claude Code, Copilot CLI, VS Code and Codex. Verify in one real session per agent that live feedback arrives after editing a test, and record the verified agent versions in `docs/agents/matrix.md`.

## 4. Installer (installer-cli)

- [x] 4.1 Port the rf-agentskills installer core (`cli`, `manifest`, `transforms`, interactive multi-select, detection) into `rf_harness.installer`, with adapters for Claude Code, Codex, Copilot CLI, VS Code and OpenCode. Verify `rf-harness targets` lists all five with detection results, and `install --dry-run` prints planned changes without writing.
- [x] 4.2 Implement plugin and files modes at project and user scope, including OpenCode files fallback and VS Code user-settings guidance. Verify with installer tests per agent × mode × scope against temporary homes and projects.
- [x] 4.3 Implement `envfind` and consented runtime provisioning (`uv pip install` / `pip install "robotframework-harness[runtime]==<version>"`), `.rf/harness.json`, and the import verification. Verify against venv, uv-managed and poetry fixtures that the runtime lands in the right environment and that no other package changes.
- [x] 4.4 Implement Codex hook-trust provisioning (trusted hash) with a `/hooks` fallback, plus coexistence detection for rf-agentskills hooks, rf-mcp entries and research-prototype installs. Verify with fixtures that trust entries match exactly the installed hooks and that the other tools' entries stay byte-identical.
- [x] 4.5 Implement manifest-based upgrade and uninstall (remove obsolete files, keep and report modified files). Verify install twice reports no change, the upgrade test removes an obsolete file, and uninstall leaves only the user's entries.
- [x] 4.6 Implement `doctor`: per-agent install and trust checks, a synthetic hook event through the launcher per agent format, environment and library report, and a 10-second live smoke step against `demo/site`. Verify that doctor fails with untrusted Codex hooks and passes after trust.

## 5. Evaluation harness (harness-evaluation)

- [x] 5.1 Port `ab/harness` to `eval/` (scenarios, journey grader, analyzer, OpenRouter routes, resilient runner). Verify that `eval check-scenarios` reports IDENTICAL to the round-7 definitions and that the round-7 reports regenerate byte-identically from the archived results.
- [x] 5.2 Add the round-7 fixes: per-run budgets, account-balance pre-check, transcript scan for provider errors and backend outages, regex-tolerant value graders. Verify with unit tests on the recorded 402, outage and `916\.99` cases.
- [x] 5.3 Add the release-gate report (non-inferiority margin 0.05 for the main agent, significant per-agent regressions) and `eval/quickstart_check.py`. Verify that the gate verdicts on the round-6 and round-7 data match the findings files.
- [x] 5.4 Add the manual/nightly `eval.yml` workflow using repository secrets. Verify with a dry run that no secret appears in artifacts (scrub run on the workflow outputs).

## 6. Evidence archive (experiment-evidence)

- [x] 6.1 Write `evidence/scrub.py` (key/token patterns, literal secret values from the environment, OAuth fields, agent homes, e-mail addresses, home-path normalization) and run it in CI on every `evidence/` change. Verify with a planted fake key that the check fails, and that a clean run produces an empty report.
- [x] 6.2 Import the rf-mcp research tree (commit `7994ae3`) into `evidence/rounds/<NN>-<topic>/`, with the static-analysis report, harness-version snapshots, eval snapshots, `incidents.md` and excluded-row files. Write `checksums.sha256`. Verify the scrub is clean and checksums match.
- [x] 6.3 Write `evidence/claims.yaml` for every number in the README and docs, and `check_claims.py`, which recomputes them. Verify the check passes, and fails after editing one archived result row.
- [x] 6.4 Pack the scrubbed transcripts per round as `.tar.zst` with a manifest (sha256, result-row key), and document download and verification. Verify the verification script on the packed assets locally.
- [ ] 6.5 Write reproduction guides per round (prerequisites, agent and model versions, commands, cost and duration, same-window rule). Verify the round-7 guide by running a 1-rep smoke of its command.

## 7. Documentation (harness-documentation)

- [ ] 7.1 Set up MkDocs Material with the sections from design D8, plus generators for the CLI and environment-variable reference from argparse and `config.py`, with the undocumented-item check. Verify that the docs build fails when a test variable is added to `config.py` without docs.
- [ ] 7.2 Write the per-agent quick starts (Claude Code, Codex, Copilot CLI, VS Code, OpenCode) and "use it in your project". Verify each in a real session with `eval/quickstart_check.py` (five commands or fewer, under 5 minutes, recorded duration).
- [ ] 7.3 Write the concept pages for every component listed in the spec, each linking to its evidence. Verify the link check passes and every concept page links at least one evidence file.
- [ ] 7.4 Write troubleshooting, the comparison with rf-mcp and rf-agentskills, the agent support matrix, and the evidence summary (with confidence intervals and limits). Verify that the lychee link check and the claims check pass in the docs workflow.

## 8. Release v1.0.0

- [ ] 8.1 Run the same-window release gate: rf-harness vs the hookpkg32 prototype on Claude Code, Codex, OpenCode and Qwen 3.8 Flash, 3 reps, live scenarios. Verify the gate report passes non-inferiority and archive it as evidence round 8.
- [ ] 8.2 With the owner's explicit go-ahead (repository already private from 1.3): make it public, enable Pages, configure PyPI trusted publishing, tag `v1.0.0`, move `stable`, and publish the wheel, sdist and transcript assets. Verify that `uvx robotframework-harness install` works from PyPI on a clean machine and that `claude plugin marketplace add manykarim/robotframework-ai-engineering` installs v1.0.0.
- [ ] 8.3 Add a pointer in rf-mcp's change `robotcode-agent-harness` (design D9 and runtime specs superseded by this repository). Verify `openspec validate` passes in both repositories.
