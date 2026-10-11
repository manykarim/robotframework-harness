## Context

See proposal.md (Why). Inputs this design builds on:

- **The measured harness: v3.2 prototype**, at `rf-mcp-robotcode/experiments/robotcode-remote/ab/hookpkg32`
  (commit `7994ae3` on rf-mcp branch `research/robotcode-remote-mcp`).
  - Package `rfharness32`, about 10k lines.
  - Hook dispatcher, robotcode-embedded helper (`execd`), live timeouts (`livetmo`), Playwright-log classification
    (`pwlog`), page state (`pagestate`), keyword docs (`kwdoc`/`docsgen`), lint daemon (`lintd`), output profiles
    (`profiles`, `leanfmt`, `richfmt`), REPL format rules (`replfmt`), guards, installer (`install.py`).
  - A simulation suite with 224 checks.
- **The evidence:** rf-mcp `experiments/robotcode-remote/**` (about 27 MB committed, about 130 MB of transcripts not
  committed) and `docs/research/static-analysis-quality-gates.md`. Findings files run per round, from
  `findings.md` to `findings_v31.md`.
- **The distribution model to adapt: `robotframework-agentskills`.**
  - One `.claude-plugin/marketplace.json` read by Claude Code, Copilot CLI, VS Code and Codex.
  - `plugins/<name>/` with `.claude-plugin/plugin.json`, `hooks/hooks.json` and `variants/{codex,opencode}`.
  - A Python installer (`installer/src/rf_agentskills`: `cli`, `adapters`, `transforms`, `manifest`, `hatch_build`
    bundling assets).
  - Releases tagged `v<version>`.
  - Its hooks are Node scripts that only validate.
- **What makes this harness different:** its hooks drive a stateful local Robot Framework session. That needs the
  project's Python environment, the one with Robot Framework, Browser and so on.
- **Hook facts per agent:** round-4 matrix plus the agentskills verification.
  - Claude Code and Codex support every event. Codex needs hook trust.
  - Copilot CLI's sessionEnd fires after every run, and only a hook's decision/reason reaches the model.
  - OpenCode has no blocking stop; the plugin uses a noReply workaround.
  - VS Code supports hooks behind `chat.useHooks`.

## Goals / Non-Goals

**Goals:**
- A user goes from zero to live feedback in at most five commands in any of the five supported agents.
- The harness ships at parity with the v3.2 prototype on the evaluation, then improves only through the release gate.
- One source of truth for plugin assets, consumed by both the marketplace and the installer.
- Every published number can be traced and recomputed from the archive.

**Non-Goals:**
- Cursor, Goose, Gemini CLI and Claude Desktop in v1. Cursor may work through the marketplace but stays unverified
  and undocumented until tested live.
- An MCP server. rf-mcp remains the MCP option; the docs explain when to use which.
- Hosting or cloud execution; everything runs on the user's machine.
- Selenium and mobile live-feedback parity in v1 (Browser and Requests first; desktop gated behind parity tests).

## Decisions

### D1. Repository layout: one plugin, one Python distribution, docs, evidence, eval

```
.claude-plugin/marketplace.json          marketplace "robotframework-ai-engineering" -> plugin rf-harness
plugins/rf-harness/
  .claude-plugin/plugin.json             version == release version
  skills/rf-harness/SKILL.md (+ references/)
  hooks/hooks.json                       Claude Code / Copilot / VS Code format -> bin/rfh-launch
  bin/rfh-launch                         stdlib-only launcher (see D3)
  variants/codex/ variants/opencode/     agent-specific hook/plugin formats
src/rf_harness/
  installer/  cli.py detect.py envfind.py adapters/<agent>.py transforms.py manifest.py doctor.py
  runtime/    hook.py execd.py livetmo.py pwlog.py pagestate.py kwdoc.py lint.py profiles.py
              feedback/{lean,rich}.py replfmt.py guards.py desktop/ robotcode_adapter.py
  config.py                              registry of every RFH_* variable (single source for docs)
  _assets/                               plugin files bundled into the wheel at build time
docs/        MkDocs site (D8)
evidence/    archive (D9)
eval/        A/B evaluation harness, never packaged (D10)
tests/       unit, simulation, adapter payload replay, installer, docs and evidence checks
.github/workflows/  ci, docs, evidence-scrub, release, eval (manual/nightly)
```

