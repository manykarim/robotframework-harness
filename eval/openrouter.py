"""OpenRouter helpers for the evaluation harness (eval/harness.py) and the resilient runner (stdlib only).

Ported from the research harness (rf-mcp-robotcode experiments/robotcode-remote/ab/harness/openrouter.py, round 7) with
the round-7 fixes:
  * per-run budgets (RunBudget): a run's budget counts only that run's own spend, i.e. the sum of its cells' provider
    usage deltas (/api/v1/key before/after the cell) or, when the delta is shared with other OpenRouter cells (Activity
    registry: any other OpenRouter cell active on this machine, in this or another run, during the cell), the token-based
    cost estimate. The state file keeps the run's per-cell spend, never an account-wide baseline;
  * a separate global guard (AccountGuard) for the key's limit and the ACCOUNT balance (/credits: total_credits -
    total_usage); below the minimum (AB_MIN_OR_BALANCE, default 0.5 USD) no new OpenRouter cells start;
  * `python3 openrouter.py balance-check` for the runner (exit 0 ok, 5 balance/limit below the minimum, 1 no usable key).

Agents routed through OpenRouter:
  cc-or:<short>  Claude Code against an OpenRouter model (OpenRouter's Claude Code integration): isolated
                 CLAUDE_CONFIG_DIR WITHOUT subscription credentials, ANTHROPIC_BASE_URL=https://openrouter.ai/api,
                 ANTHROPIC_AUTH_TOKEN=<key>, ANTHROPIC_API_KEY="" (empty), ANTHROPIC_MODEL + small/fast/haiku/sonnet/opus
                 /subagent model = the same id, nonessential traffic disabled.
  oc-or:<short>  OpenCode's native OpenRouter provider (`-m openrouter/<id>`, key via OPENROUTER_API_KEY in the
                 process env, model registered in the cell's opencode.json without any key).

SECRETS: the key is read at runtime from the process env (OPENROUTER_API_KEY) or from an .env file (AB_OR_ENV_FILE /
--or-env-file, default <repo>/.env; only the OPENROUTER_* lines are parsed). It is only ever passed via a child
process environment -- never printed, logged or written (cmd.json / results / prices cache hold no key). The /key
endpoint's `label` (a masked key fragment) is never kept. `scrub()` removes the key (and any OpenRouter-key-shaped token) from text.

Cost: per-cell estimate = tokens x the model's OpenRouter prices (GET /api/v1/models, cached in or_prices.json) and,
independently, the account usage delta of GET /api/v1/key before/after the cell (includes every concurrent
OpenRouter cell and lags a few seconds -> used for the run budget only when no other OpenRouter cell overlapped).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ENV_FILE = Path(os.environ.get("AB_OR_ENV_FILE") or (HERE.parent / ".env"))
DEFAULT_API = "https://openrouter.ai/api/v1"
ANTHROPIC_BASE = "https://openrouter.ai/api"          # Claude Code appends /v1/messages
PRICES_CACHE = Path(os.environ.get("AB_OR_PRICES_CACHE") or (Path(os.environ.get("AB_OUT_DIR") or HERE / "runs")
                                                             / "or_prices.json"))
ACTIVITY_FILE = Path(os.environ.get("AB_OR_ACTIVITY_FILE")
                     or (Path.home() / ".cache" / "ab-eval" / "or_activity.json"))
MIN_BALANCE_USD = float(os.environ.get("AB_MIN_OR_BALANCE", "0.5"))
EXIT_BALANCE = 5                                      # runner / harness exit code: balance or key limit too low
ROUTES = {"cc-or": "claude", "oc-or": "opencode"}
DEFAULT_MODELS = "deepseek/deepseek-v4.1-flash,qwen/qwen3.8-flash,z-ai/glm-5.3-flash,google/gemini-3.8-flash"
KEY_PREFIX = "sk-" + "or-"                             # (built, so greps for the literal prefix stay clean)
_KEY_RX = re.compile(re.escape(KEY_PREFIX) + r"[A-Za-z0-9_\-]{8,}")


# ------------------------------------------------------------------------------------------------ key / base url
def _env_file_vars(path: Path = ENV_FILE) -> dict[str, str]:
    out: dict[str, str] = {}
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


def load_key(env_file: Path | None = None) -> str | None:
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k.strip()
    return (_env_file_vars(env_file or ENV_FILE).get("OPENROUTER_API_KEY") or "").strip() or None


def api_base(env_file: Path | None = None) -> str:
    return (os.environ.get("OPENROUTER_BASE_URL") or _env_file_vars(env_file or ENV_FILE).get("OPENROUTER_BASE_URL")
            or DEFAULT_API).rstrip("/")


def scrub(text: str, key: str | None = None) -> str:
    if not text:
        return text
    if key:
        text = text.replace(key, "<OPENROUTER_KEY>")
    return _KEY_RX.sub("<redacted-openrouter-key>", text)


def _get(path: str, key: str | None = None, timeout: float = 20.0) -> dict[str, Any]:
    req = urllib.request.Request(api_base() + path, headers={"Accept": "application/json",
                                                             **({"Authorization": f"Bearer {key}"} if key else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ------------------------------------------------------------------------------------------------ usage / budget
def key_info(key: str) -> dict[str, Any]:
    """{usage, limit, limit_remaining} in USD (the masked `label` is dropped on purpose); {} on error."""
    try:
        d = (_get("/key", key) or {}).get("data") or {}
    except (urllib.error.URLError, OSError, ValueError):
        return {}
    return {k: d.get(k) for k in ("usage", "limit", "limit_remaining", "usage_daily") if k in d}


def account_balance(key: str) -> float | None:
    """Account-wide credit balance in USD (total_credits - total_usage, /credits); None on error. A key with
    limit_remaining > 0 still gets HTTP 402 once the ACCOUNT balance is used up (2026-10-10: 64 cells lost)."""
    try:
        d = (_get("/credits", key) or {}).get("data") or {}
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(d.get("total_credits"), (int, float)) or not isinstance(d.get("total_usage"), (int, float)):
        return None
    return round(float(d["total_credits"]) - float(d["total_usage"]), 4)


def key_usage(key: str) -> float | None:
    u = key_info(key).get("usage")
    return float(u) if isinstance(u, (int, float)) else None


def settled_usage(key: str, before: float | None, wait_s: float = 40.0, step: float = 6.0) -> float | None:
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


def cell_spend(est: float | None, delta: float | None, shared: bool) -> tuple[float, str]:
    """What one OpenRouter cell costs THIS run: (usd, source).

    The /key usage delta is the provider-booked spend, but it is account-wide: it is used only when no other OpenRouter
    cell (of this or any other run on this machine) overlapped the cell, and when it is plausible against the estimate
    (<= 3x est + $0.05; a larger delta means foreign spend leaked in). Otherwise the token-based estimate is booked. With
    neither an estimate nor a solo delta, the shared delta is booked (over-counting is the safe side for a budget)."""
    if delta is not None and delta >= 0 and not shared and (est is None or delta <= 3 * est + 0.05):
        return round(delta, 6), "usage_delta"
    if est is not None:
        return round(float(est), 6), "estimate"
    if delta is not None:
        return round(max(float(delta), 0.0), 6), "usage_delta_shared"
    return 0.0, "none"


class RunBudget:
    """--or-budget-usd: stop scheduling new OpenRouter cells once THIS run's own spend reaches the budget.

    spent = sum of the run's per-cell spend (cell_spend()), recorded per cell id in the state file (one per results
    file; survives restarts; no secrets, no account-wide baseline). Concurrent runs that share a key therefore never
    consume each other's budgets; the account balance and the key limit are guarded separately (AccountGuard).
    Cells already in the results file (row["openrouter"]["run_spend_usd"]) are merged in, so a lost state file does not
    reset the spend. A legacy state file (round-7 format with `baseline_usage`) is ignored."""

    FORMAT = "per-run-v2"

    def __init__(self, budget_usd: float, state: Path, reset: bool = False, results: Path | None = None):
        self.budget, self.state = float(budget_usd), Path(state)
        self._lock = threading.Lock()
        self.exhausted = False
        data: dict[str, Any] = {}
        if self.state.exists() and not reset:
            try:
                data = json.loads(self.state.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        self.legacy_ignored = "baseline_usage" in data and data.get("format") != self.FORMAT
        if data.get("format") != self.FORMAT:
            data = {"format": self.FORMAT, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "cells": {}}
        data["budget_usd"] = self.budget
        self.data = data
        if results is not None and not reset:
            self._merge_results(Path(results))
        self._save()

    def _merge_results(self, results: Path) -> None:
        try:
            lines = results.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        cells = self.data.setdefault("cells", {})
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            o = r.get("openrouter") if isinstance(r, dict) else None
            if isinstance(o, dict) and isinstance(o.get("run_spend_usd"), (int, float)) and r.get("cell_id") \
                    and r["cell_id"] not in cells:
                cells[r["cell_id"]] = {"usd": float(o["run_spend_usd"]), "source": o.get("run_spend_source"),
                                       "key": r.get("key"), "from": "results"}

    def _save(self) -> None:
        self.state.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state.with_name(self.state.name + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.state)

    def record(self, cell_id: str, usd: float, source: str, key: str | None = None) -> float:
        """Book one cell's spend (idempotent per cell id); returns the run's total spend."""
        with self._lock:
            self.data.setdefault("cells", {})[cell_id] = {"usd": round(float(usd), 6), "source": source, "key": key,
                                                          "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            self._save()
            return self._spent()

    def _spent(self) -> float:
        return round(sum(float(c.get("usd") or 0.0) for c in (self.data.get("cells") or {}).values()), 6)

    def spent(self, fresh: bool = False) -> float:      # `fresh` kept for call-site compatibility (no API call)
        with self._lock:
            return self._spent()

    def remaining(self) -> float:
        return round(self.budget - self.spent(), 6)

    def allow(self) -> bool:
        if self.spent() >= self.budget:
            self.exhausted = True
        return not self.exhausted


class AccountGuard:
    """Global guard on top of the per-run budget: the key's remaining limit (/key limit_remaining, None = unlimited)
    and the ACCOUNT balance (/credits) must both stay >= min_usd. A key with limit_remaining > 0 still gets HTTP 402
    once the account balance is used up (round-7 incident). Unknown values (endpoint error) do not block."""

    def __init__(self, key: str, min_usd: float = MIN_BALANCE_USD, cache_s: float = 60.0,
                 key_info_fn: Callable[[str], dict[str, Any]] | None = None,
                 balance_fn: Callable[[str], float | None] | None = None):
        self.key, self.min, self.cache_s = key, float(min_usd), cache_s
        self._key_info = key_info_fn or key_info
        self._balance = balance_fn or account_balance
        self._t = -1e9
        self._res: tuple[bool, str] = (True, "unchecked")
        self.blocked_reason: str | None = None      # sticky block (e.g. a 402 seen in a transcript)
        self._lock = threading.Lock()

    def block(self, reason: str) -> None:
        with self._lock:
            self.blocked_reason = reason

    def check(self, fresh: bool = False) -> tuple[bool, str]:
        with self._lock:
            if self.blocked_reason:
                return False, self.blocked_reason
            if not fresh and time.monotonic() - self._t < self.cache_s:
                return self._res
            bal = self._balance(self.key)
            rem = (self._key_info(self.key) or {}).get("limit_remaining")
            if isinstance(bal, (int, float)) and bal < self.min:
                res = (False, f"account balance ${bal:.2f} < ${self.min:.2f} (AB_MIN_OR_BALANCE)")
            elif isinstance(rem, (int, float)) and rem < self.min:
                res = (False, f"key limit remaining ${rem:.2f} < ${self.min:.2f}")
            else:
                res = (True, f"balance={'?' if bal is None else f'${bal:.2f}'} "
                             f"key_remaining={'unlimited' if rem is None else f'${rem:.2f}'}")
            self._t, self._res = time.monotonic(), res
            return res

    def ok(self, fresh: bool = False) -> bool:
        return self.check(fresh)[0]


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class Activity:
    """Machine-wide registry of running OpenRouter cells (all runs, all harness processes), so a cell knows whether its
    /key usage delta is its own. State: {"seq": <cells started so far>, "active": {token: {pid, start_seq}}} in one
    JSON file under an exclusive flock; entries of dead processes are dropped.

        start_seq, others = act.enter(token)   ...   shared = act.leave(token)

    shared = another cell was active at start or at end, or any cell started in between."""

    def __init__(self, path: Path = ACTIVITY_FILE):
        self.path = Path(path)
        self._starts: dict[str, tuple[int, int]] = {}
        self._tlock = threading.Lock()

    def _update(self, fn):
        import fcntl  # POSIX only (the harness itself is POSIX only)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_name(self.path.name + ".lock"), "a+") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    data = {}
                data.setdefault("seq", 0)
                act = data.setdefault("active", {})
                for tok in [t for t, v in act.items() if not _pid_alive(int(v.get("pid") or 0))]:
                    act.pop(tok, None)
                out = fn(data)
                tmp = self.path.with_name(self.path.name + ".tmp")
                tmp.write_text(json.dumps(data), encoding="utf-8")
                os.replace(tmp, self.path)
                return out
            finally:
                fcntl.flock(lk, fcntl.LOCK_UN)

    def enter(self, token: str) -> tuple[int, int]:
        def fn(d):
            d["seq"] += 1
            others = len([t for t in d["active"] if t != token])
            d["active"][token] = {"pid": os.getpid(), "start_seq": d["seq"], "t": time.time()}
            return d["seq"], others
        start_seq, others = self._update(fn)
        with self._tlock:
            self._starts[token] = (start_seq, others)
        return start_seq, others

    def leave(self, token: str) -> bool:
        with self._tlock:
            start_seq, others_start = self._starts.pop(token, (None, 1))

        def fn(d):
            others_now = len([t for t in d["active"] if t != token])
            d["active"].pop(token, None)
            return others_start > 0 or others_now > 0 or start_seq is None or d["seq"] != start_seq
        return bool(self._update(fn))


# ------------------------------------------------------------------------------------------------ prices / cost
def prices(refresh: bool = False, max_age_s: float = 86400.0) -> dict[str, dict[str, float]]:
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
    out: dict[str, dict[str, float]] = {}
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
        PRICES_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PRICES_CACHE.write_text(json.dumps({"fetched": time.strftime("%Y-%m-%d %H:%M:%S"), "prices": out}))
    except OSError:
        pass
    return out


def estimate_cost(model_id: str, in_uncached: int | None, out_tok: int | None, cache_read: int | None = 0,
                  cache_write: int | None = 0, table: dict[str, dict[str, float]] | None = None
                  ) -> float | None:
    p = (table if table is not None else prices()).get(model_id)
    if not p or "prompt" not in p:
        return None
    pr, co = p["prompt"], p.get("completion", 0.0)
    cr = p.get("input_cache_read", pr)
    cw = p.get("input_cache_write", pr)
    usd = (in_uncached or 0) * pr + (cache_write or 0) * cw + (cache_read or 0) * cr + (out_tok or 0) * co
    return round(usd, 6)


# ------------------------------------------------------------------------------------------------ agents
def parse_models(spec: str | None) -> dict[str, str]:
    """'a/b-c,x/y' or 'short=a/b-c,...' -> {short: id}; short defaults to the id's last path segment."""
    out: dict[str, str] = {}
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


