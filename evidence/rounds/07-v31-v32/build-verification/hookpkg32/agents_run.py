"""Real headless agent sessions with the hookpkg32 arm (v3.1, output profiles) -- or, for comparison, --pkg=v3 / v2 / mcp
(rf-mcp MCP server, no hooks) -- installed via install.py (smoke test, not the A/B itself).

  PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 verify/agents_run.py [--pkg=v32|v31|v3|v2|mcp] \
      [--task=web3|web|repl|api|gate|rewrite|journey] [--claude-model=claude-haiku-5-5] \
      [--or-models=deepseek/deepseek-v4.1-flash,qwen/qwen3.8-flash,...] \
      [claude codex opencode cc-or:<short> oc-or:<short> ...]
Agents: claude = Claude Code on the subscription (--claude-model, default claude-haiku-5-5); cc-or:<short> = Claude Code
against an OpenRouter model (no subscription credentials; ../../harness/openrouter.py); oc-or:<short> = OpenCode's
native openrouter provider; opencode = MiniMax M2.5 (coding plan); codex.
  web3 : the web task on site3/ -- Tricentis-like radios / gift checkbox COVERED by styled spans, payment IFRAME,
         confirmation that appears 4 s after placing the order -- + repair of repair3/checkout.robot
Records per session into $RESULTS_FILE (default verify/results_agents.json): route, pass (both plain robot runs),
turns, wall, tool calls, output profile (hook log), context chars per edit, tokens, OpenRouter cost (estimate from
OpenRouter prices + /api/v1/key usage delta), leftover processes. Copied credentials are deleted afterwards; the
OpenRouter key only ever lives in the child process env.
"""
from __future__ import annotations

import collections
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AB = HERE.parent.parent
VERSION = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--pkg=")), "v32")
PKG = {"v32": HERE.parent, "v31": AB / "hookpkg31", "v3": AB / "hookpkg3", "v2": AB / "hookpkg2", "mcp": None}[VERSION]
N = {"v32": "32", "v31": "31", "v3": "3", "v2": "2", "mcp": ""}[VERSION]
sys.path.insert(0, str(HERE.parent / "rfharness32"))
sys.path.insert(0, str(AB / "harness"))
import procs  # noqa: E402
import proto  # noqa: E402
import importlib.util  # noqa: E402
import openrouter as OR  # noqa: E402
import harness as H  # noqa: E402  (transcript parsing, rf-mcp command, OpenRouter cost helpers)

if PKG is not None:
    _spec = importlib.util.spec_from_file_location(f"install_{VERSION}", PKG / "install.py")
    _inst = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_inst)
    install = _inst.install
else:
    install = None

VENV_BIN = Path("~/workspace/rf-mcp-robotcode/.venv/bin")
MODELS = {"claude": next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--claude-model=")),
                         os.environ.get("CLAUDE_MODEL") or "claude-haiku-5-5"),
          "codex": "gpt-5.6-luna", "opencode": "minimax-coding-plan/MiniMax-M2.5",
          "opencode27": "minimax-coding-plan/MiniMax-M2.7", "copilot": "auto"}
_orm = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--or-models=")), None)
if _orm:
    H.OR_MODELS = OR.parse_models(_orm)
OR_KEY = None


def model_of(agent: str) -> str:
    return H.agent_model(agent) if H.is_or(agent) else MODELS[agent]


def or_key() -> str:
    global OR_KEY
    if OR_KEY is None:
        OR_KEY = H.ensure_or_key()
    return OR_KEY
TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "1500"))
ROOT = Path(os.environ.get("AGENT_ROOT") or Path.home() / ".cache" / "rfh32-agents")
SITE = {"web3": ("site3", "repair3")}