- Plugin assets live once, under `plugins/rf-harness/`. A hatch build hook copies them into `rf_harness/_assets`, as
  rf-agentskills does, so files mode installs exactly what the marketplace ships.
- Alternative considered: separate repos for the plugin and the runtime. Rejected because of version skew between hook
  definitions and the runtime, and double releases.

### D2. One PyPI distribution `robotframework-harness`: dependency-free installer, `[runtime]` extra

- `pip install robotframework-harness` (and `uvx robotframework-harness`) has no dependencies, so the installer
  starts fast anywhere.
- Naming: the distribution is `robotframework-harness` (free on PyPI, checked 2026-10-11) and the import package is
  `rf_harness`. Two console scripts, `robotframework-harness` and `rf-harness`, run the same CLI, so
  `uvx robotframework-harness install` works without `--from`. The plugin and the skill are named `rf-harness`.
- `robotframework-harness[runtime]` adds `robotframework>=7`, `robotcode[repl,runner,analyze]>=2.7,<2.8` and optionally
  `robotframework-robocop>=9.1`.
- The installer installs `robotframework-harness[runtime]==<its own version>` into the project environment, so the two are always
  in lockstep.
- Alternative considered: two distributions (`rf-harness`, `rf-harness-runtime`). Rejected: an extra keeps one version
  number and one release.

### D3. Hooks call a stdlib-only launcher that finds the project interpreter

- The hook command is `python3 -S <plugin>/bin/rfh-launch <event>`, about 20–30 ms of overhead. The launcher resolves
  the interpreter in this order:
  1. `RFH_PYTHON`;
  2. `.rf/harness.json`, written by the installer;
  3. `VIRTUAL_ENV`;
  4. `<project>/.venv`;
  5. a uv- or poetry-managed environment;
  6. `python3` on PATH.
- It checks that `rf_harness.runtime` is importable and version-compatible (same major and minor), then execs
  `python -m rf_harness.runtime.hook <event>`, passing stdin through.
- If the runtime is missing: on session start, the launcher emits one context line with the exact setup command
  (`uvx robotframework-harness install --runtime-only`) and exits 0. The hook fails open; on Copilot, where a crashed pre-tool hook
  denies the tool, it must never crash.
- This keeps the prototype's measured design: thin hook process, heavy work in the helper that runs inside the project
  environment.
- Alternative considered: run the runtime in an isolated tool environment and spawn the project interpreter only for
  RF execution. Rejected: it duplicates the robotcode stack, and library imports and keyword docs must come from the
  project environment anyway.

### D4. Installer adapted from rf-agentskills, extended for the runtime

- The installer reuses rf-agentskills' architecture:
  - adapter per agent (`detect`, `plan(mode, scope)`, `apply`, `verify`);
  - transforms for agent-specific formats;
  - a JSON manifest with sha256 per written file and config entry;
  - interactive multi-select with detected agents preselected;
  - `targets`, `install`, `uninstall`, `list`, `doctor`, `version`.
- Additions specific to this harness:
  - `envfind`: project environment discovery (D3 order) and consented runtime install with `uv pip` or `pip`.
  - Codex hook-trust provisioning: compute the hook key and hash and write `trusted_hash`, as proven in round 4; fall
    back to printing `/hooks`.
  - Coexistence detection for rf-agentskills hooks and rf-mcp MCP entries.
  - `doctor` live probe: a synthetic hook event per agent format through the launcher, plus a 10-second live step
    against a bundled `demo/site`.
