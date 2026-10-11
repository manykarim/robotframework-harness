# Reproducing the experiments

This guide explains how to rerun each round, what you need, and what to expect. Read **The same-window rule**
before comparing your numbers with the archived ones.

## The same-window rule

**Only compare arms that ran interleaved in the same time window.**
- The live scenarios run against public websites: the Tricentis sample insurance app, the Flowline demo shop and
  the car configurator. Their markup, data, speed and availability change over time.
- Models change behind the same name, provider capacity varies by hour, and agent CLIs update often.

A rerun next month will not reproduce the archived absolute pass rates. It should reproduce the *contrasts* between
arms run in the same window. Every archived A/B round follows this rule: all arms of a round were interleaved by
the runner in one window. Comparisons *across* rounds are indicative only. For example, the same hookpkg v1 arm
scored 0.58 in round 4 and 0.51 in round 5, a run-to-run noise of about ±0.07–0.13 at 3 reps.

What reproduces exactly from the archive alone, without running any agent:
- `python3 evidence/check_claims.py --reports` recomputes every published number and regenerates the archived
  reports with the archived analyzer (Python 3.12+);
- `python3 evidence/verify_assets.py` checks the transcripts against their result rows.

## Two ways to rerun

1. **Ported harness, `eval/`** (recommended; it is the v1 release gate, task 8.1). It has the round-7 scenarios and
   graders (`python3 eval/harness.py check-scenarios`), plus the round-7 fixes: per-run budgets, an account-balance
   check, a transcript scan for provider errors and outages, and regex-tolerant value graders. Its arms are
   `rf-harness` (this repository, provisioned by the installer), `prototype-v32` (the research hookpkg32),
   `mcp` and `neither`. Its `harness_version` is `rfh-eval-1`, so rows are marked as not the research harness.
2. **Archived research harness**, `eval-snapshots/ab-7994ae3/harness/`. This is the exact code at the end of the
   research (commit `7994ae3`), with the arms of all rounds (`neither`, `mcp`, `skillpkg`, `hookpkg`, `hookpkg2`,
   `hookpkg3`, `hookpkg31`, `hookpkg32`). Only the final version was preserved, so earlier rounds rerun with the
   final harness code. The findings state that prompts and graders did not change within a `harness_version`.

### Assembling the archived harness

The archived harness expects the research `ab/` layout (harness next to the fixtures and the packages). It also
needs an rf-mcp 0.36.0 checkout whose `.venv` has Robot Framework, Browser, RequestsLibrary and robotcode:

```bash
AB=$HOME/ab-rerun && mkdir -p "$AB"
cp -r evidence/eval-snapshots/ab-7994ae3/* "$AB"/          # harness/, fixtures/, fixtures_live/
cp -r evidence/harness-versions/* "$AB"/                    # hookpkg ... hookpkg32, skillpkg
git clone https://github.com/manykarim/rf-mcp "$HOME/rf-mcp-0.36" && git -C "$HOME/rf-mcp-0.36" checkout c1a18eb
(cd "$HOME/rf-mcp-0.36" && uv sync --all-extras && uv pip install "robotcode[all]==2.7.0" && uv run rfbrowser init chromium)
```

The scrub replaced the absolute paths in the code with `~/...` literals, which `pathlib` does not expand. Edit
three constants before running:
- `REPO` in `harness/harness.py`: your rf-mcp checkout;
- `OLD_HARNESS`: only needed by `check-scenarios`;
- `ENV_FILE` in `harness/openrouter.py`, or set `AB_OR_ENV_FILE`: the dotenv file with `OPENROUTER_API_KEY`.

## Prerequisites (all A/B rounds)

| | as recorded | notes |
|---|---|---|
| OS | Linux (Ubuntu 24.04), x86_64 | the harness uses `fcntl`, process groups and `setsid`; POSIX only |
| Python | 3.12/3.13 | archived harness and analyzers are stdlib-only |
| Robot Framework stack | RF 7.5, Browser 20.5.0 + chromium, RequestsLibrary 0.9.7, robotcode 2.7.0 | in the rf-mcp checkout's `.venv` |
| rf-mcp | 0.36.0 (`c1a18eb`) | `mcp` arm, local stdio server |
| Claude Code | 2.1.286 (A/B 1–2), 2.1.289 (round 4), 2.1.295 (round 5), 2.1.295–2.1.296 (round 6), 2.1.296 (round 7) | read from the transcripts (`claude_code_version`); subscription login, or OpenRouter for `cc-or:*` |
| Codex CLI | not recorded in the A/B data; 0.153.4 (rounds 2–3 spikes), 0.161.0 (round 4 matrix) | model `gpt-5.6-luna`, effort `medium`; ChatGPT login |
| OpenCode | not recorded in the A/B data; 1.15.12 (rounds 2–4 spikes) | `minimax-coding-plan/MiniMax-M2.5` |
| OpenRouter | account with credits | rounds with `cc-or:*` agents; check the **account** balance, not only the key limit |
| disk / memory | ≥ 2 GB free (the harness stops below 1.2 GB); about 3 GB RAM per browser cell | at most 2–3 concurrent browser cells |

