# Environment variables

Generated from `src/rf_harness/config.py` (`scripts/gen_reference.py`); do not edit by hand. Set them in the
agent's environment, or as defaults in `.rf/harness.json` under `"env"` (the process environment wins).

## desktop

| variable | default | meaning |
|---|---|---|
| `RFH_DESKTOP` | `0` | Set to 1 to allow live desktop (PlatynUI) steps. Off by default until the vendored rf-mcp desktop guards pass their parity tests; even when on, every safety, isolation and focus guard still applies. |
| `RFH_PLATYNUI_ALLOW_ACTIVE_DESKTOP` | `0` | Escape hatch: 1 allows desktop input on an 'active' or 'unknown' display (audited). Input may still target the wrong window on a shared desktop; prefer an isolated display. |
| `RFH_PLATYNUI_ALLOW_CONTROL_WINDOW` | `0` | 1 allows control:Window locators on Linux (AT-SPI windows are control:Frame) with a one-time warning. |
| `RFH_PLATYNUI_ALLOW_PATH_DESCRIPTOR` | `0` | 1 allows an image path in the Take Screenshot descriptor slot with a one-time warning. |
| `RFH_PLATYNUI_ALLOW_UNSCOPED` | `0` | 1 allows //-rooted desktop Query/Evaluate locators (whole-desktop walks) with a one-time warning. |
| `RFH_PLATYNUI_HIGHLIGHT` | `1` | 0 disables highlighting the target element before desktop input. |
| `RFH_PLATYNUI_ISOLATED_DISPLAY` | (empty) | Isolation marker: the X DISPLAY(s) (comma/space separated) the harness may drive, for example ':99'. Only counts when RFH_PLATYNUI_ISOLATED_XPID names the live X server for that display. |
| `RFH_PLATYNUI_ISOLATED_XPID` | (empty) | PID of the Xvfb/Xephyr/Xorg server that owns the isolated display. Corroborates the isolation marker; without it the display is classified 'unknown' and desktop input is refused. |
| `RFH_PLATYNUI_KEEP_WAYLAND` | `0` | 1 keeps the native Wayland backend instead of forcing XDG_SESSION_TYPE=x11 before PlatynUI starts. |
| `RFH_PLATYNUI_NO_FOCUS` | `0` | 1 disables focus-before-act for desktop pointer/keyboard steps (the step is marked focus-bypassed). |
| `RFH_PLATYNUI_REQUIRE_ISOLATED` | `0` | Windows only: 1 refuses desktop input on the active Windows desktop (there is no nested-display model). |
| `RFH_PLATYNUI_SAFETY_GUARD` | `enforce` | 'warn' logs instead of refusing desktop input on a non-isolated display (transition mode). |
| `RFH_PLATYNUI_STEERING_CONFIDENCE` | `enforce` | 'warn' downgrades a 'contradicted' steering-confidence verdict from a step failure to a warning. |
| `RFH_SCREENSHOT_DIR` | (empty) | Extra directory desktop screenshots may be written to (the system temp dir is always allowed). |

## docs

| variable | default | meaning |
|---|---|---|
| `RFH_DOC_WAIT` | `1.2` | Seconds a hook waits for a keyword documentation file before naming its path anyway. |
| `RFH_KWDOC_FILES` | `0` | 1 writes .rf/docs/kw/<Owner>.<Keyword>.md on every failure (v2) instead of on demand. |

## feedback

| variable | default | meaning |
|---|---|---|
| `RFH_COMPACT_AGENTS` | `opencode` | Comma-separated agents that get the compact v2 output and image-read guard. |
| `RFH_GUIDANCE_FIRST` | `opencode` | Comma-separated agents whose feedback starts with the guidance (hint, NEXT:). |
| `RFH_LEAN` | `1` | 0 switches to the v2 output format (ablation only). |
| `RFH_LOOP_AT` | `3` | Number of identical failures after which the one-time loop hint is shown. |
| `RFH_MAX_CONTEXT` | `2048` | Maximum characters of any hook context returned to the agent. |
| `RFH_MAX_CONTEXT_OPENCODE` | `1200` | Maximum characters of hook context for OpenCode. |
| `RFH_MAX_CTX_CLAUDE` | (empty) | Lean-profile budget for claude as 'ok,fail' characters; default: the per-agent caps in leanfmt. |
| `RFH_MAX_CTX_CODEX` | (empty) | Lean-profile budget for codex as 'ok,fail' characters; default: the per-agent caps in leanfmt. |
| `RFH_MAX_CTX_COPILOT` | (empty) | Lean-profile budget for copilot as 'ok,fail' characters; default: the per-agent caps in leanfmt. |
| `RFH_MAX_CTX_OPENCODE` | (empty) | Lean-profile budget for opencode as 'ok,fail' characters; default: the per-agent caps in leanfmt. |
| `RFH_MAX_CTX_RICH` | (empty) | Rich-profile budget as 'ok,fail' characters for every agent; default 1200,1200. |
| `RFH_MAX_CTX_RICH_CLAUDE` | (empty) | Rich-profile budget for claude as 'ok,fail' characters (RFH_MAX_CTX_RICH wins). |
| `RFH_MAX_CTX_RICH_CODEX` | (empty) | Rich-profile budget for codex as 'ok,fail' characters (RFH_MAX_CTX_RICH wins). |
| `RFH_MAX_CTX_RICH_COPILOT` | (empty) | Rich-profile budget for copilot as 'ok,fail' characters (RFH_MAX_CTX_RICH wins). |
| `RFH_MAX_CTX_RICH_OPENCODE` | (empty) | Rich-profile budget for opencode as 'ok,fail' characters (RFH_MAX_CTX_RICH wins). |
| `RFH_MAX_CTX_RICH_VSCODE` | (empty) | Rich-profile budget for vscode as 'ok,fail' characters (RFH_MAX_CTX_RICH wins). |
| `RFH_MAX_CTX_VSCODE` | (empty) | Lean-profile budget for vscode as 'ok,fail' characters; default: the per-agent caps in leanfmt. |
| `RFH_READ_STREAK_AT` | `8` | Consecutive reads without an edit or command after which a note is added (again at twice the value); 0 disables it. |
| `RFH_REPRODUCE` | `1` | 0 disables the live reproduction of the first failure of a plain robot run. |
| `RFH_RFMCP_HINTS` | `0` | 1 adds hints from the vendored rf-mcp hint engine (runtime/hints.py) to live failures. Off by default: the measured v3.2 prototype ran without it. |

