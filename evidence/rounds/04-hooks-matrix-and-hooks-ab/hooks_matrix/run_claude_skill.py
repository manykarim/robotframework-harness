#!/usr/bin/env python3
"""Claude-only probes: (a) hooks declared in SKILL.md frontmatter (active only after the skill is invoked),
(b) an asyncRewake PostToolUse hook that finishes 8 s later with exit 2 (does it wake the model in -p mode?).

  python3 run_claude_skill.py
Output: runs/claude/skill/
"""
import json
import shutil
import subprocess
import time
from pathlib import Path

import run_probe as rp

cell = rp.BASE / "runs" / "claude" / "skill"
if cell.exists():
    shutil.rmtree(cell)
proj = cell / "proj"
(proj / "tests").mkdir(parents=True)
subprocess.run(["git", "init", "-q"], cwd=proj)
home = cell / "home"
home.mkdir()
shutil.copy2(Path.home() / ".claude" / ".credentials.json", home / ".credentials.json")
shutil.copy2(Path.home() / ".claude.json", home / ".claude.json")
(cell / "empty_mcp.json").write_text('{"mcpServers":{}}')
(cell / "behavior.json").write_text(json.dumps({
    "POST": {}, "STOP": {"stop": "block_once"},
    "REWAKE": {"sleep": 8, "exit": 2, "stderr": "{marker}: async RF run finished: 1 test, 0 passed, 1 failed (Clik not found)",
               "context": False}}))
pdir = cell / "plugin" / "rfharness"
(pdir / ".claude-plugin").mkdir(parents=True)
(pdir / "hooks").mkdir()
(pdir / "skills" / "rf-harness").mkdir(parents=True)
(pdir / ".claude-plugin" / "plugin.json").write_text(json.dumps(
    {"name": "rfharness", "version": "0.0.1", "description": "RF harness probe (skill hooks + asyncRewake)"}))
H = lambda ev, src, extra="": f"{rp.PY} {rp.HOOK} --agent claude --event {ev} --cell {cell} --src {src}{extra}"
(pdir / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {
    "PostToolUse": [{"matcher": "Write|Edit", "hooks": [
        {"type": "command", "command": H("PostToolUse", "rewake", " --bkey REWAKE"), "asyncRewake": True,
         "timeout": 60}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": H("SessionEnd", "plugin", " --passive")}]}]}}, indent=1))
(pdir / "skills" / "rf-harness" / "SKILL.md").write_text(f"""---
name: rf-harness
description: Robot Framework harness. ALWAYS use this skill before creating or editing any .robot file.
hooks:
  PostToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: "{H('PostToolUse', 'skill')}"
  Stop:
    - hooks:
        - type: command
          command: "{H('Stop', 'skill')}"
---
# RF harness
When writing Robot Framework files, use 4-space separators. After each file write you may receive harness
feedback; follow it.
""")
prompt = ("First invoke the rf-harness skill. Then create the file tests/s.robot containing a test case `Probe` with "
          "the single step `Log    hello`, using your file-writing tool. Then wait by running the shell command "
          "`sleep 12` and then reply with DONE plus every string starting with `ZQX-` you have seen anywhere, "
          "verbatim, each with where you saw it.")
env = rp.clean_env()
env["CLAUDE_CONFIG_DIR"] = str(home)
cmd = ["claude", "-p", prompt, "--model", rp.MODELS["claude"], "--output-format", "stream-json", "--verbose",
       "--include-hook-events", "--dangerously-skip-permissions", "--max-turns", "30",
       "--mcp-config", str(cell / "empty_mcp.json"), "--strict-mcp-config",
       "--debug-file", str(cell / "claude_debug.log"), "--plugin-dir", str(pdir)]
t0 = time.time()
with open(cell / "agent_stdout.log", "wb") as o, open(cell / "agent_stderr.log", "wb") as e:
    rc = subprocess.run(cmd, cwd=proj, env=env, stdout=o, stderr=e, stdin=subprocess.DEVNULL, timeout=400).returncode
t1 = time.time()
files = {str(f.relative_to(proj)): f.read_text()[:300] for f in proj.rglob("*") if f.is_file() and ".git" not in f.parts}
(cell / "result.json").write_text(json.dumps({"rc": rc, "t_start": t0, "t_end": t1, "wall_s": round(t1 - t0, 1),
                                              "files": files}, indent=1))
for cred in (".credentials.json", ".claude.json"):
    (home / cred).unlink(missing_ok=True)
print(json.dumps({"rc": rc, "wall_s": round(t1 - t0, 1), "files": list(files)}))