Agents run with isolated homes per cell (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `OPENCODE_CONFIG`, `COPILOT_HOME`).
Credentials are copied in and deleted after the cell. Run the agents under your own accounts and do not commit the
result files before running `evidence/scrub.py`.

## Expected cost and duration

Measured in the archived runs. Claude cost is Claude Code's own per-session estimate (`metrics.cost_usd`). Codex and
OpenCode ran on flat-rate subscriptions and were not metered. OpenRouter cost is the list-price estimate plus the
account usage delta.

| round | sessions | window (wall clock) | agent-hours | metered cost |
|---|---|---|---|---|
| A/B 1 (03a) | 180 (+45 pilot/smoke) | 1.3 h | 3.0 | Claude $5.82 |
| A/B 2 (03b) | 135 (+52 pilot/smoke) | 12.2 h (incl. the auth re-run) | 24.6 | Claude $27.70 |
| 4 | 90 | 4.1 h | 9.7 | Claude $14.58 |
| 5 | 90 | 10.9 h (incl. an overnight stop) | 10.9 | Claude $13.63 |
| 6 | 180 (+15 pilot) | 8.9 h | 21.3 | Claude $27.14 |
| 7 v31sub | 135 | 8.9 h | 16.7 | Claude (Haiku 5.5) $1.42 |
| 7 v31or | 71 valid of 135 | 5.7 h | 10.5 | OpenRouter est. $6.22 (the full 135 cells were budgeted at $50) |
| 7 v31gem | 10 of 20 (stopped) | 2.2 h | 2.0 | OpenRouter about $2.40 per cell real spend (est. $14.63 total) |
| 7 v32 | 39 | 4.2 h | 3.8 | OpenRouter est. $0.40 (Qwen) |

## Per round

### 03a: A/B round 1

File authoring, 4 hard scenarios, 3 agents × 3 arms × 5 reps. Harness `rc-1`.

```bash
cd "$AB/harness"
python3 harness.py verify-ref --scenarios round1            # references must pass, pristine fixtures must fail
python3 harness.py run --reps 5 --agents claude,codex,opencode --scenarios round1 --arms neither,mcp,skillpkg
python3 analyze.py results_rc.jsonl --out report_rc.txt --json summary_rc.json
```

### 03b: A/B round 2

5 live scenarios, 3 agents × 3 arms × 3 reps, 80-turn cap. Harness `rc-3-journey`.

```bash
python3 harness.py verify-ref --scenarios live --runs 3 --negatives --json verify_live_journey.json
python3 harness.py run --reps 3 --agents claude,codex,opencode --scenarios live --arms neither,mcp,skillpkg \
    --max-turns 80 --browser-concurrency 3
python3 analyze.py results_live.jsonl --out report_live.txt --json summary_live.json
```

### 04: round 4

hookpkg vs skillpkg on the live scenarios (the hook matrix itself is in `rounds/04-.../hooks_matrix/`, with
`run_probe.py` and `run_claude_skill.py`).

```bash
./run_hooks_ab.sh       # = harness.py run --scenarios live --reps 3 --arms hookpkg,skillpkg --agents claude,codex,opencode
                        #   --max-turns 80 --browser-concurrency 3 --tag hooks   (up to 3 passes)
python3 analyze_hooks.py results_live_hooks.jsonl --out report_live_hooks.txt --json summary_live_hooks.json
```

### 05: round 5

hookpkg vs hookpkg2.

```bash
./run_v2_ab.sh          # = harness.py run --scenarios live --reps 3 --arms hookpkg,hookpkg2 --agents claude,codex,opencode
                        #   --max-turns 80 --browser-concurrency 3 --tag v2      (up to 3 passes)
python3 analyze_hooks.py results_live_v2.jsonl --arms hookpkg,hookpkg2 --out report_live_v2.txt --json summary_live_v2.json
```

### 06: round 6

rf-mcp vs v2 vs v3, 4 reps, self-healing runner under systemd (restarts after a SIGTERM, drops aborted rows,
resumes):

