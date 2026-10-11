#!/usr/bin/env python3
"""A/B/C harness: rf-mcp (MCP server) vs. skill + local package + hooks (no MCP) vs. no help.

Research driver only (never shipped). Adapted from the eval#3/#4 harness
(rf-mcp/experiments/bundle-agent-skills-eval/harness.py); the 4 HARD scenarios
(iframe, apinested, results_complex, browser_dynamic) keep their prompts and
graders VERBATIM (see `check-scenarios`).

Arms (the only variable inside an agent x scenario cell):
    neither   - no MCP server, no skill, no hooks (true baseline)
    mcp       - rf-mcp v0.36.0 as a local stdio MCP server (== eval#3 `mcp_only`)
    skillpkg  - no MCP; Agent Skill + local robotcode-based helper package + hooks,
                provisioned by `skillpkg.install.install(agent, workspace, agent_home,
                venv_bin) -> {"extra_args": [...], "extra_env": {...}, "notes": "..."}`
                (package dir ../skillpkg/, built separately). Optional extra keys the
                harness honours if present: "markers" (strings that identify helper-CLI /
                skill use in transcripts) and "hook_log" (a file whose lines = hook firings).
    hookpkg   - no MCP, NO agent-facing CLI; Agent Skill + hooks only (SessionStart / PreToolUse static
                gate / PostToolUse live execution of edited test lines + robot-run summaries / Stop
                quality gate / SessionEnd), provisioned by `hookpkg.install.install(...)` (same
                interface; package ../hookpkg/, module rfharness). Hook firings are logged to
                <cell>/rfh_hooks.jsonl (RFH_HOOK_LOG) -> row["hookpkg"] (firings per event, auto-executed
                lines, denials, rewrites, Stop-gate blocks). Contamination: `rfmcp` CLI calls in this arm;
                rfharness / .rf/hook usage in any other arm.
    hookpkg2  - v2 of hookpkg (package ../hookpkg2/, module rfharness2, state .rf/hook2, env RFH2_*): adds failing-keyword
                docs (.rf/docs/kw), per-step page capture (.rf/state/latest + history), short live timeouts with a
                slow-vs-missing recheck, import docs, REPL/debugger format enforcement, suite/install/-P/big-read
                guards, loop hints, UserPromptSubmit context. NOT in the default --arms list: request it explicitly,
                e.g. `--arms hookpkg,hookpkg2`. Log <cell>/rfh2_hooks.jsonl -> row["hookpkg2"]. Contamination:
                v1 markers (rfharness without 2, .rf/hook) in this arm and v2 markers (rfharness2, .rf/hook2) in
                the hookpkg arm.
    hookpkg3  - v3 of hookpkg (package ../hookpkg3/, module rfharness3, state .rf/hook3, env RFH3_*): tuned v2 after
                the round-5 A/B + round-6 diagnosis -- Playwright-log failure classes before any re-check (COVERED /
                NOT_VISIBLE / ... ; SLOW only for absent -> present), adaptive per-page/origin live timeouts, captures
                only on failure + after the last step (no per-step settle), lean per-agent context budgets, kw docs on
                demand, race-aware reproduction, denials only for certain hard errors (else allow + one-line warning).
                Opt-in like hookpkg2 (`--arms hookpkg2,hookpkg3`). Log <cell>/rfh3_hooks.jsonl -> row["hookpkg3"]
                (hookpkg2 metrics + context chars per edit, captures/skipped, rechecks by verdict incl. skipped, adaptive
                timeout changes, denials vs warnings, race reproductions). Contamination: v1/v2/v3 markers cross-checked
                between the three hook arms.

    hookpkg31 - v3.1 of hookpkg (package ../hookpkg31/, module rfharness31, state .rf/hook31, env RFH31_*): v3 + per agent /
                model OUTPUT PROFILES -- `lean` (= v3; Claude / Codex GPT models) and `rich` (v2-like guidance with v3's
                correct facts: controls list after navigation, <= 8 nearest controls, keyword signature + first doc
                sentence and a failure-type hint on every failure, ~1,200 chars; MiniMax, DeepSeek, Qwen, GLM, Gemini,
                Kimi, unknown models). The hook picks the profile itself (RFH31_PROFILE forces one). Opt-in arm. Log
                <cell>/rfh31_hooks.jsonl -> row["hookpkg31"] (v3 metrics + profile / profile_src / profile_model).
                Contamination: v1/v2/v3/v3.1 markers cross-checked between the four hook arms.

Agents: claude (Claude Code), codex (Codex CLI), opencode (OpenCode), copilot (Copilot CLI), plus OpenRouter-routed
variants (see openrouter.py): `cc-or:<short>` = Claude Code against an OpenRouter model (isolated home WITHOUT
subscription credentials, ANTHROPIC_BASE_URL=https://openrouter.ai/api + ANTHROPIC_AUTH_TOKEN, all model env vars = the
id) and `oc-or:<short>` = OpenCode's native openrouter provider. <short> comes from `--or-models` (id list or
short=id pairs; default short = last path segment), `cc-or:*` / `cc-or` = every --or-models entry. Per OpenRouter
cell: token counts, cost estimate from OpenRouter prices (or_prices.json cache) and the account usage delta of
/api/v1/key before/after (row["openrouter"]; concurrent OpenRouter cells share that delta). `--or-budget-usd` (default
150): no new OpenRouter cells once the account usage since the batch start (baseline in or_budget_<tag>.json, survives
restarts; --or-budget-reset) exceeds it; the harness then exits 4 (run_ab_resilient.sh: no restart).
Every cell runs in a fresh fixture copy under WORK_ROOT with an isolated agent home:
    claude   CLAUDE_CONFIG_DIR=<cell>/agent_home (credentials copied, deleted after the cell);
             always --strict-mcp-config (+ an empty or rf-mcp --mcp-config)
    codex    CODEX_HOME=<cell>/agent_home (auth.json copied, deleted after the cell)
    opencode OPENCODE_CONFIG=<cell>/agent_home/opencode.json (global auth; global config is empty)
    copilot  COPILOT_HOME=<cell>/agent_home (keeps ~/.copilot/mcp-config.json's RobotMCP out),
             --disable-builtin-mcps, rf-mcp via --additional-mcp-config @file

OPS safety:
  * a background Reaper kills ONLY processes that belong to a finished/aborted cell of this
    harness: cwd or cmdline under WORK_ROOT, or env marker AB_EVAL_CELL=<cell under WORK_ROOT>
    (set on the agent and passed explicitly to the MCP server), plus the recorded process tree of
    the cell's agent. It never pattern-kills by program name.
  * at most 2 concurrent browser cells; at most 2 concurrent cells per agent.
  * disk guard: refuses to start / stops scheduling when free space < 1.2 GB (MIN_FREE_BYTES).
  * one harness instance per WORK_ROOT (flock), so reapers never fight.

Subcommands: run | pilot | verify-ref | check-scenarios | check-mcp | probe | reap

Round 2 (LIVE scenarios, `--scenarios live` | explore | debug | <ids>): exploratory authoring and
debugging of an existing failing suite against live websites (Tricentis sample app, Flowline demo
shop, car configurator). Fixtures in ../fixtures_live/ (hidden references in _reference/), per-cell
templating (`__AB_SPACE__` -> unique demoshop data space), robot_pass graded LIVE with one automatic
retry (`flaky=true` when only the retry passes), debug anti-cheat graders (test names unchanged,
expected values present on non-comment lines, forbidden failure-hiding constructs), and per-session
stepwise metrics (rf-mcp execute_step/... vs `rfmcp step|run|state|...` vs plain `robot` runs).
Live runs default to results_live.jsonl / transcripts_live / work_live (`--tag X` -> *_live_X).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import fcntl
import gzip
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Paths / config
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent                     # ab/harness
AB = HERE.parent                                           # ab/
REPO = Path("~/workspace/rf-mcp-robotcode")       # rf-mcp v0.36.0 worktree
VENV_BIN = REPO / ".venv" / "bin"                          # robot, Browser, RequestsLibrary, robotcode
FIXTURES_SRC = AB / "fixtures"
REFERENCE_SRC = FIXTURES_SRC / "_reference"                # hidden reference solutions
FIXTURES_LIVE = AB / "fixtures_live"                       # round 2: live-site scenarios
REFERENCE_LIVE = FIXTURES_LIVE / "_reference"
NEGATIVE_LIVE = FIXTURES_LIVE / "_negative"                # negative-control (shortcut) suites, must fail
OLD_HARNESS = Path("~/workspace/rf-mcp/experiments/bundle-agent-skills-eval/harness.py")
PW_BROWSERS = Path.home() / ".cache" / "ms-playwright"

WORK_ROOT = Path.home() / ".cache" / "ab-eval" / "work_rc"
RESULTS = HERE / "results_rc.jsonl"
TRANSCRIPTS = HERE / "transcripts_rc"

RF_MCP_CMD = ["uv", "run", "--directory", str(REPO), "-m", "robotmcp.server"]
CELL_ENV_MARKER = "AB_EVAL_CELL"
MIN_FREE_BYTES = int(1.2 * 1024 ** 3)     # stop starting cells below 1.2 GB free
HARNESS_VERSION = "rc-3-journey"     # rc-3: journey prompts + journey-evidence graders (live)

AGENTS = ["claude", "codex", "opencode", "copilot"]     # base agents; + cc-or:<short> / oc-or:<short> (OpenRouter)
AGENT_MODELS = {
    "claude": "claude-haiku-4-5",
    "codex": "gpt-5.6-luna",
    "opencode": "minimax-coding-plan/MiniMax-M2.5",   # fallback: --opencode-model ...MiniMax-M2.7
    "copilot": "gpt-4.1",
}
CODEX_EFFORT = "medium"
OPENCODE_VARIANT = ""            # no provider reasoning variant by default (weak-model arm)

ARMS = ["neither", "mcp", "skillpkg", "hookpkg"]
ARM_SPEC = {                     # arm -> (has_mcp, has_skillpkg)
    "neither": (False, False),
    "mcp": (True, False),
    "skillpkg": (False, True),
    "hookpkg": (False, False),   # skill + hooks only (see HOOK_ARMS)
    "hookpkg2": (False, False),  # v2 skill + hooks (opt-in arm: not in the default ARMS list)
    "hookpkg3": (False, False),  # v3 skill + hooks (opt-in arm: not in the default ARMS list)
    "hookpkg31": (False, False),  # v3.1 skill + hooks, output profiles lean|rich (opt-in arm)
    "hookpkg32": (False, False),  # v3.2 = v3.1 + concrete covered-input targets + read-streak nudge (opt-in arm)
}
HOOK_ARMS = {"hookpkg", "hookpkg2", "hookpkg3", "hookpkg31", "hookpkg32"}  # arms provisioned by ../<arm>/install.py
# per hook arm: package dir, hook-log env var + file name, usage marker, workspace state dir (contamination checks)
HOOK_PKGS = {
    "hookpkg": {"log_env": "RFH_HOOK_LOG", "log_name": "rfh_hooks.jsonl", "marker": r"rfharness(?![23])",
                "state_dir": (".rf", "hook")},
    "hookpkg2": {"log_env": "RFH2_HOOK_LOG", "log_name": "rfh2_hooks.jsonl", "marker": r"rfharness2",
                 "state_dir": (".rf", "hook2")},
    "hookpkg3": {"log_env": "RFH3_HOOK_LOG", "log_name": "rfh3_hooks.jsonl", "marker": r"rfharness3(?![12])",
                 "state_dir": (".rf", "hook3")},
    "hookpkg31": {"log_env": "RFH31_HOOK_LOG", "log_name": "rfh31_hooks.jsonl", "marker": r"rfharness31",
                  "state_dir": (".rf", "hook31")},
    "hookpkg32": {"log_env": "RFH32_HOOK_LOG", "log_name": "rfh32_hooks.jsonl", "marker": r"rfharness32",
                  "state_dir": (".rf", "hook32")},
}

# OpenRouter-routed agents (cc-or:<short> / oc-or:<short>); see openrouter.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
import openrouter as OR  # noqa: E402

OR_MODELS: dict[str, str] = OR.parse_models(OR.DEFAULT_MODELS)   # short -> OpenRouter model id (--or-models)
OR_BUDGET_USD = 150.0
OR_BUDGET_RESET = False
OR_KEY: str | None = None            # loaded at runtime only when an OpenRouter agent is scheduled; never written
OR_BUDGET = None                     # OR.Budget during a batch
OR_RUNNING = {"n": 0}
OR_SKIPPED = {"n": 0}


def or_route(agent: str) -> tuple[str | None, str | None]:
    return OR.split_agent(agent)


def base_agent(agent: str) -> str:
    """cc-or:<short> -> claude, oc-or:<short> -> opencode, else the agent itself."""
    route, _ = or_route(agent)
    return OR.ROUTES[route] if route else agent


def is_or(agent: str) -> bool:
    return or_route(agent)[0] is not None


def or_model_id(agent: str) -> str | None:
    route, short = or_route(agent)
    if not route:
        return None
    if short not in OR_MODELS:
        raise SystemExit(f"unknown OpenRouter short name {short!r} in agent {agent!r}; --or-models has "
                         f"{', '.join(OR_MODELS) or 'nothing'}")
    return OR_MODELS[short]


def agent_model(agent: str) -> str:
    """the model string the agent CLI gets (OpenCode: openrouter/<id>)."""
    mid = or_model_id(agent)
    if mid is None:
        return AGENT_MODELS[agent]
    return ("openrouter/" + mid) if base_agent(agent) == "opencode" else mid


def expand_agents(spec: str) -> list[str]:
    """'claude,cc-or:*,oc-or:qwen3.8-flash' -> concrete agent ids (cc-or / cc-or:* = every --or-models entry)."""
    out: list[str] = []
    for a in [x.strip() for x in (spec or "").split(",") if x.strip()]:
        route, short = or_route(a)
        if a in OR.ROUTES or (route and short in ("*", "all")):
            out += [f"{route or a}:{s}" for s in OR_MODELS]
        elif route:
            or_model_id(a)
            out.append(a)
        elif a in AGENTS:
            out.append(a)
        else:
            raise SystemExit(f"unknown agent {a!r} (claude|codex|opencode|copilot|cc-or:<short>|oc-or:<short>)")
    return list(dict.fromkeys(out))


def or_models_from_argv(argv: list[str]) -> dict[str, str] | None:
    for i, a in enumerate(argv):
        if a == "--or-models" and i + 1 < len(argv):
            return OR.parse_models(argv[i + 1])
        if a.startswith("--or-models="):
            return OR.parse_models(a.split("=", 1)[1])
    return None


def cli_cells(reps: int, agents_spec: str, scen_spec: str, arms_spec: str, extra_argv: list[str] | None = None):
    """the cells a `run` invocation schedules (used by run_ab_resilient.sh to count expected cells)."""
    global OR_MODELS
    om = or_models_from_argv(list(extra_argv or []))
    if om:
        OR_MODELS = om
    return build_cells(reps, expand_agents(agents_spec), expand_scenarios(scen_spec), arms_spec.split(","))


def ensure_or_key() -> str:
    global OR_KEY
    if OR_KEY is None:
        OR_KEY = OR.load_key()
        if not OR_KEY:
            raise SystemExit("[abort] OpenRouter agents requested but OPENROUTER_API_KEY is neither in the env nor in "
                             f"{OR.ENV_FILE}")
    return OR_KEY

CONCURRENCY = 3
BROWSER_CONCURRENCY = 2          # killed browser cells leak chromium -> OOM; keep this low
                                 # (live sites: also keeps load on the owner's servers modest)
AGENT_CONCURRENCY = 2            # avoid provider rate limits biasing one arm
PRUNE = True                     # delete each cell dir after recording (disk is ~98% full)
KEEP_TRANSCRIPTS = True          # gzip agent stdout into TRANSCRIPTS before pruning

_WRITE_LOCK = threading.Lock()
ABORT = threading.Event()
RUNNING: dict[str, subprocess.Popen] = {}
_RUNNING_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# Scenarios: the 4 HARD scenarios of eval#3/#4, prompts + graders VERBATIM.
# --------------------------------------------------------------------------- #
@dataclass
class Scenario:
    id: str
    skill: str
    tier: str
    fixture: str
    prompt: str
    graders: list[dict]
    primary_metric: str
    timeout_s: int
    max_turns: int
    # round 2 (defaults keep the round-1 scenarios unchanged)
    kind: str = "authoring"          # authoring (round 1) | explore | debug
    live: bool = False               # fixture lives in fixtures_live/, site under test is a live website
    browser: bool = False            # needs a browser (browser semaphore)
    template: dict | None = None     # token -> value pattern applied to every fixture file + the prompt


SCENARIOS: list[Scenario] = [
    Scenario(
        id="iframe",
        skill="browser",
        tier="hard",
        fixture="sut-iframe",
        timeout_s=1500,
        max_turns=45,
        primary_metric="all",
        prompt=(
            "This project has a page at pages/app.html. Its login form is rendered\n"
            "INSIDE an iframe (id=\"loginframe\"). After a successful login (username\n"
            "\"demo\", password \"demo\") the page shows a success message inside a custom\n"
            "element's shadow DOM: <result-box id=\"result\"> whose shadow root contains\n"
            "<span id=\"msg\">Welcome, demo</span>.\n\n"
            "Write a Browser-library Robot Framework test at tests/iframe_login.robot that:\n"
            "  1. Opens pages/app.html via a file:// URL\n"
            "  2. Fills the username and password fields (they live inside the iframe)\n"
            "  3. Clicks the submit button (also inside the iframe)\n"
            "  4. Waits for and reads the welcome message from the shadow DOM and confirms\n"
            "     it contains \"Welcome, demo\"\n\n"
            "Then run `robot tests/iframe_login.robot` and iterate until it passes green.\n"
            "Playwright browsers are already initialized."
        ),
        graders=[
            {"type": "file_exists", "path": "tests/iframe_login.robot"},
            {"type": "file_contains", "path": "tests/iframe_login.robot", "regex": r"Library\s+Browser"},
            {"type": "file_contains", "path": "tests/iframe_login.robot", "regex": r"(?i)welcome,\s*demo"},
            {"type": "robot_pass", "path": "tests/iframe_login.robot"},
            {"type": "no_deprecated_keywords", "path": "tests/iframe_login.robot"},
        ],
    ),
    Scenario(
        id="apinested",
        skill="requests",
        tier="hard",
        fixture="sut-apinested",
        timeout_s=1500,
        max_turns=45,
        primary_metric="all",
        prompt=(
            "This project ships data/orders.json (a list of orders; each has customer,\n"
            "status, and items[] with price, qty, and an OPTIONAL discount) and a Robot\n"
            "library at resources/OrdersServer.py that serves it over HTTP.\n\n"
            "Write a test tests/orders.robot that:\n"
            "  1. In Suite Setup, imports the OrdersServer library and calls\n"
            "     `Start Orders Server    ${CURDIR}/../data/orders.json` (it returns the\n"
            "     base URL; save it). Call `Stop Orders Server` in Suite Teardown.\n"
            "  2. Uses RequestsLibrary to GET /orders from that base URL and parses JSON.\n"
            "  3. Computes and ASSERTS (Should Be Equal As Numbers):\n"
            "     - total revenue of NON-cancelled orders, where a line's revenue is\n"
            "       price * qty * (1 - discount) and a missing discount means 0;\n"
            "     - total item quantity ordered by customer \"Alice\" (non-cancelled);\n"
            "     - the number of orders whose status is \"cancelled\".\n\n"
            "Then run `robot tests/orders.robot` and iterate until it passes green with\n"
            "the correct asserted values."
        ),
        graders=[
            {"type": "file_exists", "path": "tests/orders.robot"},
            {"type": "file_contains", "path": "tests/orders.robot", "regex": r"(?i)RequestsLibrary"},
            {"type": "file_contains", "path": "tests/orders.robot", "regex": r"\b114\b"},
            {"type": "robot_pass", "path": "tests/orders.robot"},
            {"type": "no_deprecated_keywords", "path": "tests/orders.robot"},
        ],
    ),
    Scenario(
        id="results_complex",
        skill="results",
        tier="hard",
        fixture="sut-results-complex",
        timeout_s=1200,
        max_turns=30,
        primary_metric="all",
        prompt=(
            "A Robot Framework run produced data/output.xml. Parse it and write a summary\n"
            "to reports/summary.md as a labelled bulleted list containing:\n"
            "  - the total number of tests\n"
            "  - the number PASSED, the number FAILED, and the number SKIPPED\n"
            "  - the names of every suite whose final status is FAIL\n\n"
            "The counts must come straight from the XML — note that a suite's teardown\n"
            "failure affects the status of its tests. Do not guess.\n"
            "Write your findings to reports/summary.md."
        ),
        graders=[
            {"type": "file_exists", "path": "reports/summary.md"},
            {"type": "file_contains", "path": "reports/summary.md", "regex": r"(?i)(total\D{0,20}\b8\b|\b8\b\D{0,20}total)"},
            {"type": "file_contains", "path": "reports/summary.md", "regex": r"(?i)(passed\D{0,20}\b4\b|\b4\b\D{0,20}passed)"},
            {"type": "file_contains", "path": "reports/summary.md", "regex": r"(?i)(failed\D{0,20}\b3\b|\b3\b\D{0,20}failed)"},
            {"type": "file_contains", "path": "reports/summary.md", "regex": r"(?i)(skipped\D{0,20}\b1\b|\b1\b\D{0,20}skipped)"},
            {"type": "file_contains", "path": "reports/summary.md", "regex": r"Checkout"},
            {"type": "file_contains", "path": "reports/summary.md", "regex": r"Regression"},
        ],
    ),
    Scenario(
        id="browser_dynamic",
        skill="browser",
        tier="hard",
        fixture="sut-dynamic",
        timeout_s=1200,
        max_turns=40,
        primary_metric="all",
        prompt=(
            "This project has a page at pages/profile.html. It has a button\n"
            "(id=\"load\"). Clicking it asynchronously (after a short delay) injects a\n"
            "profile card: a <div id=\"profile\"> that carries the user id in a\n"
            "**data-uid attribute** and contains <span id=\"name\">Ada Lovelace</span>.\n\n"
            "Write a Browser-library Robot Framework test at tests/profile.robot that:\n"
            "  1. Opens pages/profile.html via a file:// URL\n"
            "  2. Clicks the load button\n"
            "  3. Waits for the profile card to appear\n"
            "  4. Asserts the name text contains \"Ada Lovelace\"\n"
            "  5. Reads the card's data-uid ATTRIBUTE and asserts it equals \"u-42\"\n\n"
            "Then run `robot tests/profile.robot` and iterate until it passes green."
        ),
        graders=[
            {"type": "file_exists", "path": "tests/profile.robot"},
            {"type": "file_contains", "path": "tests/profile.robot", "regex": r"Library\s+Browser"},
            {"type": "file_contains", "path": "tests/profile.robot", "regex": r"(?i)ada\s+lovelace"},
            {"type": "file_contains", "path": "tests/profile.robot", "regex": r"u-42"},
            {"type": "robot_pass", "path": "tests/profile.robot"},
            {"type": "no_deprecated_keywords", "path": "tests/profile.robot"},
        ],
    ),
]

# --------------------------------------------------------------------------- #
# Round 2: LIVE scenarios (exploratory authoring + debugging an existing failing suite).
# Prompts state business goals only (no locators). Fixtures: ../fixtures_live/<fixture>/.
# --------------------------------------------------------------------------- #
_DATE_CALC_RE = r"(?i)(Get Current Date|Add Time To Date|\bdatetime\b|timedelta|relativedelta|new Date\()"
# failure-hiding constructs (checked on non-comment text of every *.robot / *.resource)
FORBIDDEN_EXPLORE = [
    r"(?i)\bPass Execution\b",
    r"(?i)(^|\s{2,}|\t)Skip( If)?(\s{2,}|\t|$)",
    r"(?i)robot:(skip|exclude|skip-on-failure)",
    r"(?i)--(skiponfailure|exitonfailure|noncritical)",
]
FORBIDDEN_DEBUG = FORBIDDEN_EXPLORE + [
    r"(?i)Run Keyword And Ignore Error",
    r"(?i)Run Keyword And Return Status",
    r"(?i)Run Keyword And Expect Error",
    r"(?i)Run Keyword And Warn On Failure",
    r"(?im)^\s+(TRY|EXCEPT)(\s|$)",
    r"(?i)Set Tags.*robot:",
]
_LIVE_RULES = (
    "Rules: keep all {n} test cases (do not delete, rename, skip or tag-exclude tests); do not remove,\n"
    "weaken or comment out assertions and do not change expected values; do not hide failures (no\n"
    "Run Keyword And Ignore Error / Run Keyword And Return Status / TRY-EXCEPT / Pass Execution / Skip).\n"
    "Keep using the Browser library. The suite runs nightly, so the fixes must make it pass reliably,\n"
    "also on future days.\n\n"
)
DEMOSHOP_TESTS = ["Demo Account Can Sign In", "Search Finds Standing Desk",
                  "Speaker Can Be Added From Search Results", "Cart Badge Counts Every Added Item",
                  "Checkout Adds Tax And Confirms Order"]
TRUCK_TESTS = ["Product Data Is Accepted", "Truck Price Table Is Calculated", "Truck Quote Can Be Sent"]

# Round 2b (journey tightening): one explicit sentence per kind, inserted before the "run robot" line.
JOURNEY_EXPLORE = (
    "The test must complete the whole user journey through the site's UI up to the final confirmation (start on\n"
    "the home page; no direct URLs to later pages), fill every field for which data is given above (all required\n"
    "fields included) with exactly that data, wait until the final confirmation/quote is actually shown and assert\n"
    "it by reading it from the page.\n"
)
JOURNEY_DEBUG = (
    "The tests must still complete their whole user journey through the site's UI up to the final confirmation\n"
    "(no new direct URLs to later pages), fill every required field with the suite's data, wait until the final\n"
    "confirmation/quote is actually shown and assert it by reading it from the page.\n\n"
)

# Journey-evidence specs (graded from the robot_pass run's output.xml by journey_evidence.py, robot run with
# --loglevel TRACE). confirm/values: regexes that must be READ FROM THE PAGE by a passing Browser keyword;
# min_inputs: distinct selectors driven by Browser input keywords (~75-80% of the reference's count);
# data: tokens (alternatives) that must appear in the values entered (default scope "typed" = entered
# values only; "all" also matches selectors, for radio/checkbox choices); allowed_urls: the only URLs a
# New Page / Go To may open (deep links to later pages / success pages are shortcuts).
_TRICENTIS_HOME = r"^https?://sampleapp\.tricentis\.com/?(101/?)?(index\.php)?$"
_CARCONFIG_HOME = r"^https?://carconfig\.makrocode\.de/?$"
_DEMOSHOP_HOME = r"^https?://demoshop\.makrocode\.de/?(\?space=[^&#/]+)?$"
_PWD = "<<fillsecret>>"          # Fill Secret / Type Secret hide the value -> any secret keyword satisfies a password
JOURNEY_SPECS: dict[str, dict] = {
    "tricentis_quote": {
        "confirm": [r"Sending e-mail success!"],
        "values": [r"(?<![\d.,])509\.00(?!\d)"],
        "min_inputs": 28,                       # reference: 36 (all 4 tabs + price + send quote)
        "data": [["bmw"], ["110"], ["06/15/2020"], {"any": ["5"], "exact": True}, ["petrol"], ["30000"],
                 ["rf2026"], ["12000"], ["ada"], ["lovelace"], ["12/10/1985"], ["main street 1"], ["germany"],
                 ["10115"], ["berlin"], ["employee"], ["7000000", "7.000.000"], ["bonus 1"], ["no coverage"],
                 {"any": ["yes"], "exact": True}, ["ada@example.com"], ["0301234567"], ["adal"],
                 ["secret123", _PWD],
                 {"any": ["female"], "scope": "all"}, {"any": ["skydiving"], "scope": "all"},
                 {"any": ["euro protection", "europrotection"], "scope": "all"},
                 {"any": ["platinum"], "scope": "all"}],
        "allowed_urls": [_TRICENTIS_HOME],
    },
    "carconfig_order": {
        "confirm": [r"Bestellung erfolgreich!", r"CO-\d+"],
        "values": [r"82\.400,00"],
        "min_inputs": 14,                       # reference: 17 (car, 6 options, buy, 7 fields, payment, order)
        "data": [["erika"], ["musterfrau"], ["erika@example.com"], ["+49 30 1234567"],
                 ["hauptstraße 5", "hauptstrasse 5"], ["10115"], ["berlin"],
                 {"any": ["überweisung", "ueberweisung", "bank transfer"], "scope": "all"}],
        "allowed_urls": [_CARCONFIG_HOME],
    },
    "demoshop_order": {
        "confirm": [r"Order ORD-[0-9A-Z]+ confirmed", r"confirmation email to morgan\.lee@example\.com"],
        "values": [r"\$857\.00", r"\$916\.99"],
        "min_inputs": 12,                       # reference: 16 (sign-in 4, search+add 5, cart, checkout 6)
        "data": [["jamie@flowlinesupply.com", "alex.productlead@example.com"], ["demo123", "flowline", _PWD],
                 ["horizon", "display"], ["cascade", "bottle"], ["morgan.lee@example.com"], ["morgan lee"],
                 ["42 harbor lane"], ["portland"], ["97201"], {"any": ["8"], "exact": True},
                 ["leave at the front desk"]],
        "allowed_urls": [_DEMOSHOP_HOME],
    },
    "demoshop_debug": {
        "confirm": [r"Order ORD-\w+ confirmed"],
        "values": [r"\$517\.00", r"\$553\.19"],
        "min_inputs": 8,                        # reference: 10
        "data": [["jamie@flowlinesupply.com"], ["demo123", _PWD], ["desk"], ["speaker"]],
        # the existing suite deep-links product pages and the cart; anything else (e.g. /checkout) is new
        "allowed_urls": [_DEMOSHOP_HOME,
                         r"^https?://demoshop\.makrocode\.de/(products/\d+|cart)/?(\?space=[^&#/]+)?$"],
    },
    "tricentis_debug": {
        "confirm": [r"Sending e-mail success!"],
        "values": [r"1,784\.00", r"3,501\.00"],
        "min_inputs": 28,                       # reference: 36
        "data": [["volvo"], ["250"], ["03/01/2019"], ["diesel"], ["800"], ["7500"], ["85000"], ["trk-778"],
                 ["60000"], ["grace"], ["hopper"], ["12/09/1976"], ["harbour road 7"], ["netherlands"], ["1011"],
                 ["amsterdam"], ["selfemployed"], ["10000000", "10.000.000"], ["full coverage"],
                 ["grace@example.com"], ["0201234567"], ["ghopper"], ["cobol1959", _PWD],
                 {"any": ["female"], "scope": "all"}, {"any": ["other"], "scope": "all"},
                 {"any": ["legaldefense", "legal defense"], "scope": "all"}, {"any": ["gold"], "scope": "all"}],
        "allowed_urls": [_TRICENTIS_HOME],
    },
}
JOURNEY_PARTS = [("confirm", "journey: confirmation read from page"),
                 ("values", "journey: value read from page"),
                 ("inputs", "journey: form fields driven"),
                 ("nav", "journey: no shortcut (deep link/hard-coded)")]


def _journey(sid: str) -> list[dict]:
    return [{"type": "journey", "part": part, "label": label, "spec": JOURNEY_SPECS[sid]}
            for part, label in JOURNEY_PARTS]

LIVE_SCENARIOS: list[Scenario] = [
    Scenario(
        id="tricentis_quote", skill="browser", tier="live", kind="explore", live=True, browser=True,
        fixture="sut-tricentis-quote", timeout_s=1800, max_turns=50, primary_metric="all",
        prompt=(
            "Write a Browser-library Robot Framework test at tests/auto_quote.robot that requests an\n"
            "Automobile insurance quote end to end on the LIVE Tricentis Vehicle Insurance sample app\n"
            "(http://sampleapp.tricentis.com/ - start on that home page). You do not know its page\n"
            "structure yet: explore the live site to find working locators.\n\n"
            "Use this data:\n"
            "  Vehicle:  make BMW, engine performance 110 kW, date of manufacture 06/15/2020, 5 seats,\n"
            "            fuel Petrol, list price 30000, license plate RF2026, annual mileage 12000\n"
            "  Insurant: Ada Lovelace, born 12/10/1985, female, Main Street 1, 10115 Berlin, Germany,\n"
            "            occupation Employee, hobby Skydiving\n"
            "  Product:  insurance start date = the day two months from today (compute it when the test\n"
            "            runs; the app rejects start dates less than one month ahead), insurance sum\n"
            "            7.000.000,00, merit rating Bonus 1, damage insurance No Coverage, optional\n"
            "            product Euro Protection, courtesy car Yes\n"
            "  Price:    choose Platinum - the test must assert that the Platinum price per year is 509.00\n"
            "  Quote:    e-mail ada@example.com, phone 0301234567, username adal, password Secret123\n"
            "            (confirm it), then send the quote\n\n"
            "The test must finally assert that the confirmation \"Sending e-mail success!\" is shown.\n"
            + JOURNEY_EXPLORE +
            "Then run `robot tests/auto_quote.robot` and iterate until it passes green.\n"
            "Playwright browsers are already initialized (use headless Chromium)."
        ),
        graders=[
            {"type": "file_exists", "path": "tests/auto_quote.robot"},
            {"type": "file_contains", "path": "tests/auto_quote.robot", "regex": r"Library\s+Browser"},
            {"type": "file_contains", "path": "tests/auto_quote.robot", "regex": r"(?i)sending e-mail success"},
            {"type": "file_contains", "path": "tests/auto_quote.robot", "regex": r"\b509(\.00)?\b"},
            {"type": "file_contains", "path": "tests/auto_quote.robot", "regex": _DATE_CALC_RE,
             "label": "start date computed at run time"},
            {"type": "files_not_contain", "suite": "tests/auto_quote.robot", "patterns": FORBIDDEN_EXPLORE},
            {"type": "robot_pass", "path": "tests/auto_quote.robot", "retry": 1, "min_tests": 1,
             "timeout_s": 300, "loglevel": "TRACE"},
            *_journey("tricentis_quote"),
            {"type": "no_deprecated_keywords", "path": "tests/auto_quote.robot"},
        ],
    ),
    Scenario(
        id="carconfig_order", skill="browser", tier="live", kind="explore", live=True, browser=True,
        fixture="sut-carconfig-order", timeout_s=1800, max_turns=50, primary_metric="all",
        prompt=(
            "Write a Browser-library Robot Framework test at tests/x5_order.robot for the LIVE German car\n"
            "configurator https://carconfig.makrocode.de/ (start on that home page). You do not know its\n"
            "page structure yet: explore the live site to find working locators.\n\n"
            "The test must:\n"
            "  1. open the configurator for the \"Luxury X5 SUV\"\n"
            "  2. configure it with exactly these options (switch away from pre-selected defaults where an\n"
            "     option group allows only one choice): Sportmotor 3.0L V6, Perleffekt-Lackierung,\n"
            "     20\" Premium Felgen, Leder-Ausstattung, Fahrassistenz-Paket Plus, Adaptive LED-Scheinwerfer\n"
            "  3. assert that the configurator's total price (Gesamtpreis) is 82.400,00 €\n"
            "  4. buy it (\"Jetzt kaufen\"), enter the customer data Erika Musterfrau, erika@example.com,\n"
            "     +49 30 1234567, Hauptstraße 5, 10115 Berlin, choose payment by bank transfer\n"
            "     (Banküberweisung) and place the order\n"
            "  5. assert that the success page (\"Bestellung erfolgreich!\") shows an order number and the\n"
            "     total 82.400,00 €\n\n"
            + JOURNEY_EXPLORE +
            "Then run `robot tests/x5_order.robot` and iterate until it passes green.\n"
            "Playwright browsers are already initialized (use headless Chromium)."
        ),
        graders=[
            {"type": "file_exists", "path": "tests/x5_order.robot"},
            {"type": "file_contains", "path": "tests/x5_order.robot", "regex": r"Library\s+Browser"},
            {"type": "file_contains", "path": "tests/x5_order.robot", "regex": r"82\.400,00"},
            {"type": "file_contains", "path": "tests/x5_order.robot", "regex": r"(?i)Bestellung erfolgreich"},
            {"type": "files_not_contain", "suite": "tests/x5_order.robot", "patterns": FORBIDDEN_EXPLORE},
            {"type": "robot_pass", "path": "tests/x5_order.robot", "retry": 1, "min_tests": 1,
             "timeout_s": 300, "loglevel": "TRACE"},
            *_journey("carconfig_order"),
            {"type": "no_deprecated_keywords", "path": "tests/x5_order.robot"},
        ],
    ),
    Scenario(
        id="demoshop_order", skill="browser", tier="live", kind="explore", live=True, browser=True,
        fixture="sut-demoshop-order", timeout_s=1800, max_turns=50, primary_metric="all",
        template={"__AB_SPACE__": "ab-{cell}"},
        prompt=(
            "Write a Browser-library Robot Framework test at tests/shop_order.robot that places a complete order in\n"
            "the LIVE Flowline Supply demo shop. Start on its home page\n"
            "https://demoshop.makrocode.de/?space=__AB_SPACE__ (keep this ?space= parameter on the start URL: it\n"
            "gives your test its own isolated shop data). You do not know the shop's page structure yet: explore the\n"
            "live site to find working locators.\n\n"
            "The test must:\n"
            "  1. sign in with the demo account that the shop's sign-in dialog suggests (the first one shown there)\n"
            "  2. use the shop's product search to find the \"Horizon Portable Display\" and add 2 of it to the cart,\n"
            "     then search for the \"Cascade Water Bottle\" and add 1 of it\n"
            "  3. open the cart and assert that it contains 2 x Horizon Portable Display and 1 x Cascade Water\n"
            "     Bottle, that the cart badge shows 3 items and that the cart total is $857.00\n"
            "  4. proceed to checkout and enter this data (replace anything that is prefilled): e-mail\n"
            "     morgan.lee@example.com, full name Morgan Lee, address 42 Harbor Lane, Portland, OR 97201,\n"
            "     team size 8, special instructions Leave at the front desk\n"
            "  5. assert the order summary: subtotal $857.00, tax $59.99, total $916.99\n"
            "  6. place the order and assert that the confirmation shows the order number (ORD-...) and says that\n"
            "     the confirmation e-mail was sent to morgan.lee@example.com\n\n"
            + JOURNEY_EXPLORE +
            "Then run `robot tests/shop_order.robot` and iterate until it passes green.\n"
            "Playwright browsers are already initialized (use headless Chromium)."
        ),
        graders=[
            {"type": "file_exists", "path": "tests/shop_order.robot"},
            {"type": "file_contains", "path": "tests/shop_order.robot", "regex": r"Library\s+Browser"},
            {"type": "file_contains", "path": "tests/shop_order.robot", "regex": r"\bab-[0-9a-f]{10}\b",
             "label": "own ?space= kept"},
            {"type": "file_contains", "path": "tests/shop_order.robot", "regex": r"\$?916\.99"},
            {"type": "file_contains", "path": "tests/shop_order.robot", "regex": r"ORD-"},
            {"type": "files_not_contain", "suite": "tests/shop_order.robot", "patterns": FORBIDDEN_EXPLORE},
            {"type": "robot_pass", "path": "tests/shop_order.robot", "retry": 1, "min_tests": 1,
             "timeout_s": 300, "loglevel": "TRACE"},
            *_journey("demoshop_order"),
            {"type": "no_deprecated_keywords", "path": "tests/shop_order.robot"},
        ],
    ),
    Scenario(
        id="demoshop_debug", skill="browser", tier="live", kind="debug", live=True, browser=True,
        fixture="sut-demoshop-debug", timeout_s=1800, max_turns=50, primary_metric="all",
        template={"__AB_SPACE__": "ab-{cell}"},
        prompt=(
            "This project contains a Robot Framework regression suite for the LIVE Flowline Supply demo\n"
            "shop (https://demoshop.makrocode.de/): tests/shop.robot with its keywords in\n"
            "resources/shop.resource (Browser library). It used to pass, but now several tests fail.\n\n"
            "The business expectations in the suite are correct (demo account, search results, cart badge\n"
            "counts, cart total, subtotal/tax/total, order confirmation). The failures are caused by\n"
            "defects in the test code. Find and fix them so that `robot tests/shop.robot` passes.\n\n"
            + _LIVE_RULES.format(n=len(DEMOSHOP_TESTS)) + JOURNEY_DEBUG +
            "Run `robot tests/shop.robot` and iterate until it passes green.\n"
            "Playwright browsers are already initialized."
        ),
        graders=[
            {"type": "file_exists", "path": "tests/shop.robot"},
            {"type": "test_names", "path": "tests/shop.robot", "names": DEMOSHOP_TESTS},
            {"type": "files_contain", "suite": "tests/shop.robot", "regex": r"Library\s+Browser"},
            {"type": "files_contain", "suite": "tests/shop.robot", "regex": r"\$517\.00"},
            {"type": "files_contain", "suite": "tests/shop.robot", "regex": r"\$36\.19"},
            {"type": "files_contain", "suite": "tests/shop.robot", "regex": r"\$553\.19"},
            {"type": "files_contain", "suite": "tests/shop.robot", "regex": r"ORD-"},
            {"type": "files_contain", "suite": "tests/shop.robot", "regex": r"\bJamie\b"},
            {"type": "files_contain", "suite": "tests/shop.robot", "regex": r"Atlas Standing Desk"},
            {"type": "files_contain", "suite": "tests/shop.robot",
             "regex": r"(?i)(Cart Badge Should Show|cart-count)\W.*\b3\b", "label": "cart badge == 3 kept"},
            {"type": "files_not_contain", "suite": "tests/shop.robot", "patterns": FORBIDDEN_DEBUG},
            {"type": "robot_pass", "path": "tests/shop.robot", "retry": 1, "exact_tests": len(DEMOSHOP_TESTS),
             "timeout_s": 300, "loglevel": "TRACE"},
            *_journey("demoshop_debug"),
            {"type": "no_deprecated_keywords", "suite": "tests/shop.robot"},
        ],
    ),
    Scenario(
        id="tricentis_debug", skill="browser", tier="live", kind="debug", live=True, browser=True,
        fixture="sut-tricentis-debug", timeout_s=1800, max_turns=50, primary_metric="all",
        prompt=(
            "This project contains a Robot Framework regression suite for the LIVE Tricentis Vehicle\n"
            "Insurance sample app (http://sampleapp.tricentis.com/): tests/truck_quote.robot with its\n"
            "keywords in resources/truck.resource (Browser library). It covers truck insurance quotes and\n"
            "used to pass, but now all of its tests fail.\n\n"
            "The business expectations in the suite are correct (the quote data, the expected yearly\n"
            "prices, the success message). The failures are caused by defects in the test code. Find and\n"
            "fix them so that `robot tests/truck_quote.robot` passes.\n\n"
            + _LIVE_RULES.format(n=len(TRUCK_TESTS)) + JOURNEY_DEBUG +
            "Run `robot tests/truck_quote.robot` and iterate until it passes green.\n"
            "Playwright browsers are already initialized."
        ),
        graders=[
            {"type": "file_exists", "path": "tests/truck_quote.robot"},
            {"type": "test_names", "path": "tests/truck_quote.robot", "names": TRUCK_TESTS},
            {"type": "files_contain", "suite": "tests/truck_quote.robot", "regex": r"Library\s+Browser"},
            {"type": "files_contain", "suite": "tests/truck_quote.robot", "regex": r"1,784\.00"},
            {"type": "files_contain", "suite": "tests/truck_quote.robot", "regex": r"3,501\.00"},
            {"type": "files_contain", "suite": "tests/truck_quote.robot", "regex": r"Sending e-mail success!"},
            {"type": "files_contain", "suite": "tests/truck_quote.robot",
             "regex": r"enterproductdata[^\n]*==\s+0\s*$", "label": "product counter == 0 kept"},
            {"type": "files_contain", "suite": "tests/truck_quote.robot", "regex": _DATE_CALC_RE,
             "label": "start date computed at run time"},
            {"type": "files_not_contain", "suite": "tests/truck_quote.robot", "patterns": FORBIDDEN_DEBUG},
            {"type": "robot_pass", "path": "tests/truck_quote.robot", "retry": 1, "exact_tests": len(TRUCK_TESTS),
             "timeout_s": 300, "loglevel": "TRACE"},
            *_journey("tricentis_debug"),
            {"type": "no_deprecated_keywords", "suite": "tests/truck_quote.robot"},
        ],
    ),
]

SCEN_BY_ID = {s.id: s for s in SCENARIOS + LIVE_SCENARIOS}
SCENARIO_ALIASES = {
    "round1": [s.id for s in SCENARIOS],
    "live": [s.id for s in LIVE_SCENARIOS],
    "explore": [s.id for s in LIVE_SCENARIOS if s.kind == "explore"],
    "debug": [s.id for s in LIVE_SCENARIOS if s.kind == "debug"],
}
BROWSER_FIXTURES = {"sut-iframe", "sut-dynamic"}
# empty dirs the fixtures ship with (git does not track empty dirs)
FIXTURE_MKDIRS = {"sut-iframe": ["tests"], "sut-apinested": ["tests"], "sut-dynamic": ["tests"],
                  "sut-tricentis-quote": ["tests"], "sut-carconfig-order": ["tests"],
                  "sut-demoshop-order": ["tests"]}


def expand_scenarios(spec: str) -> list[str]:
    """'live' / 'explore' / 'debug' / 'round1' aliases and/or comma-separated scenario ids."""
    out: list[str] = []
    for tok in [t.strip() for t in spec.split(",") if t.strip()]:
        for sid in SCENARIO_ALIASES.get(tok, [tok]):
            if sid not in out:
                out.append(sid)
    return out


def is_browser(scen: Scenario) -> bool:
    return scen.browser or scen.fixture in BROWSER_FIXTURES


# --------------------------------------------------------------------------- #
# Process utilities + Reaper (kills ONLY this harness' cell processes)
# --------------------------------------------------------------------------- #
def _proc_start(pid: int) -> int | None:
    try:
        st = Path(f"/proc/{pid}/stat").read_text()
        return int(st[st.rindex(")") + 2:].split()[19])
    except Exception:
        return None


def _children_map() -> dict[int, list[int]]:
    kids: dict[int, list[int]] = {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            st = (d / "stat").read_text()
            ppid = int(st[st.rindex(")") + 2:].split()[1])
            kids.setdefault(ppid, []).append(int(d.name))
        except Exception:
            continue
    return kids


def _descendants(root: int, kids: dict[int, list[int]] | None = None) -> list[int]:
    kids = kids if kids is not None else _children_map()
    out, stack = [], [root]
    while stack:
        p = stack.pop()
        for c in kids.get(p, []):
            out.append(c)
            stack.append(c)
    return out


def _self_and_ancestors() -> set[int]:
    pids, pid = set(), os.getpid()
    while pid > 1:
        pids.add(pid)
        try:
            st = Path(f"/proc/{pid}/stat").read_text()
            pid = int(st[st.rindex(")") + 2:].split()[1])
        except Exception:
            break
    return pids


def _kill(pid: int, start: int | None, sig=signal.SIGKILL) -> bool:
    """Kill pid only if it is still the same process (start time matches)."""
    if start is not None and _proc_start(pid) != start:
        return False
    try:
        os.kill(pid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


class Reaper(threading.Thread):
    """Background sweeper: kills processes that map to a cell under WORK_ROOT that is NOT active.

    A process maps to a cell if its cwd, any cmdline arg, or its AB_EVAL_CELL env marker points
    inside WORK_ROOT/<agent>/<cell>. Nothing outside WORK_ROOT is ever touched.
    """

    def __init__(self, work_root: Path, interval: float = 5.0):
        super().__init__(daemon=True, name="reaper")
        self.root = str(work_root.resolve())
        self.interval = interval
        self.active: set[str] = set()
        self.lock = threading.Lock()
        self.stop_ev = threading.Event()
        self.killed: list[dict] = []
        self.protect = _self_and_ancestors()
        self.log_path = work_root / "reaper.log"

    def register(self, cell: Path) -> None:
        with self.lock:
            self.active.add(str(cell))

    def unregister(self, cell: Path) -> None:
        with self.lock:
            self.active.discard(str(cell))

    def _cell_from_path(self, s: str) -> str | None:
        i = s.find(self.root + "/")
        if i < 0:
            return None
        rel = s[i + len(self.root) + 1:]
        parts = re.split(r"[/\s'\"]", rel)
        if len(parts) < 2 or not parts[0] or not parts[1]:
            return None
        return f"{self.root}/{parts[0]}/{parts[1]}"

    def cell_of(self, pid: int) -> str | None:
        d = Path(f"/proc/{pid}")
        try:
            env = (d / "environ").read_bytes().split(b"\0")
            for kv in env:
                if kv.startswith(CELL_ENV_MARKER.encode() + b"="):
                    c = self._cell_from_path(kv.decode(errors="replace").split("=", 1)[1] + "/")
                    if c:
                        return c
        except Exception:
            pass
        try:
            c = self._cell_from_path(os.readlink(d / "cwd") + "/")
            if c:
                return c
        except Exception:
            pass
        try:
            cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            return self._cell_from_path(cmd)
        except Exception:
            return None

    def sweep(self, only_cell: Path | None = None, force: bool = False, dry_run: bool = False) -> list[dict]:
        """Kill processes of inactive cells (or every process of `only_cell` when force=True)."""
        killed = []
        with self.lock:
            active = set(self.active)
        target = str(only_cell) if only_cell else None
        for d in Path("/proc").iterdir():
            if not d.name.isdigit():
                continue
            pid = int(d.name)
            if pid in self.protect:
                continue
            cell = self.cell_of(pid)
            if not cell:
                continue
            if target and cell != target:
                continue
            if cell in active and not force:
                continue
            start = _proc_start(pid)
            try:
                cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")[:160]
            except Exception:
                cmd = "?"
            if dry_run:
                killed.append({"pid": pid, "cell": cell, "cmd": cmd, "dry_run": True})
            elif _kill(pid, start):
                killed.append({"pid": pid, "cell": cell, "cmd": cmd, "t": _now()})
        if killed and not dry_run:
            self.killed.extend(killed)
            try:
                with self.log_path.open("a", encoding="utf-8") as f:
                    for k in killed:
                        f.write(json.dumps(k) + "\n")
            except Exception:
                pass
        return killed

    def run(self) -> None:
        while not self.stop_ev.wait(self.interval):
            try:
                self.sweep()
            except Exception:
                pass

    def stop(self) -> None:
        self.stop_ev.set()


class TreeTracker(threading.Thread):
    """Records every descendant (pid, starttime) of the agent process while it runs, so that
    orphans re-parented to init (Playwright node/chromium) can still be killed afterwards."""

    def __init__(self, root_pid: int, interval: float = 1.0):
        super().__init__(daemon=True, name=f"tree-{root_pid}")
        self.root = root_pid
        self.interval = interval
        self.seen: dict[int, int | None] = {}
        self.stop_ev = threading.Event()

    def run(self) -> None:
        while not self.stop_ev.is_set():
            try:
                for p in _descendants(self.root):
                    if p not in self.seen:
                        self.seen[p] = _proc_start(p)
            except Exception:
                pass
            self.stop_ev.wait(self.interval)

    def kill_survivors(self) -> int:
        n = 0
        for pid, start in list(self.seen.items()):
            if _kill(pid, start):
                n += 1
        return n


def _killpg(pgid: int) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(3 if sig == signal.SIGTERM else 0)


def _run_bounded(cmd: list[str], cwd: Path, env: dict, timeout_s: int) -> tuple[int | None, bool, str]:
    """Run in its own session; on timeout kill the whole process group. Returns (rc, timed_out, out)."""
    p = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True, text=True)
    try:
        out, _ = p.communicate(timeout=timeout_s)
        rc, to = p.returncode, False
    except subprocess.TimeoutExpired:
        _killpg(p.pid)
        out, _ = p.communicate()
        rc, to = None, True
    try:
        os.killpg(p.pid, signal.SIGKILL)          # leftovers that stayed in the group
    except (ProcessLookupError, PermissionError):
        pass
    return rc, to, (out or "")[-3000:]


# --------------------------------------------------------------------------- #
# Deterministic graders (semantics identical to eval#3/#4)
# --------------------------------------------------------------------------- #
_DEPRECATED = (
    re.compile(r"\bRun Keyword If\b", re.IGNORECASE),
    re.compile(r"\bRun Keyword Unless\b", re.IGNORECASE),
    re.compile(r"\bReturn From Keyword\b", re.IGNORECASE),
)


def _grade_env(cell_dir: Path | None = None) -> dict:
    env = _clean_env()
    env["PATH"] = f"{VENV_BIN}:{env.get('PATH', '')}"
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(PW_BROWSERS)
    if cell_dir is not None:
        env[CELL_ENV_MARKER] = str(cell_dir)
    return env


def _grade_one(check: dict, workspace: Path, grader_out: Path, cell_dir: Path | None) -> dict:
    ctype = check["type"]
    path = check.get("path")
    target = workspace / path if path else workspace
    ok, detail = False, ""
    extra: dict = {}
    try:
        if ctype == "file_exists":
            ok, detail = target.is_file(), str(target)
        elif ctype == "file_contains":
            if not target.is_file():
                ok, detail = False, f"missing {target}"
            else:
                content = target.read_text(encoding="utf-8", errors="replace")
                ok = re.search(check["regex"], content, re.MULTILINE) is not None
                detail = f"regex={check['regex']!r}"
        elif ctype == "no_deprecated_keywords" and "glob" not in check and "suite" not in check:
            if not target.is_file():
                ok, detail = False, f"missing {target}"
            else:
                content = target.read_text(encoding="utf-8", errors="replace")
                hits = [p.pattern for p in _DEPRECATED if p.search(content)]
                ok, detail = not hits, f"deprecated={hits}"
        elif ctype == "robot_pass" and not any(k in check for k in ("retry", "min_tests", "exact_tests")):
            ok, detail = _robot_pass(target, workspace, grader_out, check.get("timeout_s", 180), cell_dir)
        elif ctype == "robot_pass":                                   # round 2: live, retry, stats
            ok, detail, extra = _robot_pass_live(target, workspace, grader_out, check, cell_dir)
        elif ctype == "journey":                                      # journey evidence from output.xml
            ok, detail, extra = _journey_part(check, grader_out)
        elif ctype == "files_contain":                                # any matching file, non-comment text
            files = (_suite_files(workspace, workspace / check["suite"]) if "suite" in check
                     else _glob_files(workspace, check["glob"]))
            hit = next((os.path.relpath(f, workspace) for f in files
                        if re.search(check["regex"], _strip_rf_comments(f.read_text(encoding="utf-8",
                                                                                     errors="replace")),
                                     re.MULTILINE)), None)
            ok = hit is not None
            detail = f"{check.get('label') or 'regex=' + repr(check['regex'])} -> {hit or 'not found'}"
        elif ctype == "files_not_contain":                            # forbidden constructs
            hits = []
            files = (_suite_files(workspace, workspace / check["suite"]) if "suite" in check
                     else _glob_files(workspace, check["glob"]))
            for f in files:
                txt = _strip_rf_comments(f.read_text(encoding="utf-8", errors="replace"))
                hits += [f"{os.path.relpath(f, workspace)}:{p}" for p in check["patterns"]
                         if re.search(p, txt, re.MULTILINE)]
            ok, detail = not hits, f"forbidden={hits}"
        elif ctype == "test_names":                                   # anti-cheat: same tests, same count
            if not target.is_file():
                ok, detail = False, f"missing {target}"
            else:
                names = _robot_test_names(target.read_text(encoding="utf-8", errors="replace"))
                want = list(check["names"])
                ok = sorted(n.lower() for n in names) == sorted(n.lower() for n in want)
                detail = f"found {len(names)}/{len(want)}" + ("" if ok else f" names={names}")
        elif ctype == "no_deprecated_keywords" and ("glob" in check or "suite" in check):
            hits = []
            files = (_suite_files(workspace, workspace / check["suite"]) if "suite" in check
                     else _glob_files(workspace, check["glob"]))
            for f in files:
                content = f.read_text(encoding="utf-8", errors="replace")
                hits += [f"{os.path.relpath(f, workspace)}:{p.pattern}" for p in _DEPRECATED if p.search(content)]
            ok, detail = not hits, f"deprecated={hits}"
        else:
            ok, detail = False, f"unknown check {ctype}"
    except Exception as exc:  # graders never crash the batch
        ok, detail = False, f"grader error: {exc}"
    v = {"type": ctype, "path": path, "passed": bool(ok), "detail": detail[:400]}
    if check.get("label"):
        v["label"] = check["label"]
    if check.get("part"):
        v["part"] = check["part"]
    if extra:
        v.update(extra)
    return v


_SKIP_DIRS = {"grader_out", "results", "output", ".git", "node_modules", "browser", ".venv", "__pycache__"}


def _glob_files(workspace: Path, globs) -> list[Path]:
    globs = [globs] if isinstance(globs, str) else list(globs)
    seen: dict[str, Path] = {}
    for g in globs:
        for f in workspace.glob(g):
            rel = f.relative_to(workspace)
            if f.is_file() and not (set(rel.parts[:-1]) & _SKIP_DIRS):
                seen[str(rel)] = f
    return [seen[k] for k in sorted(seen)]


def _suite_files(workspace: Path, suite: Path) -> list[Path]:
    """The suite file plus every resource file it imports (recursively; ${CURDIR} resolved).
    Anti-cheat: expected values must live in the files the graded run actually uses, not in a
    backup copy somewhere in the workspace."""
    out, todo = [], [suite]
    while todo:
        f = todo.pop()
        if not f.is_file() or f in out:
            continue
        out.append(f)
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"(?i)^Resource(?:\s{2,}|\t)+(\S.*?)\s*$", line)
            if m:
                ref = m.group(1).split("  ")[0].replace("${CURDIR}", str(f.parent))
                cand = Path(ref) if Path(ref).is_absolute() else (f.parent / ref)
                todo.append(cand.resolve())
    return out


def _strip_rf_comments(text: str) -> str:
    """Drop RF comment lines and trailing `    # ...` comments (cells starting with #)."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.append(re.sub(r"(\s{2,}|\t)#.*$", "", line))
    return "\n".join(out)


def _robot_test_names(text: str) -> list[str]:
    names, in_tc = [], False
    for line in text.splitlines():
        if line.startswith("*"):
            in_tc = re.match(r"\*+\s*(test cases?|tasks?)\b", line, re.I) is not None
            continue
        if in_tc and line.strip() and not line[0].isspace() and not line.startswith("#"):
            names.append(re.split(r"\s{2,}|\t|\s+\|\s+", line.strip())[0])
    return names


def _output_stats(xml: Path) -> dict | None:
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(xml).getroot()
        st = root.find("./statistics/total/stat")
        if st is None:
            return None
        return {k: int(st.get(k, 0)) for k in ("pass", "fail", "skip")}
    except Exception:
        return None


def _robot_pass_live(target: Path, workspace: Path, grader_out: Path, check: dict,
                     cell_dir: Path | None) -> tuple[bool, str, dict]:
    """Plain `robot <file>` against the live site; one automatic retry on failure.

    Pass = exit 0 AND no skipped tests AND (exact_tests | >= min_tests) tests. A pass that needs the
    retry is recorded as flaky=True. Returns (ok, detail, extra-verdict-fields)."""
    if not target.exists():
        return False, f"robot file missing: {target}", {"attempts": 0, "flaky": False, "first_pass": False}
    attempts, details, durations, stats_all = [], [], [], []
    for i in range(1 + int(check.get("retry", 0))):
        od = grader_out / f"attempt{i + 1}"
        od.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        ll = ["--loglevel", str(check["loglevel"])] if check.get("loglevel") else []
        rc, to, out = _run_bounded([str(VENV_BIN / "robot"), "--outputdir", str(od), *ll, str(target)],
                                   workspace, _grade_env(cell_dir), int(check.get("timeout_s", 300)))
        durations.append(round(time.monotonic() - t0, 1))
        # the journey-evidence graders read the output.xml of the passing (else the last) attempt
        (grader_out / ROBOT_PASS_MARKER).write_text(str(od / "output.xml"), encoding="utf-8")
        stats = _output_stats(od / "output.xml")
        stats_all.append(stats)
        total = sum(stats.values()) if stats else 0
        ok = (not to and rc == 0 and stats is not None and stats["skip"] == 0 and stats["fail"] == 0
              and (total == check["exact_tests"] if "exact_tests" in check else total >= check.get("min_tests", 1)))
        tail = " | ".join(l.strip() for l in out.splitlines()
                          if re.search(r"tests?, \d+ passed|\| FAIL \||Error", l))[-200:]
        details.append(f"#{i + 1} exit={rc}{' TIMEOUT' if to else ''} stats={stats} {tail}")
        attempts.append(ok)
        if ok:
            break
    passed = any(attempts)
    extra = {"attempts": len(attempts), "first_pass": attempts[0], "flaky": passed and not attempts[0],
             "durations_s": durations, "stats": stats_all}
    return passed, " || ".join(details)[-400:], extra


ROBOT_PASS_MARKER = "robot_pass_output.txt"
JOURNEY_SCRIPT = HERE / "journey_evidence.py"
_JOURNEY_CACHE: dict[tuple, dict] = {}
_JOURNEY_LOCK = threading.Lock()


def _journey_eval(xml: Path, spec: dict) -> dict:
    """Run journey_evidence.py (grading venv, robot.api) once per (output.xml, spec); cached."""
    key = (str(xml), xml.stat().st_mtime_ns, json.dumps(spec, sort_keys=True))
    with _JOURNEY_LOCK:
        if key in _JOURNEY_CACHE:
            return _JOURNEY_CACHE[key]
    spec_file = xml.parent / f"journey_spec_{abs(hash(key[2])) % 10 ** 8}.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    try:
        p = subprocess.run([str(VENV_BIN / "python"), str(JOURNEY_SCRIPT), str(xml), str(spec_file)],
                           capture_output=True, text=True, timeout=180, env=_grade_env())
        res = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else \
            {"error": f"no output (exit {p.returncode}): {p.stderr[-300:]}"}
    except Exception as exc:
        res = {"error": f"{type(exc).__name__}: {exc}"}
    with _JOURNEY_LOCK:
        _JOURNEY_CACHE[key] = res
    return res


def _journey_part(check: dict, grader_out: Path) -> tuple[bool, str, dict]:
    """One part (confirm | values | inputs | nav) of the journey evidence of the robot_pass run."""
    marker = grader_out / ROBOT_PASS_MARKER
    xml = Path(marker.read_text(encoding="utf-8").strip()) if marker.exists() else None
    if xml is None or not xml.is_file():
        return False, "no output.xml from the robot_pass run", {}
    res = _journey_eval(xml, check["spec"])
    if "error" in res:
        return False, f"journey grader error: {res['error']}", {}
    part = check["part"]
    r = res.get(part) or {}
    if part in ("confirm", "values"):
        detail = (f"missing={r.get('missing')}" if r.get("missing") else "read") + f" hits={r.get('hits')}"
    elif part == "inputs":
        detail = f"distinct={r.get('distinct')}/{r.get('min')} missing_data={r.get('missing_data')}"
    else:
        detail = (f"bad_urls={r.get('bad_urls')} js_nav={r.get('js_nav')} "
                  f"hardcoded={r.get('hardcoded_asserts')} urls={r.get('urls')}")
    if not res.get("trace"):
        detail += " (no TRACE args: unresolved)"
    return bool(r.get("ok")), detail, {"journey": {k: v for k, v in r.items() if k != "ok"}}


def _robot_pass(target: Path, workspace: Path, grader_out: Path, timeout_s: int,
                cell_dir: Path | None) -> tuple[bool, str]:
    if not target.exists():
        return False, f"robot file missing: {target}"
    grader_out.mkdir(parents=True, exist_ok=True)
    rc, to, out = _run_bounded([str(VENV_BIN / "robot"), "--outputdir", str(grader_out), str(target)],
                               workspace, _grade_env(cell_dir), timeout_s)
    if to:
        return False, "robot run timed out"
    tail = " | ".join(l.strip() for l in out.splitlines()
                      if re.search(r"tests?, \d+ passed|\| FAIL \||Error", l))[-250:]
    return rc == 0, f"exit={rc} {tail}"


def grade(scenario: Scenario, workspace: Path, grader_out: Path,
          cell_dir: Path | None = None) -> tuple[list[dict], bool]:
    verdicts = [_grade_one(c, workspace, grader_out, cell_dir) for c in scenario.graders]
    if scenario.primary_metric == "all":
        primary = all(v["passed"] for v in verdicts)
    else:
        primary = next((v["passed"] for v in verdicts if v["type"] == scenario.primary_metric), False)
    return verdicts, bool(primary)


# --------------------------------------------------------------------------- #
# skillpkg provisioning (built by another agent; stub until it exists)
# --------------------------------------------------------------------------- #
# extra transcript markers for the skillpkg arm (install() may add its own via "markers").
# NB: never use "skillpkg" itself - it is part of every skillpkg cell's workspace path.
DEFAULT_SKILLPKG_MARKERS: list[str] = []
SKILL_READ_RE = re.compile(r"SKILL\.md|skills/robotframework|\"skill\":\s*\"robotframework")
HOOK_LOG_NAME = "rfmcp_hook.jsonl"     # RFMCP_HOOK_LOG target (rfmcp edithook appends 1 line per firing)
# the helper CLI (`rfmcp`, package rfmcp-skill) - also used to flag contamination in non-skillpkg arms
HELPER_CLI_RE = re.compile(r"(?<![\w-])rfmcp(?![\w-])|rfmcp_skill|rfmcp-skill")


# hookpkg provisioning (skill + hooks, no CLI). Usage marker: the package name `rfharness` (the agent never needs
# to type it) and the hook state dir .rf/hook/ in the workspace (created only by the hooks).
HOOK_LOG_NAME_RFH = "rfh_hooks.jsonl"  # RFH_HOOK_LOG target (rfharness hook appends 1 line per firing)
HOOK_USE_RE = re.compile(r"rfharness")


def load_hookpkg_install():
    """Return hookpkg.install.install, or a stub raising NotImplementedError."""
    if str(AB) not in sys.path:
        sys.path.insert(0, str(AB))
    try:
        from hookpkg.install import install  # type: ignore
        return install
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"

        def _stub(agent, workspace, agent_home, venv_bin):
            raise NotImplementedError(f"hookpkg.install unavailable ({err})")
        _stub.unavailable = err  # type: ignore[attr-defined]
        return _stub


def load_hook_install(arm: str):
    """<arm>.install.install for a hook arm (hookpkg -> load_hookpkg_install, unchanged), stub when unavailable."""
    if arm == "hookpkg":
        return load_hookpkg_install()
    if str(AB) not in sys.path:
        sys.path.insert(0, str(AB))
    try:
        mod = importlib.import_module(f"{arm}.install")
        return mod.install
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"

        def _stub(agent, workspace, agent_home, venv_bin):
            raise NotImplementedError(f"{arm}.install unavailable ({err})")
        _stub.unavailable = err  # type: ignore[attr-defined]
        return _stub


def hookpkg2_usage(calls: list[dict], info: dict, hook_log: Path, ws: Path | None) -> dict:
    """hookpkg_usage() + the v2 hooks: docs files, page captures, timeout rechecks, REPL format rewrites/denials,
    loop hints, guard denials (install / pythonpath / big read / suite), format card, prompt context."""
    base = hookpkg_usage(calls, info, hook_log, ws)
    base["hook_dir"] = bool(ws is not None and (ws / ".rf" / "hook2").is_dir())
    m: Counter = Counter()
    verdicts: Counter = Counter()
    cap_ms: list = []
    try:
        lines = hook_log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        m["docs_kw_files"] += int(d.get("docs_kw") or 0)
        m["docs_lib_files"] += len(d.get("docs_lib") or [])
        m["captures"] += int(d.get("captures") or 0)
        cap_ms += [x for x in (d.get("capture_ms") or []) if isinstance(x, (int, float))]
        m["timeout_rechecks"] += int(d.get("rechecks") or 0)
        for v in d.get("recheck_verdicts") or []:
            verdicts[str(v)] += 1
        if d.get("repl"):
            m["repl_commands"] += 1
            if d.get("action") == "rewrite":
                m["format_rewrites"] += 1
            if d.get("action") == "deny":
                m["format_denials"] += 1
        m["loop_hints"] += int(d.get("loop_hint") or 0)
        if d.get("guard") and d.get("action") in ("deny", "rewrite"):
            m[f"guard_denials_{d['guard']}"] += 1
            m["guard_denials"] += 1
        m["card_shown"] += 1 if d.get("card") else 0
        m["prompt_context"] += 1 if d.get("prompt_ctx") else 0
        m["repl_failures"] += int(d.get("repl_fails") or 0)
        m["valve_allows"] += 1 if d.get("valve") else 0
    reads = [c.get("input") or "" for c in calls if c["kind"] in ("read", "shell", "other")]
    base.update({k: m.get(k, 0) for k in (
        "docs_kw_files", "docs_lib_files", "captures", "timeout_rechecks", "repl_commands", "format_rewrites",
        "format_denials", "loop_hints", "guard_denials", "guard_denials_install", "guard_denials_pythonpath",
        "guard_denials_bigread", "guard_denials_suite", "card_shown", "prompt_context", "repl_failures",
        "valve_allows")})
    base["docs_files"] = base["docs_kw_files"] + base["docs_lib_files"]
    base["recheck_verdicts"] = dict(verdicts)
    base["capture_ms_median"] = sorted(cap_ms)[len(cap_ms) // 2] if cap_ms else None
    base["kwdoc_reads"] = sum(1 for s in reads if ".rf/docs/kw" in s)
    base["latest_reads"] = sum(1 for s in reads if ".rf/state/latest" in s or ".rf/state/step-" in s)
    return base


def hookpkg3_usage(calls: list[dict], info: dict, hook_log: Path, ws: Path | None) -> dict:
    """hookpkg2_usage() + the v3 metrics: injected context chars per edit (success / failure outputs), captures and
    skipped captures, re-checks by verdict incl. skipped (quiet page), adaptive timeout changes, denials vs one-line
    warnings, race reproductions, keyword signatures vs on-demand doc files."""
    base = hookpkg2_usage(calls, info, hook_log, ws)
    base["hook_dir"] = bool(ws is not None and (ws / ".rf" / "hook3").is_dir())
    m: Counter = Counter()
    ctx_edit: list = []
    ctx_ok: list = []
    ctx_fail: list = []
    ctx_robot: list = []
    rc_s: list = []
    changes: list = []
    classes: Counter = Counter()
    try:
        lines = hook_log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        for fc in d.get("fail_classes") or []:
            classes[str(fc)] += 1
        ch = d.get("ctx_chars")
        if isinstance(ch, (int, float)) and d.get("event") == "post-tool":
            if d.get("files"):
                ctx_edit.append(ch)
                (ctx_fail if d.get("ctx_kind") == "fail" else ctx_ok).append(ch)
            elif d.get("robot"):
                ctx_robot.append(ch)
        m["capture_skipped"] += int(d.get("capture_skipped") or 0)
        m["capture_settles"] += int(d.get("capture_settles") or 0)
        m["rechecks_skipped"] += int(d.get("rechecks_skipped") or 0)
        rc_s += [x for x in (d.get("recheck_s") or []) if isinstance(x, (int, float))]
        changes += list(d.get("tmo_changes") or [])
        m["warnings"] += int(d.get("warnings") or 0)
        m["repro_race"] += 1 if d.get("repro_race") else 0
        m["kw_signatures"] += int(d.get("kw_signatures") or 0)
        m["docs_on_demand"] += len(d.get("docs_on_demand") or [])
        if d.get("event") == "pre-tool" and d.get("action") == "deny":
            m["denials_v3"] += 1
    mean = (lambda xs: round(sum(xs) / len(xs), 1) if xs else None)
    base.update({
        "ctx_chars_per_edit": mean(ctx_edit), "ctx_chars_edit_ok": mean(ctx_ok), "ctx_chars_edit_fail": mean(ctx_fail),
        "ctx_chars_robot": mean(ctx_robot), "ctx_chars_total": sum(ctx_edit) + sum(ctx_robot),
        "edits_with_output": len(ctx_edit),
        "capture_skipped": m["capture_skipped"], "capture_settles": m["capture_settles"],
        "rechecks_skipped": m["rechecks_skipped"], "recheck_s_total": round(sum(rc_s), 1),
        "tmo_changes": len(changes), "tmo_changes_detail": changes[:5],
        "warnings": m["warnings"], "repro_race": m["repro_race"], "kw_signatures": m["kw_signatures"],
        "docs_on_demand": m["docs_on_demand"], "fail_classes": dict(classes)})
    return base


def hookpkg31_usage(calls: list[dict], info: dict, hook_log: Path, ws: Path | None) -> dict:
    """hookpkg3_usage() + the v3.1 output profile of the session (hook log: profile / profile_src / model per event)."""
    base = hookpkg3_usage(calls, info, hook_log, ws)
    base["hook_dir"] = bool(ws is not None and (ws / ".rf" / "hook31").is_dir())
    profs: Counter = Counter()
    src = model = None
    try:
        lines = hook_log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("profile"):
            profs[str(d["profile"])] += 1
            src = d.get("profile_src") or src
            model = d.get("model") or model
    base["profile"] = profs.most_common(1)[0][0] if profs else None
    base["profile_counts"] = dict(profs)
    base["profile_src"] = src
    base["profile_model"] = model
    return base


def hookpkg32_usage(calls: list[dict], info: dict, hook_log: Path, ws: Path | None) -> dict:
    """hookpkg31_usage() for v3.2 (.rf/hook32) + read-streak nudges (hook log guard=readstreak)."""
    base = hookpkg31_usage(calls, info, hook_log, ws)
    base["hook_dir"] = bool(ws is not None and (ws / ".rf" / "hook32").is_dir())
    n = 0
    try:
        for line in hook_log.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                n += 1 if json.loads(line).get("guard") == "readstreak" else 0
            except Exception:
                continue
    except OSError:
        pass
    base["read_streak_nudges"] = n
    return base


HOOK_USAGE = {}   # arm -> per-session metrics function (filled below, after the functions are defined)


def hookpkg_usage(calls: list[dict], info: dict, hook_log: Path, ws: Path | None) -> dict:
    """Per-session hook metrics from the rfharness hook log + transcript reads of hook-maintained files."""
    ev: Counter = Counter()
    act: Counter = Counter()
    ran = nonpass = reproduced = running = delivered = 0
    lat: dict[str, list] = {}
    errors: list[str] = []
    try:
        lines = hook_log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        e = str(d.get("event"))
        ev[e] += 1
        act[f"{e}:{d.get('action')}"] += 1
        ran += int(d.get("ran_lines") or 0)
        nonpass += int(d.get("failed_lines") or 0)
        reproduced += 1 if d.get("reproduced") else 0
        running += 1 if d.get("still_running") else 0
        delivered += int(d.get("pending_delivered") or 0)
        if isinstance(d.get("ms"), (int, float)):
            lat.setdefault(e, []).append(d["ms"])
        if d.get("error"):
            errors.append(str(d["error"])[:200])
    reads = [c.get("input") or "" for c in calls if c["kind"] in ("read", "shell", "other")]
    return {"firings": sum(ev.values()), "firings_by_event": dict(ev), "actions": dict(act),
            "auto_executed_lines": ran, "auto_non_pass_lines": nonpass,
            "denials": act.get("pre-tool:deny", 0), "rewrites": act.get("pre-tool:rewrite", 0),
            "stop_blocks": act.get("stop:block", 0), "reproductions": reproduced,
            "still_running": running, "pending_delivered": delivered,
            "state_reads": sum(1 for s in reads if ".rf/state" in s), "docs_reads": sum(1 for s in reads if ".rf/docs" in s),
            "skill_read": any(c["kind"] == "skill" or SKILL_READ_RE.search(c.get("input") or "") for c in calls),
            "hook_events_transcript": info.get("hook_events"),
            "latency_ms_median": {k: sorted(v)[len(v) // 2] for k, v in lat.items()},
            "hook_dir": bool(ws is not None and (ws / ".rf" / "hook").is_dir()), "errors": errors[:3]}


HOOK_USAGE.update({"hookpkg": hookpkg_usage, "hookpkg2": hookpkg2_usage, "hookpkg3": hookpkg3_usage,
                   "hookpkg31": hookpkg31_usage, "hookpkg32": hookpkg32_usage})


def load_skillpkg_install():
    """Return skillpkg.install.install, or a stub raising NotImplementedError."""
    if str(AB) not in sys.path:
        sys.path.insert(0, str(AB))
    try:
        from skillpkg.install import install  # type: ignore
        return install
    except Exception as exc:  # ImportError or a half-built package
        err = f"{type(exc).__name__}: {exc}"

        def _stub(agent, workspace, agent_home, venv_bin):
            raise NotImplementedError(f"skillpkg.install unavailable ({err})")
        _stub.unavailable = err  # type: ignore[attr-defined]
        return _stub


# --------------------------------------------------------------------------- #
# Agent homes + configs
# --------------------------------------------------------------------------- #
def _clean_env() -> dict:
    """Parent env minus anything that would leak the outer Claude Code session or a venv."""
    drop = {"CLAUDECODE", "ANTHROPIC_BASE_URL", "VIRTUAL_ENV", "CODEX_HOME", "COPILOT_HOME",
            "OPENCODE_CONFIG", CELL_ENV_MARKER, "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
            "OPENROUTER_API_KEY"}             # OpenRouter credentials only reach OpenRouter cells (build_cmd)
    return {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k in drop)}


def _mcp_env(cell_dir: Path) -> dict:
    return {CELL_ENV_MARKER: str(cell_dir), "ROBOTMCP_SCREENSHOT_MODE": "disabled",
            "PLAYWRIGHT_BROWSERS_PATH": str(PW_BROWSERS)}


def prepare_agent_home(agent: str, cell_dir: Path) -> Path:
    home = cell_dir / "agent_home"
    home.mkdir(parents=True, exist_ok=True)
    if is_or(agent):          # OpenRouter: NO subscription credentials, no account data
        if base_agent(agent) == "claude":
            (home / ".claude.json").write_text(json.dumps(OR.claude_code_home_json()), encoding="utf-8")
        return home
    if agent == "claude":
        shutil.copy2(Path.home() / ".claude" / ".credentials.json", home / ".credentials.json")
        src = Path.home() / ".claude.json"
        if src.exists():  # onboarding/account state only; drop per-project + user MCP config
            try:
                d = json.loads(src.read_text(encoding="utf-8"))
                for k in ("projects", "mcpServers", "skillUsage", "toolUsage", "pluginUsage",
                          "githubRepoPaths", "tipsHistory", "tipsHistoryByCommand"):
                    d.pop(k, None)
                (home / ".claude.json").write_text(json.dumps(d), encoding="utf-8")
            except Exception:
                pass
    elif agent == "codex":
        shutil.copy2(Path.home() / ".codex" / "auth.json", home / "auth.json")
    return home


def scrub_credentials(agent: str, home: Path) -> None:
    for name in (".credentials.json", "auth.json"):
        p = home / name
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def write_agent_config(agent: str, workspace: Path, home: Path, cell_dir: Path, has_mcp: bool) -> None:
    menv = _mcp_env(cell_dir)
    full, agent = agent, base_agent(agent)
    if agent == "claude":
        cfg: dict = {"mcpServers": {}}
        if has_mcp:
            cfg["mcpServers"]["robotmcp"] = {"type": "stdio", "command": RF_MCP_CMD[0],
                                             "args": RF_MCP_CMD[1:], "env": menv}
        (cell_dir / "claude_mcp.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    elif agent == "codex":
        txt = (f'model = "{AGENT_MODELS["codex"]}"\n'
               f'model_reasoning_effort = "{CODEX_EFFORT}"\n\n'
               f'[projects."{workspace}"]\ntrust_level = "trusted"\n')
        if has_mcp:
            args_toml = ", ".join(json.dumps(a) for a in RF_MCP_CMD[1:])
            env_toml = ", ".join(f"{k} = {json.dumps(v)}" for k, v in menv.items())
            txt += ("\n[mcp_servers.robotmcp]\n"
                    f"command = {json.dumps(RF_MCP_CMD[0])}\n"
                    f"args = [{args_toml}]\n"
                    f"env = {{ {env_toml} }}\n"
                    "startup_timeout_sec = 90\n"
                    "tool_timeout_sec = 300\n")
        (home / "config.toml").write_text(txt, encoding="utf-8")
    elif agent == "opencode":
        cfg = {"$schema": "https://opencode.ai/config.json",
               "permission": {"edit": "allow", "bash": "allow", "webfetch": "allow",
                              "external_directory": "allow"}}
        if has_mcp:
            cfg["mcp"] = {"robotmcp": {"type": "local", "command": RF_MCP_CMD, "enabled": True,
                                       "environment": menv, "timeout": 90000}}
        if is_or(full):        # native openrouter provider; the key comes from the process env only
            cfg["provider"] = OR.opencode_provider_cfg(or_model_id(full))
        (home / "opencode.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    elif agent == "copilot":
        if has_mcp:
            cfg = {"mcpServers": {"robotmcp": {"type": "local", "command": RF_MCP_CMD[0],
                                               "args": RF_MCP_CMD[1:], "env": menv, "tools": ["*"]}}}
            (cell_dir / "copilot_mcp.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def build_cmd(agent: str, scenario: Scenario, prompt: str, workspace: Path, home: Path,
              cell_dir: Path, has_mcp: bool, extra_args: list[str]) -> tuple[list[str], dict]:
    full, agent = agent, base_agent(agent)
    env = _clean_env()
    env["PATH"] = f"{VENV_BIN}:{env.get('PATH', '')}"
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(PW_BROWSERS)
    env["ROBOTMCP_SCREENSHOT_MODE"] = "disabled"
    env[CELL_ENV_MARKER] = str(cell_dir)
    if is_or(full):              # OpenRouter credentials: process env only (never cmd.json / results)
        if agent == "claude":
            env.update(OR.claude_code_env(or_model_id(full), ensure_or_key()))
        else:
            env.update(OR.opencode_env(ensure_or_key(), home))
    if agent == "claude":
        env["CLAUDE_CONFIG_DIR"] = str(home)
        cmd = ["claude", "-p", prompt, "--model", agent_model(full),
               "--output-format", "stream-json", "--verbose", "--include-hook-events",
               "--dangerously-skip-permissions", "--max-turns", str(scenario.max_turns),
               "--mcp-config", str(cell_dir / "claude_mcp.json"), "--strict-mcp-config",
               *extra_args]
    elif agent == "codex":
        env["CODEX_HOME"] = str(home)
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-C", str(workspace),
               "--dangerously-bypass-approvals-and-sandbox", *extra_args, prompt]
    elif agent == "opencode":
        env["OPENCODE_CONFIG"] = str(home / "opencode.json")
        cmd = ["opencode", "run", "--dir", str(workspace), "-m", agent_model(full),
               "--format", "json", "--dangerously-skip-permissions"]
        if OPENCODE_VARIANT:
            cmd += ["--variant", OPENCODE_VARIANT]
        cmd += [*extra_args, prompt]
    elif agent == "copilot":
        env["COPILOT_HOME"] = str(home)
        env["COPILOT_AUTO_UPDATE"] = "false"
        cmd = ["copilot", "-p", prompt, "--model", AGENT_MODELS["copilot"], "--allow-all",
               "--no-ask-user", "--output-format", "json", "-C", str(workspace),
               "--log-dir", str(cell_dir / "copilot_logs"), "--no-auto-update",
               "--disable-builtin-mcps"]
        if has_mcp:
            cmd += ["--additional-mcp-config", "@" + str(cell_dir / "copilot_mcp.json")]
        cmd += extra_args
    else:
        raise ValueError(agent)
    return cmd, env


# --------------------------------------------------------------------------- #
# Transcript parsing -> metrics + normalized tool calls
# --------------------------------------------------------------------------- #
def _cut(x: Any, n: int = 300) -> str:
    s = x if isinstance(x, str) else json.dumps(x, default=str)
    return s if len(s) <= n else s[:n] + "..."


def _events(path: Path):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("{"):
                    try:
                        yield json.loads(line)
                    except Exception:
                        continue
    except FileNotFoundError:
        return


def _kind(tool: str) -> str:
    t = tool.lower()
    if t in ("report_intent", "toolsearch"):      # CLI bookkeeping, not work (excluded from tool_calls)
        return "meta"
    if "robotmcp" in t:
        return "mcp"
    if t in ("bash", "command_execution", "shell", "run_in_terminal", "local_shell_call", "exec_command",
             "write_bash", "read_bash", "stop_bash"):
        return "shell"
    if t == "skill":
        return "skill"
    if t in ("edit", "write", "multiedit", "file_change", "apply_patch", "create", "str_replace_editor",
             "str_replace", "patch", "notebookedit"):
        return "edit"
    if t in ("read", "view", "glob", "grep", "list", "ls", "find", "search"):
        return "read"
    if t.startswith("mcp") or t == "mcp_tool_call":
        return "mcp_other"
    return "other"


def parse_transcript(agent: str, out_path: Path) -> tuple[dict, list[dict], dict]:
    """Returns (metrics, calls, info). calls = [{tool, kind, input}] (inputs truncated)."""
    m: dict[str, Any] = {"turns": None, "tool_calls": 0, "in_tok": None, "out_tok": None,
                         "cache_read_tok": None, "cost_usd": None, "final_text": None}
    calls: list[dict] = []
    info: dict[str, Any] = {"mcp_servers": None, "errors": [], "hook_events": 0, "skills_loaded": None,
                            "model_seen": None}

    def add(tool: str, inp: Any, extra: dict | None = None) -> None:
        c = {"tool": tool, "kind": _kind(tool), "input": _cut(inp, 400)}
        if extra:
            c.update(extra)
        calls.append(c)

    if agent == "claude":
        hook_sub: Counter = Counter()
        for d in _events(out_path):
            t = d.get("type")
            if t == "system":
                st = d.get("subtype", "") or ""
                if st == "init":
                    info["mcp_servers"] = d.get("mcp_servers")
                    info["model_seen"] = d.get("model")
                    info["skills_loaded"] = d.get("skills")
                    info["api_key_source"] = d.get("apiKeySource")
                elif st.startswith("hook"):
                    hook_sub[st] += 1
            elif t == "assistant":
                msg = d.get("message") or {}
                if msg.get("model") and not str(msg["model"]).startswith("<"):
                    info["assistant_models"] = sorted(set(info.get("assistant_models") or []) | {msg["model"]})
                for c in msg.get("content", []) or []:
                    if c.get("type") == "tool_use":
                        add(c.get("name", "?"), c.get("input"))
                    elif c.get("type") == "text":
                        m["final_text"] = c.get("text")
            elif t == "result":
                m["turns"] = d.get("num_turns")
                m["cost_usd"] = d.get("total_cost_usd")
                u = d.get("usage") or {}
                m["in_tok"] = (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                m["in_uncached_tok"] = u.get("input_tokens") or 0
                m["cache_write_tok"] = u.get("cache_creation_input_tokens") or 0
                m["cache_read_tok"] = u.get("cache_read_input_tokens")
                m["out_tok"] = u.get("output_tokens")
                mu = d.get("modelUsage") or {}
                if mu and any(isinstance(x, dict) and x.get("inputTokens") is not None for x in mu.values()):
                    # per-model totals incl. side calls of the small/fast model (OpenRouter cost estimate only)
                    m["model_usage"] = {k: {kk: x.get(kk) for kk in ("inputTokens", "outputTokens",
                                                                     "cacheReadInputTokens",
                                                                     "cacheCreationInputTokens")}
                                        for k, x in mu.items() if isinstance(x, dict)}
                m["final_text"] = d.get("result") or m["final_text"]
                if d.get("is_error") or d.get("subtype") not in (None, "success"):
                    info["errors"].append(f"result:{d.get('subtype')}")
        started = sum(v for k, v in hook_sub.items() if "start" in k)
        info["hook_events"] = started or sum(hook_sub.values())
        info["hook_subtypes"] = dict(hook_sub) or None
    elif agent == "codex":
        in_tok = out_tok = cached = 0
        turns = 0
        for d in _events(out_path):
            t = d.get("type", "")
            if t == "turn.completed":
                turns += 1
                u = d.get("usage") or {}
                in_tok += u.get("input_tokens", 0) or 0
                cached += u.get("cached_input_tokens", 0) or 0
                out_tok += u.get("output_tokens", 0) or 0
            elif t in ("turn.failed", "error"):
                info["errors"].append(_cut(d.get("error") or d.get("message") or d, 300))
            elif t == "item.completed":
                it = d.get("item") or {}
                ty = it.get("type")
                if ty == "agent_message":
                    m["final_text"] = it.get("text")
                elif ty == "mcp_tool_call":
                    add(f"{it.get('server')}__{it.get('tool')}", it.get("arguments"),
                        {"status": it.get("status")})
                elif ty == "command_execution":
                    add("command_execution", it.get("command"), {"exit": it.get("exit_code")})
                elif ty == "file_change":
                    add("file_change", [c.get("path") for c in it.get("changes", [])])
                elif ty not in ("reasoning", "todo_list", None):
                    add(ty, {k: v for k, v in it.items() if k not in ("aggregated_output", "id")})
        # OpenAI input_tokens INCLUDE cached_input_tokens -> report uncached input like the other CLIs.
        # codex exec runs a single "turn" per prompt, so turns stays None (use tool_calls instead).
        m.update(in_tok=(in_tok - cached) or None, out_tok=out_tok or None, cache_read_tok=cached or None,
                 turns=None)
    elif agent == "opencode":
        in_tok = out_tok = cache_r = in_unc = cache_w = 0
        cost = 0.0
        steps = 0
        for d in _events(out_path):
            t = d.get("type", "")
            part = d.get("part") if isinstance(d.get("part"), dict) else {}
            if t == "tool_use":
                st = part.get("state") or {}
                add(part.get("tool", "?"), st.get("input"), {"status": st.get("status")})
            elif t == "text" and part.get("text"):
                m["final_text"] = part.get("text")
            elif t == "step_start":
                steps += 1
            elif t == "step_finish":
                tk = part.get("tokens") or {}
                in_tok += (tk.get("input", 0) or 0) + ((tk.get("cache") or {}).get("write", 0) or 0)
                in_unc += tk.get("input", 0) or 0
                cache_w += (tk.get("cache") or {}).get("write", 0) or 0
                out_tok += (tk.get("output", 0) or 0) + (tk.get("reasoning", 0) or 0)
                cache_r += (tk.get("cache") or {}).get("read", 0) or 0
                if isinstance(part.get("cost"), (int, float)):
                    cost += part["cost"]
            elif t == "error":
                info["errors"].append(_cut(d.get("error") or d, 300))
        m.update(in_tok=in_tok or None, out_tok=out_tok or None, cache_read_tok=cache_r or None,
                 cost_usd=round(cost, 6) if cost else None, turns=steps or None, in_uncached_tok=in_unc,
                 cache_write_tok=cache_w)
    elif agent == "copilot":
        out_tok, turns = 0, 0
        for d in _events(out_path):
            t, data = d.get("type"), d.get("data") or {}
            if t == "tool.execution_start":
                tool = data.get("toolName", "?")
                if data.get("mcpServerName"):
                    tool = f"{data['mcpServerName']}__{data.get('mcpToolName') or tool}"
                add(tool, data.get("arguments"))
            elif t == "assistant.message":
                out_tok += data.get("outputTokens") or 0
                if data.get("content"):
                    m["final_text"] = data["content"]
                info["model_seen"] = data.get("model") or info["model_seen"]
            elif t == "assistant.turn_start":
                turns += 1
            elif t == "session.mcp_servers_loaded":
                info["mcp_servers"] = data.get("servers")
            elif t == "session.skills_loaded":
                info["skills_loaded"] = [s.get("name") for s in data.get("skills", [])]
            elif t in ("session.error", "error"):
                info["errors"].append(_cut(data or d, 300))
            elif isinstance(t, str) and t.startswith("hook") and "start" in t:
                info["hook_events"] += 1
            elif t == "result":
                u = d.get("usage") or {}
                info["premium_requests"] = u.get("premiumRequests")
                info["api_ms"] = u.get("totalApiDurationMs")
                if d.get("exitCode") not in (0, None):
                    info["errors"].append(f"exitCode={d.get('exitCode')}")
        m.update(out_tok=out_tok or None, turns=turns or None)
    m["tool_calls"] = sum(1 for c in calls if c["kind"] != "meta")
    if m["final_text"]:
        m["final_text"] = m["final_text"][:600]
    return m, calls, info


def summarize_calls(calls: list[dict]) -> dict:
    kinds = Counter(c["kind"] for c in calls)
    mcp_tools = Counter(re.sub(r"^.*?robotmcp(__|_|-|/|\.)", "", c["tool"], flags=re.I)
                        for c in calls if c["kind"] == "mcp")
    return {"by_kind": dict(kinds), "mcp_calls": kinds.get("mcp", 0), "mcp_tools": dict(mcp_tools),
            "shell_calls": kinds.get("shell", 0)}


_LEAK_MARKERS = ("_reference", "work_conf", "bundle-agent-skills-eval", "ab/fixtures", "results_rc",
                 "fixtures_live", "results_live", "ab/harness")


def detect_leak(calls: list[dict]) -> list[str]:
    hits = set()
    for c in calls:
        s = c.get("input") or ""
        for mk in _LEAK_MARKERS:
            if mk in s:
                hits.add(mk)
    return sorted(hits)


# --- round 2: "does the helper replace execute_step?" ------------------------------------------
MCP_STEP_TOOLS = ("execute_step", "execute_batch", "intent_action", "get_session_state", "run_test_suite",
                  "find_keywords")
HELPER_STEP_SUBCMDS = ("step", "run", "state", "search", "doc", "check")
_HELPER_SUB_RE = re.compile(r"(?<![\w-])rfmcp\s+([a-z][\w-]*)")
_ROBOT_RUN_RE = re.compile(r"(?:^|[\s;&|(/\"'`])robot\s+(?!-{1,2}(?:version|help)\b)|-m\s+robot(?:\s|$)")
_ADHOC_BROWSER_RE = re.compile(r"(?i)playwright|chromium|from Browser import|Browser\(\)|robotcode\s+repl")


def stepwise_metrics(calls: list[dict]) -> dict:
    """Per-session counts of live/stepwise execution, comparable across arms:
    live_steps   = rf-mcp execute_step + execute_batch + intent_action  |  `rfmcp step`
    live_inspect = rf-mcp get_session_state                             |  `rfmcp state`
    tool_runs    = rf-mcp run_test_suite                                |  `rfmcp run`
    kw_lookup    = rf-mcp find_keywords + get_keyword_info              |  `rfmcp search` + `rfmcp doc`
    robot_runs   = plain `robot ...` / `python -m robot` shell invocations (every arm)
    adhoc_browser= shell calls driving a browser outside RF (playwright/chromium/robotcode repl)"""
    mcp: Counter = Counter()
    helper: Counter = Counter()
    robot_runs = adhoc = 0
    for c in calls:
        inp = c.get("input") or ""
        if c["kind"] == "mcp":
            mcp[re.sub(r"^.*?robotmcp(__|_|-|/|\.)", "", c["tool"], flags=re.I)] += 1
        elif c["kind"] in ("shell", "other"):
            for m in _HELPER_SUB_RE.finditer(inp):
                helper[m.group(1)] += 1
            robot_runs += len(_ROBOT_RUN_RE.findall(inp))
            if _ADHOC_BROWSER_RE.search(inp):
                adhoc += 1
    out = {
        "mcp": {t: mcp.get(t, 0) for t in MCP_STEP_TOOLS},
        "mcp_other": sum(v for k, v in mcp.items() if k not in MCP_STEP_TOOLS),
        "helper": {t: helper.get(t, 0) for t in HELPER_STEP_SUBCMDS},
        "helper_other": sum(v for k, v in helper.items() if k not in HELPER_STEP_SUBCMDS),
        "live_steps": mcp["execute_step"] + mcp["execute_batch"] + mcp["intent_action"] + helper["step"],
        "live_inspect": mcp["get_session_state"] + helper["state"],
        "tool_runs": mcp["run_test_suite"] + helper["run"],
        "kw_lookup": mcp["find_keywords"] + mcp["get_keyword_info"] + helper["search"] + helper["doc"],
        "helper_check": helper["check"],
        "robot_runs": robot_runs,
        "adhoc_browser": adhoc,
    }
    out["stepwise_any"] = (out["live_steps"] + out["live_inspect"]) > 0
    return out


def skillpkg_usage(calls: list[dict], markers: list[str], info: dict, cell_dir: Path,
                   hook_log: str | None) -> dict:
    def is_helper(c: dict) -> bool:
        inp = c.get("input") or ""
        return c["kind"] in ("shell", "other", "skill") and (
            bool(HELPER_CLI_RE.search(inp)) or any(mk in inp for mk in markers))
    helper = [c for c in calls if is_helper(c)]
    sub = Counter()
    for c in helper:
        mt = re.search(r"(?<![\w-])rfmcp\s+([a-z][\w-]*)", c.get("input") or "")
        sub[mt.group(1) if mt else "?"] += 1
    skill_read = any(c["kind"] == "skill" or SKILL_READ_RE.search(c.get("input") or "") for c in calls)
    firings = with_files = None
    cands = [Path(hook_log)] if hook_log else []
    cands += [p for p in cell_dir.rglob("*hook*.jsonl") if p.is_file() and p not in cands]
    for p in cands:
        try:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    firings = (firings or 0) + 1
                    try:
                        if json.loads(line).get("files"):
                            with_files = (with_files or 0) + 1
                    except Exception:
                        pass
        except Exception:
            continue
    return {"helper_calls": len(helper), "helper_used": bool(helper), "helper_subcmds": dict(sub),
            "skill_read": skill_read, "hook_firings_log": firings, "hook_firings_with_files": with_files,
            "hook_events_transcript": info.get("hook_events"),
            "helper_examples": [c["input"][:160] for c in helper[:5]]}


# --------------------------------------------------------------------------- #
# One cell
# --------------------------------------------------------------------------- #
def cell_key(agent: str, arm: str, scen: str, rep: int) -> str:
    return f"{agent}|{arm}|{scen}|{rep}"


def fixture_root(scenario: Scenario) -> Path:
    return FIXTURES_LIVE if scenario.live else FIXTURES_SRC


def reference_root(scenario: Scenario) -> Path:
    return REFERENCE_LIVE if scenario.live else REFERENCE_SRC


def template_values(scenario: Scenario, cell_dir: Path) -> dict[str, str]:
    """Per-cell template values, e.g. {'__AB_SPACE__': 'ab-<cell hash>'} (unique demoshop space)."""
    if not scenario.template:
        return {}
    import hashlib
    cell = hashlib.sha1(str(cell_dir).encode()).hexdigest()[:10]
    return {tok: pat.format(cell=cell) for tok, pat in scenario.template.items()}


def apply_template(text: str, values: dict[str, str]) -> str:
    for tok, val in values.items():
        text = text.replace(tok, val)
    return text


def template_workspace(ws: Path, values: dict[str, str]) -> int:
    n = 0
    if not values:
        return n
    for f in ws.rglob("*"):
        if f.is_file() and f.suffix in (".robot", ".resource", ".py", ".toml", ".yaml", ".yml", ".json",
                                        ".txt", ".md", ".csv"):
            t = f.read_text(encoding="utf-8", errors="replace")
            t2 = apply_template(t, values)
            if t2 != t:
                f.write_text(t2, encoding="utf-8")
                n += 1
    return n


def provision_workspace(scenario: Scenario, cell_dir: Path) -> Path:
    ws = cell_dir / "workspace"
    if ws.exists():
        shutil.rmtree(ws)
    shutil.copytree(fixture_root(scenario) / scenario.fixture, ws)
    for d in FIXTURE_MKDIRS.get(scenario.fixture, []):
        (ws / d).mkdir(parents=True, exist_ok=True)
    for pat in ("output.xml", "log.html", "report.html"):
        for p in ws.rglob(pat):
            if "data" not in p.relative_to(ws).parts:
                p.unlink()
    template_workspace(ws, template_values(scenario, cell_dir))
    return ws


def run_agent(agent: str, scenario: Scenario, ws: Path, home: Path, cell_dir: Path,
              has_mcp: bool, extra_args: list[str], extra_env: dict) -> dict:
    prompt = apply_template(scenario.prompt, template_values(scenario, cell_dir))
    cmd, env = build_cmd(agent, scenario, prompt, ws, home, cell_dir, has_mcp, extra_args)
    env.update({k: str(v) for k, v in (extra_env or {}).items()})
    shown_env = {k: env[k] for k in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "COPILOT_HOME", "OPENCODE_CONFIG",
                                     CELL_ENV_MARKER, "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL") if k in env}
    if is_or(agent):
        shown_env.update({k: "<redacted>" for k in ("ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY") if k in env})
        if "XDG_DATA_HOME" in env:
            shown_env["XDG_DATA_HOME"] = env["XDG_DATA_HOME"]
    shown_env.update({k: str(v) for k, v in (extra_env or {}).items()})
    (cell_dir / "cmd.json").write_text(json.dumps({"cmd": cmd, "env_overrides": shown_env}, indent=1))
    out_path, err_path = cell_dir / "agent_stdout.log", cell_dir / "agent_stderr.log"
    t0 = time.monotonic()
    timed_out, exit_code, survivors = False, None, 0
    with out_path.open("wb") as o, err_path.open("wb") as e:
        try:
            p = subprocess.Popen(cmd, cwd=str(ws), env=env, stdout=o, stderr=e,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
        except FileNotFoundError as exc:
            (cell_dir / "spawn_error.txt").write_text(str(exc))
            return {"wall_s": 0.0, "timed_out": False, "exit_code": None, "spawn_error": str(exc)}
        with _RUNNING_LOCK:
            RUNNING[str(cell_dir)] = p
        tracker = TreeTracker(p.pid)
        tracker.start()
        try:
            exit_code = p.wait(timeout=scenario.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _killpg(p.pid)
            p.wait()
        finally:
            with _RUNNING_LOCK:
                RUNNING.pop(str(cell_dir), None)
            tracker.stop_ev.set()
            tracker.join(timeout=5)
            try:
                os.killpg(p.pid, signal.SIGKILL)       # stragglers still in the agent's group
            except (ProcessLookupError, PermissionError):
                pass
            survivors = tracker.kill_survivors()       # re-parented orphans (node/chromium/rf-mcp)
    elapsed = time.monotonic() - t0
    return {"wall_s": round(elapsed, 1), "timed_out": timed_out, "exit_code": exit_code,
            "aborted": ABORT.is_set(), "orphans_killed": survivors}


def _scrub_cell_logs(cell_dir: Path) -> None:
    """OpenRouter cells: remove the key from anything the cell wrote before it is archived (defensive)."""
    if not OR_KEY:
        return
    for f in [cell_dir / "agent_stdout.log", cell_dir / "agent_stderr.log", *cell_dir.glob("*.jsonl")]:
        try:
            s = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if OR_KEY in s or OR.KEY_PREFIX in s:
            f.write_text(OR.scrub(s, OR_KEY), encoding="utf-8")


def _archive_transcript(agent: str, cell_dir: Path, calls: list[dict]) -> str | None:
    if not KEEP_TRANSCRIPTS:
        return None
    if is_or(agent):
        _scrub_cell_logs(cell_dir)
    dst_dir = TRANSCRIPTS / agent
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{cell_dir.name}.jsonl.gz"
    src = cell_dir / "agent_stdout.log"
    try:
        with gzip.open(dst, "wb", compresslevel=6) as g:
            if src.exists():
                with src.open("rb") as s:
                    shutil.copyfileobj(s, g)
            g.write(b"\n" + json.dumps({"__harness_calls__": calls}).encode() + b"\n")
            err = cell_dir / "agent_stderr.log"
            if err.exists():
                g.write(json.dumps({"__stderr_tail__": err.read_text(errors="replace")[-4000:]}).encode()
                        + b"\n")
        return str(dst.relative_to(HERE))
    except Exception:
        return None


def or_cost(agent: str, metrics: dict, info: dict, usage_before: float | None) -> dict:
    """per-cell OpenRouter accounting: tokens, estimate from OpenRouter prices, account usage delta (/api/v1/key;
    shared with concurrent OpenRouter cells, booked with a few seconds delay). metrics["cost_usd"] := the estimate
    (the agent's own figure stays in cost_usd_agent_reported)."""
    mid = or_model_id(agent)
    mu = metrics.get("model_usage") or {}
    if mu:
        tok = {"in_uncached": sum(int(x.get("inputTokens") or 0) for x in mu.values()),
               "out": sum(int(x.get("outputTokens") or 0) for x in mu.values()),
               "cache_read": sum(int(x.get("cacheReadInputTokens") or 0) for x in mu.values()),
               "cache_write": sum(int(x.get("cacheCreationInputTokens") or 0) for x in mu.values())}
    else:
        tok = {"in_uncached": int(metrics.get("in_uncached_tok") or 0), "out": int(metrics.get("out_tok") or 0),
               "cache_read": int(metrics.get("cache_read_tok") or 0), "cache_write": int(metrics.get("cache_write_tok") or 0)}
    table = OR.prices()
    est = OR.estimate_cost(mid, tok["in_uncached"], tok["out"], tok["cache_read"], tok["cache_write"], table)
    after = OR.settled_usage(ensure_or_key(), usage_before, wait_s=40.0) if usage_before is not None else None
    seen = sorted(set((info.get("assistant_models") or []) + [info.get("model_seen") or ""]) - {""})
    res = {"route": or_route(agent)[0], "model_id": mid, "tokens": tok, "price_per_mtok": {
               k: round(v * 1e6, 4) for k, v in (table.get(mid) or {}).items()},
           "est_cost_usd": est, "usage_before": usage_before, "usage_after": after,
           "usage_delta_usd": (round(after - usage_before, 6) if after is not None and usage_before is not None
                               else None),
           "models_seen": seen, "api_key_source": info.get("api_key_source"),
           "via_openrouter": bool(any(mid.split("/", 1)[-1] in s for s in seen)
                                  or (after is not None and usage_before is not None and after > usage_before))}
    if res["usage_delta_usd"] is not None and est:
        # < 0.1: the session was (mostly) billed to ANOTHER key (e.g. a key stored in the agent's own auth store) --
        # unless concurrent OpenRouter cells blur the delta (or_concurrent_at_start/end > 1)
        res["delta_vs_est"] = round(res["usage_delta_usd"] / est, 2)
        res["billed_to_this_key"] = res["delta_vs_est"] >= 0.1   # list prices overestimate DeepSeek ~2-4x
    metrics["cost_usd_agent_reported"] = metrics.get("cost_usd")
    metrics["cost_usd"] = est
    return res


def run_cell(agent: str, arm: str, scenario: Scenario, rep: int, reaper: Reaper,
             skillpkg_install=None, hookpkg_install=None) -> dict:
    key = cell_key(agent, arm, scenario.id, rep)
    cell_dir = WORK_ROOT / agent / f"{scenario.id}-{arm}-rep{rep}-{uuid.uuid4().hex[:6]}"
    cell_dir.mkdir(parents=True, exist_ok=True)
    has_mcp, has_pkg = ARM_SPEC[arm]
    has_hook = arm in HOOK_ARMS
    bagent = base_agent(agent)
    row: dict[str, Any] = {
        "key": key, "agent": agent, "arm": arm, "scenario": scenario.id, "tier": scenario.tier,
        "rep": rep, "model": agent_model(agent),
        "effort": CODEX_EFFORT if bagent == "codex" else (OPENCODE_VARIANT or None),
        "started_at": _now(), "cell_id": cell_dir.name, "has_mcp": has_mcp, "has_skillpkg": has_pkg,
        "harness_version": HARNESS_VERSION, "kind": scenario.kind, "live": scenario.live,
        "max_turns": scenario.max_turns, "timeout_s": scenario.timeout_s,
    }
    if bagent != agent:
        row["base_agent"] = bagent
        row["route"] = or_route(agent)[0]
    reaper.register(cell_dir)
    if has_hook:
        row["has_hookpkg"] = True
    home = None
    ws = None
    calls: list[dict] = []
    or_before = None
    try:
        ws = provision_workspace(scenario, cell_dir)
        home = prepare_agent_home(agent, cell_dir)
        write_agent_config(agent, ws, home, cell_dir, has_mcp)
        extra_args: list[str] = []
        extra_env: dict = {}
        inst: dict = {}
        if has_pkg:
            inst = (skillpkg_install or load_skillpkg_install())(bagent, ws, home, VENV_BIN) or {}
            extra_args = [str(a) for a in (inst.get("extra_args") or [])]
            extra_env = dict(inst.get("extra_env") or {})
            extra_env.setdefault("RFMCP_HOOK_LOG", str(cell_dir / HOOK_LOG_NAME))
            row["skillpkg_install"] = {"notes": str(inst.get("notes", ""))[:500],
                                       "extra_args": extra_args, "extra_env_keys": sorted(extra_env)}
        if has_hook:
            hspec = HOOK_PKGS[arm]
            installer = (hookpkg_install if arm == "hookpkg" else None) or load_hook_install(arm)
            inst = installer(bagent, ws, home, VENV_BIN) or {}
            extra_args = [str(a) for a in (inst.get("extra_args") or [])]
            extra_env = dict(inst.get("extra_env") or {})
            extra_env.setdefault(hspec["log_env"], str(cell_dir / hspec["log_name"]))
            row[f"{arm}_install"] = {"notes": str(inst.get("notes", ""))[:500],
                                     "extra_args": extra_args, "extra_env_keys": sorted(extra_env)}
        if is_or(agent):
            with _WRITE_LOCK:
                OR_RUNNING["n"] += 1
                row["or_concurrent_at_start"] = OR_RUNNING["n"]
            or_before = OR.key_usage(ensure_or_key())
        try:
            run = run_agent(agent, scenario, ws, home, cell_dir, has_mcp, extra_args, extra_env)
        finally:
            if is_or(agent):
                with _WRITE_LOCK:
                    row["or_concurrent_at_end"] = OR_RUNNING["n"]
                    OR_RUNNING["n"] -= 1
        reaper.sweep(only_cell=cell_dir, force=True)          # nothing of the agent survives into grading
        metrics, calls, info = parse_transcript(bagent, cell_dir / "agent_stdout.log")
        metrics.update(run)
        if is_or(agent):
            row["openrouter"] = or_cost(agent, metrics, info, or_before)
        verdicts, primary = grade(scenario, ws, cell_dir / "grader_out", cell_dir)
        reaper.sweep(only_cell=cell_dir, force=True)
        cs = summarize_calls(calls)
        row.update(metrics=metrics, verdicts=verdicts, primary_pass=primary,
                   n_checks=len(verdicts), n_pass=sum(v["passed"] for v in verdicts))
        row["mcp"] = {"configured": has_mcp, "servers": info.get("mcp_servers"),
                      "calls": cs["mcp_calls"], "tools": cs["mcp_tools"]}
        row["calls"] = {"by_kind": cs["by_kind"], "shell": cs["shell_calls"]}
        row["agent_info"] = {k: info.get(k) for k in ("errors", "model_seen", "premium_requests", "api_ms",
                                                       "hook_subtypes", "api_key_source", "assistant_models")
                             if info.get(k)}
        if info.get("skills_loaded") is not None:
            row["agent_info"]["skills_loaded"] = _cut(info.get("skills_loaded"), 300)
        if "result:error_max_turns" in (info.get("errors") or []):
            row["turn_cap"] = True        # --max-turns budget ran out (label, not an agent-side error)
        if has_pkg:
            row["skillpkg"] = skillpkg_usage(calls, list(inst.get("markers") or DEFAULT_SKILLPKG_MARKERS),
                                             info, cell_dir, inst.get("hook_log") or extra_env.get("RFMCP_HOOK_LOG"))
        if has_hook:
            hspec = HOOK_PKGS[arm]
            usage = HOOK_USAGE.get(arm, hookpkg2_usage)
            row[arm] = usage(calls, info, Path(extra_env.get(hspec["log_env"]) or cell_dir / hspec["log_name"]), ws)
        helper_hits = sum(1 for c in calls if c["kind"] in ("shell", "other", "skill")
                          and HELPER_CLI_RE.search(c.get("input") or ""))
        row["helper_cli_calls"] = helper_hits
        hook_hits = sum(1 for c in calls if HOOK_USE_RE.search(c.get("input") or ""))
        if not has_hook:   # hook machinery must not appear outside the hookpkg arm
            hook_hits += 1 if (ws / ".rf" / "hook").is_dir() else 0
            hook_hits += 1 if (ws / ".rf" / "hook2").is_dir() else 0
            hook_hits += 1 if (ws / ".rf" / "hook3").is_dir() else 0
            hook_hits += 1 if (ws / ".rf" / "hook31").is_dir() else 0
            hook_hits += 1 if (ws / ".rf" / "hook32").is_dir() else 0
        if hook_hits:
            row["hook_usage_hits"] = hook_hits
        cross_hits = 0     # the OTHER hook packages' markers inside a hook arm (v1 / v2 / v3 / v3.1 must not cross)
        if has_hook:
            for other, ospec in HOOK_PKGS.items():
                if other == arm:
                    continue
                orx = re.compile(ospec["marker"])
                cross_hits += sum(1 for c in calls if orx.search(c.get("input") or ""))
                cross_hits += 1 if (ws / Path(*ospec["state_dir"])).is_dir() else 0
            if cross_hits:
                row["hook_cross_hits"] = cross_hits
        row["stepwise"] = stepwise_metrics(calls)
        rp = [v for v in verdicts if v["type"] == "robot_pass"]
        row["flaky"] = any(v.get("flaky") for v in rp)
        row["robot_first_pass"] = all(v.get("first_pass", v["passed"]) for v in rp) if rp else None
        if scenario.template:
            row["template_values"] = template_values(scenario, cell_dir)
        row["contaminated"] = (((not has_mcp) and cs["mcp_calls"] > 0) or ((not has_pkg) and helper_hits > 0)
                               or ((not has_hook) and hook_hits > 0) or (has_hook and cross_hits > 0))
        row["leak_markers"] = detect_leak(calls)
        try:
            row["stderr_tail"] = (cell_dir / "agent_stderr.log").read_text(errors="replace")[-600:]
            if OR_KEY:
                row["stderr_tail"] = OR.scrub(row["stderr_tail"], OR_KEY)
        except Exception:
            pass
        if run.get("spawn_error"):
            row.update(status="error", error=f"spawn: {run['spawn_error']}")
        elif run.get("aborted") and (run.get("timed_out") or run.get("exit_code") != 0):
            row["status"] = "aborted"
        else:
            row["status"] = "ok"
    except Exception as exc:
        row.update(status="error", error=f"{type(exc).__name__}: {exc}",
                   traceback=traceback.format_exc()[-1500:], primary_pass=False)
    finally:
        if home is not None:
            scrub_credentials(agent, home)
        row["transcript"] = _archive_transcript(agent, cell_dir, calls)
        reaper.unregister(cell_dir)
        reaper.sweep(only_cell=cell_dir, force=True)
        row["finished_at"] = _now()
        if PRUNE:
            shutil.rmtree(cell_dir, ignore_errors=True)
    return row


def append_result(row: dict) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        with RESULTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")


def completed_keys() -> set[str]:
    done: set[str] = set()
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if r.get("status") == "ok":
                    done.add(r["key"])
            except Exception:
                continue
    return done


# --------------------------------------------------------------------------- #
# Disk guard, lock, signals
# --------------------------------------------------------------------------- #
def free_bytes(p: Path = Path.home()) -> int:
    return shutil.disk_usage(str(p)).free


def _df_line() -> str:
    try:
        return subprocess.run(["df", "-h", str(Path.home())], capture_output=True, text=True).stdout.strip()
    except Exception:
        return f"free={free_bytes() / 1e9:.2f} GB"


class HarnessLock:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / ".harness.lock"
        self.fh = None

    def __enter__(self):
        self.fh = self.path.open("w")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(f"another harness instance holds {self.path}; refusing to run concurrently")
        self.fh.write(str(os.getpid()))
        self.fh.flush()
        return self

    def __exit__(self, *a):
        try:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
            self.fh.close()
        except Exception:
            pass


def _install_signal_handlers() -> None:
    def _h(signum, frame):
        if ABORT.is_set():
            return
        ABORT.set()
        _log(f"signal {signum}: aborting - killing running agents, no new cells")
        with _RUNNING_LOCK:
            procs = list(RUNNING.values())
        for p in procs:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except Exception:
                pass
    signal.signal(signal.SIGINT, _h)
    signal.signal(signal.SIGTERM, _h)


# --------------------------------------------------------------------------- #
# Batch orchestrator
# --------------------------------------------------------------------------- #
def build_cells(reps: int, agents: list[str], scen_ids: list[str], arms: list[str]) -> list[tuple]:
    """Rep-major order so a partial/aborted run stays balanced across arms and agents."""
    cells = []
    for rep in range(1, reps + 1):
        for scen in scen_ids:
            for agent in agents:
                for arm in arms:
                    cells.append((agent, arm, SCEN_BY_ID[scen], rep))
    return cells


def preflight_browsers() -> None:
    """Browser cells need the Chromium build the venv's Browser library pins (playwright browsers.json).
    Someone else's cache cleanup deleted it once mid-session -> every robot run failed with
    'Executable doesn't exist'. Abort early with the fix instead of burning cells."""
    try:
        bj = next((VENV_BIN.parent / "lib").glob("python3*/site-packages/Browser/wrapper/node_modules/"
                                                   "playwright-core/browsers.json"))
        revs = {b["name"]: b["revision"] for b in json.loads(bj.read_text())["browsers"]}
    except Exception as exc:
        _log(f"[preflight] cannot read Browser's playwright browsers.json ({exc}); skipping browser check")
        return
    need = PW_BROWSERS / f"chromium_headless_shell-{revs.get('chromium-headless-shell')}"
    if not need.is_dir():
        raise SystemExit(f"[abort] missing {need} (Browser library's Chromium). Fix: cd {bj.parent.parent.parent} && "
                         f"PLAYWRIGHT_BROWSERS_PATH={PW_BROWSERS} node node_modules/playwright-core/cli.js install "
                         "chromium-headless-shell chromium")


def run_batch(reps: int, agents: list[str], scen_ids: list[str], arms: list[str], concurrency: int) -> None:
    global OR_BUDGET
    for a in agents:
        assert base_agent(a) in AGENTS, a
        if is_or(a):
            or_model_id(a)
    for s in scen_ids:
        assert s in SCEN_BY_ID, s
    for arm in arms:
        assert arm in ARM_SPEC, arm
    skill_install = None
    if "skillpkg" in arms:
        skill_install = load_skillpkg_install()
        if getattr(skill_install, "unavailable", None):
            raise SystemExit(f"[abort] arm 'skillpkg' requested but {skill_install.unavailable}; "
                             "run with --arms neither,mcp until ab/skillpkg exists")
    hook_install = None
    for harm in [a for a in arms if a in HOOK_ARMS]:
        inst_fn = load_hook_install(harm)
        if getattr(inst_fn, "unavailable", None):
            raise SystemExit(f"[abort] arm '{harm}' requested but {inst_fn.unavailable}")
        if harm == "hookpkg":
            hook_install = inst_fn
    if any(is_browser(SCEN_BY_ID[s]) for s in scen_ids):
        preflight_browsers()
    if any(is_or(a) for a in agents):
        key = ensure_or_key()
        OR.prices(refresh=True)
        OR_BUDGET = OR.Budget(key, OR_BUDGET_USD, RESULTS.with_name(RESULTS.stem + ".or_budget.json"),
                              reset=OR_BUDGET_RESET)
        _log(f"[openrouter] models={OR_MODELS} budget=${OR_BUDGET_USD:.2f} baseline usage=${OR_BUDGET.baseline:.4f} "
             f"spent since batch start=${OR_BUDGET.spent(fresh=True) or 0:.4f}")
    _log("disk before:\n" + _df_line())
    if free_bytes() < MIN_FREE_BYTES:
        raise SystemExit(f"[abort] only {free_bytes() / 1e9:.2f} GB free (< {MIN_FREE_BYTES / 1024 ** 3:.1f} GiB)")
    with HarnessLock(WORK_ROOT):
        reaper = Reaper(WORK_ROOT)
        stale = reaper.sweep()                          # leftovers of a crashed earlier run
        if stale:
            _log(f"reaper: killed {len(stale)} stale processes from earlier runs")
        reaper.start()
        _install_signal_handlers()
        done = completed_keys()
        cells = [c for c in build_cells(reps, agents, scen_ids, arms)
                 if cell_key(c[0], c[1], c[2].id, c[3]) not in done]
        total = len(cells)
        _log(f"[batch] {total} cells to run (skipping {len(done)} done), concurrency={concurrency}, "
             f"browser<={BROWSER_CONCURRENCY}, per-agent<={AGENT_CONCURRENCY}, prune={PRUNE}")
        browser_sem = threading.Semaphore(min(BROWSER_CONCURRENCY, concurrency))
        agent_sem = {a: threading.Semaphore(AGENT_CONCURRENCY) for a in agents}
        counter = {"n": 0, "skipped": 0}

        def _work(cell):
            agent, arm, scen, rep = cell
            sems = [agent_sem[agent]] + ([browser_sem] if is_browser(scen) else [])
            for s in sems:
                s.acquire()
            try:
                if ABORT.is_set():
                    counter["skipped"] += 1
                    return None
                if is_or(agent) and OR_BUDGET is not None and not OR_BUDGET.allow():
                    with _WRITE_LOCK:
                        OR_SKIPPED["n"] += 1
                        if OR_SKIPPED["n"] == 1:
                            _log(f"[openrouter] budget ${OR_BUDGET_USD:.2f} exhausted (spent ${OR_BUDGET.spent():.4f} "
                                 "since the batch start) - no new OpenRouter cells")
                    counter["skipped"] += 1
                    return None
                fb = free_bytes()
                if fb < MIN_FREE_BYTES:
                    ABORT.set()
                    _log(f"[abort] disk free {fb / 1e9:.2f} GB < {MIN_FREE_BYTES / 1024 ** 3:.1f} GiB - no new cells")
                    counter["skipped"] += 1
                    return None
                t = time.monotonic()
                row = run_cell(agent, arm, scen, rep, reaper, skill_install, hook_install)
                append_result(row)
                with _WRITE_LOCK:
                    counter["n"] += 1
                    m = row.get("metrics") or {}
                    orr = row.get("openrouter") or {}
                    _log(f"[{counter['n']}/{total}] {row['key']} -> status={row.get('status')} "
                         f"primary={row.get('primary_pass')} pass={row.get('n_pass')}/{row.get('n_checks')} "
                         f"mcp_calls={(row.get('mcp') or {}).get('calls')} tools={m.get('tool_calls')} "
                         f"{round(time.monotonic() - t, 1)}s"
                         + (f" or_est=${orr.get('est_cost_usd')} or_delta=${orr.get('usage_delta_usd')}" if orr else "")
                         + (f" ERR={row.get('error')}" if row.get("error") else ""))
                return row
            finally:
                for s in reversed(sems):
                    s.release()

        try:
            with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
                list(ex.map(_work, cells))
        finally:
            reaper.stop()
            time.sleep(0.5)
            final = reaper.sweep()                      # nothing is active any more
            _log(f"[batch] done: ran={counter['n']} skipped={counter['skipped']} "
                 f"reaper_kills_total={len(reaper.killed)} (final sweep {len(final)})"
                 + (f" openrouter: spent ${OR_BUDGET.spent(fresh=True)} of ${OR_BUDGET_USD:.2f}, "
                    f"{OR_SKIPPED['n']} cells skipped by the budget" if OR_BUDGET is not None else ""))
            _log("disk after:\n" + _df_line())


# --------------------------------------------------------------------------- #
# Verification subcommands
# --------------------------------------------------------------------------- #
def verify_reference(scen_ids: list[str], runs: int = 1, out_json: Path | None = None,
                     negatives: bool = False, pristine: bool = True) -> bool:
    """Grade the hidden reference solution (must pass) and the pristine fixture (must fail).

    runs > 1 grades the reference `runs` times (live flakiness: first-attempt pass x/runs, pass with
    the grader's automatic retry, robot wall times). negatives=True also grades every negative-control
    overlay in fixtures_live/_negative/<scenario>/<name>/ (shortcut suites that must FAIL)."""
    if any(is_browser(SCEN_BY_ID[s]) for s in scen_ids):
        preflight_browsers()
    root = WORK_ROOT / "_verify"
    ok_all = True
    summary: dict[str, Any] = {}
    with HarnessLock(WORK_ROOT):
        reaper = Reaper(WORK_ROOT)
        for sid in scen_ids:
            sc = SCEN_BY_ID[sid]
            summary[sid] = {"reference": [], "pristine": None}
            negs = sorted(d.name for d in (NEGATIVE_LIVE / sid).iterdir() if d.is_dir()) \
                if negatives and (NEGATIVE_LIVE / sid).is_dir() else []
            if negs:
                summary[sid]["negatives"] = {}
            for variant in ["reference"] * runs + (["pristine"] if pristine else []) + [f"neg:{n}" for n in negs]:
                cell = root / f"{sid}-{variant.replace(':', '_')}-{uuid.uuid4().hex[:4]}"
                shutil.rmtree(cell, ignore_errors=True)
                cell.mkdir(parents=True)
                reaper.register(cell)
                ws = provision_workspace(sc, cell)
                if variant == "reference":
                    shutil.copytree(reference_root(sc) / sid, ws, dirs_exist_ok=True)
                    template_workspace(ws, template_values(sc, cell))
                elif variant.startswith("neg:"):
                    shutil.copytree(NEGATIVE_LIVE / sid / variant[4:], ws, dirs_exist_ok=True)
                    template_workspace(ws, template_values(sc, cell))
                t = time.monotonic()
                verdicts, primary = grade(sc, ws, cell / "grader_out", cell)
                reaper.unregister(cell)
                reaper.sweep(only_cell=cell, force=True)
                expect = variant == "reference"
                good = primary == expect
                ok_all &= good
                rp = next((v for v in verdicts if v["type"] == "robot_pass"), {})
                rec = {"primary": primary, "checks": f"{sum(v['passed'] for v in verdicts)}/{len(verdicts)}",
                       "first_pass": rp.get("first_pass"), "flaky": rp.get("flaky"),
                       "durations_s": rp.get("durations_s"), "grade_s": round(time.monotonic() - t, 1),
                       "failed_checks": [v.get("label") or v["type"] for v in verdicts if not v["passed"]],
                       "robot_detail": rp.get("detail", "")[:400]}
                if variant == "reference":
                    summary[sid]["reference"].append(rec)
                elif variant.startswith("neg:"):
                    rec["journey"] = {v["part"]: {"passed": v["passed"], "detail": v["detail"][:300]}
                                      for v in verdicts if v["type"] == "journey"}
                    summary[sid]["negatives"][variant[4:]] = rec
                else:
                    summary[sid]["pristine"] = rec
                print(f"{'OK ' if good else 'BAD'} {sid:16s} {variant:9s} primary={primary} "
                      f"({rec['checks']}) first_pass={rec['first_pass']} flaky={rec['flaky']} "
                      f"robot_s={rec['durations_s']} {rec['grade_s']:.1f}s", flush=True)
                for v in verdicts:
                    if (variant == "reference" and runs == 1) or not v["passed"] \
                            or (variant.startswith("neg:") and v["type"] in ("journey", "robot_pass")):
                        print(f"      {'+' if v['passed'] else '-'} {v['type']:22s} "
                              f"{(v.get('label') or '')[:30]} {v['detail'][:220]}")
                if PRUNE:
                    shutil.rmtree(cell, ignore_errors=True)
            refs = summary[sid]["reference"]
            if refs:
                fp = sum(1 for r in refs if r["first_pass"] or (r["first_pass"] is None and r["primary"]))
                summary[sid]["reference_first_pass"] = f"{fp}/{len(refs)}"
                summary[sid]["reference_pass_with_retry"] = f"{sum(1 for r in refs if r['primary'])}/{len(refs)}"
                d1 = [r["durations_s"][0] for r in refs if r.get("durations_s")]
                summary[sid]["robot_s_first_attempt"] = d1
                print(f"   == {sid}: reference first-attempt pass {summary[sid]['reference_first_pass']}, "
                      f"with retry {summary[sid]['reference_pass_with_retry']}, robot s {d1}", flush=True)
        shutil.rmtree(root, ignore_errors=True)
    if out_json:
        out_json.write_text(json.dumps({"at": _now(), "runs": runs, "scenarios": summary}, indent=1),
                            encoding="utf-8")
    return ok_all


def check_scenarios() -> bool:
    spec = importlib.util.spec_from_file_location("old_harness", OLD_HARNESS)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["old_harness"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    ok = True
    for s in SCENARIOS:
        o = mod.SCEN_BY_ID[s.id]
        diffs = [f for f in ("prompt", "graders", "primary_metric", "timeout_s", "max_turns", "fixture", "tier")
                 if getattr(o, f) != getattr(s, f)]
        ok &= not diffs
        print(f"{'IDENTICAL' if not diffs else 'DIFFERENT'} {s.id}: {diffs or ''}")
    return ok


def check_mcp(timeout_s: int = 180) -> bool:
    """Raw MCP stdio handshake against RF_MCP_CMD: initialize + tools/list."""
    env = _clean_env()
    env["ROBOTMCP_SCREENSHOT_MODE"] = "disabled"
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(PW_BROWSERS)
    t0 = time.monotonic()
    p = subprocess.Popen(RF_MCP_CMD, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, start_new_session=True)
    result: dict[str, Any] = {"cmd": RF_MCP_CMD}
    err_chunks: list[bytes] = []
    threading.Thread(target=lambda: err_chunks.append(p.stderr.read()), daemon=True).start()

    def send(obj):
        p.stdin.write((json.dumps(obj) + "\n").encode())
        p.stdin.flush()

    def recv(want_id):
        while True:
            line = p.stdout.readline()
            if not line:
                return None
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("id") == want_id:
                return d

    timer = threading.Timer(timeout_s, lambda: _killpg(p.pid))
    timer.start()
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "ab-harness", "version": HARNESS_VERSION}}})
        init = recv(1)
        result["init_s"] = round(time.monotonic() - t0, 1)
        result["server"] = (init or {}).get("result", {}).get("serverInfo")
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tl = recv(2)
        tools = [t["name"] for t in (tl or {}).get("result", {}).get("tools", [])]
        result["tools_n"] = len(tools)
        result["tools"] = tools
        result["total_s"] = round(time.monotonic() - t0, 1)
    finally:
        timer.cancel()
        _killpg(p.pid)
    time.sleep(0.5)
    result["stderr_tail"] = b"".join(err_chunks).decode(errors="replace")[-400:]
    print(json.dumps(result, indent=1))
    return bool(result.get("tools_n"))


PROBE_PROMPT = ("Run the shell command `echo PONG` exactly once, then reply with exactly the single word "
                "PONG and nothing else.")
PROBE_MCP_PROMPT = ("Use the `robotmcp` MCP server: call its `find_keywords` tool once with the query "
                    "'Click' (any arguments the tool needs). Do not use the shell. Then reply with the "
                    "word PONG followed by the number of keywords the tool returned.")


def probe(agents: list[str], with_mcp: bool) -> None:
    """Cheap per-agent check: auth + model availability (+ MCP wiring when with_mcp)."""
    sc = Scenario(id="probe", skill="", tier="probe", fixture="sut-results-complex",
                  prompt=PROBE_MCP_PROMPT if with_mcp else PROBE_PROMPT, graders=[],
                  primary_metric="all", timeout_s=300, max_turns=6)
    with HarnessLock(WORK_ROOT):
        reaper = Reaper(WORK_ROOT)
        for agent in agents:
            cell = WORK_ROOT / "_probe" / f"{agent}-{'mcp' if with_mcp else 'plain'}-{uuid.uuid4().hex[:4]}"
            cell.mkdir(parents=True)
            reaper.register(cell)
            home = None
            try:
                ws = provision_workspace(sc, cell)
                home = prepare_agent_home(agent, cell)
                write_agent_config(agent, ws, home, cell, with_mcp)
                or_before = OR.key_usage(ensure_or_key()) if is_or(agent) else None
                run = run_agent(agent, sc, ws, home, cell, with_mcp, [], {})
                m, calls, info = parse_transcript(base_agent(agent), cell / "agent_stdout.log")
                orr = or_cost(agent, m, info, or_before) if is_or(agent) else None
                cs = summarize_calls(calls)
                err = (cell / "agent_stderr.log").read_text(errors="replace")[-300:]
                if OR_KEY:
                    err = OR.scrub(err, OR_KEY)
                print(json.dumps({"agent": agent, "model": agent_model(agent), "exit": run.get("exit_code"),
                                  "wall_s": run.get("wall_s"), "final": (m.get("final_text") or "")[:120],
                                  "mcp_calls": cs["mcp_calls"], "mcp_tools": cs["mcp_tools"],
                                  "tools": [c["tool"] for c in calls][:8], "turns": m.get("turns"),
                                  "in_tok": m.get("in_tok"), "out_tok": m.get("out_tok"),
                                  "mcp_servers": _cut(info.get("mcp_servers"), 300),
                                  "model_seen": info.get("model_seen"), "errors": info.get("errors"),
                                  "orphans_killed": run.get("orphans_killed"),
                                  **({"openrouter": orr} if orr else {}),
                                  "api_key_source": info.get("api_key_source"),
                                  "stderr_tail": err if run.get("exit_code") not in (0,) else ""}), flush=True)
            finally:
                if home is not None:
                    scrub_credentials(agent, home)
                reaper.unregister(cell)
                reaper.sweep(only_cell=cell, force=True)
                if PRUNE:
                    shutil.rmtree(cell, ignore_errors=True)
        if PRUNE:
            shutil.rmtree(WORK_ROOT / "_probe", ignore_errors=True)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _add_common(p) -> None:
    p.add_argument("--tag", default=None, help="results_rc_<tag>.jsonl + work_rc_<tag> (isolate a run set); "
                                               "live scenarios: results_live_<tag>.jsonl + work_live_<tag>")
    for a in AGENTS:
        p.add_argument(f"--{a}-model", default=None)
    p.add_argument("--codex-effort", default=None, help="minimal|low|medium|high|xhigh")
    p.add_argument("--opencode-variant", default=None)
    p.add_argument("--no-prune", action="store_true", help="keep cell dirs (default: prune)")
    p.add_argument("--no-transcripts", action="store_true", help="do not archive gz transcripts")
    p.add_argument("--browser-concurrency", type=int, default=None,
                   help=f"max concurrent browser cells (default {BROWSER_CONCURRENCY})")
    p.add_argument("--max-turns", type=int, default=None,
                   help="override max_turns (Claude Code --max-turns) for the selected scenarios")
    p.add_argument("--timeout-s", type=int, default=None, help="override the per-cell agent timeout")
    p.add_argument("--or-models", default=None,
                   help="OpenRouter models for cc-or:<short> / oc-or:<short> agents: ids or short=id pairs, "
                        f"comma-separated (default {OR.DEFAULT_MODELS}; short = last path segment)")
    p.add_argument("--or-budget-usd", type=float, default=None,
                   help=f"stop scheduling OpenRouter cells once the account usage since the batch start exceeds this "
                        f"(default {OR_BUDGET_USD:g}); exit code 4 when cells were skipped")
    p.add_argument("--or-budget-reset", action="store_true",
                   help="start a new budget baseline (default: keep the baseline of this results file across restarts)")
    p.add_argument("--or-env-file", default=None, help=f"where OPENROUTER_API_KEY is read from (default {OR.ENV_FILE})")


def _apply_overrides(args, live: bool = False) -> None:
    global CODEX_EFFORT, OPENCODE_VARIANT, RESULTS, WORK_ROOT, PRUNE, KEEP_TRANSCRIPTS, TRANSCRIPTS
    global BROWSER_CONCURRENCY, OR_MODELS, OR_BUDGET_USD, OR_BUDGET_RESET
    if getattr(args, "or_models", None):
        OR_MODELS = OR.parse_models(args.or_models)
    if getattr(args, "or_budget_usd", None) is not None:
        OR_BUDGET_USD = float(args.or_budget_usd)
    OR_BUDGET_RESET = bool(getattr(args, "or_budget_reset", False))
    if getattr(args, "or_env_file", None):
        OR.ENV_FILE = Path(args.or_env_file)
    PRUNE = not getattr(args, "no_prune", False)
    KEEP_TRANSCRIPTS = not getattr(args, "no_transcripts", False)
    for a in AGENTS:
        v = getattr(args, f"{a}_model", None)
        if v:
            AGENT_MODELS[a] = v
    if getattr(args, "codex_effort", None) is not None:
        CODEX_EFFORT = args.codex_effort
    if getattr(args, "opencode_variant", None) is not None:
        OPENCODE_VARIANT = args.opencode_variant
    if getattr(args, "browser_concurrency", None):
        BROWSER_CONCURRENCY = args.browser_concurrency
    tag = getattr(args, "tag", None)
    if live:                                   # round 2: separate results / transcripts / work root
        sfx = f"_{tag}" if tag else ""
        RESULTS = HERE / f"results_live{sfx}.jsonl"
        TRANSCRIPTS = HERE / f"transcripts_live{sfx}"
        WORK_ROOT = Path.home() / ".cache" / "ab-eval" / f"work_live{sfx}"
    elif tag:
        RESULTS = HERE / f"results_rc_{tag}.jsonl"
        TRANSCRIPTS = HERE / f"transcripts_rc_{tag}"
        WORK_ROOT = Path.home() / ".cache" / "ab-eval" / f"work_rc_{tag}"
    _log(f"[config] models={AGENT_MODELS} codex_effort={CODEX_EFFORT!r} opencode_variant={OPENCODE_VARIANT!r} "
         f"results={RESULTS} work={WORK_ROOT} prune={PRUNE} browser_concurrency={BROWSER_CONCURRENCY} "
         f"or_models={OR_MODELS} or_budget_usd={OR_BUDGET_USD:g}")


def main() -> None:
    ap = argparse.ArgumentParser(description="A/B/C harness: neither vs rf-mcp vs skillpkg (vs hookpkg)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    scen_help = ("comma-separated scenario ids and/or aliases: round1 (default), live, explore, debug; "
                 f"live ids: {', '.join(s.id for s in LIVE_SCENARIOS)}")

    p_run = sub.add_parser("run", help="run the (partial) matrix")
    p_run.add_argument("--reps", type=int, default=5)
    p_run.add_argument("--agents", default=",".join(AGENTS))
    p_run.add_argument("--scenarios", default=",".join(s.id for s in SCENARIOS), help=scen_help)
    p_run.add_argument("--arms", default=",".join(ARMS))
    p_run.add_argument("--concurrency", type=int, default=CONCURRENCY)
    _add_common(p_run)

    p_pil = sub.add_parser("pilot", help="1 rep of the grid into results_rc_pilot.jsonl (live: results_live_pilot)")
    p_pil.add_argument("--agents", default=",".join(AGENTS))
    p_pil.add_argument("--scenarios", default=",".join(s.id for s in SCENARIOS), help=scen_help)
    p_pil.add_argument("--arms", default=",".join(ARMS))
    p_pil.add_argument("--concurrency", type=int, default=CONCURRENCY)
    _add_common(p_pil)

    p_ver = sub.add_parser("verify-ref", help="grade hidden reference (must pass) + pristine fixture (must fail)")
    p_ver.add_argument("--scenarios", default=",".join(s.id for s in SCENARIOS), help=scen_help)
    p_ver.add_argument("--runs", type=int, default=1, help="grade the reference N times (live flakiness)")
    p_ver.add_argument("--json", default=None, help="write the verification summary here")
    p_ver.add_argument("--negatives", action="store_true",
                       help="also grade the negative-control suites in fixtures_live/_negative/ (must fail)")
    p_ver.add_argument("--no-pristine", action="store_true", help="skip grading the pristine fixture")
    p_ver.add_argument("--tag", default=None)
    sub.add_parser("check-scenarios", help="prove prompts/graders are identical to the eval#3/#4 harness")
    sub.add_parser("check-mcp", help="raw stdio MCP handshake with rf-mcp")
    p_pr = sub.add_parser("probe", help="per-agent auth/model (+ --mcp wiring) check")
    p_pr.add_argument("--agents", default=",".join(AGENTS))
    p_pr.add_argument("--mcp", action="store_true")
    _add_common(p_pr)
    p_reap = sub.add_parser("reap", help="one-shot: kill every leftover process of any cell under WORK_ROOT")
    p_reap.add_argument("--tag", default=None)
    p_reap.add_argument("--live", action="store_true", help="the live round's work root (work_live[_tag])")
    p_reap.add_argument("--dry-run", action="store_true", help="only list what would be killed")

    args = ap.parse_args()
    if args.cmd == "pilot" and not args.tag:
        args.tag = "pilot"
    scen_ids = expand_scenarios(args.scenarios) if hasattr(args, "scenarios") else []
    for sid in scen_ids:
        if sid not in SCEN_BY_ID:
            raise SystemExit(f"unknown scenario {sid!r}; {scen_help}")
    live = bool(scen_ids) and all(SCEN_BY_ID[s].live for s in scen_ids)
    if scen_ids and not live and any(SCEN_BY_ID[s].live for s in scen_ids):
        raise SystemExit("do not mix round-1 and live scenarios in one invocation (separate results files)")
    _apply_overrides(args, live=live or getattr(args, "live", False))
    for sid in scen_ids:                       # per-invocation budget overrides (recorded in each row)
        if getattr(args, "max_turns", None):
            SCEN_BY_ID[sid].max_turns = args.max_turns
        if getattr(args, "timeout_s", None):
            SCEN_BY_ID[sid].timeout_s = args.timeout_s
    if args.cmd in ("run", "pilot"):
        run_batch(1 if args.cmd == "pilot" else args.reps, expand_agents(args.agents),
                  scen_ids, args.arms.split(","), args.concurrency)
        if OR_SKIPPED["n"]:
            _log(f"[openrouter] exit 4: {OR_SKIPPED['n']} OpenRouter cells not run (budget ${OR_BUDGET_USD:.2f})")
            sys.exit(4)
    elif args.cmd == "verify-ref":
        out = Path(args.json) if args.json else None
        sys.exit(0 if verify_reference(scen_ids, runs=args.runs, out_json=out, negatives=args.negatives,
                                       pristine=not args.no_pristine) else 1)
    elif args.cmd == "check-scenarios":
        sys.exit(0 if check_scenarios() else 1)
    elif args.cmd == "check-mcp":
        sys.exit(0 if check_mcp() else 1)
    elif args.cmd == "probe":
        probe(expand_agents(args.agents), args.mcp)
    elif args.cmd == "reap":
        if args.dry_run:   # no lock needed to look
            print(json.dumps(Reaper(WORK_ROOT).sweep(dry_run=True), indent=1))
        else:
            with HarnessLock(WORK_ROOT):
                print(json.dumps(Reaper(WORK_ROOT).sweep(), indent=1))


if __name__ == "__main__":
    main()
