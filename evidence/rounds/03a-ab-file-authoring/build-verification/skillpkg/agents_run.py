"""One headless session per agent with the skill arm installed via install.py (smoke test, not the A/B itself).

  python3 verify/agents_run.py WORKROOT [claude codex opencode copilot]
Task: Browser test against a file:// page whose card field sits inside an iframe (needs `>>>`), run with robot.
Records per agent into verify/results_agents.json: skill discovered/loaded, rfmcp commands used, hook calls,
independent re-run of the produced test, leftover helper processes. Copied credentials are deleted afterwards.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG))
from install import install  # noqa: E402

VENV_BIN = Path("~/workspace/rf-mcp-robotcode/.venv/bin")
MODELS = {"claude": "claude-haiku-4-5", "codex": "gpt-5.6-luna",
          "opencode": "minimax-coding-plan/MiniMax-M2.7", "copilot": "gpt-4.1"}
TIMEOUT = 900


def prompt(site: str) -> str:
    return (f"There is a small web app at {site} . Create the Robot Framework test file tests/pay.robot with one "
            "test case `Pay With Card` that uses the Browser library (headless chromium) to open the page, log in "
            "as user `alice` (any password), verify the welcome message, enter the card number 4242 in the "
            "payment form, click `Pay now` and verify that `Paid with 4242` is shown. Then run it with "
            "`robot -d results tests/pay.robot` and fix it until it passes. "
            "Finish with the final robot summary line.")


def clean_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k == "CLAUDECODE")}
    env.pop("ANTHROPIC_BASE_URL", None)
    env.pop("VIRTUAL_ENV", None)
    return env


def prepare(agent: str, cell: Path):
    ws, home = cell / "ws", cell / "home"
    shutil.rmtree(cell, ignore_errors=True)
    (ws / "site").mkdir(parents=True)
    home.mkdir(parents=True)
    for f in ("index.html", "frame.html"):
        shutil.copy2(HERE / "site" / f, ws / "site" / f)
    subprocess.run(["git", "init", "-q"], cwd=ws)
    creds = []
    if agent == "claude":
        shutil.copy2(Path.home() / ".claude" / ".credentials.json", home / ".credentials.json")
        shutil.copy2(Path.home() / ".claude.json", home / ".claude.json")
        (cell / "empty_mcp.json").write_text('{"mcpServers":{}}')
        creds += [home / ".credentials.json", home / ".claude.json"]
    elif agent == "codex":
        shutil.copy2(Path.home() / ".codex" / "auth.json", home / "auth.json")
        (home / "config.toml").write_text(f'model = "{MODELS["codex"]}"\nmodel_reasoning_effort = "low"\n'
                                          f'[projects."{ws}"]\ntrust_level = "trusted"\n')
        creds.append(home / "auth.json")
    elif agent == "opencode":
        (ws / "opencode.json").write_text(json.dumps({"$schema": "https://opencode.ai/config.json", "permission": {
            "edit": "allow", "bash": "allow", "webfetch": "allow", "external_directory": "allow"}}))
    info = install(agent, ws, home, VENV_BIN)
    return ws, home, info, creds


def build_cmd(agent: str, ws: Path, home: Path, cell: Path, info: dict, text: str):
    env = {**clean_env(), **info["extra_env"], "RFMCP_HOOK_LOG": str(cell / "hook.jsonl")}
    if agent == "claude":
        env["CLAUDE_CONFIG_DIR"] = str(home)
        cmd = ["claude", "-p", text, "--model", MODELS["claude"], "--output-format", "stream-json", "--verbose",
               "--dangerously-skip-permissions", "--max-turns", "40", "--mcp-config", str(cell / "empty_mcp.json"),
               "--strict-mcp-config"]
    elif agent == "codex":
        env["CODEX_HOME"] = str(home)
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-C", str(ws),
               "--dangerously-bypass-approvals-and-sandbox", *info["extra_args"], text]
    elif agent == "opencode":
        cmd = ["opencode", "run", "--dir", str(ws), "-m", MODELS["opencode"], "--format", "json",
               "--dangerously-skip-permissions", text]
    else:
        cmd = ["copilot", "-p", text, "--model", MODELS["copilot"], "--allow-all", "--no-ask-user",
               "--output-format", "json", "-C", str(ws), "--no-auto-update",
               *info["extra_args"]]
    return cmd, env


def walk_strings(o, out: list) -> None:
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, str) and k in ("command", "cmd", "arguments", "input", "description", "skill", "name",
                                            "file_path", "filePath", "path"):
                out.append((k, v))
            else:
                walk_strings(v, out)
    elif isinstance(o, list):
        for v in o:
            walk_strings(v, out)
    elif isinstance(o, str) and o.startswith("{") and "rfmcp" in o:
        try:
            walk_strings(json.loads(o), out)
        except ValueError:
            pass


def analyze(agent: str, log: str) -> dict:
    strs: list = []
    for line in log.splitlines():
        if '"session.skills_loaded"' in line or '"commands_changed"' in line or '"subtype": "init"' in line \
                or '"subtype":"init"' in line:
            continue  # skill catalogs announced by the agent, not a use of the skill
        try:
            walk_strings(json.loads(line), strs)
        except ValueError:
            continue
    cmds, seen = [], set()
    for k, v in strs:
        for m in re.finditer(r"rfmcp\s+(start|stop|status|step|run|check|search|doc|state|guide|wait|vars)\b[^\n\"]{0,80}", v):
            s = m.group(0)
            if s not in seen:
                seen.add(s)
                cmds.append(s)
    sub = {}
    for c in cmds:
        k = c.split()[1]
        sub[k] = sub.get(k, 0) + 1
    skill = any((k in ("skill", "name") and v == "robotframework") or "robotframework/SKILL.md" in v
                for k, v in strs)
    res = {"rfmcp_cmds_distinct": len(cmds), "by_subcommand": sub, "skill_loaded": skill, "first_cmds": cmds[:12]}
    m = re.findall(r'"total_cost_usd":\s*([\d.]+)', log)
    if m:
        res["cost_usd"] = float(m[-1])
    m = re.findall(r'"num_turns":\s*(\d+)', log)
    if m:
        res["turns"] = int(m[-1])
    return res


def run_agent(agent: str, root: Path, results: dict) -> None:
    cell = root / agent
    ws, home, info, creds = prepare(agent, cell)
    site = (ws / "site" / "index.html").as_uri()
    cmd, env = build_cmd(agent, ws, home, cell, info, prompt(site))
    t0 = time.time()
    with open(cell / "agent_stdout.log", "w") as out:
        try:
            p = subprocess.run(cmd, cwd=ws, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=TIMEOUT)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    dur = round(time.time() - t0)
    log = (cell / "agent_stdout.log").read_text(errors="replace")
    r = {"rc": rc, "secs": dur, **analyze(agent, log)}
    # helper still running? (agent forgot rfmcp stop) -> record, then stop it
    st = ws / ".rf" / "rfmcp.json"
    r["helper_left_running"] = False
    if st.exists():
        s = json.loads(st.read_text())
        r["helper_left_running"] = not s.get("stopped") and Path(f"/proc/{s.get('pid')}").exists()
        sp = subprocess.run([str(VENV_BIN / "rfmcp"), "stop"], cwd=ws, capture_output=True, text=True,
                            env={**clean_env(), **info["extra_env"]})
        r["final_stop"] = sp.stdout.strip()[-200:]
    hl = cell / "hook.jsonl"
    hooks = [json.loads(l) for l in hl.read_text().splitlines()] if hl.exists() else []
    r["hook_calls"] = len(hooks)
    r["hook_calls_with_robot_file"] = sum(1 for h in hooks if h.get("files"))
    test = ws / "tests" / "pay.robot"
    r["test_exists"] = test.exists()
    if test.exists():
        rr = subprocess.run([str(VENV_BIN / "robot"), "-d", str(cell / "rerun"), "--console", "none", str(test)],
                            cwd=ws, env={**clean_env(), **info["extra_env"]}, timeout=300)
        r["independent_rerun_rc"] = rr.returncode
        r["uses_frame_piercing"] = ">>>" in test.read_text()
    for c in creds:
        try:
            c.unlink()
        except OSError:
            pass
    results[agent] = r
    print(agent, json.dumps(r)[:900], flush=True)


def main() -> int:
    root = Path(sys.argv[1])
    agents = sys.argv[2:] or ["claude", "codex", "opencode", "copilot"]
    results: dict = {}
    ths = [threading.Thread(target=run_agent, args=(a, root, results)) for a in agents]
    for t in ths:
        t.start()
        time.sleep(3)
    for t in ths:
        t.join()
    out = HERE / "results_agents.json"
    prev = json.loads(out.read_text()) if out.exists() else {}
    prev.update(results)
    out.write_text(json.dumps(prev, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