PROMPT = """This project contains a small web shop under site/ (open it with the Browser library as
file://${CURDIR}/../site/login.html from a test in tests/).
1. Create tests/order.robot with one test case `Express Gift Order` (Browser library, headless chromium) that: accepts
   the cookie banner, signs in as user `alice` with password `secret`, verifies the greeting `Hello, alice`, chooses
   Express shipping, country Norway and gift wrap, enters card number 4242 in the payment form and confirms the card,
   places the order and verifies that the confirmation message says the order is confirmed with `Total: 60.00 EUR`
   (the confirmation is shown a few seconds after placing the order).
2. tests/checkout.robot used to pass and now fails. Repair it: keep all its tests and assertions, fix the test code.
Both suites must pass with a plain `robot -d results tests/order.robot tests/checkout.robot` run.
Finish with the final robot summary line."""


PROMPT_JOURNEY = """This project contains a small web shop under site/ (open it with the Browser library as
file://${CURDIR}/../site/login.html from a test in tests/).
Create tests/journey.robot with one test case `Gift Order` (Browser library, headless chromium) that: accepts the
cookie banner, signs in as user `bob` with password `pw`, chooses Express shipping, country Italy and gift wrap,
enters card number 5555 in the payment form and confirms the card, places the order and verifies the confirmation
message `Total: 60.00 EUR`. It must pass with a plain `robot -d results tests/journey.robot` run.
Finish with the final robot summary line."""


PROMPT_REPL = """This project contains a small web shop under site/ (start page: site/login.html). Explore it interactively
with the Robot Framework REPL of robotcode (`robotcode repl`, already installed; Browser library, headless chromium) --
do NOT write any .robot files. In the REPL: open file://<absolute path of site/login.html>, accept the cookie banner,
sign in as user `alice` with password `secret`, then on the next page read the greeting heading and the names of the
countries in the country dropdown. Report: the greeting text, the country names, and the exact REPL statements that
worked."""


PROMPT_API = """A JSON API runs at {url} (GET /api/items lists items, POST /api/items with a JSON body creates one).
Create tests/api.robot with one test case `Items Api` (RequestsLibrary) that checks that the first listed item is
named Apple, then creates an item named Kiwi with price 2 (expect status 201) and checks that the response contains
the name Kiwi. Just write the file; you do not need to run robot yourself."""


PROMPT_GATE = """Create the file tests/gate.robot with EXACTLY this content (copy it verbatim with your file-writing tool,
do not correct anything yourself):
```
*** Settings ***
Library    Browser

*** Test Cases ***
Gate Probe
    New Browser    chromium    headless=True
    New Page    file://${CURDIR}/../site/login.html
    Run Keyword If    True    Log    deprecated form
    Clik    text=Accept all
```
If the write is refused, follow the reason you are given and write the corrected file. Then answer in two lines:
whether the write was refused (and why) and what the file's line 8 contains now."""


PROMPT_MCP = """Use ONLY the tools of the `robotmcp` MCP server for this task (no shell commands, no file edits).
1. Call `find_keywords` once to look up the Browser keyword that opens a page.
2. With `execute_step` (one call per keyword, same session) run: `New Browser` with arguments `chromium` and
   `headless=True`, then `New Page` with the argument `{url}`, then `Get Title`.
Reply with the page title and the list of robotmcp tools you called."""


PROMPT_REWRITE = """Create the file tests/legacy.robot with EXACTLY this content (copy it verbatim with your file-writing
tool, do not modernize anything yourself):
```
*** Settings ***
Library    Browser

*** Test Cases ***
Legacy Probe
    New Browser    chromium    headless=True
    New Page    file://${CURDIR}/../site/login.html
    Run Keyword If    True    Click    text=Accept all
```
Then answer in one line: what line 8 of the file on disk contains now."""