def split_agent(agent: str) -> tuple[str | None, str | None]:
    """'cc-or:qwen3.8-flash' -> ('cc-or', 'qwen3.8-flash'); plain agents -> (None, None)."""
    if ":" in agent:
        route, short = agent.split(":", 1)
        if route in ROUTES:
            return route, short
    return None, None


def claude_code_env(model_id: str, key: str) -> dict[str, str]:
    """env for Claude Code against OpenRouter (merge AFTER the cell env; never write it to disk)."""
    return {"ANTHROPIC_BASE_URL": ANTHROPIC_BASE, "ANTHROPIC_AUTH_TOKEN": key, "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_MODEL": model_id, "ANTHROPIC_SMALL_FAST_MODEL": model_id,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model_id, "ANTHROPIC_DEFAULT_SONNET_MODEL": model_id,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model_id, "CLAUDE_CODE_SUBAGENT_MODEL": model_id,
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
            "DISABLE_AUTOUPDATER": "1"}


def claude_code_home_json() -> dict[str, Any]:
    """minimal .claude.json for an OpenRouter-routed Claude Code home: onboarding done, NO account / oauth data."""
    return {"hasCompletedOnboarding": True, "bypassPermissionsModeAccepted": True, "numStartups": 1,
            "autoUpdates": False}


