"""Installer for the A/B arm `hookpkg2` (v2 of hookpkg): Agent Skill + hooks, NO agent-facing CLI, no MCP.
Side by side with v1: package `rfharness2`, state dirs .rf/{hook2,exec2,lint2}, env prefix RFH2_, markers rfharness2.

    from install import install
    info = install("claude", workspace, agent_home, venv_bin)
    # -> {"extra_args": [...], "extra_env": {...}, "notes": "...", "markers": [...], "hook_log": None}

Same interface as skillpkg/install.py. Every hook calls ONE entry point:
    "<venv>/bin/python" -S "<hookpkg>/rfharness2/hook.py" <Event> --agent <agent>
per agent (hook capabilities verified in round4/hooks_matrix):
  claude   skill  <ws>/.claude/skills/robotframework/
           hooks  <ws>/.claude/settings.json: SessionStart, UserPromptSubmit, PreToolUse(Write|Edit|MultiEdit|Bash|Read),
                  PostToolUse(Write|Edit|MultiEdit|Bash), PostToolUseFailure(Bash: failing robot run), Stop, SessionEnd
  codex    skill  <ws>/.agents/skills/robotframework/
           hooks  <agent_home>/config.toml [[hooks.*]] SessionStart, UserPromptSubmit, PreToolUse + PostToolUse
                  (apply_patch|Edit|Write|Bash), Stop, SessionEnd (3 s cap) + `--dangerously-bypass-hook-trust` (headless runs only
                  trusted hooks)
  opencode skill  <ws>/.opencode/skills/robotframework/
           plugin <ws>/.opencode/plugins/rfharness2.js: tool.execute.before (deny = throw -- the Python side turns a
                  repeated denial into allow + warning after 2, rewrite = mutate args), tool.execute.after (context
                  PREPENDED to the tool output, short), chat.message (first prompt: project context),
                  assistant-message-finish Stop gate (noReply prompt), dispose
  copilot  plugin <agent_home>/rfharness2-plugin/ (--plugin-dir): skills/ + hooks.json {"version":1} camelCase events
                  sessionStart, userPromptSubmitted, preToolUse, postToolUse, postToolUseFailure, agentStop (sessionEnd is NOT used:
                  copilot fires it after every run; the daemons exit with the agent process / idle)
  pointer  AGENTS.md (all) and CLAUDE.md (claude): short "use the robotframework skill; results arrive by hook"
The package is installed editable into venv_bin's interpreter if missing. Nothing is put on PATH.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

PKG = Path(__file__).resolve().parent
HOOK = PKG / "rfharness2" / "hook.py"
SKILL_SRC = PKG / "rfharness2" / "skill"
SKILL_NAME = "robotframework"
BEGIN, END = "<!-- rfharness2:begin -->", "<!-- rfharness2:end -->"
POINTER = f"""{BEGIN}
## Robot Framework
For any Robot Framework task (.robot/.resource files, robot runs, output.xml) load the `{SKILL_NAME}` skill first.
Hooks run every test line you write live and attach the result (PASS/FAIL per line, failure hints, a short page
summary) to your edit. Page files after each page-changing step: .rf/state/latest/ (controls.txt, aria.yaml,
source.html, screenshot.jpg; history .rf/state/step-NN-*/); docs of a failing keyword: .rf/docs/kw/; library docs:
.rf/docs/*.md (grep them). There is no helper command: just edit the .robot file and finish with a plain
`robot -d results <file>` run. The final suite must pass with plain `robot <file>`: import project
libraries/resources by path (`${{CURDIR}}/...`), never via -P/PYTHONPATH.
{END}
"""
TIMEOUTS = {"SessionStart": 30, "UserPromptSubmit": 10, "PreToolUse": 15, "PostToolUse": 180,
            "PostToolUseFailure": 180, "Stop": 90, "SessionEnd": 5}


def _cmd(py: Path, event: str, agent: str) -> str:
    return f"{shlex.quote(str(py))} -S {shlex.quote(str(HOOK))} {event} --agent {agent}"


def _copy_skill(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SKILL_SRC, dest, ignore=shutil.ignore_patterns("__pycache__"))


def _pointer(path: Path) -> None:
    text = path.read_text() if path.exists() else ""
    if BEGIN in text:
        text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", POINTER, text, flags=re.S)
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + POINTER
    path.write_text(text)


def _ensure_pkg(venv_bin: Path) -> Path:
    py = venv_bin / "python"
    ok = subprocess.run([str(py), "-c", "import rfharness2.execd, rfharness2.lintd"], capture_output=True,
                        timeout=120).returncode == 0
    if not ok:
        uv = shutil.which("uv")
        cmd = [uv, "pip", "install", "-e", str(PKG), "--python", str(py)] if uv else \
            [str(py), "-m", "pip", "install", "-e", str(PKG)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    return py


def _playwright_env(venv_bin: Path) -> Dict[str, str]:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return {}
    for sp in (venv_bin.parent / "lib").glob("python3*/site-packages/Browser/wrapper/node_modules/playwright-core"):
        try:
            data = json.loads((sp / "browsers.json").read_text())
        except (OSError, ValueError):
            continue
        rev = next((b["revision"] for b in data.get("browsers", []) if b.get("name") == "chromium-headless-shell"), None)
        if rev and not any((sp / ".local-browsers").glob(f"chromium_headless_shell-{rev}")):
            cache = Path.home() / ".cache" / "ms-playwright"
            if (cache / f"chromium_headless_shell-{rev}").exists():
                return {"PLAYWRIGHT_BROWSERS_PATH": str(cache)}
    return {}