def clean_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k in (
        "CLAUDECODE", "ANTHROPIC_BASE_URL", "VIRTUAL_ENV", "CODEX_HOME", "COPILOT_HOME", "OPENCODE_CONFIG",
        "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "OPENROUTER_API_KEY"))}
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(Path.home() / ".cache" / "ms-playwright")
    return env


def _base(agent: str) -> str:
    if H.is_or(agent):
        return H.base_agent(agent)
    return "opencode" if agent.startswith("opencode") else agent


def _mcp_cfg(cell: Path) -> dict:
    return {"type": "stdio", "command": H.RF_MCP_CMD[0], "args": H.RF_MCP_CMD[1:], "env": H._mcp_env(cell)}


def prepare(agent: str, cell: Path):
    ws, home = cell / "ws", cell / "home"
    shutil.rmtree(cell, ignore_errors=True)
    (ws / "tests").mkdir(parents=True)
    home.mkdir(parents=True)
    site_dir, repair_dir = SITE.get(TASK, ("site", "repair"))
    shutil.copytree(HERE / site_dir, ws / "site")
    shutil.copy2(HERE / repair_dir / "checkout.robot", ws / "tests" / "checkout.robot")
    subprocess.run(["git", "init", "-q"], cwd=ws)
    creds = []
    mcp_json = {"mcpServers": {"robotmcp": _mcp_cfg(cell)} if VERSION == "mcp" else {}}
    if agent.startswith("cc-or:"):         # OpenRouter: NO subscription credentials, no account data
        (home / ".claude.json").write_text(json.dumps(OR.claude_code_home_json()))
        (cell / "empty_mcp.json").write_text(json.dumps(mcp_json))
    elif agent.startswith("oc-or:"):
        cfg = {"$schema": "https://opencode.ai/config.json", "permission": {
            "edit": "allow", "bash": "allow", "webfetch": "allow", "external_directory": "allow"},
            "provider": OR.opencode_provider_cfg(H.or_model_id(agent))}
        if VERSION == "mcp":
            cfg["mcp"] = {"robotmcp": {"type": "local", "command": H.RF_MCP_CMD, "enabled": True,
                                       "environment": H._mcp_env(cell), "timeout": 90000}}
        (home / "opencode.json").write_text(json.dumps(cfg))
    elif agent == "claude":
        shutil.copy2(Path.home() / ".claude" / ".credentials.json", home / ".credentials.json")
        d = json.loads((Path.home() / ".claude.json").read_text())
        for k in ("projects", "mcpServers", "skillUsage", "toolUsage", "pluginUsage", "githubRepoPaths"):
            d.pop(k, None)
        (home / ".claude.json").write_text(json.dumps(d))
        (cell / "empty_mcp.json").write_text(json.dumps(mcp_json))
        creds += [home / ".credentials.json", home / ".claude.json"]
    elif agent == "codex":
        shutil.copy2(Path.home() / ".codex" / "auth.json", home / "auth.json")
        (home / "config.toml").write_text(f'model = "{MODELS["codex"]}"\nmodel_reasoning_effort = "low"\n\n'
                                          f'[projects."{ws}"]\ntrust_level = "trusted"\n')
        creds.append(home / "auth.json")
    elif agent.startswith("opencode"):
        cfg = {"$schema": "https://opencode.ai/config.json", "permission": {
            "edit": "allow", "bash": "allow", "webfetch": "allow", "external_directory": "allow"}}
        if VERSION == "mcp":
            cfg["mcp"] = {"robotmcp": {"type": "local", "command": H.RF_MCP_CMD, "enabled": True,
                                       "environment": H._mcp_env(cell), "timeout": 90000}}
        (home / "opencode.json").write_text(json.dumps(cfg))
    elif agent == "copilot":
        (home / "config.json").write_text(json.dumps({"trusted_folders": []}))
    info = install(_base(agent), ws, home, VENV_BIN) if install else {"extra_env": {}, "extra_args": []}
    return ws, home, info, creds


def build_cmd(agent: str, ws: Path, home: Path, cell: Path, info: dict, prompt: str = PROMPT):
    PROMPT = prompt  # noqa: N806
    env = {**clean_env(), **info["extra_env"]}
    if N:
        env[f"RFH{N}_HOOK_LOG"] = str(cell / "hooks.jsonl")
    if VERSION == "mcp":
        env.update({H.CELL_ENV_MARKER: str(cell), "PATH": f"{VENV_BIN}:{env.get('PATH', '')}"})
    base = _base(agent)
    if agent.startswith("cc-or:"):
        env.update(OR.claude_code_env(H.or_model_id(agent), or_key()))
    elif agent.startswith("oc-or:"):
        env.update(OR.opencode_env(or_key(), home))
    if base == "claude":
        env["CLAUDE_CONFIG_DIR"] = str(home)
        cmd = ["claude", "-p", PROMPT, "--model", model_of(agent), "--output-format", "stream-json", "--verbose",
               "--include-hook-events", "--dangerously-skip-permissions", "--max-turns", "80",
               "--mcp-config", str(cell / "empty_mcp.json"), "--strict-mcp-config"]
    elif agent == "codex":
        env["CODEX_HOME"] = str(home)
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-C", str(ws),
               "--dangerously-bypass-approvals-and-sandbox", *info["extra_args"], PROMPT]
    elif base == "opencode":
        env["OPENCODE_CONFIG"] = str(home / "opencode.json")
        cmd = ["opencode", "run", "--dir", str(ws), "-m", model_of(agent), "--format", "json",
               "--dangerously-skip-permissions", PROMPT]
    else:
        env["COPILOT_HOME"] = str(home)
        env["COPILOT_AUTO_UPDATE"] = "false"
        cmd = ["copilot", "-p", PROMPT, "--model", MODELS["copilot"], "--allow-all", "--no-ask-user",
               "--output-format", "json", "-C", str(ws), "--no-auto-update", *info["extra_args"]]
    return cmd, env