```bash
systemd-run --user --unit=ab-v3main -p Restart=always -p RestartSec=60 -p "RestartPreventExitStatus=0 2 4" \
  -p StartLimitIntervalSec=0 --working-directory="$PWD" --setenv=PATH="$PATH" --setenv=HOME="$HOME" \
  ./run_ab_resilient.sh v3main mcp,hookpkg2,hookpkg3 4
python3 analyze_hooks.py results_live_v3main.jsonl --arms mcp,hookpkg2,hookpkg3 --out report_live_v3main.txt \
  --json summary_live_v3main.json
```

### 07: round 7

Four units started in parallel at 06:37 local on 2026-10-10. The exact invocations are in
`rounds/07-v31-v32/logs/run_ab_*.log`. The runner adds `--max-turns 80 --browser-concurrency 3 --tag <TAG>`, and a
later `--browser-concurrency` in the extra arguments wins:

```bash
./run_ab_resilient.sh v31sub mcp,hookpkg3,hookpkg31 3 claude,codex,opencode live \
    --claude-model claude-haiku-5-5 --browser-concurrency 2
./run_ab_resilient.sh v31or mcp,hookpkg3,hookpkg31 3 \
    cc-or:deepseek-v4.1-flash,cc-or:qwen3.8-flash,cc-or:glm-5.3-flash live \
    --or-models deepseek/deepseek-v4.1-flash,qwen/qwen3.8-flash,z-ai/glm-5.3-flash --or-budget-usd 50 \
    --browser-concurrency 2
./run_ab_resilient.sh v31gem mcp,hookpkg31 2 cc-or:gemini-3.8-flash live \
    --or-models google/gemini-3.8-flash --or-budget-usd 90 --browser-concurrency 1        # stopped after 10 cells
./run_ab_resilient.sh v32 hookpkg31,hookpkg32 3 codex,cc-or:qwen3.8-flash live \
    --or-models qwen/qwen3.8-flash --or-budget-usd 15 --browser-concurrency 1
python3 analyze_hooks.py results_live_v31sub.jsonl --arms mcp,hookpkg3,hookpkg31 --out report_live_v31sub.txt
python3 analyze_hooks.py results_live_v31or.jsonl --arms mcp,hookpkg3,hookpkg31 --out report_live_v31or.txt
python3 analyze_hooks.py results_live_v32.jsonl --arms hookpkg31,hookpkg32 --out report_live_v32.txt
```

The pooled numbers (0.83 vs 0.69) combine `v31sub` and `v31or`; see `claims.yaml` (`readme-pooled-*`).

**Checked.** The three `harness.py run …` command lines these units expand to parse with the archived harness's
argument parser. They were checked with a parse-only shim that stops after `parse_args`, so no agent was started.
They were not executed again: a real rerun needs the agent subscriptions and OpenRouter credits.

**Before you start an OpenRouter unit:**
- top up the account and check `/api/v1/credits`;
- do not run two OpenRouter units against one baseline (incident 4 in `incidents.md`);
- expect Codex backend outages to show up as short failed cells, and re-run them (incident 5).

### 08: round 8 (release gate)

Not run yet (task 8.1). The planned command, with the ported harness and the same-window rule: rf-harness vs the
hookpkg32 prototype, 3 reps, Claude Code, Codex, OpenCode and Qwen 3.8 Flash.

```bash
python3 eval/harness.py check-scenarios                      # must report IDENTICAL to round 7
python3 eval/harness.py run --scenarios live --reps 3 --arms prototype-v32,rf-harness \
    --agents claude,codex,opencode,cc-or:qwen3.8-flash --or-models qwen/qwen3.8-flash --or-budget-usd 15 \
    --max-turns 80 --browser-concurrency 2 --tag r8gate
```

`python3 eval/harness.py --help` runs, and the command line above parses with `eval/harness.py`'s argument parser
(parse-only check, 2026-10-11). The ported harness is still being finished in parallel (tasks 5.x), so check
`eval/` for the final options. Archive the results as `rounds/08-release-gate/` with
`import_research.py`-style provenance, a `README.md`, `config.json`, `checksums.sha256` and claims.

## Rounds 1–3 and the static-analysis study

These are scripted spikes, not A/B runs. Every study folder has its scripts next to its `findings.md`. Most need
robotcode 2.7.0, Robot Framework 7.5, Browser 20.5.0 and network access to the public demo sites. The `agents` and
`agent_lsp` studies also need the agent CLIs listed in the round README. Run the scripts from their folder. Like
the harness, scripts that hard-coded the research worktree now carry `~/...` paths, so adjust them to your
checkout.