def _claude(ws: Path, py: Path) -> List[str]:
    _copy_skill(ws / ".claude" / "skills" / SKILL_NAME)
    sp = ws / ".claude" / "settings.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    settings: Dict[str, Any] = json.loads(sp.read_text()) if sp.exists() else {}
    hooks = settings.setdefault("hooks", {})
    spec = {"SessionStart": None, "UserPromptSubmit": None, "PreToolUse": "Write|Edit|MultiEdit|Bash|Read",
            "PostToolUse": "Write|Edit|MultiEdit|Bash", "PostToolUseFailure": "Bash", "Stop": None, "SessionEnd": None}
    for ev, matcher in spec.items():
        lst = [h for h in hooks.get(ev, []) if "rfharness2" not in json.dumps(h)]
        entry: Dict[str, Any] = {"hooks": [{"type": "command", "command": _cmd(py, ev, "claude"),
                                            "timeout": TIMEOUTS[ev]}]}
        if matcher:
            entry["matcher"] = matcher
        lst.append(entry)
        hooks[ev] = lst
    sp.write_text(json.dumps(settings, indent=2) + "\n")
    _pointer(ws / "CLAUDE.md")
    _pointer(ws / "AGENTS.md")
    return []


def _codex(ws: Path, home: Path, py: Path) -> List[str]:
    _copy_skill(ws / ".agents" / "skills" / SKILL_NAME)
    home.mkdir(parents=True, exist_ok=True)
    cfg = home / "config.toml"
    text = cfg.read_text() if cfg.exists() else ""
    text = re.sub(r"\n?# rfharness2:begin.*?# rfharness2:end\n?", "\n", text, flags=re.S).rstrip()
    spec = [("SessionStart", None), ("UserPromptSubmit", None), ("PreToolUse", "apply_patch|Edit|Write|Bash"),
            ("PostToolUse", "apply_patch|Edit|Write|Bash"), ("Stop", None), ("SessionEnd", None)]
    block = ["", "", "# rfharness2:begin"]
    for ev, matcher in spec:
        block.append(f"[[hooks.{ev}]]")
        if matcher:
            block.append(f"matcher = {json.dumps(matcher)}")
        block += [f"[[hooks.{ev}.hooks]]", 'type = "command"', f"command = {json.dumps(_cmd(py, ev, 'codex'))}",
                  f"timeout = {3 if ev == 'SessionEnd' else TIMEOUTS[ev]}", ""]
    block.append("# rfharness2:end\n")
    cfg.write_text((text + "\n".join(block)).lstrip("\n"))
    _pointer(ws / "AGENTS.md")
    return ["--dangerously-bypass-hook-trust"]