def tool_strings(agent: str, log: str) -> list:
    """(tool, input-string) of every tool call in the transcript."""
    agent = _base(agent)
    out = []
    for line in log.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if agent == "claude" and d.get("type") == "assistant":
            for c in (d.get("message") or {}).get("content", []) or []:
                if c.get("type") == "tool_use":
                    out.append((c.get("name"), json.dumps(c.get("input"))))
        elif agent == "codex" and d.get("type") == "item.completed":
            it = d.get("item") or {}
            if it.get("type") == "command_execution":
                out.append(("shell", it.get("command") or ""))
            elif it.get("type") == "file_change":
                out.append(("apply_patch", json.dumps(it.get("changes"))))
        elif agent.startswith("opencode") and d.get("type") == "tool_use":
            p = d.get("part") or {}
            out.append((p.get("tool"), json.dumps((p.get("state") or {}).get("input"))))
        elif agent == "copilot" and d.get("type") == "tool.execution_start":
            dd = d.get("data") or {}
            out.append((dd.get("toolName"), json.dumps(dd.get("arguments"))))
    return out


def plain_run(ws: Path, files: list) -> dict:
    existing = [f for f in files if (ws / f).exists()]
    if not existing:
        return {"rc": None, "line": "no files"}
    r = subprocess.run([str(VENV_BIN / "robot"), "-d", "grade_out", "--console", "dotted", *existing], cwd=ws,
                       capture_output=True, text=True, timeout=600, env=clean_env())
    m = re.findall(r"^(\d+ tests?, \d+ passed, \d+ failed.*)$", r.stdout, re.M)
    return {"rc": r.returncode, "line": m[-1] if m else r.stdout[-300:]}