- v1 agents: Claude Code, Codex, Copilot CLI, VS Code (Copilot), OpenCode. OpenCode always uses files mode (plugin JS,
  as in the prototype). VS Code needs the user settings `chat.plugins.enabled` and `chat.useHooks`; the installer
  prints them for user scope.

### D5. The runtime is ported from v3.2 with behavior parity, then hardened

- Port `rfharness32` into `rf_harness.runtime`:
  - env prefix `RFH32_` becomes `RFH_` (registry in `config.py`);
  - the state directory stays `.rf/` (agents and the skill already use those paths; the installer adds it to
    `.gitignore`);
  - markers become `[rfh]`.
- Parity is shown in three steps:
  1. the 224-check simulation suite ported as tests (`tests/simulation`);
  2. adapter payload replay from the round-4 recordings;
  3. a same-window A/B of `rf-harness` vs the hookpkg32 prototype before the first release (gate in D10).
- Hardening after parity, all behind the release gate:
  - robotcode adapter with contract tests;
  - Windows transport (loopback TCP with a token) and Job Objects;
  - sandbox detection with a synchronous fallback.

### D6. Desktop safety is vendored with parity tests; desktop is off until they pass

- rf-mcp's desktop safety, isolation and focus guards (ADR-026/027) are ported into `rf_harness.runtime.desktop`, with
  attribution.
- Parity tests replay recorded guard decisions from rf-mcp's test corpus.
- Live desktop steps stay refused with guidance until parity passes (`RFH_DESKTOP=1` opt-in for testers).
- Alternative considered: depend on rf-mcp for the guards. Rejected: it pulls in the MCP server stack.

### D7. Coexistence with rf-agentskills and rf-mcp

- The skill is named `rf-harness`, so it does not collide with rf-agentskills' `rf-*` skills.
- Duplicate validation: rf-agentskills validates on edit too. The installer default keeps both and sets
  `RFH_STATIC=runtime-only`. The harness then reports only runtime results, while rf-agentskills' validator
  reports static errors.
- When an rf-mcp server is configured, the docs and doctor explain that both routes work but agents may mix them; this
  is known from the bundle evaluation (skills and rf-mcp substitute rather than complement each other). The user
  chooses.

### D8. Documentation: MkDocs Material, generated reference, tested quick starts

- Sections:
  - Get started: one quick start per agent, plus "your own project";
  - Concepts: one page per component, as listed in the spec;
  - Agents: support matrix, per-agent setup details and limits;
  - Reference: CLI, environment variables, files, hook events;
  - Evidence: summary with confidence intervals and limits, linking into `evidence/`;
  - Troubleshooting;
  - Comparison with rf-mcp and rf-agentskills;
  - Contributing and releasing.
- The CLI reference comes from the argparse tree, and the environment-variable reference from `config.py`. A check
  fails on undocumented flags or variables.
- Links are checked with lychee (offline mode for internal links).
- Quick starts:
  - CI runs the agent-independent part on Linux and Windows: install, runtime, doctor, plain `robot` on the demo.
  - The agent-session part runs in the release check script (`eval/quickstart_check.py`), with real agents, and
    records its duration.
- Hosting: GitHub Pages from `main`.

### D9. Evidence import: scrubbed, checksummed, indexed, with transcripts as release assets

- Import from rf-mcp `research/robotcode-remote-mcp`:
  - the committed `experiments/robotcode-remote/**` tree;
  - `docs/research/static-analysis-quality-gates.md`;
  - **only the findings summary** of `robotcode-experiments` (the prior CLI study), linked as upstream
    evidence (owner decision 2026-10-11; its raw data stays in that repository).
- Target structure:
  - `evidence/rounds/<NN>-<topic>/`;
  - `evidence/harness-versions/` (v1–v3.2 source snapshots, for provenance);
  - `evidence/eval-snapshots/` (the harness code as used per round);
  - `evidence/incidents.md`;
  - `evidence/claims.yaml`;
  - `evidence/checksums.sha256`.