OPENCODE_PLUGIN = r"""// rfharness2 hooks for OpenCode: every event goes to the same Python entry point as the other agents.
// tool.execute.before -> PreToolUse (deny = throw; the Python side allows + warns after 2 denials of the same kind,
// rewrite = mutate output.args), tool.execute.after -> PostToolUse (context PREPENDED to the tool output so a weak
// model reads it first), chat.message -> UserPromptSubmit (first prompt only), assistant message finished -> Stop
// gate (noReply prompt keeps `opencode run` going), plugin init -> SessionStart, dispose -> SessionEnd.
// OpenCode has no hook timeout: every call is bounded here (spawnSync timeout).
import { spawn } from "node:child_process";

const PY = %(py)s;
const HOOK = %(hook)s;
const EDIT = new Set(["write", "edit", "multiedit", "patch", "apply_patch"]);
const READ = new Set(["read", "view"]);
const RF = /\.(robot|resource)\b/;
const SHELL_PRE = /(^|[\s;&|(\/'"])(robot|robotcode|pip3?|uv|playwright|rfbrowser|npm|npx|PYTHONPATH=|cat|less)\b|PYTHONPATH/;
const ROBOT = /(^|[\s;&|(\/])(robot|robotcode)\s/;

// async (round-5 finding: spawnSync blocked OpenCode's event loop for the whole hook, ~5 s per edit)
function call(event, payload, ms) {
  return new Promise((resolve) => {
    let out = "", done = false;
    const finish = (v) => { if (!done) { done = true; clearTimeout(timer); resolve(v); } };
    let p;
    try {
      p = spawn(PY, ["-S", HOOK, event, "--agent", "opencode"], { cwd: payload.cwd, stdio: ["pipe", "pipe", "ignore"] });
    } catch (e) { return finish({}); }
    const timer = setTimeout(() => { try { p.kill("SIGKILL"); } catch (e) {} finish({}); }, ms);
    p.stdout.on("data", (d) => { out += d; });
    p.on("error", () => finish({}));
    p.on("close", () => { try { finish(out.trim() ? JSON.parse(out.trim()) : {}); } catch (e) { finish({}); } });
    try { p.stdin.end(JSON.stringify(payload)); } catch (e) {}
  });
}

export const RfHarness2 = async ({ directory, client }) => {
  await call("SessionStart", { hook_event_name: "SessionStart", cwd: directory }, 30000);
  const notes = new Map();
  let lastStopAt = 0;
  let prompted = false;
  return {
    "chat.message": async (input, output) => {
      if (prompted) return;
      prompted = true;
      const res = await call("UserPromptSubmit", { hook_event_name: "UserPromptSubmit", cwd: directory,
        session_id: input && input.sessionID }, 10000);
      const tp = output && output.parts && output.parts.find((p) => p.type === "text");
      if (res.text && tp) tp.text += "\n\n" + res.text;
    },
    "tool.execute.before": async (input, output) => {
      const tool = String(input.tool || "").toLowerCase();
      const args = output.args || {};
      const s = JSON.stringify(args);
      const want = (EDIT.has(tool) && RF.test(s)) || (tool === "bash" && SHELL_PRE.test(" " + (args.command || "")))
        || (READ.has(tool) && /\.(xml|html?|json|log|txt|yaml|jpe?g|png)\b/.test(s));
      if (!want) return;
      const res = await call("PreToolUse", { hook_event_name: "PreToolUse", tool_name: input.tool, tool_input: args,
        cwd: directory, session_id: input.sessionID }, 20000);
      if (res.action === "deny") throw new Error(res.text || "refused by the Robot Framework hook");
      if (res.action === "rewrite" && res.args) Object.assign(output.args, res.args);
      if (res.text) notes.set(input.callID, res.text);
    },
    "tool.execute.after": async (input, output) => {
      const tool = String(input.tool || "").toLowerCase();
      const args = input.args || {};
      const s = JSON.stringify(args);
      let text = notes.get(input.callID) || "";
      notes.delete(input.callID);
      if ((EDIT.has(tool) && RF.test(s)) || (tool === "bash" && ROBOT.test(" " + (args.command || "")))) {
        const res = await call("PostToolUse", { hook_event_name: "PostToolUse", tool_name: input.tool, tool_input: args,
          tool_response: output && output.output, cwd: directory, session_id: input.sessionID }, 180000);
        text = [res.text, text].filter(Boolean).join("\n\n");
      }
      if (text && output && typeof output.output === "string")
        output.output = "[Robot Framework hook]\n" + text + "\n[/hook]\n\n" + output.output;
    },
    event: async ({ event }) => {
      const info = event.properties && event.properties.info;
      if (event.type === "message.updated" && info && info.role === "assistant" && info.finish
          && info.finish !== "tool-calls" && Date.now() - lastStopAt > 5000) {
        lastStopAt = Date.now();
        const res = await call("Stop", { hook_event_name: "Stop", cwd: directory, session_id: info.sessionID }, 90000);
        if (res.action === "block" && res.text) {
          try {
            await client.session.prompt({ path: { id: info.sessionID }, body: { noReply: true,
              parts: [{ type: "text", text: res.text }] } });
          } catch (e) {}
        }
      }
    },
    dispose: async () => { await call("SessionEnd", { hook_event_name: "SessionEnd", cwd: directory }, 5000); },
  };
};
"""