def analyze_hooks(path: Path) -> dict:
    ev = collections.Counter()
    acts = collections.Counter()
    ran = failed = 0
    lat = collections.defaultdict(list)
    errors = []
    tools = collections.Counter()
    v2 = collections.Counter()
    for line in (path.read_text().splitlines() if path.exists() else []):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        v2["docs_kw"] += d.get("docs_kw", 0) or 0
        v2["docs_lib"] += len(d.get("docs_lib") or [])
        v2["captures"] += d.get("captures", 0) or 0
        v2["rechecks"] += d.get("rechecks", 0) or 0
        for x in d.get("recheck_verdicts") or []:
            v2["recheck_" + str(x)] += 1
        if d.get("repl"):
            v2["repl_pre"] += 1 if d.get("event") == "pre-tool" else 0
            v2["repl_rewrite"] += 1 if d.get("action") == "rewrite" else 0
            v2["repl_deny"] += 1 if d.get("action") == "deny" else 0
        v2["loop_hints"] += d.get("loop_hint", 0) or 0
        if d.get("guard"):
            v2["guard_" + d["guard"] + "_" + str(d.get("action"))] += 1
        v2["card"] += 1 if d.get("card") else 0
        v2["prompt_ctx"] += 1 if d.get("prompt_ctx") else 0
        v2["valve"] += 1 if d.get("valve") else 0
        v2["repl_fails"] += d.get("repl_fails", 0) or 0
        ev[d.get("event")] += 1
        acts[f"{d.get('event')}:{d.get('action')}"] += 1
        ran += d.get("ran_lines", 0) or 0
        failed += d.get("failed_lines", 0) or 0
        if d.get("ms") is not None:
            lat[d.get("event")].append(d["ms"])
        if d.get("error"):
            errors.append(d["error"])
        if d.get("tool"):
            tools[d["tool"]] += 1
    return {"events": dict(ev), "actions": dict(acts), "auto_executed_lines": ran, "non_pass_lines": failed,
            "stop_blocks": acts.get("stop:block", 0), "denials": acts.get("pre-tool:deny", 0),
            "rewrites": acts.get("pre-tool:rewrite", 0), "tools_seen": dict(tools),
            "latency_ms": {k: {"median": sorted(v)[len(v) // 2], "max": max(v), "n": len(v)} for k, v in lat.items()},
            "errors": errors[:5], "v2": dict(v2)}


_TF = {"gate": "gate", "rewrite": "legacy", "journey": "journey"}


TASK = "web"


def ctx_metrics(path: Path) -> dict:
    """injected context per PostToolUse of an edit / robot run (hook log out_bytes: JSON output incl. ~70 B wrapper;
    v3 also logs ctx_chars = the text itself), rechecks by verdict, failure classes."""
    ed, rb, cc = [], [], []
    verdicts, classes = collections.Counter(), collections.Counter()
    for line in (path.read_text().splitlines() if path.exists() else []):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        for v in d.get("recheck_verdicts") or []:
            verdicts[str(v)] += 1
        for c in d.get("fail_classes") or []:
            classes[str(c)] += 1
        if d.get("event") != "post-tool":
            continue
        if d.get("files"):
            ed.append(int(d.get("out_bytes") or 0))
            if d.get("ctx_chars") is not None:
                cc.append(d["ctx_chars"])
        elif d.get("robot"):
            rb.append(int(d.get("out_bytes") or 0))
    mean = (lambda xs: round(sum(xs) / len(xs)) if xs else None)
    return {"edits_with_hook": len(ed), "out_bytes_per_edit": mean(ed), "out_bytes_edits_total": sum(ed),
            "ctx_chars_per_edit": mean(cc), "out_bytes_per_robot_run": mean(rb), "robot_runs_hooked": len(rb),
            "recheck_verdicts": dict(verdicts), "fail_classes": dict(classes)}


def num_turns(agent: str, log: str):
    if _base(agent) == "claude":
        for line in log.splitlines()[::-1]:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") == "result":
                return d.get("num_turns")
    return None


def run(agent: str, task: str = "web") -> dict:
    global TASK
    TASK = task
    cell = ROOT / f"{VERSION}-{agent}-{task}-{time.strftime('%H%M%S')}"
    ws, home, info, creds = prepare(agent, cell)
    api = None
    prompt = PROMPT
    if task == "gate":
        prompt = PROMPT_GATE
    if task == "rewrite":
        prompt = PROMPT_REWRITE
    if task == "repl":
        prompt = PROMPT_REPL
    if task == "journey":
        prompt = PROMPT_JOURNEY
    if task == "mcpprobe":         # --pkg=mcp: proves MCP tool calls work through the agent's model route
        prompt = PROMPT_MCP.format(url=f"file://{ws}/site/login.html")
    if task == "api":
        import socket
        so = socket.socket()
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
        so.close()
        api = subprocess.Popen([sys.executable, str(HERE / "api_server.py"), str(port)])
        prompt = PROMPT_API.format(url=f"http://127.0.0.1:{port}")
    cmd, env = build_cmd(agent, ws, home, cell, info, prompt)
    (cell / "cmd.json").write_text(json.dumps({"cmd": cmd[:3] + ["<prompt>"] if cmd[:2] == ["claude", "-p"] else cmd[:6],
                                               "env": OR.redacted_env({k: v for k, v in env.items() if k.startswith(
                                                   ("ANTHROPIC", "OPENROUTER", "CLAUDE_CONFIG", "OPENCODE_CONFIG",
                                                    "RFH"))}, OR_KEY)}, indent=1))
    or_before = OR.key_usage(or_key()) if H.is_or(agent) else None
    t0 = time.time()
    out = (cell / "stdout.jsonl").open("w")
    p = subprocess.Popen(cmd, cwd=ws, env=env, stdout=out, stderr=open(cell / "stderr.txt", "w"),
                         stdin=subprocess.DEVNULL, start_new_session=True)
    timed_out = False
    try:
        p.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(p.pid, 9)
        p.wait()
    wall = round(time.time() - t0)
    out.close()
    api_result = plain_run(ws, ["tests/api.robot"]) if api else None
    if api:
        api.terminate()
    for c in creds:
        try:
            c.unlink()
        except OSError:
            pass
    time.sleep(4)   # SessionEnd / watch-pid / plugin dispose
    toks = [((proto.read_state(ws / ".rf" / k) or {}).get("token_env")) for k in (f"exec{N}", f"lint{N}")]
    left = [pid for t in toks if t for pid in procs.token_procs(t)]
    alive_daemons = [k for k in (f"exec{N}", f"lint{N}") if proto.pid_alive((proto.read_state(ws / ".rf" / k) or {}).get("pid"))
                     and not (proto.read_state(ws / ".rf" / k) or {}).get("stopped")]
    strays = []                      # anything else still pointing at this cell (chromium, docs workers, REPLs)
    for n in os.listdir("/proc"):
        if n.isdigit():
            try:
                cl = open(f"/proc/{n}/cmdline", "rb").read().decode(errors="replace")
                cwd = os.readlink(f"/proc/{n}/cwd")
            except OSError:
                continue
            if str(cell) in cl or cwd.startswith(str(cell)):
                strays.append(int(n))
    if strays:
        procs.terminate(strays)
    killed = len(left)
    if left:
        procs.terminate(left)
    if OR_KEY:          # defensive: the key must never stay in anything the session wrote
        for fp in (cell / "stdout.jsonl", cell / "stderr.txt", cell / "hooks.jsonl"):
            if fp.exists():
                s0 = fp.read_text(errors="replace")
                if OR_KEY in s0 or OR.KEY_PREFIX in s0:
                    fp.write_text(OR.scrub(s0, OR_KEY))
    log = (cell / "stdout.jsonl").read_text(errors="replace")
    calls = tool_strings(agent, log)
    hm, _hcalls, hinfo = H.parse_transcript(_base(agent), cell / "stdout.jsonl")
    orr = H.or_cost(agent, hm, hinfo, or_before) if H.is_or(agent) else None
    prof = collections.Counter()
    prof_src = prof_model = None
    for line in ((cell / "hooks.jsonl").read_text(errors="replace").splitlines() if (cell / "hooks.jsonl").exists() else []):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("profile"):
            prof[d["profile"]] += 1
            prof_src, prof_model = d.get("profile_src") or prof_src, d.get("model") or prof_model
    rfmcp = [s[:200] for _, s in calls if re.search(r"(?<![\w-])rfmcp(?![\w-])|rfmcp_skill", s)]
    manual_hook = [s[:200] for _, s in calls if f"rfharness{N}" in s and "hook.py" in s]
    evidence = {k: log.count(k) for k in ("Live run of", "appeared after", "recheck: MISSING --", "docs: .rf/docs/kw/",
                                          "LOOP:", "REPL command auto-fixed", "Keyword docs for the",
                                          "project context (hook)", "[rfh32] ", "RF REPL format (hook card)",
                                          "Plain robot run:", "Reproduced live", "REFUSED", "already installed",
                                          "NEXT:")}
    reads = {"kwdoc_reads": sum(1 for _, s in calls if ".rf/docs/kw" in s),
             "latest_reads": sum(1 for _, s in calls if ".rf/state/latest" in s or ".rf/state/step-" in s),
             "repl_calls": sum(1 for _, s in calls if re.search(r"robotcode[^\n]{0,80}\b(repl|shell|robot-debug)\b", s))}
    hooks = analyze_hooks(cell / "hooks.jsonl")
    route = ("cc-or (Claude Code -> OpenRouter)" if agent.startswith("cc-or:") else
             "oc-or (OpenCode native openrouter provider)" if agent.startswith("oc-or:") else
             "claude subscription" if agent == "claude" else agent)
    res = {"agent": agent, "pkg": VERSION, "route": route, "model": model_of(agent), "wall_s": wall,
           "timed_out": timed_out, "exit": p.returncode, "turns": num_turns(agent, log) or hm.get("turns"),
           "ctx": ctx_metrics(cell / "hooks.jsonl"),
           "profile": prof.most_common(1)[0][0] if prof else None, "profile_counts": dict(prof),
           "profile_src": prof_src, "profile_model": prof_model,
           "tokens": {k: hm.get(k) for k in ("in_tok", "in_uncached_tok", "cache_write_tok", "cache_read_tok", "out_tok")},
           "agent_reported_cost_usd": hm.get("cost_usd") if not orr else hm.get("cost_usd_agent_reported"),
           "openrouter": orr, "api_key_source": hinfo.get("api_key_source"),
           "models_seen": sorted(set((hinfo.get("assistant_models") or []) + [hinfo.get("model_seen") or ""]) - {""}),
           "agent_errors": hinfo.get("errors"), "mcp_tool_calls": sum(1 for t_, _ in calls if "robotmcp" in str(t_)),
           "tool_calls": len(calls), "tool_kinds": dict(collections.Counter(t for t, _ in calls)),
           "rfmcp_cli_calls": len(rfmcp), "rfmcp_examples": rfmcp[:3], "manual_hook_calls": len(manual_hook),
           "skill_read": any("SKILL.md" in s or "robotframework" in s.lower() and "skill" in s.lower() for _, s in calls),
           "state_reads": sum(1 for _, s in calls if ".rf/state" in s), "docs_reads": sum(1 for _, s in calls if ".rf/docs" in s),
           "robot_runs": sum(1 for _, s in calls if re.search(r"(^|[\s;&|(/\"'])robot\s", s)),
           "hooks": hooks, "task": task, "evidence_in_transcript": evidence, **reads,
           "stray_processes_after_exit": len(strays),
           **({"plain_api": api_result} if api else {f"plain_{task}": plain_run(ws, [f"tests/{_TF[task]}.robot"]),
                                                     "probe_file": (ws / f"tests/{_TF[task]}.robot").read_text()[-260:]
                                                     if (ws / f"tests/{_TF[task]}.robot").exists() else None}
              if task in _TF else ({} if task in ("repl", "mcpprobe") else {"plain_order": plain_run(ws, ["tests/order.robot"]),
                                                     "plain_checkout": plain_run(ws, ["tests/checkout.robot"])})),
           "processes_left_after_exit": killed, "daemons_alive_after_exit": alive_daemons,
           "creds_deleted": not any(c.exists() for c in creds), "cell": str(cell)}
    final = ""
    for line in log.splitlines()[::-1]:
        if '"result"' in line or '"agent_message"' in line or '"text"' in line:
            final = line[-400:]
            break
    res["final_tail"] = final
    print(json.dumps({k: v for k, v in res.items() if k not in ("hooks",)}, default=str)[:1500])
    print(json.dumps(hooks)[:1500], flush=True)
    return res


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith(("--pkg=", "--claude-model=", "--or-models="))]
    task = "web"
    if args and args[0].startswith("--task="):
        task = args.pop(0).split("=", 1)[1]
    agents = args or ["claude", "codex", "opencode"]
    results_path = Path(os.environ.get("RESULTS_FILE") or HERE / "results_agents.json")
    for a in agents:
        r = run(a, task)
        allres = json.loads(results_path.read_text()) if results_path.exists() else {}
        allres[f"{VERSION}:{a}:{task}"] = r
        results_path.write_text(json.dumps(allres, indent=1, default=str))
