#!/usr/bin/env python3
"""Round-4 hook capability probes.

  python3 run_probe.py <agent> <cell> [tag]
  agent: claude | codex | opencode | copilot
  cell:  main  = all lifecycle events + context markers + PreToolUse rewrite/deny + Stop block-once
                 + SessionStart setsid helper / SessionEnd stop
         slow  = 20 s synchronous PostToolUse on file writes, 3 s timeout on a 10 s Bash PostToolUse,
                 crashing (exit 1) PreToolUse on one Bash command
Output: runs/<agent>/<cell>[_tag]/{hooks.jsonl, helper.log, agent_stdout.log, result.json, proj/}
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
HOOK = BASE / "bin" / "hooklog.py"
HELPER = BASE / "bin" / "fake_helper.py"
OC_PLUGIN = BASE / "plugins" / "opencode_probe.js"
PY = "/usr/bin/python3"
MODELS = {"claude": "claude-haiku-4-5", "codex": "gpt-5.6-luna",
          "opencode": "minimax-coding-plan/MiniMax-M2.7", "copilot": "gpt-4.1"}
TIMEOUT = int(os.environ.get("PROBE_TIMEOUT", "420"))
if os.environ.get("PROBE_MODEL"):  # e.g. copilot: gpt-4.1 is no longer selectable in CLI 1.0.91
    MODELS[sys.argv[1]] = os.environ["PROBE_MODEL"]

ROBOT = "*** Test Cases ***\nProbe\n    Clik    id=x\n"
PROMPTS = {
    "main": (
        "This is a hook-probe session. Do exactly these steps, one tool call at a time (never in parallel):\n"
        "1. Create the file tests/b.robot with exactly this content, using your file-writing/editing tool "
        "(NOT the shell):\n```\n" + ROBOT + "```\n"
        "2. Create the file tests/deny_me.robot with the same content, using your file-writing tool. If that is "
        "blocked, follow the instructions you receive.\n"
        "3. Run the shell command `echo hello-from-bash`.\n"
        "4. Run the shell command `sh -c 'echo failing-step; exit 3'` (it is expected to fail).\n"
        "5. Read tests/b.robot back.\n"
        "Then answer with: (a) the final content of tests/b.robot, (b) EVERY string starting with `ZQX-` that "
        "appeared anywhere in your context (system/developer messages, reminders, your prompt, tool results, "
        "hook feedback) - verbatim, one per line, each with where you saw it, (c) whether any tool call was "
        "blocked or changed and why."),
    "stopgate": (
        "Create the file notes/one.txt containing the single word `one` using your file-writing tool, then reply "
        "with DONE and every string starting with `ZQX-` that you saw anywhere (system prompt, messages, tool "
        "results), verbatim. Also state the exact text of any 'Session context from the RF harness' line in your "
        "system prompt, if there is one."),
    "parallel": (
        "In ONE single assistant response, issue THREE shell tool calls IN PARALLEL (all three in the same "
        "response, do not wait between them): `echo one`, `echo two`, `echo three`. Then, in one further response, "
        "issue three parallel file-write tool calls creating p/a.txt, p/b.txt and p/c.txt (content: a, b, c). "
        "Then reply DONE."),
    "slow": (
        "Do exactly these steps, one tool call at a time (never in parallel):\n"
        "1. Create the file notes/one.txt containing the single word `one`, using your file-writing tool (NOT the "
        "shell).\n"
        "2. Run the shell command `date +%s.%N`.\n"
        "3. Run the shell command `echo second-step`.\n"
        "Then answer with the output of step 2, whether any step failed or was blocked (quote any message), and "
        "EVERY string starting with `ZQX-` that you saw anywhere, verbatim."),
}
BEHAVIOR = {
    "main": {"SS": {"start_daemon": True}, "SE": {"stop_daemon": True, "context": False},
             "PRE": {"pre": "robot"}, "STOP": {"stop": "block_once"}},
    "stopgate_text": {"STOP": {"stop": "text_complete"}},
    "stopgate_msg": {"STOP": {"stop": "msg_finish"}},
    "stopgate_idle": {"STOP": {"stop": "block_once"}},
    "stopgate_sys0": {"SYS": {"mode": "append0"}},
    "parallel": {"POST": {"sleep": 5}, "STOP": {"context": False}, "SE": {"context": False}},
    "stopgate_survive": {"SS": {"start_daemon": True}, "SE": {"context": False}},
    "stopgate_notrust": {},
    "slow": {"POST": {"sleep": 20, "only_tools": "Write|Edit|write|edit|create|apply_patch"},
             "POST_bash": {"sleep": 10, "only_cmd": "date"},
             "PRE_bash": {"exit": 1, "stderr": "probe crash {marker}", "only_cmd": "second-step"},
             "STOP": {"context": False}, "SE": {"context": False}},
}


def hcmd(agent, event, cell, src="plugin", passive=False, bkey=None):
    c = f"{PY} {HOOK} --agent {agent} --event {event} --cell {cell} --src {src}"
    if bkey:
        c += f" --bkey {bkey}"
    return c + (" --passive" if passive else "")


def clean_env():
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k == "CLAUDECODE")}
    env.pop("ANTHROPIC_BASE_URL", None)
    env.pop("VIRTUAL_ENV", None)
    return env


def claude_hooks(cell, kind):
    H = lambda ev, **kw: {"type": "command", "command": hcmd("claude", ev, cell, **kw)}
    if kind != "slow":
        return {
            "SessionStart": [{"hooks": [H("SessionStart")]}],
            "UserPromptSubmit": [{"hooks": [H("UserPromptSubmit")]}],
            "PreToolUse": [{"matcher": "Write|Edit|MultiEdit|Bash", "hooks": [H("PreToolUse")]}],
            "PostToolUse": [{"matcher": "Write|Edit|MultiEdit|Bash|Read", "hooks": [H("PostToolUse")]}],
            "PostToolUseFailure": [{"hooks": [H("PostToolUseFailure")]}],
            "PostToolBatch": [{"hooks": [H("PostToolBatch", passive=True)]}],
            "Stop": [{"hooks": [H("Stop")]}],
            "SessionEnd": [{"hooks": [H("SessionEnd")]}],
            "Notification": [{"hooks": [H("Notification", passive=True)]}],
            "PreCompact": [{"hooks": [H("PreCompact", passive=True)]}],
            "StopFailure": [{"hooks": [H("StopFailure", passive=True)]}],
        }
    return {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{**H("PreToolUse", bkey="PRE_bash"), "timeout": 30}]}],
        "PostToolUse": [{"matcher": "Write|Edit", "hooks": [{**H("PostToolUse"), "timeout": 60}]},
                        {"matcher": "Bash", "hooks": [{**H("PostToolUse", bkey="POST_bash"), "timeout": 3}]}],
        "PostToolUseFailure": [{"hooks": [H("PostToolUseFailure", passive=True)]}],
        "Stop": [{"hooks": [H("Stop", passive=True)]}],
        "SessionEnd": [{"hooks": [H("SessionEnd", passive=True)]}],
    }


def codex_toml(cell, kind):
    def block(ev, matcher=None, timeout=None, **kw):
        s = f"\n[[hooks.{ev}]]\n" + (f'matcher = "{matcher}"\n' if matcher else "")
        s += f"[[hooks.{ev}.hooks]]\ntype = \"command\"\ncommand = \"{hcmd('codex', ev, cell, **kw)}\"\n"
        return s + (f"timeout = {timeout}\n" if timeout else "")
    if kind != "slow":
        return "".join([block("SessionStart"), block("UserPromptSubmit"),
                        block("PreToolUse", "apply_patch|Edit|Write|Bash"),
                        block("PostToolUse", "apply_patch|Edit|Write|Bash"),
                        block("PermissionRequest", passive=True), block("Stop"), block("SessionEnd"),
                        block("PreCompact", passive=True), block("Interrupt", passive=True)])
    return "".join([block("PreToolUse", "Bash", 30, bkey="PRE_bash"),
                    block("PostToolUse", "apply_patch|Edit|Write", 60),
                    block("PostToolUse", "Bash", 3, bkey="POST_bash"),
                    block("Stop", passive=True), block("SessionEnd", passive=True)])


def copilot_hooks(cell, kind):
    H = lambda ev, **kw: {"type": "command", "bash": hcmd("copilot", ev, cell, **kw), "timeoutSec": 30}
    if kind != "slow":
        return {"version": 1, "hooks": {
            "sessionStart": [H("sessionStart")], "userPromptSubmitted": [H("userPromptSubmitted")],
            "userPromptTransformed": [H("userPromptTransformed", passive=True)],
            "preToolUse": [H("preToolUse")], "postToolUse": [H("postToolUse")],
            "postToolUseFailure": [H("postToolUseFailure")], "agentStop": [H("agentStop")],
            "sessionEnd": [H("sessionEnd")], "errorOccurred": [H("errorOccurred", passive=True)],
            "notification": [H("notification", passive=True)],
            "permissionRequest": [H("permissionRequest", passive=True)],
            "preCompact": [H("preCompact", passive=True)]}}
    pre = H("preToolUse", bkey="PRE_bash")
    post_w = H("postToolUse")
    post_w["timeoutSec"] = 60
    post_b = H("postToolUse", bkey="POST_bash")
    post_b["timeoutSec"] = 3
    return {"version": 1, "hooks": {"preToolUse": [pre], "postToolUse": [post_w, post_b],
                                    "postToolUseFailure": [H("postToolUseFailure", passive=True)],
                                    "agentStop": [H("agentStop", passive=True)],
                                    "sessionEnd": [H("sessionEnd", passive=True)]}}


def prepare(agent, kind, cell):
    proj = cell / "proj"
    (proj / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=proj)
    (cell / "behavior.json").write_text(json.dumps(BEHAVIOR[kind], indent=1))
    kind = kind.split("_")[0]
    home = cell / "home"
    home.mkdir()
    if agent == "claude":
        shutil.copy2(Path.home() / ".claude" / ".credentials.json", home / ".credentials.json")
        shutil.copy2(Path.home() / ".claude.json", home / ".claude.json")
        (cell / "empty_mcp.json").write_text('{"mcpServers":{}}')
        pdir = cell / "plugin" / "rfprobe"
        (pdir / ".claude-plugin").mkdir(parents=True)
        (pdir / "hooks").mkdir()
        (pdir / ".claude-plugin" / "plugin.json").write_text(json.dumps(
            {"name": "rfprobe", "version": "0.0.1", "description": "hook probe"}))
        (pdir / "hooks" / "hooks.json").write_text(json.dumps({"hooks": claude_hooks(cell, kind)}, indent=1))
        # passive duplicate in project settings: does project-scope load in -p mode?
        (proj / ".claude").mkdir()
        (proj / ".claude" / "settings.json").write_text(json.dumps({"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": hcmd("claude", "SessionStart", cell, "project", True)}]}],
            "PreToolUse": [{"hooks": [{"type": "command", "command": hcmd("claude", "PreToolUse", cell, "project", True)}]}],
            "SessionEnd": [{"hooks": [{"type": "command", "command": hcmd("claude", "SessionEnd", cell, "project", True)}]}]}},
            indent=1))
    elif agent == "codex":
        shutil.copy2(Path.home() / ".codex" / "auth.json", home / "auth.json")
        cfg = f'model = "{MODELS["codex"]}"\nmodel_reasoning_effort = "low"\n'
        cfg += f'[projects."{proj}"]\ntrust_level = "trusted"\n'
        (home / "config.toml").write_text(cfg + codex_toml(cell, kind))
        (proj / ".codex").mkdir()
        (proj / ".codex" / "hooks.json").write_text(json.dumps({"hooks": {
            ev: [{"hooks": [{"type": "command", "command": hcmd("codex", ev, cell, "project", True)}]}]
            for ev in ("SessionStart", "PreToolUse", "SessionEnd")}}, indent=1))
    elif agent == "opencode":
        (proj / ".opencode" / "plugins").mkdir(parents=True)
        shutil.copy2(OC_PLUGIN, proj / ".opencode" / "plugins" / "rfprobe.js")
        (proj / "opencode.json").write_text(json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "permission": {"edit": "allow", "bash": "allow", "webfetch": "allow", "external_directory": "allow"}},
            indent=1))
    elif agent == "copilot":
        pdir = cell / "plugin" / "rfprobe"
        (pdir / ".claude-plugin").mkdir(parents=True)
        (pdir / ".claude-plugin" / "plugin.json").write_text(json.dumps(
            {"name": "rfprobe", "version": "0.0.1", "description": "hook probe"}))
        (pdir / "hooks.json").write_text(json.dumps(copilot_hooks(cell, kind), indent=1))
        # isolated COPILOT_HOME (auth still works via keyring); optional folder trust; passive user-level hooks
        trusted = [str(proj)] if os.environ.get("COPILOT_TRUST", "1") != "0" else []
        (home / "config.json").write_text(json.dumps({"trusted_folders": trusted}, indent=1))
        (home / "hooks").mkdir()
        (home / "hooks" / "probe.json").write_text(json.dumps({"version": 1, "hooks": {
            ev: [{"type": "command", "bash": hcmd("copilot", ev, cell, "user", True)}]
            for ev in ("sessionStart", "preToolUse", "sessionEnd")}}, indent=1))
        # passive duplicate in repo .github/hooks: does it load in -p mode?
        (proj / ".github" / "hooks").mkdir(parents=True)
        (proj / ".github" / "hooks" / "probe.json").write_text(json.dumps({"version": 1, "hooks": {
            ev: [{"type": "command", "bash": hcmd("copilot", ev, cell, "repo", True)}]
            for ev in ("sessionStart", "preToolUse", "sessionEnd")}}, indent=1))
    return proj, home


def build_cmd(agent, kind, prompt, proj, home, cell):
    env = clean_env()
    env["HOOK_CELL"] = str(cell)
    if agent == "claude":
        env["CLAUDE_CONFIG_DIR"] = str(home)
        cmd = ["claude", "-p", prompt, "--model", MODELS["claude"], "--output-format", "stream-json",
               "--verbose", "--include-hook-events", "--dangerously-skip-permissions", "--max-turns", "30",
               "--mcp-config", str(cell / "empty_mcp.json"), "--strict-mcp-config",
               "--debug-file", str(cell / "claude_debug.log"), "--plugin-dir", str(cell / "plugin" / "rfprobe")]
    elif agent == "codex":
        env["CODEX_HOME"] = str(home)
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-C", str(proj),
               "--dangerously-bypass-approvals-and-sandbox"]
        if os.environ.get("NO_BYPASS_TRUST") != "1":
            cmd.append("--dangerously-bypass-hook-trust")
        cmd.append(prompt)
    elif agent == "opencode":
        env["HOOK_HELPER"] = str(HELPER)
        cmd = ["opencode", "run", "--dir", str(proj), "-m", MODELS["opencode"], "--format", "json",
               "--dangerously-skip-permissions", "--print-logs", "--log-level", "INFO", prompt]
    elif agent == "copilot":
        env["COPILOT_HOME"] = str(home)
        cmd = ["copilot", "-p", prompt, "--model", MODELS["copilot"], "--allow-all", "--no-ask-user",
               "--output-format", "json", "-C", str(proj), "--log-dir", str(cell / "copilot_logs"),
               "--log-level", "debug", "--no-auto-update", "--disable-builtin-mcps", "--disable-mcp-server", "RobotMCP",
               "--plugin-dir", str(cell / "plugin" / "rfprobe")]
    return cmd, env


def helper_alive(cell):
    pidf = cell / "helper.pid"
    if not pidf.exists():
        return None
    try:
        pid = int(pidf.read_text())
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def run(agent, kind, tag=""):
    cell = BASE / "runs" / agent / (kind + (f"_{tag}" if tag else ""))
    if cell.exists():
        shutil.rmtree(cell)
    cell.mkdir(parents=True)
    proj, home = prepare(agent, kind, cell)
    prompt = PROMPTS[kind.split("_")[0]]
    cmd, env = build_cmd(agent, kind, prompt, proj, home, cell)
    (cell / "cmd.json").write_text(json.dumps({"cmd": cmd, "prompt": prompt}, indent=1))
    t0 = time.time()
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
    t1 = time.time()
    time.sleep(4)
    alive_after = helper_alive(cell)
    hb = (cell / "helper.heartbeat").read_text() if (cell / "helper.heartbeat").exists() else None
    if alive_after:  # cleanup: never leave the helper behind
        os.kill(alive_after, signal.SIGTERM)
    files = {str(f.relative_to(proj)): f.read_text()[:500] for f in proj.rglob("*")
             if f.is_file() and ".git" not in f.parts and ".opencode" not in f.parts and ".claude" not in f.parts
             and ".codex" not in f.parts and ".github" not in f.parts and f.name != "opencode.json"}
    res = {"agent": agent, "cell": kind, "tag": tag, "model": MODELS[agent], "rc": rc, "timed_out": timed_out,
           "t_start": round(t0, 3), "t_end": round(t1, 3), "wall_s": round(t1 - t0, 1),
           "helper_alive_4s_after_exit": bool(alive_after), "helper_last_heartbeat": hb, "files": files}
    (cell / "result.json").write_text(json.dumps(res, indent=1))
    for cred in ("auth.json", ".credentials.json", ".claude.json"):  # never keep copied credentials
        (home / cred).unlink(missing_ok=True)
    print(json.dumps({k: res[k] for k in ("agent", "cell", "tag", "rc", "timed_out", "wall_s",
                                          "helper_alive_4s_after_exit")}))
    return res


if __name__ == "__main__":
    run(*sys.argv[1:])