def _opencode(ws: Path, py: Path) -> List[str]:
    _copy_skill(ws / ".opencode" / "skills" / SKILL_NAME)
    pdir = ws / ".opencode" / "plugins"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "rfharness2.js").write_text(OPENCODE_PLUGIN % {"py": json.dumps(str(py)), "hook": json.dumps(str(HOOK))})
    _pointer(ws / "AGENTS.md")
    return []


def _copilot(ws: Path, home: Path, py: Path) -> List[str]:
    pdir = home / "rfharness2-plugin"
    if pdir.exists():
        shutil.rmtree(pdir)
    (pdir / ".claude-plugin").mkdir(parents=True)
    (pdir / ".claude-plugin" / "plugin.json").write_text(json.dumps(
        {"name": "rfharness2-robotframework", "version": "0.1.0",
         "description": "Robot Framework skill + hooks v2 (live execution after edits, page capture, keyword docs, "
                        "REPL format, static + suite gates, quality gate)"}))
    _copy_skill(pdir / "skills" / SKILL_NAME)
    ev = {"sessionStart": ("SessionStart", 30), "userPromptSubmitted": ("UserPromptSubmit", 10),
          "preToolUse": ("PreToolUse", 20), "postToolUse": ("PostToolUse", 180),
          "postToolUseFailure": ("PostToolUse", 180), "agentStop": ("Stop", 90)}
    hooks = {k: [{"type": "command", "bash": _cmd(py, k, "copilot"), "timeoutSec": t}] for k, (_, t) in ev.items()}
    (pdir / "hooks.json").write_text(json.dumps({"version": 1, "hooks": hooks}, indent=1))
    _pointer(ws / "AGENTS.md")
    names: List[str] = []
    home_cfg = Path(os.environ.get("COPILOT_HOME") or (Path.home() / ".copilot"))
    for f in (home_cfg / "mcp-config.json", ws / ".mcp.json"):
        try:
            names += list((json.loads(f.read_text()).get("mcpServers") or {}).keys())
        except (OSError, ValueError):
            pass
    off = [a for n in dict.fromkeys(names) for a in ("--disable-mcp-server", n)]
    return ["--plugin-dir", str(pdir), "--disable-builtin-mcps", *off]


def install(agent: str, workspace: Path, agent_home: Path, venv_bin: Path) -> dict:
    workspace, agent_home, venv_bin = Path(workspace).resolve(), Path(agent_home).resolve(), Path(venv_bin).resolve()
    agent = agent.lower()
    py = _ensure_pkg(venv_bin)
    if agent == "claude":
        extra_args = _claude(workspace, py)
    elif agent == "codex":
        extra_args = _codex(workspace, agent_home, py)
    elif agent == "opencode":
        extra_args = _opencode(workspace, py)
    elif agent == "copilot":
        extra_args = _copilot(workspace, agent_home, py)
    else:
        raise ValueError(f"unknown agent {agent!r} (claude|codex|opencode|copilot)")
    env = {"PATH": f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}", "RFH2_ROOT": str(workspace),
           **_playwright_env(venv_bin)}
    notes = (f"v2 skill '{SKILL_NAME}' + hooks (SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/Stop/SessionEnd -> "
             f"rfharness2/{HOOK.name}) for "
             f"{agent}; no CLI, no MCP. State in <workspace>/.rf/ (exec + lint daemons, docs, page state, hook log "
             ".rf/hook2/hooks.jsonl or $RFH2_HOOK_LOG). Daemons exit on SessionEnd, when the agent process is gone, or "
             "after 20 min idle."
             + (" codex: --dangerously-bypass-hook-trust; call install() AFTER writing config.toml." if agent == "codex" else "")
             + (" copilot: plugin dir via --plugin-dir; MCP servers disabled." if agent == "copilot" else "")
             + (" opencode: .opencode/plugins/rfharness2.js." if agent == "opencode" else ""))
    return {"extra_args": extra_args, "extra_env": env, "notes": notes,
            "markers": ["rfharness2"], "hook_log": None}


if __name__ == "__main__":  # manual use: python install.py AGENT WORKSPACE AGENT_HOME VENV_BIN
    import sys

    print(json.dumps(install(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])), indent=1))
