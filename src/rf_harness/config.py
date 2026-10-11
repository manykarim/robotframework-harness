"""Registry of every RFH_* environment variable: the single source for runtime defaults and the docs reference.

Each runtime module reads its settings through `get()` / `get_float()` / `get_int()` / `get_bool()` / `get_list()`, so a
variable that is not registered here raises at import time in tests, and `docs/reference/environment.md` is generated
from `VARIABLES`. Defaults are the measured v3.2 prototype values (hookpkg32); change them only through the release
gate.

Precedence: the process environment, then the `env` object of the project's `.rf/harness.json` (written by the
installer, e.g. `{"python": ..., "version": ..., "env": {"RFH_STATIC": "runtime-only"}}`), then the registered default.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = ("live", "feedback", "profiles", "guards", "docs", "lint", "logging", "desktop", "general")
AGENTS = ("claude", "codex", "copilot", "opencode", "vscode")
HARNESS_JSON = Path(".rf") / "harness.json"


@dataclass(frozen=True)
class Var:
    name: str
    default: str
    doc: str
    category: str = "general"


VARIABLES: dict[str, Var] = {}
_PROJECT_ENV: dict[str, str] | None = None


def register(name: str, default: str, doc: str, category: str = "general") -> Var:
    if not name.startswith("RFH_"):
        raise ValueError(f"harness variables start with RFH_: {name}")
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r} for {name}; one of {', '.join(CATEGORIES)}")
    var = Var(name, default, doc, category)
    VARIABLES[name] = var
    return var


def get(name: str) -> str:
    var = VARIABLES.get(name)
    if var is None:
        raise KeyError(f"unregistered harness variable {name}; add it to rf_harness.config")
    value = os.environ.get(name)
    if value is not None:
        return value
    return project_env().get(name, var.default)


def find_harness_json(start: str | os.PathLike[str] | None = None) -> Path | None:
    """`.rf/harness.json` of the project: in RFH_ROOT / CLAUDE_PROJECT_DIR when set, else in `start` (default: the
    cwd) or one of its six nearest parents."""
    # os.environ directly, not get(): get() consults project_env(), which calls this function
    env_root = os.environ.get("RFH_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
    if start is None and env_root and Path(env_root).is_dir():
        candidates = [Path(env_root)]
    else:
        base = Path(start or os.getcwd()).absolute()
        candidates = [base, *list(base.parents)[:6]]
    for d in candidates:
        f = d / HARNESS_JSON
        if f.is_file():
            return f
    return None


def load_project_env(path: Path | None) -> dict[str, str]:
    """RFH_* entries of the `env` object in a harness.json (anything unreadable or malformed is ignored)."""
    if path is None:
        return {}
    try:
        env = (json.loads(path.read_text(encoding="utf-8")) or {}).get("env") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(env, dict):
        return {}
    return {str(k): str(v) for k, v in env.items()
            if str(k).startswith("RFH_") and isinstance(v, (str, int, float, bool))}


def project_env() -> dict[str, str]:
    """Project defaults from `.rf/harness.json` (discovered once per process, see find_harness_json)."""
    global _PROJECT_ENV
    if _PROJECT_ENV is None:
        _PROJECT_ENV = load_project_env(find_harness_json())
    return _PROJECT_ENV


def set_project_root(root: str | os.PathLike[str] | None) -> None:
    """Use `<root>/.rf/harness.json` from now on (None: rediscover on next access; tests)."""
    global _PROJECT_ENV
    _PROJECT_ENV = None if root is None else load_project_env(Path(root) / HARNESS_JSON)


def get_float(name: str) -> float:
    try:
        return float(get(name))
    except ValueError:
        return float(VARIABLES[name].default)


def get_int(name: str) -> int:
    return int(get_float(name))


def get_bool(name: str) -> bool:
    return get(name).strip().lower() not in ("0", "false", "no", "off", "")


def get_list(name: str) -> list[str]:
    """Comma-separated value; an empty value means the default (like the prototype's `os.environ.get(X) or default`)."""
    return (get(name) or VARIABLES[name].default).split(",")


def is_registered(name: str) -> bool:
    return name in VARIABLES


# ---------------------------------------------------------------------------------------------------- general
register("RFH_ROOT", "", "Project root; default: CLAUDE_PROJECT_DIR, else the nearest parent of the hook's cwd that "
         "already has .rf/hook, else the cwd.", "general")
register("RFH_PYTHON", "", "Interpreter for the helper daemons and doc workers; default: the hook's own interpreter.",
         "general")
register("RFH_WATCH_PID", "", "PID of the agent process the daemons watch (they exit when it is gone); 0 disables the "
         "watch; default: detected from the hook's ancestors.", "general")
register("RFH_TOKEN", "", "Internal: random per-daemon token set in the daemons' environment to find and clean up "
         "their child processes. Do not set it.", "general")
register("RFH_FORCE_REPL", "0", "1 activates the REPL-only short-timeout listener also outside `robotcode repl|shell` "
         "(tests only).", "general")

# ---------------------------------------------------------------------------------------------------- live session
register("RFH_BUDGET", "90", "Maximum seconds a PostToolUse hook waits for live results before reporting 'still "
         "running' (the result is delivered with the next hook event).", "live")
register("RFH_IDLE_EXIT", "1200", "Seconds without requests after which the helper daemons exit.", "live")
register("RFH_SHORT_TIMEOUTS", "1", "0 disables the short live element timeouts (live and REPL listener).", "live")
register("RFH_SHORT_TIMEOUT", "2.5", "Live element-keyword timeout in seconds (Browser).", "live")
register("RFH_SHORT_TIMEOUT_SELENIUM", "", "Live element timeout for SeleniumLibrary; default: RFH_SHORT_TIMEOUT.",
         "live")
register("RFH_STABLE_S", "2", "Seconds without DOM change after which a page counts as stable (a missing element on a "
         "stable page is MISSING at once).", "live")
register("RFH_ADAPT_FACTOR", "1.5", "A late element raises the site's learned short timeout to this factor times its "
         "observed latency.", "live")
register("RFH_FRESH_DOC_S", "6", "A document younger than this many seconds is not yet considered stable.", "live")
register("RFH_MAX_CAPTURES", "2", "Maximum page captures per edit (failure + end of run).", "live")
register("RFH_STATE_HISTORY", "15", "Number of step-* capture directories kept in .rf/state.", "live")
register("RFH_CAPTURE", "end", "Page capture mode: end (after the last step and on failures), step (after every "
         "page keyword) or off.", "live")
register("RFH_CAPTURE_SETTLE", "1.5", "Maximum seconds the end-of-run capture waits for the page to settle.", "live")
register("RFH_CAPTURE_GATE", "1", "0 captures after every page keyword (v2 behavior) instead of only on navigation, "
         "failures and real DOM changes.", "live")
register("RFH_GUARD_SETTLE", "5.0", "Seconds the pre-execution guard lets a page settle between back-to-back file "
         "lines.", "live")
register("RFH_PAGE_TEXT", "4000", "Maximum characters of visible page text in .rf/state/latest/page.txt.", "live")

# ---------------------------------------------------------------------------------------------------- feedback
register("RFH_MAX_CONTEXT", "2048", "Maximum characters of any hook context returned to the agent.", "feedback")
register("RFH_MAX_CONTEXT_OPENCODE", "1200", "Maximum characters of hook context for OpenCode.", "feedback")
register("RFH_LEAN", "1", "0 switches to the v2 output format (ablation only).", "feedback")
register("RFH_REPRODUCE", "1", "0 disables the live reproduction of the first failure of a plain robot run.",
         "feedback")
register("RFH_LOOP_AT", "3", "Number of identical failures after which the one-time loop hint is shown.", "feedback")
register("RFH_READ_STREAK_AT", "8", "Consecutive reads without an edit or command after which a note is added "
         "(again at twice the value); 0 disables it.", "feedback")
register("RFH_COMPACT_AGENTS", "opencode", "Comma-separated agents that get the compact v2 output and image-read "
         "guard.", "feedback")
register("RFH_RFMCP_HINTS", "0", "1 adds hints from the vendored rf-mcp hint engine (runtime/hints.py) to live failures. "
         "Off by default: the measured v3.2 prototype ran without it.", "feedback")
register("RFH_GUIDANCE_FIRST", "opencode", "Comma-separated agents whose feedback starts with the guidance "
         "(hint, NEXT:).", "feedback")
for _agent in AGENTS:
    register(f"RFH_MAX_CTX_{_agent.upper()}", "", f"Lean-profile budget for {_agent} as 'ok,fail' characters; default: "
             "the per-agent caps in leanfmt.", "feedback")
register("RFH_MAX_CTX_RICH", "", "Rich-profile budget as 'ok,fail' characters for every agent; default 1200,1200.",
         "feedback")
for _agent in AGENTS:
    register(f"RFH_MAX_CTX_RICH_{_agent.upper()}", "", f"Rich-profile budget for {_agent} as 'ok,fail' characters "
             "(RFH_MAX_CTX_RICH wins).", "feedback")
del _agent

# ---------------------------------------------------------------------------------------------------- profiles
register("RFH_PROFILE", "", "Force the output profile: lean or rich; default: chosen from the model in use.",
         "profiles")
register("RFH_MODEL", "", "Model id used for the profile choice; default: from the hook payload, the agent's "
         "environment, transcript or config.", "profiles")

# ---------------------------------------------------------------------------------------------------- guards
register("RFH_RELAXED_DENIALS", "1", "0 restores the v2 denial policy (refuse every static finding; ablation only).",
         "guards")
register("RFH_DENY_CODES", "TokenError,ParsingError,InvalidHeader,ModelError", "Comma-separated static-analysis codes "
         "that refuse an edit; every other finding is a one-line warning.", "guards")
register("RFH_REWRITE_AGENTS", "claude,opencode,codex,copilot", "Comma-separated agents whose tool input may be "
         "rewritten (deprecated-syntax fixes, REPL format fixes).", "guards")
register("RFH_MAX_DENIALS", "3", "Refusals of the same kind before the edit or command is let through with a note.",
         "guards")
register("RFH_MAX_DENIALS_OPENCODE", "2", "RFH_MAX_DENIALS for OpenCode.", "guards")
register("RFH_MAX_STOP_BLOCKS", "2", "How often the end of a turn is blocked for a missing green plain robot run.",
         "guards")

# ---------------------------------------------------------------------------------------------------- docs
register("RFH_DOC_WAIT", "1.2", "Seconds a hook waits for a keyword documentation file before naming its path "
         "anyway.", "docs")
register("RFH_KWDOC_FILES", "0", "1 writes .rf/docs/kw/<Owner>.<Keyword>.md on every failure (v2) instead of on "
         "demand.", "docs")

# ---------------------------------------------------------------------------------------------------- lint
register("RFH_STATIC", "on", "on: the harness checks edits statically (refusals for certainly-wrong structure, one-line "
         "warnings, deprecated-syntax fixes). runtime-only: only certainly-wrong structural edits are refused, no static "
         "warnings or fixes, and live runs execute lines without the static pre-check (used when rf-agentskills "
         "validates edits).", "lint")
register("RFH_GATE_TIMEOUT", "2.5", "Seconds the PreToolUse static gate waits for the lint daemon; on timeout the "
         "edit proceeds.", "lint")

# ---------------------------------------------------------------------------------------------------- desktop
# Read by rf_harness.runtime.desktop through its own _env.env_get (rf-mcp's exact truthiness rules); registered here
# for the docs reference. Name/default/doc copied from desktop/_env.py ENV_VARIABLES (a test keeps them in sync).
register("RFH_DESKTOP", "0", "Set to 1 to allow live desktop (PlatynUI) steps. Off by default until the vendored rf-mcp "
         "desktop guards pass their parity tests; even when on, every safety, isolation and focus guard still applies.",
         "desktop")
register("RFH_PLATYNUI_ISOLATED_DISPLAY", "", "Isolation marker: the X DISPLAY(s) (comma/space separated) the harness "
         "may drive, for example ':99'. Only counts when RFH_PLATYNUI_ISOLATED_XPID names the live X server for that "
         "display.", "desktop")
register("RFH_PLATYNUI_ISOLATED_XPID", "", "PID of the Xvfb/Xephyr/Xorg server that owns the isolated display. "
         "Corroborates the isolation marker; without it the display is classified 'unknown' and desktop input is "
         "refused.", "desktop")
register("RFH_PLATYNUI_ALLOW_ACTIVE_DESKTOP", "0", "Escape hatch: 1 allows desktop input on an 'active' or 'unknown' "
         "display (audited). Input may still target the wrong window on a shared desktop; prefer an isolated display.",
         "desktop")
register("RFH_PLATYNUI_SAFETY_GUARD", "enforce", "'warn' logs instead of refusing desktop input on a non-isolated "
         "display (transition mode).", "desktop")
register("RFH_PLATYNUI_REQUIRE_ISOLATED", "0", "Windows only: 1 refuses desktop input on the active Windows desktop "
         "(there is no nested-display model).", "desktop")
register("RFH_PLATYNUI_ALLOW_UNSCOPED", "0", "1 allows //-rooted desktop Query/Evaluate locators (whole-desktop walks) "
         "with a one-time warning.", "desktop")
register("RFH_PLATYNUI_ALLOW_PATH_DESCRIPTOR", "0", "1 allows an image path in the Take Screenshot descriptor slot "
         "with a one-time warning.", "desktop")
register("RFH_PLATYNUI_ALLOW_CONTROL_WINDOW", "0", "1 allows control:Window locators on Linux (AT-SPI windows are "
         "control:Frame) with a one-time warning.", "desktop")
register("RFH_PLATYNUI_NO_FOCUS", "0", "1 disables focus-before-act for desktop pointer/keyboard steps (the step is "
         "marked focus-bypassed).", "desktop")
register("RFH_PLATYNUI_HIGHLIGHT", "1", "0 disables highlighting the target element before desktop input.", "desktop")
register("RFH_PLATYNUI_KEEP_WAYLAND", "0", "1 keeps the native Wayland backend instead of forcing "
         "XDG_SESSION_TYPE=x11 before PlatynUI starts.", "desktop")
register("RFH_PLATYNUI_STEERING_CONFIDENCE", "enforce", "'warn' downgrades a 'contradicted' steering-confidence verdict "
         "from a step failure to a warning.", "desktop")
register("RFH_SCREENSHOT_DIR", "", "Extra directory desktop screenshots may be written to (the system temp dir is "
         "always allowed).", "desktop")

# ---------------------------------------------------------------------------------------------------- logging
register("RFH_HOOK_LOG", "", "Path of the JSONL hook event log; default: .rf/hook/hooks.jsonl.", "logging")