## general

| variable | default | meaning |
|---|---|---|
| `RFH_FORCE_REPL` | `0` | 1 activates the REPL-only short-timeout listener also outside `robotcode repl/shell` (tests only). |
| `RFH_PYTHON` | (empty) | Interpreter for the helper daemons and doc workers; default: the hook's own interpreter. |
| `RFH_ROOT` | (empty) | Project root; default: CLAUDE_PROJECT_DIR, else the nearest parent of the hook's cwd that already has .rf/hook, else the cwd. |
| `RFH_TOKEN` | (empty) | Internal: random per-daemon token set in the daemons' environment to find and clean up their child processes. Do not set it. |
| `RFH_WATCH_PID` | (empty) | PID of the agent process the daemons watch (they exit when it is gone); 0 disables the watch; default: detected from the hook's ancestors. |

## guards

| variable | default | meaning |
|---|---|---|
| `RFH_DENY_CODES` | `TokenError,ParsingError,InvalidHeader,ModelError` | Comma-separated static-analysis codes that refuse an edit; every other finding is a one-line warning. |
| `RFH_MAX_DENIALS` | `3` | Refusals of the same kind before the edit or command is let through with a note. |
| `RFH_MAX_DENIALS_OPENCODE` | `2` | RFH_MAX_DENIALS for OpenCode. |
| `RFH_MAX_STOP_BLOCKS` | `2` | How often the end of a turn is blocked for a missing green plain robot run. |
| `RFH_RELAXED_DENIALS` | `1` | 0 restores the v2 denial policy (refuse every static finding; ablation only). |
| `RFH_REWRITE_AGENTS` | `claude,opencode,codex,copilot` | Comma-separated agents whose tool input may be rewritten (deprecated-syntax fixes, REPL format fixes). |

## lint

| variable | default | meaning |
|---|---|---|
| `RFH_GATE_TIMEOUT` | `2.5` | Seconds the PreToolUse static gate waits for the lint daemon; on timeout the edit proceeds. |
| `RFH_STATIC` | `on` | on: the harness checks edits statically (refusals for certainly-wrong structure, one-line warnings, deprecated-syntax fixes). runtime-only: only certainly-wrong structural edits are refused, no static warnings or fixes, and live runs execute lines without the static pre-check (used when rf-agentskills validates edits). |

## live

| variable | default | meaning |
|---|---|---|
| `RFH_ADAPT_FACTOR` | `1.5` | A late element raises the site's learned short timeout to this factor times its observed latency. |
| `RFH_BUDGET` | `90` | Maximum seconds a PostToolUse hook waits for live results before reporting 'still running' (the result is delivered with the next hook event). |
| `RFH_CAPTURE` | `end` | Page capture mode: end (after the last step and on failures), step (after every page keyword) or off. |
| `RFH_CAPTURE_GATE` | `1` | 0 captures after every page keyword (v2 behavior) instead of only on navigation, failures and real DOM changes. |
| `RFH_CAPTURE_SETTLE` | `1.5` | Maximum seconds the end-of-run capture waits for the page to settle. |
| `RFH_FRESH_DOC_S` | `6` | A document younger than this many seconds is not yet considered stable. |
| `RFH_GUARD_SETTLE` | `5.0` | Seconds the pre-execution guard lets a page settle between back-to-back file lines. |
| `RFH_IDLE_EXIT` | `1200` | Seconds without requests after which the helper daemons exit. |
| `RFH_MAX_CAPTURES` | `2` | Maximum page captures per edit (failure + end of run). |
| `RFH_PAGE_TEXT` | `4000` | Maximum characters of visible page text in .rf/state/latest/page.txt. |
| `RFH_SHORT_TIMEOUT` | `2.5` | Live element-keyword timeout in seconds (Browser). |
| `RFH_SHORT_TIMEOUTS` | `1` | 0 disables the short live element timeouts (live and REPL listener). |
| `RFH_SHORT_TIMEOUT_SELENIUM` | (empty) | Live element timeout for SeleniumLibrary; default: RFH_SHORT_TIMEOUT. |
| `RFH_STABLE_S` | `2` | Seconds without DOM change after which a page counts as stable (a missing element on a stable page is MISSING at once). |
| `RFH_STATE_HISTORY` | `15` | Number of step-* capture directories kept in .rf/state. |

## logging

| variable | default | meaning |
|---|---|---|
| `RFH_HOOK_LOG` | (empty) | Path of the JSONL hook event log; default: .rf/hook/hooks.jsonl. |

## profiles

| variable | default | meaning |
|---|---|---|
| `RFH_MODEL` | (empty) | Model id used for the profile choice; default: from the hook payload, the agent's environment, transcript or config. |
| `RFH_PROFILE` | (empty) | Force the output profile: lean or rich; default: chosen from the model in use. |
