"""Real headless agent sessions with the hookpkg arm installed via install.py (smoke test, not the A/B itself).

  PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 verify/agents_run.py [claude codex opencode copilot]
Task (local only): (1) write a multi-step Browser journey test against site/ (file://: cookie banner, login, styled
radio, select, hidden checkbox, payment iframe, async confirmation), (2) repair tests/checkout.robot (3 planted bugs).
Records per agent into verify/results_agents.json: hook firings per event (from the hook log), auto-executed lines,
denials/rewrites, Stop-gate blocks, `rfmcp` CLI calls (must be 0), independent plain-robot re-run of both suites,
leftover processes after the session. Copied credentials are deleted afterwards.
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
PKG = HERE.parent
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "rfharness"))
from install import install  # noqa: E402
import procs  # noqa: E402
import proto  # noqa: E402

VENV_BIN = Path("~/workspace/rf-mcp-robotcode/.venv/bin")
MODELS = {"claude": "claude-haiku-4-5", "codex": "gpt-5.6-luna", "opencode": "minimax-coding-plan/MiniMax-M2.7",
          "copilot": "auto"}
TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "1500"))
ROOT = Path(os.environ.get("AGENT_ROOT") or Path.home() / ".cache" / "rfh-agents")

PROMPT = """This project contains a small web shop under site/ (open it with the Browser library as
file://${CURDIR}/../site/login.html from a test in tests/).
1. Create tests/order.robot with one test case `Express Gift Order` (Browser library, headless chromium) that: accepts
   the cookie banner, signs in as user `alice` with password `secret`, verifies the greeting `Hello, alice`, chooses
   Express shipping, country Norway and gift wrap, enters card number 4242 in the payment form and confirms the card,
   places the order and verifies that the confirmation says the order is confirmed with `Total: 60.00 EUR`.
2. tests/checkout.robot used to pass and now fails. Repair it: keep all its tests and assertions, fix the test code.
Both suites must pass with a plain `robot -d results tests/order.robot tests/checkout.robot` run.
Finish with the final robot summary line."""


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
        "CLAUDECODE", "ANTHROPIC_BASE_URL", "VIRTUAL_ENV", "CODEX_HOME", "COPILOT_HOME", "OPENCODE_CONFIG"))}
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(Path.home() / ".cache" / "ms-playwright")
    return env


def prepare(agent: str, cell: Path):
    ws, home = cell / "ws", cell / "home"
    shutil.rmtree(cell, ignore_errors=True)
    (ws / "tests").mkdir(parents=True)
    home.mkdir(parents=True)
    shutil.copytree(HERE / "site", ws / "site")
    shutil.copy2(HERE / "repair" / "checkout.robot", ws / "tests" / "checkout.robot")
    subprocess.run(["git", "init", "-q"], cwd=ws)
    creds = []
    if agent == "claude":
        shutil.copy2(Path.home() / ".claude" / ".credentials.json", home / ".credentials.json")
        d = json.loads((Path.home() / ".claude.json").read_text())
        for k in ("projects", "mcpServers", "skillUsage", "toolUsage", "pluginUsage", "githubRepoPaths"):
            d.pop(k, None)
        (home / ".claude.json").write_text(json.dumps(d))
        (cell / "empty_mcp.json").write_text('{"mcpServers":{}}')
        creds += [home / ".credentials.json", home / ".claude.json"]
    elif agent == "codex":
        shutil.copy2(Path.home() / ".codex" / "auth.json", home / "auth.json")
        (home / "config.toml").write_text(f'model = "{MODELS["codex"]}"\nmodel_reasoning_effort = "low"\n\n'
                                          f'[projects."{ws}"]\ntrust_level = "trusted"\n')
        creds.append(home / "auth.json")
    elif agent == "opencode":
        (home / "opencode.json").write_text(json.dumps({"$schema": "https://opencode.ai/config.json", "permission": {
            "edit": "allow", "bash": "allow", "webfetch": "allow", "external_directory": "allow"}}))
    elif agent == "copilot":
        (home / "config.json").write_text(json.dumps({"trusted_folders": []}))
    info = install(agent, ws, home, VENV_BIN)
    return ws, home, info, creds


def build_cmd(agent: str, ws: Path, home: Path, cell: Path, info: dict, prompt: str = PROMPT):
    PROMPT = prompt  # noqa: N806
    env = {**clean_env(), **info["extra_env"], "RFH_HOOK_LOG": str(cell / "hooks.jsonl")}
    if agent == "claude":
        env["CLAUDE_CONFIG_DIR"] = str(home)
        cmd = ["claude", "-p", PROMPT, "--model", MODELS["claude"], "--output-format", "stream-json", "--verbose",
               "--include-hook-events", "--dangerously-skip-permissions", "--max-turns", "80",
               "--mcp-config", str(cell / "empty_mcp.json"), "--strict-mcp-config"]
    elif agent == "codex":
        env["CODEX_HOME"] = str(home)
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-C", str(ws),
               "--dangerously-bypass-approvals-and-sandbox", *info["extra_args"], PROMPT]
    elif agent == "opencode":
        env["OPENCODE_CONFIG"] = str(home / "opencode.json")
        cmd = ["opencode", "run", "--dir", str(ws), "-m", MODELS["opencode"], "--format", "json",
               "--dangerously-skip-permissions", PROMPT]
    else:
        env["COPILOT_HOME"] = str(home)
        env["COPILOT_AUTO_UPDATE"] = "false"
        cmd = ["copilot", "-p", PROMPT, "--model", MODELS["copilot"], "--allow-all", "--no-ask-user",
               "--output-format", "json", "-C", str(ws), "--no-auto-update", *info["extra_args"]]
    return cmd, env


def tool_strings(agent: str, log: str) -> list:
    """(tool, input-string) of every tool call in the transcript."""
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
        elif agent == "opencode" and d.get("type") == "tool_use":
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
    for line in (path.read_text().splitlines() if path.exists() else []):
        try:
            d = json.loads(line)
        except ValueError:
            continue
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
            "errors": errors[:5]}


_TF = {"gate": "gate", "rewrite": "legacy"}


def run(agent: str, task: str = "web") -> dict:
    cell = ROOT / f"{agent}-{task}-{time.strftime('%H%M%S')}"
    ws, home, info, creds = prepare(agent, cell)
    api = None
    prompt = PROMPT
    if task == "gate":
        prompt = PROMPT_GATE
    if task == "rewrite":
        prompt = PROMPT_REWRITE
    if task == "api":
        import socket
        so = socket.socket()
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
        so.close()
        api = subprocess.Popen([sys.executable, str(HERE / "api_server.py"), str(port)])
        prompt = PROMPT_API.format(url=f"http://127.0.0.1:{port}")
    cmd, env = build_cmd(agent, ws, home, cell, info, prompt)
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
    toks = [((proto.read_state(ws / ".rf" / k) or {}).get("token_env")) for k in ("exec", "lint")]
    left = [pid for t in toks if t for pid in procs.token_procs(t)]
    alive_daemons = [k for k in ("exec", "lint") if proto.pid_alive((proto.read_state(ws / ".rf" / k) or {}).get("pid"))
                     and not (proto.read_state(ws / ".rf" / k) or {}).get("stopped")]
    killed = len(left)
    if left:
        procs.terminate(left)
    log = (cell / "stdout.jsonl").read_text(errors="replace")
    calls = tool_strings(agent, log)
    rfmcp = [s[:200] for _, s in calls if re.search(r"(?<![\w-])rfmcp(?![\w-])|rfmcp_skill", s)]
    manual_hook = [s[:200] for _, s in calls if "rfharness" in s and "hook.py" in s]
    hooks = analyze_hooks(cell / "hooks.jsonl")
    res = {"agent": agent, "model": MODELS[agent], "wall_s": wall, "timed_out": timed_out, "exit": p.returncode,
           "tool_calls": len(calls), "tool_kinds": dict(collections.Counter(t for t, _ in calls)),
           "rfmcp_cli_calls": len(rfmcp), "rfmcp_examples": rfmcp[:3], "manual_hook_calls": len(manual_hook),
           "skill_read": any("SKILL.md" in s or "robotframework" in s.lower() and "skill" in s.lower() for _, s in calls),
           "state_reads": sum(1 for _, s in calls if ".rf/state" in s), "docs_reads": sum(1 for _, s in calls if ".rf/docs" in s),
           "robot_runs": sum(1 for _, s in calls if re.search(r"(^|[\s;&|(/\"'])robot\s", s)),
           "hooks": hooks, "task": task,
           **({"plain_api": api_result} if api else {f"plain_{task}": plain_run(ws, [f"tests/{_TF[task]}.robot"]),
                                                     "probe_file": (ws / f"tests/{_TF[task]}.robot").read_text()[-260:]
                                                     if (ws / f"tests/{_TF[task]}.robot").exists() else None}
              if task in _TF else {"plain_order": plain_run(ws, ["tests/order.robot"]),
                                                     "plain_checkout": plain_run(ws, ["tests/checkout.robot"])}),
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
    args = sys.argv[1:]
    task = "web"
    if args and args[0].startswith("--task="):
        task = args.pop(0).split("=", 1)[1]
    agents = args or ["claude", "codex", "opencode"]
    results_path = HERE / "results_agents.json"
    for a in agents:
        r = run(a, task)
        allres = json.loads(results_path.read_text()) if results_path.exists() else {}
        allres[f"{a}:{task}"] = r
        results_path.write_text(json.dumps(allres, indent=1, default=str))
