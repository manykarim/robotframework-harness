"""OpenRouter helpers for the A/B harness and the hookpkg31 smoke runner (research driver, stdlib only).

Agents routed through OpenRouter:
  cc-or:<short>  Claude Code against an OpenRouter model (OpenRouter's Claude Code integration): isolated
                 CLAUDE_CONFIG_DIR WITHOUT subscription credentials, ANTHROPIC_BASE_URL=https://openrouter.ai/api,
                 ANTHROPIC_AUTH_TOKEN=<key>, ANTHROPIC_API_KEY="" (empty), ANTHROPIC_MODEL + small/fast/haiku/sonnet/opus
                 /subagent model = the same id, nonessential traffic disabled.
  oc-or:<short>  OpenCode's native OpenRouter provider (`-m openrouter/<id>`, key via OPENROUTER_API_KEY in the
                 process env, model registered in the cell's opencode.json without any key).

SECRETS: the key is read at runtime from the process env (OPENROUTER_API_KEY) or from the .env file
(~/workspace/rf-mcp/.env; only the OPENROUTER_* lines are parsed). It is only ever passed via a child
process environment -- never printed, logged or written (cmd.json / results / prices cache hold no key). The /key
endpoint's `label` (a masked key fragment) is never kept. `scrub()` removes the key (and any OpenRouter-key-shaped token) from text.

Cost: per-cell estimate = tokens x the model's OpenRouter prices (GET /api/v1/models, cached in or_prices.json) and,
independently, the account usage delta of GET /api/v1/key before/after the cell (includes every concurrent
OpenRouter cell and lags a few seconds -> a cross-check, not a per-cell truth when cells overlap).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

HERE = Path(__file__).resolve().parent
ENV_FILE = Path(os.environ.get("AB_OR_ENV_FILE") or "~/workspace/rf-mcp/.env")
DEFAULT_API = "https://openrouter.ai/api/v1"
ANTHROPIC_BASE = "https://openrouter.ai/api"          # Claude Code appends /v1/messages
PRICES_CACHE = HERE / "or_prices.json"
ROUTES = {"cc-or": "claude", "oc-or": "opencode"}
DEFAULT_MODELS = "deepseek/deepseek-v4.1-flash,qwen/qwen3.8-flash,z-ai/glm-5.3-flash,google/gemini-3.8-flash"
KEY_PREFIX = "sk-" + "or-"                             # (built, so greps for the literal prefix stay clean)
_KEY_RX = re.compile(re.escape(KEY_PREFIX) + r"[A-Za-z0-9_\-]{8,}")


# ------------------------------------------------------------------------------------------------ key / base url
def _env_file_vars(path: Path = ENV_FILE) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*(?:export\s+)?(OPENROUTER_[A-Z_]+)\s*=\s*(.*?)\s*$", line)
            if m:
                v = m.group(2)
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                out[m.group(1)] = v
    except OSError:
        pass
    return out


def load_key(env_file: Optional[Path] = None) -> Optional[str]:
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k.strip()
    return (_env_file_vars(env_file or ENV_FILE).get("OPENROUTER_API_KEY") or "").strip() or None


def api_base(env_file: Optional[Path] = None) -> str:
    return (os.environ.get("OPENROUTER_BASE_URL") or _env_file_vars(env_file or ENV_FILE).get("OPENROUTER_BASE_URL")
            or DEFAULT_API).rstrip("/")


def scrub(text: str, key: Optional[str] = None) -> str:
    if not text:
        return text
    if key:
        text = text.replace(key, "<OPENROUTER_KEY>")
    return _KEY_RX.sub("<redacted-openrouter-key>", text)


def _get(path: str, key: Optional[str] = None, timeout: float = 20.0) -> Dict[str, Any]:
    req = urllib.request.Request(api_base() + path, headers={"Accept": "application/json",
                                                             **({"Authorization": f"Bearer {key}"} if key else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ------------------------------------------------------------------------------------------------ usage / budget
def key_info(key: str) -> Dict[str, Any]:
    """{usage, limit, limit_remaining} in USD (the masked `label` is dropped on purpose); {} on error."""
    try:
        d = (_get("/key", key) or {}).get("data") or {}
    except (urllib.error.URLError, OSError, ValueError):
        return {}
    return {k: d.get(k) for k in ("usage", "limit", "limit_remaining", "usage_daily") if k in d}


def account_balance(key: str) -> Optional[float]:
    """Account-wide credit balance in USD (total_credits - total_usage, /credits); None on error. A key with
    limit_remaining > 0 still gets HTTP 402 once the ACCOUNT balance is used up (2026-10-10: 64 cells lost)."""
    try:
        d = (_get("/credits", key) or {}).get("data") or {}
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(d.get("total_credits"), (int, float)) or not isinstance(d.get("total_usage"), (int, float)):
        return None
    return round(float(d["total_credits"]) - float(d["total_usage"]), 4)


def key_usage(key: str) -> Optional[float]:
    u = key_info(key).get("usage")
    return float(u) if isinstance(u, (int, float)) else None


def settled_usage(key: str, before: Optional[float], wait_s: float = 40.0, step: float = 6.0) -> Optional[float]:
    """usage after a cell: OpenRouter books credits asynchronously and in pieces -- poll until the usage moved past
    `before` AND two readings `step` s apart agree (or `wait_s` is over)."""
    t_end = time.monotonic() + wait_s
    u = key_usage(key)
    last = None
    while time.monotonic() < t_end:
        moved = before is None or (u is not None and u > before)
        if moved and last is not None and u == last:
            break
        last = u
        time.sleep(step)
        u = key_usage(key)
    return u


class Budget:
    """--or-budget-usd: stop scheduling new OpenRouter cells once the account usage since the batch start exceeds the
    budget. The baseline survives restarts (state file per tag, no secrets)."""

    def __init__(self, key: str, budget_usd: float, state: Path, reset: bool = False, cache_s: float = 15.0):
        self.key, self.budget, self.state, self.cache_s = key, float(budget_usd), state, cache_s
        self._t, self._u = 0.0, None
        self.exhausted = False
        data = {}
        if state.exists() and not reset:
            try:
                data = json.loads(state.read_text())
            except (OSError, ValueError):
                data = {}
        if not isinstance(data.get("baseline_usage"), (int, float)):
            u = key_usage(key)
            data = {"baseline_usage": u if u is not None else 0.0, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        data["budget_usd"] = self.budget
        self.baseline = float(data["baseline_usage"])
        state.write_text(json.dumps(data, indent=1))

    def spent(self, fresh: bool = False) -> Optional[float]:
        if fresh or self._u is None or time.monotonic() - self._t > self.cache_s:
            u = key_usage(self.key)
            if u is not None:
                self._u, self._t = u, time.monotonic()
        return None if self._u is None else round(self._u - self.baseline, 4)

    def allow(self) -> bool:
        s = self.spent()
        if s is not None and s >= self.budget:
            self.exhausted = True
        return not self.exhausted


# ------------------------------------------------------------------------------------------------ prices / cost
def prices(refresh: bool = False, max_age_s: float = 86400.0) -> Dict[str, Dict[str, float]]:
    """model id -> USD per token {prompt, completion, input_cache_read, input_cache_write} (cached, no secrets)."""
    if not refresh and PRICES_CACHE.exists() and time.time() - PRICES_CACHE.stat().st_mtime < max_age_s:
        try:
            return json.loads(PRICES_CACHE.read_text())["prices"]
        except (OSError, ValueError, KeyError):
            pass
    try:
        data = _get("/models", None, timeout=30).get("data") or []
    except (urllib.error.URLError, OSError, ValueError):
        try:
            return json.loads(PRICES_CACHE.read_text())["prices"]
        except (OSError, ValueError, KeyError):
            return {}
    out: Dict[str, Dict[str, float]] = {}
    for m in data:
        p = m.get("pricing") or {}
        row = {}
        for k in ("prompt", "completion", "input_cache_read", "input_cache_write", "internal_reasoning"):
            try:
                if p.get(k) not in (None, ""):
                    row[k] = float(p[k])
            except (TypeError, ValueError):
                pass
        if row:
            out[m["id"]] = row
    try:
        PRICES_CACHE.write_text(json.dumps({"fetched": time.strftime("%Y-%m-%d %H:%M:%S"), "prices": out}))
    except OSError:
        pass
    return out


def estimate_cost(model_id: str, in_uncached: Optional[int], out_tok: Optional[int], cache_read: Optional[int] = 0,
                  cache_write: Optional[int] = 0, table: Optional[Dict[str, Dict[str, float]]] = None
                  ) -> Optional[float]:
    p = (table if table is not None else prices()).get(model_id)
    if not p or "prompt" not in p:
        return None
    pr, co = p["prompt"], p.get("completion", 0.0)
    cr = p.get("input_cache_read", pr)
    cw = p.get("input_cache_write", pr)
    usd = (in_uncached or 0) * pr + (cache_write or 0) * cw + (cache_read or 0) * cr + (out_tok or 0) * co
    return round(usd, 6)


# ------------------------------------------------------------------------------------------------ agents
def parse_models(spec: Optional[str]) -> Dict[str, str]:
    """'a/b-c,x/y' or 'short=a/b-c,...' -> {short: id}; short defaults to the id's last path segment."""
    out: Dict[str, str] = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            short, mid = (x.strip() for x in part.split("=", 1))
        else:
            mid = part
            short = part.rsplit("/", 1)[-1]
        short = re.sub(r"[^A-Za-z0-9._-]", "-", short)
        out[short] = mid
    return out


