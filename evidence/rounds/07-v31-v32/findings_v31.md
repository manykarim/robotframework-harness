# Round 7: v3.1 per-model output profiles, cheap OpenRouter models, Haiku 5.5, and v3.2 (2026-10-10)

## Data

| file | run | cells | notes |
|---|---|---|---|
| `harness/results_live_v31sub.jsonl` | subscription agents: Claude Code + **claude-haiku-5-5**, Codex (gpt-5.6-luna), OpenCode (MiniMax-M2.5) × {mcp, hookpkg3, hookpkg31} × 5 live scenarios × 3 reps | **135/135** | report `report_live_v31sub.txt` |
| `harness/results_live_v31or.jsonl` | Claude Code against OpenRouter: **DeepSeek V4.1 Flash, Qwen 3.8 Flash, GLM 5.3 Flash** × same arms | **71/135 valid** | rep 1 complete, rep 2 partial; 64 cells dropped, see "Incident"; report `report_live_v31or.txt` |
| `harness/results_live_v31gem.jsonl` | Gemini 3.8 Flash × {mcp, hookpkg31} | 10 | **stopped**, see below |
| `harness/results_live_v32.jsonl` | **v3.1 vs v3.2**: Codex (complete) + Qwen (partial) | 39 | report `report_live_v32.txt` |
| `harness/results_live_v32smoke.jsonl` | v3.2 smoke, Qwen tricentis_quote | 1 | PASS 12/12 |

All runs were in the same time window (06:37–15:33) and use the same live scenarios and journey-evidence graders as
round 6 (`findings_v3main.md`). There were 0 auth failures and 0 leak hits. One cell was contaminated
(`codex|mcp|tricentis_debug|1`, a helper-CLI marker in the mcp arm) and is excluded by the analyzer.

## 1. Correctness

**Pooled over the two v3.1 runs (206 valid cells):**

| arm | pass | 95% CI |
|---|---:|---|
| rf-mcp 0.36.0 | 47/68 = **0.69** | 0.57–0.79 |
| hookpkg3 (v3, lean) | 51/68 = **0.75** | 0.64–0.84 |
| hookpkg31 (v3.1, per-model profile) | 58/70 = **0.83** | 0.72–0.90 |

- v3.1 vs rf-mcp: +0.14 (Fisher p = 0.073). By cell, 7 better and 2 worse (sign test p = 0.18).
- v3 vs rf-mcp: +0.06 (p = 0.57).

| agent / model | rf-mcp | v3 | v3.1 | v3.1 profile |
|---|---|---|---|---|
| Claude Code + Haiku 5.5 | **0.93** | 0.80 | **0.93** | lean |
| Codex (gpt-5.6-luna) | 0.87 | 0.87 | 0.87 | lean |
| OpenCode + MiniMax-M2.5 | 0.27 | 0.47 | **0.53** | rich |
| DeepSeek V4.1 Flash (Claude Code via OpenRouter) | 1.00 | 1.00 | 1.00 | rich |
| GLM 5.3 Flash | 0.71 | 0.75 | **0.88** | rich |
| Qwen 3.8 Flash | 0.38 | 0.75 | **0.88** | rich |

By scenario kind (v31sub): debug 0.67 / 0.78 / **0.83**; explore 0.70 / 0.67 / **0.74**.

**Grader artifact.** Four v31sub cells fail **only** because the suite asserts the total as a regex
(`Should Match Regexp … \$916\.99`), and the file-content grader looks for the literal `916.99`:
- affected cells: mcp 1, v3 2, v3.1 1, plus 1 rf-mcp cell in v3main;
- adjusted v31sub: rf-mcp 0.71, v3 0.76, v3.1 0.80;
- adjusted Claude: 1.00 / 0.93 / 1.00.

The artifact hits all arms about equally and changes no conclusion. Fix the grader for the next round by accepting
regex-escaped literals.

## 2. Efficiency

| agent | rf-mcp | v3 | v3.1 |
|---|---|---|---|
| Claude (Haiku 5.5): cost / wall / turns | $0.036 / 313 s / 32 | $0.025 / 381 s / 28 | $0.033 / 317 s / 33 |
| Codex: wall / tool calls | 405 s / 39 | 207 s / 28 | **199 s / 28** |
| OpenCode: wall / turns / timeouts (30 min) | 1,237 s / 104 / **7** | 513 s / 45 / 1 | **436 s / 52 / 0** |
| DeepSeek: est. $ / turns | $0.210 / 64 | $0.052 / 46 | **$0.052 / 39** |
| GLM: est. $ / wall | $0.153 / 455 s | $0.086 / 464 s | **$0.070 / 286 s** |
| Qwen: est. $ / wall / timeouts | $0.075 / 1,146 s / 2 | $0.046 / 644 s / 0 | $0.054 / 676 s / 0 |

- v3.1 context: 338 characters per edit for Claude and 366 for Codex (lean). With the rich profile: 709 for OpenCode
  and 707–732 for the OpenRouter models.
- The profile was detected correctly in **70 of 70** v3.1 sessions:
  - Claude via the transcript;
  - Codex and OpenCode via the payload;
  - OpenRouter models via `ANTHROPIC_MODEL`.
- The 71 valid OpenRouter sessions cost **$6.22** in total (list-price estimate).

## 3. What changed vs round 6

- **Haiku 5.5 closes the gap for Claude.** In round 6 (Haiku 4.5) Claude scored 0.30 with rf-mcp vs 0.65 with v3. With
  Haiku 5.5, rf-mcp and v3.1 are tied at 0.93, and cost and wall time are similar. The harness's correctness advantage
  now sits with weaker or cheaper models:
  - OpenCode/MiniMax: +0.27;
  - Qwen: +0.50;
  - GLM: +0.17.