- The scrub (`evidence/scrub.py`, also run in CI):
  - provider key and token patterns, plus the literal key values supplied through the environment at import time;
  - OAuth JSON fields;
  - agent home directories and `auth.json`;
  - e-mail addresses other than the author's public one;
  - absolute home paths normalized to `~`.

  It writes a scrub report. Numbers are recomputed after scrubbing (`evidence/check_claims.py` re-runs `analyze_hooks`
  on archived results).
- Transcripts, about 130 MB gz across rounds, are scrubbed and packed per round as `.tar.zst` release assets, with a
  manifest of sha256 and result row. They are not committed.
- Excluded rows (credit 402s, auth expiry, Codex outage) stay in separate `excluded_*.jsonl` files, each with a
  reason.

### D10. The evaluation harness moves to `eval/` with the round-7 fixes

- Port `ab/harness` (harness, analyzer, OpenRouter routes, resilient runner, journey grader) into `eval/`, adding:
  - per-run budgets: the sum of cell usage deltas, plus a global key-limit guard;
  - an account-balance pre-check;
  - a transcript scan for provider errors and backend outages;
  - regex-tolerant value graders;
  - a `quickstart_check.py`.
- The release gate compares the candidate with the previous release, and with the hookpkg32 prototype for v1, in the
  same window: Claude Code, Codex, OpenCode, plus one cheap OpenRouter model (Qwen 3.8 Flash), with at least 3 reps.
- It blocks the release on non-inferiority failures.
- It runs only through a manual or nightly workflow with repository secrets, never on PRs.

### D11. Versioning and release

- Semantic versioning; `plugin.json` version, package version and tag `v<version>` are equal (checked in CI). A
  `stable` ref moves on each release.
- The release workflow builds the wheel and sdist with bundled assets, runs the evidence scrub and claim check, then
  publishes to PyPI via trusted publishing and creates the GitHub release with the transcript assets.
- **The first public publish and creating the GitHub repository need the owner's explicit go-ahead.**

## Risks / Trade-offs

- [The runtime must be in the project environment; users have many layouts (uv, poetry, pipx, system Python, conda)]
  → Use the D3 search order, record the choice in `.rf/harness.json`, provide `--python`, and have `doctor` show what
  was chosen. A missing runtime degrades to a setup hint, never a broken agent.
- [Agent plugin and hook APIs drift (Codex trust hashing, Copilot model gating, VS Code preview flags)] → Payload
  replay contract tests per agent, a verified-version matrix in the docs, and doctor probes on the user's machine.
- [Version skew between plugin (marketplace update) and runtime (project environment)] → The launcher's
  compatibility check, plus a one-line upgrade hint (`uvx robotframework-harness install --runtime-only`).
- [Scrub misses a secret in transcripts] → Pattern plus literal-value scans, CI enforcement, transcripts only as
  release assets (deletable), and a manual review checklist for the first release.
- [Live-site drift makes evidence and the release gate noisy] → Only same-window comparisons; bundled local demo
  pages for quick starts and doctor; live sites only in the gate.
- [Maintenance load of five agent adapters] → The shared event model (D4/D5) and payload-replay tests. New agents are
  added only after a live verification.
- [robotcode internal API changes] → Adapter pin `<2.8`, contract tests, and a tracked upstream stable-API request.

## Migration Plan

- This is a new repository; nothing to migrate.
- After v1, the rf-mcp change `robotcode-agent-harness` points here. Its distribution decision D9 and its runtime
  specs are superseded.
- Users of the research prototypes switch with `rf-harness install`. The installer detects prototype installs
  (`rfharness3*` markers in settings) and offers to remove them.
- Rollback: `rf-harness uninstall` per project or user, or pin the previous tag in the committed settings.

## Resolved Decisions (owner, 2026-10-11)

- Publish the GitHub repository as **private** first. Making it public and the first PyPI publish are later,
  separate decisions.
- PyPI distribution name: `robotframework-harness` (CLI and plugin `rf-harness`).
- Import only the findings summary of `robotcode-experiments`.
- Cursor, Goose and Gemini CLI stay out of v1 until tested live.