def split_agent(agent: str) -> Tuple[Optional[str], Optional[str]]:
    """'cc-or:qwen3.8-flash' -> ('cc-or', 'qwen3.8-flash'); plain agents -> (None, None)."""
    if ":" in agent:
        route, short = agent.split(":", 1)
        if route in ROUTES:
            return route, short
    return None, None


def claude_code_env(model_id: str, key: str) -> Dict[str, str]:
    """env for Claude Code against OpenRouter (merge AFTER the cell env; never write it to disk)."""
    return {"ANTHROPIC_BASE_URL": ANTHROPIC_BASE, "ANTHROPIC_AUTH_TOKEN": key, "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_MODEL": model_id, "ANTHROPIC_SMALL_FAST_MODEL": model_id,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model_id, "ANTHROPIC_DEFAULT_SONNET_MODEL": model_id,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model_id, "CLAUDE_CODE_SUBAGENT_MODEL": model_id,
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
            "DISABLE_AUTOUPDATER": "1"}


def claude_code_home_json() -> Dict[str, Any]:
    """minimal .claude.json for an OpenRouter-routed Claude Code home: onboarding done, NO account / oauth data."""
    return {"hasCompletedOnboarding": True, "bypassPermissionsModeAccepted": True, "numStartups": 1,
            "autoUpdates": False}


def opencode_provider_cfg(model_id: str) -> Dict[str, Any]:
    """opencode.json fragment registering the model with the native openrouter provider. The key is an `{env:...}`
    reference (no secret on disk); together with opencode_env() it beats a key stored in OpenCode's global auth.json
    (smoke finding: without it OpenCode billed the user's stored OpenRouter key, not OPENROUTER_API_KEY)."""
    return {"openrouter": {"options": {"apiKey": "{env:OPENROUTER_API_KEY}"},
                           "models": {model_id: {"name": model_id, "tool_call": True}}}}


def opencode_env(key: str, home: Path) -> Dict[str, str]:
    """env for an oc-or cell: the key + a cell-local XDG data dir (no global auth.json / session DB)."""
    data = Path(home) / "xdg_data"
    data.mkdir(parents=True, exist_ok=True)
    return {"OPENROUTER_API_KEY": key, "XDG_DATA_HOME": str(data)}


def redacted_env(env: Dict[str, str], key: Optional[str]) -> Dict[str, str]:
    return {k: ("<redacted>" if (key and v == key) or k in ("ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY") else v)
            for k, v in env.items()}