- **The harness cuts cost and time for most agents.**
  - Codex: wall time −51%.
  - OpenCode: wall time −65%, and 0 vs 7 timeouts.
  - DeepSeek: −75% estimated cost.
- **The per-model profile (v3.1 vs v3) points the right way, but not significantly.**
  - Lean agents: identical output, so differences are noise (Claude 0.93 vs 0.80; Codex 0.87 = 0.87).
  - Rich agents: 31/40 = 0.78 vs 26/38 = 0.68 (+0.09, p = 0.45). Three of four rich-profile agents improved; DeepSeek
    was tied at 1.00.
  - Decision for design D6: keep per-model profiles (lean for Claude and GPT, rich for open-weight models). It costs
    nothing for lean agents.

## 4. Failure analysis → v3.2

1. **Covered radio with no usable target (tricentis_quote).**
   - The Tricentis price radio sits inside a `<label>` with no `for=` and no text, under a non-unique
     `span.ideal-radio`. So the COVERED verdict named no click target.
   - Agents improvised `label.choosePrice >> nth=2`. It is positional and brittle, and the journey grader reports it as
     "missing platinum".
   - In tricentis_quote transcripts, v3.1 agents used a positional `nth=` pick 3 times, v3.2 agents 0 times.
2. **Read loop (Gemini only).** Gemini made about 71 Reads per session, with up to 35 in a row (`source.html` paged,
   the test file re-read). All other models: 0.4–6 per session.
3. **Deep-link shortcuts (OpenCode, demoshop_order).**
   - `Go To …/cart?space=…` after the start page appeared in 9 hook-arm failures.
   - The once-per-session deep-link note is ignored.
   - Not fixed in v3.2. Candidate for v3.3: repeat the note per distinct URL path, and escalate at the stop gate when
     the prompt asks for an end-to-end journey.
4. **Start date not computed (tricentis_debug).** This still appears in all arms. It is a task-semantics miss, not a
   harness gap.

**v3.2** (`ab/hookpkg32`, build report `ab/hookpkg32_build_findings.md`):
- concrete, uniqueness-verified `label:has(#id)` / `#id + span.cls` targets in the controls list and in COVERED;
- read-streak nudge at 8 and 16 consecutive Reads;
- skill text: "never a positional `nth=` pick".

Simulation passed 221/224. The 3 failures are a pre-tool lint timing flake under load that v3.1 also shows.

**v3.1 vs v3.2 (same window):**

| agent | v3.1 | v3.2 |
|---|---|---|
| Codex | 14/15 | **15/15** (wall 240 → 209 s, tool calls 31 → 27) |
| Qwen (partial) | 4/4 | 4/5 |

- Codex had one infrastructure failure (Codex backend timeout, 3 tool calls). That cell was rerun.
- Overall: 18/19 vs 19/20 (n.s.).
- The live smoke (Qwen, tricentis_quote) used `label:has(#…)` for every styled input and passed 12/12.
- Verdict: v3.2 is at least as good as v3.1. Ship its fixes, but their effect is not yet statistically confirmed.

## 5. Gemini 3.8 Flash: stopped

- 10 cells: **0/10** in both arms (rf-mcp 0/5, v3.1 0/5). 9 of 10 hit the 80-turn cap.
- **About $2.40 per cell** in real spend, against an estimate of $1.0–3.8 (hidden reasoning tokens are not in the
  estimate).
- The unit was stopped after 10 of 20 cells to save about $25.
- The v3.2 read-streak nudge targets exactly this pattern. Testing it needs OpenRouter credits (about $20 for 8 cells).

## 6. Incident: OpenRouter account balance exhausted (12:00 local)

- From about 12:00, every OpenRouter request returned **HTTP 402** ("requires more credits … can only afford 27,823
  tokens").
- The **account** balance was used up: $455.17 spent of $455 total credits. This key had used only $32.28 of its $250
  limit. So the key limit is not the only limit.
- Claude Code records the 402 as a normal `result:success` turn. The runner checked only stderr/agent_info, so 64
  v31or cells and 12 v32 Qwen cells were written as `ok`. Some were cut off mid-session after 48–60 tool calls.
- Fixes (in place; the running v31sub was safe because the script was replaced atomically):
  - `run_ab_resilient.sh` scans OpenRouter transcripts for `API Error: 402/401` / `requires more credits` and drops
    those rows.
  - `or_ok` checks `openrouter.account_balance()` (the `/credits` endpoint) and refuses to start below $0.50
    (`AB_MIN_OR_BALANCE`).
  - The 76 rows were removed, with backups in `*.credits402.jsonl`.
- Related: the budget guard compares account-wide usage against a per-run baseline, so parallel OpenRouter runs consume
  each other's budgets. The spec `harness-evaluation` now requires per-run budgets.
- To finish v31or (64 cells, about $4) and the v32 Qwen cells (about $1.5), the account needs a top-up.

## 7. Conclusions for the architecture (openspec change `robotcode-agent-harness`)

1. **Hooks harness ≥ rf-mcp in every agent, in the same window.** Pooled pass rate 0.83 vs 0.69. The large wins are
   with weaker/cheaper models and OpenCode, plus big wall-time and cost cuts.
2. **Strong models (Haiku 5.5, Codex) are near the ceiling with either delivery.** For them, the harness's value is
   speed, cost and portability: execution is local, and no MCP server is needed.
3. **Keep per-model output profiles.** The rich profile helps open-weight models; lean costs Claude and GPT nothing.
4. **Evaluation needs:**
   - account-balance checks and transcript-level error detection;
   - per-run budgets;
   - infrastructure-failure detection for Codex backend outages;
   - regex-tolerant value graders.

   All four are now in the spec or the harness.
