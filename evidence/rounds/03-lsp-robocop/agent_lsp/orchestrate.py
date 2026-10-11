#!/usr/bin/env python3
"""Round-3 agent x robotcode-LSP orchestrator.

  python3 orchestrate.py <agent> <variant> <scenario> [rep]
  agent:    claude | codex | opencode | copilot
  variant:  pass  = robotcode LS behind rc_lsp_shim --passthrough (native client behaviour, traffic logged)
            fix   = robotcode LS behind rc_lsp_shim (full-change -> ranged change, languageId fix)
            hook  = no LSP; PostToolUse hook runs `robotcode analyze code` (claude/codex)
            none  = no LSP, no hook (control)
            pass_norc / fix_norc = like pass/fix but robocop disabled via LSP settings (claude only)
  scenario: natural | forced | tools
Results in runs/<agent>/<variant>_<scenario>_r<rep>/
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUNS = BASE / "runs"
TEMPLATE = BASE / "proj_template"
SHIM = BASE / "shim" / "rc_lsp_shim.py"
HOOK = BASE / "hooks" / "rf_analyze_hook.py"
RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
PY = "/usr/bin/python3"
MODELS = {"claude": "claude-haiku-4-5", "codex": "gpt-5.6-luna",
          "opencode": "minimax-coding-plan/MiniMax-M2.7", "copilot": "gpt-4.1"}
TIMEOUT = 420

SNIPPET = """Planted Errors
    Launch Storefront
    Clik    id=search-button
    Type Into Product Finder    shoes    extra-arg
    Hit Count Should Be    ${undefined}"""

PROMPTS = {
    "natural": (
        "In this Robot Framework project, add a new test case named `Search Works` to tests/shop.robot. "
        "It must open the shop page, enter the search term `shoes` into the product finder and check that "
        "exactly 3 results are shown. Use the keywords defined in resources/shop.resource. "
        "IMPORTANT: do NOT run any tests and do NOT run robot, robotcode, python or any other command that "
        "executes or checks the suite - only edit files. If after an edit you are told about problems in "
        "the file, fix them with further edits. When finished, reply with DONE, then list verbatim any "
        "problem/diagnostic reports you were shown after your edits (or `NO_DIAGNOSTICS_SEEN`)."),
    "forced": (
        "Append exactly the following test case to the END of the *** Test Cases *** section in "
        "tests/shop.robot. Copy it verbatim, INCLUDING its mistakes, with a blank line before it and "
        "4-space indentation as shown:\n```\n" + SNIPPET + "\n```\n"
        "IMPORTANT: do NOT run any tests and do NOT run robot, robotcode, python or any other command that "
        "executes or checks the suite - only read/edit files. After your edit, if you are told about any "
        "problems in the file (by your tools or the system), fix every reported problem with further edits "
        "(for an undefined variable use the literal value 3). If you are not told about any problems, leave "
        "the snippet unchanged. When finished, reply with DONE, then quote verbatim every problem/diagnostic "
        "report you received after your edits (or write `NO_DIAGNOSTICS_SEEN`)."),
    "forced2": None,  # filled below
    "tools": (
        "Use ONLY your LSP / language-server code-intelligence tool (not grep, not reading files, not the "
        "shell) to answer, and report the raw tool results verbatim:\n"
        "1) hover on the keyword `Probe Catalog Endpoint` in tests/shop.robot line 7 (it starts at column 17)\n"
        "2) hover on `Should Be Equal As Integers` in tests/shop.robot line 8 column 5\n"
        "3) hover on `Fill Text` in resources/shop.resource line 22 column 5\n"
        "4) workspace symbol search for `Product`\n"
        "5) workspace symbol search for `Fill Text`\n"
        "6) go to definition of `Probe Catalog Endpoint` in tests/shop.robot line 7 column 17\n"
        "Make the tool calls strictly one at a time (never in parallel). "
        "If you have no LSP tool, answer NO_LSP_TOOL and stop."),
}


PROMPTS["forced2"] = PROMPTS["forced"].replace(
    "When finished, reply with DONE",
    "After the edit, as a separate later step, read resources/shop.resource and count the keywords it defines. "
    "When finished, reply with DONE and the keyword count")


PROMPTS["forced3"] = (
    "Do these steps in order, each as its own separate file edit / tool call:\n"
    "STEP 1: append a new last line `# --- search tests ---` (after a blank line) to tests/shop.robot.\n"
    "STEP 2: in a SECOND, separate edit, append exactly the following test case after that comment line in "
    "tests/shop.robot. Copy it verbatim, INCLUDING its mistakes, with a blank line before it and 4-space "
    "indentation as shown:\n```\n" + SNIPPET + "\n```\n"
    "STEP 3: read resources/shop.resource and count the keywords it defines.\n"
    "IMPORTANT: do NOT run any tests and do NOT run robot, robotcode, python or any other command that "
    "executes or checks the suite - only read/edit files. If at any point you are told about problems in "
    "tests/shop.robot (by your tools or the system), fix every reported ERROR with further edits (for an "
    "undefined variable use the literal value 3). If you are not told about any problems, leave the snippet "
    "unchanged. When finished, reply with DONE and the keyword count, then quote verbatim every "
    "problem/diagnostic report you received (or write `NO_DIAGNOSTICS_SEEN`).")


def clean_env():
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k == "CLAUDECODE")}
    env.pop("ANTHROPIC_BASE_URL", None)
    return env


def lsp_cmd(cell, variant):
    args = [str(SHIM), "--log", str(cell / "lsp.jsonl")]
    if variant.startswith("pass"):
        args.append("--passthrough")
    return PY, args + ["--", RC, "language-server", "--stdio"]


def prepare(agent, variant, cell):
    proj = cell / "proj"
    shutil.copytree(TEMPLATE, proj)
    if os.environ.get("NOGIT") != "1":  # real projects are git repos; also escapes the parent worktree's excludes
        subprocess.run(["git", "init", "-q"], cwd=proj)
    if os.environ.get("WARM") == "1":  # pre-warm robotcode's per-project analysis cache (.robotcode_cache)
        subprocess.run([RC, "analyze", "code"], cwd=proj, capture_output=True, timeout=120)
    home = RUNS / agent / "home" if agent != "codex" else cell / "codex_home"  # codex config is per cell
    home.mkdir(parents=True, exist_ok=True)
    lsp = variant.startswith(("pass", "fix"))
    cmd0, args = lsp_cmd(cell, variant)
    hook_env = {"RF_HOOK_ROBOTCODE": RC, "RF_HOOK_LOG": str(cell / "hook.jsonl")}
    if agent == "claude":
        shutil.copy2(Path.home() / ".claude" / ".credentials.json", home / ".credentials.json")
        if not (home / ".claude.json").exists():
            shutil.copy2(Path.home() / ".claude.json", home / ".claude.json")
        (cell / "empty_mcp.json").write_text('{"mcpServers":{}}')
        if lsp:
            pdir = cell / "plugin" / "rf-lsp"
            (pdir / ".claude-plugin").mkdir(parents=True)
            (pdir / ".claude-plugin" / "plugin.json").write_text(json.dumps(
                {"name": "rf-lsp", "version": "0.0.1", "description": "robotcode LSP for .robot/.resource"}))
            srv = {"command": cmd0, "args": args,
                   "extensionToLanguage": {".robot": "robotframework", ".resource": "robotframework"},
                   "startupTimeout": 120000}
            if variant.endswith("_norc"):
                srv["settings"] = {"robotcode": {"robocop": {"enabled": False}}}
            (pdir / ".lsp.json").write_text(json.dumps({"robotcode": srv}, indent=1))
        if variant == "hook":
            settings = {"hooks": {"PostToolUse": [{"matcher": "Edit|Write|MultiEdit", "hooks": [
                {"type": "command", "command": f"{' '.join(f'{k}={v}' for k, v in hook_env.items())} {PY} {HOOK}",
                 "timeout": 120}]}]}}
            (cell / "settings.json").write_text(json.dumps(settings, indent=1))
    elif agent == "codex":
        shutil.copy2(Path.home() / ".codex" / "auth.json", home / "auth.json")
        cfg = f'model = "{MODELS["codex"]}"\nmodel_reasoning_effort = "low"\n'
        cfg += f'[projects."{proj}"]\ntrust_level = "trusted"\n'
        if variant == "hook":
            envs = " ".join(f"{k}={v}" for k, v in hook_env.items())
            cfg += ('\n[[hooks.PostToolUse]]\nmatcher = "apply_patch|Edit|Write"\n'
                    '[[hooks.PostToolUse.hooks]]\ntype = "command"\n'
                    f'command = "{envs} {PY} {HOOK}"\ntimeout = 120\n')
        (home / "config.toml").write_text(cfg)
    elif agent == "opencode":
        cfg = {"$schema": "https://opencode.ai/config.json",
               "permission": {"edit": "allow", "bash": "allow", "webfetch": "allow", "external_directory": "allow"}}
        if lsp:
            cfg["lsp"] = {"robotcode": {"command": [cmd0] + args, "extensions": [".robot", ".resource"]}}
        (proj / "opencode.json").write_text(json.dumps(cfg, indent=1))
    elif agent == "copilot":
        if variant.startswith("plughook"):  # Claude-format plugin dir loaded with --plugin-dir (hooks + .lsp.json)
            pdir = cell / "plugin" / "rf-lsp"
            (pdir / ".claude-plugin").mkdir(parents=True)
            (pdir / "hooks").mkdir()
            (pdir / ".claude-plugin" / "plugin.json").write_text(json.dumps(
                {"name": "rf-lsp", "version": "0.0.1", "description": "robotcode LSP + analyze hook"}))
            envs = " ".join(f"{k}={v}" for k, v in hook_env.items())
            (pdir / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"PostToolUse": [{"hooks": [
                {"type": "command", "command": ("RF_HOOK_FORMAT=copilot " if variant == "plughook2" else "")
                 + f"{envs} {PY} {HOOK}", "timeout": 120}]}]}}, indent=1))
            cmd0, args = lsp_cmd(cell, "fix")
            (pdir / ".lsp.json").write_text(json.dumps({"robotcode": {"command": cmd0, "args": args,
                "extensionToLanguage": {".robot": "robotframework", ".resource": "robotframework"}}}, indent=1))
        if variant == "hook":
            (proj / ".github" / "hooks").mkdir(parents=True)
            envs = " ".join(f"{k}={v}" for k, v in hook_env.items())
            (proj / ".github" / "hooks" / "rf.json").write_text(json.dumps({"version": 1, "hooks": {"postToolUse": [
                {"type": "command", "bash": f"RF_HOOK_FORMAT=copilot {envs} {PY} {HOOK}", "timeoutSec": 120}]}},
                indent=1))
        if lsp:
            (proj / ".github").mkdir(exist_ok=True)
            (proj / ".github" / "lsp.json").write_text(json.dumps({"lspServers": {"robotcode": {
                "command": cmd0, "args": args,
                "fileExtensions": {".robot": "robotframework", ".resource": "robotframework"}}}}, indent=1))
    return proj, home


def build_cmd(agent, variant, scenario, prompt, proj, home, cell):
    env = clean_env()
    if agent == "claude":
        env["CLAUDE_CONFIG_DIR"] = str(home)
        cmd = ["claude", "-p", prompt, "--model", MODELS["claude"], "--output-format", "stream-json",
               "--verbose", "--dangerously-skip-permissions", "--max-turns", "25",
               "--mcp-config", str(cell / "empty_mcp.json"), "--strict-mcp-config",
               "--debug-file", str(cell / "claude_debug.log")]
        if (cell / "plugin" / "rf-lsp").exists():
            cmd += ["--plugin-dir", str(cell / "plugin" / "rf-lsp")]
        if (cell / "settings.json").exists():
            cmd += ["--settings", str(cell / "settings.json")]
    elif agent == "codex":
        env["CODEX_HOME"] = str(home)
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-C", str(proj),
               "--dangerously-bypass-approvals-and-sandbox"]
        if variant == "hook":  # codex only runs reviewed+trusted hooks; headless needs the bypass
            cmd.append("--dangerously-bypass-hook-trust")
        cmd.append(prompt)
    elif agent == "opencode":
        if scenario == "tools":
            env["OPENCODE_EXPERIMENTAL_LSP_TOOL"] = "true"
        cmd = ["opencode", "run", "--dir", str(proj), "-m", MODELS["opencode"], "--format", "json",
               "--dangerously-skip-permissions", "--print-logs", "--log-level", "INFO", prompt]
    elif agent == "copilot":
        cmd = ["copilot", "-p", prompt, "--model", MODELS["copilot"], "--allow-all", "--no-ask-user",
               "--output-format", "json", "-C", str(proj), "--log-dir", str(cell / "copilot_logs"),
               "--log-level", "debug", "--no-auto-update", "--disable-builtin-mcps"]
        if (cell / "plugin" / "rf-lsp").exists():
            cmd += ["--plugin-dir", str(cell / "plugin" / "rf-lsp")]
    return cmd, env


def tree_pids(root_pids):
    kids = {}
    for d in Path("/proc").iterdir():
        if d.name.isdigit():
            try:
                st = (d / "stat").read_text()
                kids.setdefault(int(st[st.rindex(")") + 2:].split()[1]), []).append(int(d.name))
            except Exception:
                pass
    out, stack = [], list(root_pids)
    while stack:
        p = stack.pop()
        out.append(p)
        stack.extend(kids.get(p, []))
    return out


def cell_pids(cell):
    """Shim/robotcode processes belonging to this cell (shim cmdline carries the cell path)."""
    roots = []
    for d in Path("/proc").iterdir():
        if d.name.isdigit():
            try:
                cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode()
                if str(cell) in cmd and ("rc_lsp_shim" in cmd or "rf_analyze_hook" in cmd):
                    roots.append(int(d.name))
            except Exception:
                pass
    return tree_pids(roots) if roots else []


def rss_kb(pids):
    tot = 0
    for p in pids:
        try:
            for line in Path(f"/proc/{p}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    tot += int(line.split()[1])
        except Exception:
            pass
    return tot


def run(agent, variant, scenario, rep="1"):
    cell = RUNS / agent / f"{variant}_{scenario}_r{rep}"
    if cell.exists():
        shutil.rmtree(cell)
    cell.mkdir(parents=True)
    proj, home = prepare(agent, variant, cell)
    prompt = PROMPTS[scenario]
    cmd, env = build_cmd(agent, variant, scenario, prompt, proj, home, cell)
    (cell / "cmd.json").write_text(json.dumps({"cmd": cmd, "prompt": prompt}, indent=1))
    peak = {"rss_kb": 0, "t": None, "server_seen_t": None}
    stop = threading.Event()
    t_start = time.time()

    def monitor():
        while not stop.is_set():
            pids = cell_pids(cell)
            if pids and peak["server_seen_t"] is None:
                peak["server_seen_t"] = round(time.time() - t_start, 1)
            r = rss_kb(pids)
            if r > peak["rss_kb"]:
                peak.update(rss_kb=r, t=round(time.time() - t_start, 1), npids=len(pids))
            time.sleep(0.5)

    th = threading.Thread(target=monitor, daemon=True)
    th.start()
    timed_out = False
    with open(cell / "agent_stdout.log", "wb") as o, open(cell / "agent_stderr.log", "wb") as e:
        p = subprocess.Popen(cmd, cwd=str(proj), env=env, stdout=o, stderr=e, stdin=subprocess.DEVNULL,
                             start_new_session=True)
        try:
            rc = p.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out, rc = True, None
            os.killpg(p.pid, signal.SIGTERM)
            time.sleep(3)
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    t_end = time.time()
    time.sleep(3)
    left3 = cell_pids(cell)
    stop.set()
    th.join()
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in cell_pids(cell):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(1)
    # ground truth: analyze final test file (errors only) outside the agent
    gt = subprocess.run([RC, "analyze", "code", "--severity", "error", "tests/shop.robot"], cwd=proj,
                        capture_output=True, text=True, timeout=120)
    res = {"agent": agent, "variant": variant, "scenario": scenario, "rep": rep, "model": MODELS[agent],
           "warm_cache": os.environ.get("WARM") == "1",
           "rc": rc, "timed_out": timed_out, "session_wall_s": round(t_end - t_start, 1),
           "lsp_proc_first_seen_s": peak["server_seen_t"], "lsp_peak_rss_kb": peak["rss_kb"],
           "lsp_peak_rss_t": peak["t"], "lsp_procs_left_3s_after_exit": left3,
           "final_analyze_errors": [l for l in gt.stdout.splitlines() if "[ERROR]" in l],
           "final_shop_robot": (proj / "tests" / "shop.robot").read_text()}
    (cell / "result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("agent", "variant", "scenario", "rep", "rc", "timed_out",
                                          "session_wall_s", "lsp_peak_rss_kb", "lsp_procs_left_3s_after_exit",
                                          "final_analyze_errors")}))
    return res


if __name__ == "__main__":
    run(*sys.argv[1:])