def opencode_provider_cfg(model_id: str) -> dict[str, Any]:
    """opencode.json fragment registering the model with the native openrouter provider. The key is an `{env:...}`
    reference (no secret on disk); together with opencode_env() it beats a key stored in OpenCode's global auth.json
    (smoke finding: without it OpenCode billed the user's stored OpenRouter key, not OPENROUTER_API_KEY)."""
    return {"openrouter": {"options": {"apiKey": "{env:OPENROUTER_API_KEY}"},
                           "models": {model_id: {"name": model_id, "tool_call": True}}}}


def opencode_env(key: str, home: Path) -> dict[str, str]:
    """env for an oc-or cell: the key + a cell-local XDG data dir (no global auth.json / session DB)."""
    data = Path(home) / "xdg_data"
    data.mkdir(parents=True, exist_ok=True)
    return {"OPENROUTER_API_KEY": key, "XDG_DATA_HOME": str(data)}


def redacted_env(env: dict[str, str], key: str | None) -> dict[str, str]:
    return {k: ("<redacted>" if (key and v == key) or k in ("ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY") else v)
            for k, v in env.items()}


# ------------------------------------------------------------------------------------------------ CLI (runner)
def balance_check(min_usd: float = MIN_BALANCE_USD, env_file: Path | None = None) -> tuple[int, str]:
    """(exit code, message) for the runner: 0 ok, 1 no usable key, 5 balance or key limit below `min_usd`.
    The message never contains the key."""
    key = load_key(env_file)
    if not key:
        return 1, "OPENROUTER_API_KEY missing (env or .env file)"
    info = key_info(key)
    if info.get("usage") is None:
        return 1, "OpenRouter key rejected or /key unreachable"
    ok, msg = AccountGuard(key, min_usd).check(fresh=True)
    return (0 if ok else EXIT_BALANCE), msg


def main(argv: list | None = None) -> int:
    global ENV_FILE
    ap = argparse.ArgumentParser(description="OpenRouter helpers (never prints the key)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    bc = sub.add_parser("balance-check", help="exit 0 ok, 1 no usable key, 5 balance/key limit below --min")
    bc.add_argument("--min", type=float, default=MIN_BALANCE_USD, help="minimum USD (default AB_MIN_OR_BALANCE or 0.5)")
    bc.add_argument("--env-file", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "balance-check":
        if args.env_file:
            ENV_FILE = Path(args.env_file)
        rc, msg = balance_check(args.min, Path(args.env_file) if args.env_file else None)
        print(scrub(msg), file=sys.stderr if rc else sys.stdout)
        return rc
    return 2


if __name__ == "__main__":
    sys.exit(main())
