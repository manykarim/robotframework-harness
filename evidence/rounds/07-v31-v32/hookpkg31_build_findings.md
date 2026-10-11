# hookpkg31 (v3.1) + OpenRouter harness support (build report, 2026-10-10)

Source: v3.1 builder subagent report (saved by the coordinating session). Simulation 216/216 (188 v3 + 28 profile checks); 9 real smoke sessions passed; 0 orphans; key never written to disk (grep for key value / "sk-or-" clean); OpenRouter spend for testing $0.54.

## v3.1 (`ab/hookpkg31/`, `rfharness31`)
Side-by-side copy of v3 (`RFH31_`, `.rf/{hook31,exec31,lint31}`, plugin `rfharness31.js`, `[rfh31]` markers). `profiles.py` selects the output profile; `richfmt.py` renders the rich profile: on success after navigation ≤ 8 controls (`kind "name" => selector (note)`, form fields first, already-listed header/nav skipped, hrefs never shown); on every failure ≤ 8 nearest controls (word matches first, then the keyword's targets; also for COVERED), signature + first doc sentence, failure-type hint (≤ 300 chars), `NEXT:`; plain robot runs get signature + hint every time; budget 1,200 chars (`RFH31_MAX_CTX_RICH`); OpenCode gets hint + NEXT first. `install(..., profile=)` pins a profile for ablations. Profile/source/model logged on every hook event.

Profile rules: `RFH31_PROFILE` wins; else model id (from `RFH31_MODEL`, payload, `ANTHROPIC_MODEL`, `OPENCODE_MODEL`, `CODEX_MODEL`, session store, transcript, Codex config.toml): lean = anthropic/*, claude/haiku/sonnet/opus, GPT/o-series/codex/luna; rich = MiniMax, DeepSeek, Qwen, GLM/Z.ai, Gemini, Kimi, unknown. No model id: claude/codex/copilot lean, opencode rich.

## Harness
Arm `hookpkg31` (`row["hookpkg31"]` + profile, profile_src, profile_model, profile_counts; markers `rfharness3(?!1)` etc.). Agents `cc-or:<short>` (Claude Code against an OpenRouter model: isolated home without subscription credentials, OpenRouter env) and `oc-or:<short>` (OpenCode native openrouter provider); `cc-or`/`cc-or:*` expands to all `--or-models`. `openrouter.py`: key read at runtime from rf-mcp/.env (redacted in cmd.json), price cache `or_prices.json`, cost estimate, `/key` usage, budget guard. Per OpenRouter cell `row["openrouter"]`: tokens, `est_cost_usd`, usage delta, concurrency, models seen, `delta_vs_est`, `billed_to_this_key`; `metrics.cost_usd` = estimate (agent-reported kept as `cost_usd_agent_reported`). `--or-budget-usd` (default 150) with persistent baseline `results_*.or_budget.json` (`--or-budget-reset`), exit 4 when exhausted (tested with budget 0). `analyze_hooks.py` handles any agent id (+ profile and OpenRouter cost tables; v3main report byte-identical). `run_ab_resilient.sh` passes extra args, checks OpenRouter key + Claude auth with the given `--claude-model`, drops OpenRouter auth-failure rows, exits 4 on budget exhaustion. `check-scenarios` IDENTICAL.

## Smoke sessions (local web3)
| session | route | pass | turns | wall | profile | ctx chars/edit | est $ | usage Δ $ |
|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 v3.1 | subscription | PASS | 10 | 66 s | lean | 370 | – | – |
| deepseek-v4.1-flash v3.1 | cc-or | PASS | 18 | 131 s | rich | 285 | 0.0147 | 0.0087 |
| qwen3.8-flash v3.1 | cc-or | PASS | 18 | 278 s | rich | 285 | 0.0156 | 0.0161 |
| glm-5.3-flash v3.1 | cc-or | PASS | 16 | 149 s | rich | 288 | 0.0129 | 0.0133 |
| gemini-3.8-flash v3.1 | cc-or | PASS | 33 | 369 s | rich | 368 | 0.178 | **0.432** |
| glm-5.3-flash v3.1 | oc-or | PASS | 17 | 149 s | rich | 377 | 0.0172 | 0.0182 |
| deepseek, mcp arm | cc-or | PASS | 17 | 97 s | – (0 MCP calls) | – | 0.0192 | 0.0108 |
| deepseek, MCP probe | cc-or | PASS | 5 | 18 s | – (4 MCP calls) | – | 0.0117 | 0.0031 |
cc-or works for all four models (no fallback); transcripts show OpenRouter model ids and `/key` usage rose; MCP works through cc-or.

## Known gaps
OpenCode bills a different OpenRouter key by default (global auth.json) → fixed with cell-local XDG_DATA_HOME + `{env:OPENROUTER_API_KEY}`; estimates use list prices (DeepSeek billed 0.3–0.6× of estimate; Gemini hidden reasoning tokens missing → estimate 0.41× of real charge); per-cell usage deltas mix under concurrency; budget can overshoot by running cells; Gemini is the main budget risk (~$0.43 on an easy task); Claude subscription profile is lean until the first tool event reveals the model; smoke proves routes, not rich vs lean.

## Experiments launched 2026-10-10 06:37 (systemd, self-healing)
- `ab-v31sub`: `run_ab_resilient.sh v31sub mcp,hookpkg3,hookpkg31 3 claude,codex,opencode live --claude-model claude-haiku-5-5 --browser-concurrency 2` (135 cells)
- `ab-v31or`: `… v31or mcp,hookpkg3,hookpkg31 3 'cc-or:deepseek-v4.1-flash,cc-or:qwen3.8-flash,cc-or:glm-5.3-flash' live --or-models deepseek/deepseek-v4.1-flash,qwen/qwen3.8-flash,z-ai/glm-5.3-flash --or-budget-usd 50 --browser-concurrency 2` (135 cells)
- `ab-v31gem`: `… v31gem mcp,hookpkg31 2 'cc-or:gemini-3.8-flash' live --or-models google/gemini-3.8-flash --or-budget-usd 90 --browser-concurrency 1` (20 cells)
