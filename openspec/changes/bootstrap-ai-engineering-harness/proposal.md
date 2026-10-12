> Repository renamed from `robotframework-ai-engineering` to `robotframework-harness` on 2026-10-13 to match the
> PyPI distribution name.

## Why

The research on branch `research/robotcode-remote-mcp` of rf-mcp (commit `7994ae3`) produced an agent harness for
Robot Framework: an Agent Skill, agent hooks and a local helper built on robotcode.
- It beat rf-mcp in same-window A/B runs on live end-to-end journeys: pooled pass rate 0.83 vs 0.69 over 206 cells.
- It roughly halved wall time and cost for most agents.
- It lifted weaker, cheap models the most (Qwen 3.8 Flash 0.38 → 0.88, OpenCode/MiniMax 0.27 → 0.53).

Today the harness exists only as research prototypes (`hookpkg3`/`hookpkg31`/`hookpkg32`) with hand-run installers.
Users cannot adopt it. **robotframework-harness** turns the best version (v3.2) into a product that someone can
install in minutes, for every major coding agent. It also publishes the documentation and the full experimental
evidence behind it.

## What Changes

- **New repository `robotframework-harness`** (Apache-2.0). It holds one plugin, `rf-harness`, with:
  - the Robot Framework Agent Skill and its references;
  - the hook definitions;
  - per-agent variants.

  It also holds the Python runtime and installer, the documentation, the evaluation harness and the evidence archive.
- **Plugin marketplace.** The marketplace file `.claude-plugin/marketplace.json` lets Claude Code, GitHub Copilot CLI,
  VS Code (Copilot) and OpenAI Codex install the plugin through their plugin commands at user or project scope. Each
  release is tagged, so it can be pinned. The model is the one `robotframework-agentskills` uses.
- **One-command installer** `rf-harness`, runnable with zero install via `uvx robotframework-harness install`:
  - interactive multi-select of detected agents (Claude Code, Codex, Copilot CLI, VS Code, OpenCode), or fully
    scriptable flags;
  - `--mode plugin` writes marketplace settings; `--mode files` copies native files, and is the fallback for OpenCode;
  - project or user scope;
  - installs the **runtime** into the project's Python environment, where Robot Framework and its libraries live,
    with consent;
  - provisions Codex hook trust;
  - a hash manifest for safe re-install, upgrade and uninstall;
  - `doctor` proves that the hooks fire and that prerequisites import.
- **Runtime package** `rf-harness`. It is ported from the measured v3.2 prototype into production code:
  - the robotcode-embedded live session;
  - evidence-first failure feedback, with per-model output profiles;
  - page-state and keyword-doc files;
  - static quality checks with robotcode analyze and a curated Robocop profile;
  - REPL/debugger format enforcement;
  - the stop gate requiring a green plain `robot` run;
  - desktop safety guards.
- **Quick start in under 5 minutes.** One page per agent goes from zero to a first green live-executed test against a
  bundled demo site.
- **Comprehensive documentation** of every component:
  - architecture and hook lifecycle per agent;
  - live execution and timeouts;
  - verdicts, state files and keyword knowledge;
  - output profiles and static quality;
  - refusal policy, environment variables, CLI and file layout;
  - troubleshooting, plus a comparison with rf-mcp and rf-agentskills.
- **Evidence archive** of all experiment data from rf-mcp research rounds 1–7:
  - findings, result files, reports, scenario definitions, graders and harness code;
  - an index that links every published claim to its data;
  - transcripts as a scrubbed, checksummed release asset (too large and too sensitive for git history).
- **Evaluation as a release gate.** The A/B harness runs a same-window comparison before each release.
- **rf-mcp is unchanged.** rf-mcp's change `robotcode-agent-harness` had planned to place the harness packages inside
  rf-mcp (its design D9); this repository supersedes that. Its runtime capability specs move here.

## Capabilities

### New Capabilities

- `marketplace-distribution`: the plugin and marketplace layout. Covers per-agent plugin installation (Claude Code,
  Copilot CLI, VS Code, Codex), project-scope committed settings, release tags and version pinning.
- `installer-cli`: the `rf-harness` installer. Covers agent detection, interactive and scripted selection,
  plugin/files modes, scopes, runtime provisioning into the project environment, hook trust, manifest-based
  uninstall/upgrade, `doctor`, `list`, coexistence with rf-agentskills and rf-mcp.
- `harness-live-session`: edit-driven live execution of test lines, adaptive live timeouts, plain-run reproduction,
  REPL/debugger format enforcement, helper lifecycle, desktop safety guards.
- `harness-failure-feedback`: evidence-first verdicts (including concrete targets for covered inputs), bounded
  per-model output profiles, page-state files, loop hints, the read-streak nudge, the stop gate.
- `harness-keyword-knowledge`: keyword index and docs files from robotcode libdoc, on-demand per-keyword docs, offline
  keyword search.
- `harness-static-quality`: post-edit static checks with a live-session filter, a refusal policy limited to
  certain-wrong edits, safe deprecated-syntax fixes only, portable suites.
- `harness-documentation`: documentation coverage and quality. Covers per-agent quick starts, concept pages for every
  component, a complete reference, troubleshooting, a docs build with link checks in CI.
- `experiment-evidence`: the evidence archive. Covers contents, provenance, scrubbing, the claim-to-data index,
  reproducibility instructions, the transcript release asset.
- `harness-evaluation`: the A/B evaluation as a release gate. Covers live journey scenarios with evidence graders,
  isolation and contamination checks, a resilient runner, model routes with per-run budgets and account-balance
  checks, detection of invalid sessions, the non-inferiority gate.

### Modified Capabilities

None. This is a new repository with no existing specs.

## Impact

- **New public repository** `manykarim/robotframework-harness`. Creating the GitHub repository and the first
  publish (PyPI `robotframework-harness`, release tag) need the owner's confirmation at release time. The
  repository is published **private** first; making it public is a separate, later decision.
- **Dependencies of the runtime:** `robotframework>=7`, `robotcode[repl,runner,analyze]` (pinned `>=2.7,<2.8` behind
  an adapter), optionally `robotframework-robocop>=9.1`. Browser, SeleniumLibrary, RequestsLibrary and PlatynUI stay
  user-installed.
- **The installer is pure Python with no runtime dependencies.** Plugin hooks call a stdlib-only launcher that finds
  the project's interpreter.
- **Code is ported, not copied verbatim**, from `rf-mcp-robotcode/experiments/robotcode-remote/ab/hookpkg32`
  (≈10k lines). The installer architecture (adapters, transforms, manifest) is adapted from
  `robotframework-agentskills`, same author and license.
- **Evidence.** About 27 MB of findings, results and code from the rf-mcp research commit go into the repo. About
  130 MB of transcripts become a release asset after a secret and PII scrub.
- **rf-mcp.** No code change. Its `robotcode-agent-harness` change gets a pointer to this repository.
- **Risks carried into design:**
  - the runtime has to live in the project environment while hooks are launched by the agent;
  - a skill or hook conflict when rf-agentskills is also installed;
  - Codex hook trust and Copilot model gating;
  - robotcode internal API stability;
  - publishing transcripts safely.
