"""Installer for the A/B treatment arm: Agent Skill + local `rfmcp` helper + post-edit hooks, NO MCP.

    from install import install
    info = install("claude", workspace, agent_home, venv_bin)
    # -> {"extra_args": [...], "extra_env": {...}, "notes": "..."}

What it does per agent (like a real installer would):
  skill   claude   -> <workspace>/.claude/skills/robotframework/
          codex    -> <workspace>/.agents/skills/robotframework/
          opencode -> <workspace>/.opencode/skills/robotframework/
          copilot  -> <agent_home>/rfmcp-plugin/skills/robotframework/   (plugin dir, passed with --plugin-dir)
  hooks   claude   -> <workspace>/.claude/settings.json  PostToolUse "Edit|Write|MultiEdit" -> rfmcp hook --agent claude
          codex    -> <agent_home>/config.toml [[hooks.PostToolUse]] "apply_patch|Edit|Write" (+ --dangerously-bypass-hook-trust)
          copilot  -> <agent_home>/rfmcp-plugin/hooks/hooks.json PostToolUse -> rfmcp hook --agent copilot (top-level additionalContext)
          opencode -> <workspace>/.opencode/plugins/rfmcp-hook.js  tool.execute.after appends the hook text to the edit result
  pointer AGENTS.md (all) and CLAUDE.md (claude): short "use the robotframework skill / rfmcp" block
  PATH    rfmcp must resolve via venv_bin (installed editable into that venv if missing)
No MCP configuration is written.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

PKG = Path(__file__).resolve().parent
SKILL_SRC = PKG / "rfmcp_skill" / "skill"
SKILL_NAME = "robotframework"
BEGIN, END = "<!-- rfmcp:begin -->", "<!-- rfmcp:end -->"
POINTER = f"""{BEGIN}
## Robot Framework
IMPORTANT: for any Robot Framework task (.robot/.resource files, robot runs, output.xml analysis) load the
`{SKILL_NAME}` skill first and use its local `rfmcp` helper instead of guessing keywords or selectors:
try lines live with `rfmcp step '<Keyword>    <args>'` or run your test file's new lines with `rfmcp run FILE`
(the helper starts itself); inspect pages with `rfmcp state controls` / `rfmcp state aria`; keywords via
`rfmcp search "..."` / `rfmcp doc "Name"`; failing suites: `rfmcp guide debug`; topics via `rfmcp guide`; finally
`rfmcp stop`. No helper for output.xml analysis (`robotcode results ...`) or static edits (`rfmcp check FILE`).
One rfmcp call at a time, never in parallel. The final suite must pass with plain `robot <file>`: import project
libraries/resources by path (`${{CURDIR}}/...`), never via -P/PYTHONPATH.
{END}
"""


def _copy_skill(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SKILL_SRC, dest)


def _pointer(path: Path) -> None:
    text = path.read_text() if path.exists() else ""
    if BEGIN in text:
        text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", POINTER, text, flags=re.S)
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + POINTER
    path.write_text(text)


def _ensure_rfmcp(venv_bin: Path) -> Path:
    exe = venv_bin / "rfmcp"
    if not exe.exists():
        uv = shutil.which("uv")
        py = venv_bin / "python"
        cmd = [uv, "pip", "install", "-e", str(PKG), "--python", str(py)] if uv else \
            [str(py), "-m", "pip", "install", "-e", str(PKG)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    if not exe.exists():
        raise RuntimeError(f"rfmcp not found in {venv_bin} after install")
    return exe


def _playwright_env(venv_bin: Path) -> Dict[str, str]:
    """Browser library venvs installed with `rfbrowser init --skip-browsers` need PLAYWRIGHT_BROWSERS_PATH
    pointing at an existing browser cache (same requirement for the MCP arm)."""
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return {}
    for sp in (venv_bin.parent / "lib").glob("python3*/site-packages/Browser/wrapper/node_modules/playwright-core"):
        try:
            data = json.loads((sp / "browsers.json").read_text())
        except (OSError, ValueError):
            continue
        rev = next((b["revision"] for b in data.get("browsers", []) if b.get("name") == "chromium-headless-shell"), None)
        if not rev:
            continue
        if any((sp / ".local-browsers").glob(f"chromium_headless_shell-{rev}")):
            return {}
        cache = Path.home() / ".cache" / "ms-playwright"
        if (cache / f"chromium_headless_shell-{rev}").exists():
            return {"PLAYWRIGHT_BROWSERS_PATH": str(cache)}
    return {}


def _claude(workspace: Path, rfmcp: Path) -> List[str]:
    _copy_skill(workspace / ".claude" / "skills" / SKILL_NAME)
    sp = workspace / ".claude" / "settings.json"
    settings: Dict[str, Any] = json.loads(sp.read_text()) if sp.exists() else {}
    post = settings.setdefault("hooks", {}).setdefault("PostToolUse", [])
    post[:] = [h for h in post if "rfmcp" not in json.dumps(h)]
    post.append({"matcher": "Edit|Write|MultiEdit",
                 "hooks": [{"type": "command", "command": f'"{rfmcp}" hook --agent claude', "timeout": 120}]})
    sp.write_text(json.dumps(settings, indent=2) + "\n")
    _pointer(workspace / "CLAUDE.md")
    _pointer(workspace / "AGENTS.md")
    return []


def _codex(workspace: Path, agent_home: Path, rfmcp: Path) -> List[str]:
    _copy_skill(workspace / ".agents" / "skills" / SKILL_NAME)
    agent_home.mkdir(parents=True, exist_ok=True)
    cfg = agent_home / "config.toml"
    text = cfg.read_text() if cfg.exists() else ""
    text = re.sub(r"\n?# rfmcp:begin.*?# rfmcp:end\n?", "\n", text, flags=re.S).rstrip()
    block = ("\n\n# rfmcp:begin\n[[hooks.PostToolUse]]\nmatcher = \"apply_patch|Edit|Write\"\n"
             "[[hooks.PostToolUse.hooks]]\ntype = \"command\"\n"
             f"command = {json.dumps(str(rfmcp) + ' hook --agent codex')}\ntimeout = 120\n# rfmcp:end\n")
    cfg.write_text((text + block).lstrip("\n"))
    _pointer(workspace / "AGENTS.md")
    return ["--dangerously-bypass-hook-trust"]  # headless codex runs only trusted hooks


OPENCODE_PLUGIN = """// rfmcp post-edit hook for OpenCode (tool.execute.after): runs `rfmcp hook --agent opencode` on edits of
// .robot/.resource files and appends its findings to the edit tool's output that the model reads.
import { spawnSync } from "node:child_process";

const RFMCP = %(rfmcp)s;
const EDIT_TOOLS = new Set(["edit", "write", "patch", "multiedit", "apply_patch"]);

export const RfmcpHook = async ({ directory }) => ({
  "tool.execute.after": async (input, output) => {
    if (!EDIT_TOOLS.has(String(input.tool).toLowerCase())) return;
    const payload = JSON.stringify({ tool_name: input.tool, tool_input: input.args ?? {}, cwd: directory });
    if (!/\\.(robot|resource)/.test(payload)) return;
    const r = spawnSync(RFMCP, ["hook", "--agent", "opencode"], { input: payload, encoding: "utf8", timeout: 90000, cwd: directory });
    const text = (r.stdout || "").trim();
    if (text && output && typeof output.output === "string") output.output += "\\n\\n" + text;
  },
});
"""


def _opencode(workspace: Path, rfmcp: Path) -> List[str]:
    _copy_skill(workspace / ".opencode" / "skills" / SKILL_NAME)
    pdir = workspace / ".opencode" / "plugins"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "rfmcp-hook.js").write_text(OPENCODE_PLUGIN % {"rfmcp": json.dumps(str(rfmcp))})
    _pointer(workspace / "AGENTS.md")
    return []


def _copilot(workspace: Path, agent_home: Path, rfmcp: Path) -> List[str]:
    pdir = agent_home / "rfmcp-plugin"
    if pdir.exists():
        shutil.rmtree(pdir)
    (pdir / ".claude-plugin").mkdir(parents=True)
    (pdir / ".claude-plugin" / "plugin.json").write_text(json.dumps(
        {"name": "rfmcp-robotframework", "version": "0.1.0",
         "description": "Robot Framework skill + rfmcp post-edit hook (local helper, no MCP)"}, indent=1))
    _copy_skill(pdir / "skills" / SKILL_NAME)
    (pdir / "hooks").mkdir()
    (pdir / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"PostToolUse": [{"hooks": [
        {"type": "command", "command": f'"{rfmcp}" hook --agent copilot', "timeout": 120}]}]}}, indent=1))
    _pointer(workspace / "AGENTS.md")
    # "no MCP": Copilot also loads ~/.copilot/mcp-config.json and the workspace .mcp.json -> disable those servers
    names: List[str] = []
    home_cfg = Path(os.environ.get("COPILOT_HOME") or (Path.home() / ".copilot"))
    for f in (home_cfg / "mcp-config.json", workspace / ".mcp.json"):
        try:
            names += list((json.loads(f.read_text()).get("mcpServers") or {}).keys())
        except (OSError, ValueError):
            pass
    off = [a for n in dict.fromkeys(names) for a in ("--disable-mcp-server", n)]
    return ["--plugin-dir", str(pdir), "--disable-builtin-mcps", *off]


def install(agent: str, workspace: Path, agent_home: Path, venv_bin: Path) -> dict:
    workspace, agent_home, venv_bin = Path(workspace).resolve(), Path(agent_home).resolve(), Path(venv_bin).resolve()
    agent = agent.lower()
    rfmcp = _ensure_rfmcp(venv_bin)
    if agent == "claude":
        extra_args = _claude(workspace, rfmcp)
    elif agent == "codex":
        extra_args = _codex(workspace, agent_home, rfmcp)
    elif agent == "opencode":
        extra_args = _opencode(workspace, rfmcp)
    elif agent == "copilot":
        extra_args = _copilot(workspace, agent_home, rfmcp)
    else:
        raise ValueError(f"unknown agent {agent!r} (claude|codex|opencode|copilot)")
    env = {"PATH": f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}", **_playwright_env(venv_bin)}
    notes = (f"skill '{SKILL_NAME}' + rfmcp ({rfmcp}) + post-edit hook for {agent}; no MCP config. "
             "rfmcp keeps helper state in <workspace>/.rf/ ; run agents with cwd=workspace."
             + (" PLAYWRIGHT_BROWSERS_PATH set (venv has no bundled browsers; the MCP arm needs the same)."
                if "PLAYWRIGHT_BROWSERS_PATH" in env else "")
             + (" codex: hooks need --dangerously-bypass-hook-trust headless." if agent == "codex" else "")
             + (" opencode: hook = .opencode/plugins/rfmcp-hook.js (tool.execute.after)." if agent == "opencode" else "")
             + (" copilot: user/workspace MCP servers disabled via --disable-mcp-server." if agent == "copilot" else "")
             + " Isolate MCP for claude/codex/opencode in the harness (CLAUDE_CONFIG_DIR + --strict-mcp-config, "
               "CODEX_HOME, no opencode mcp). Call install() AFTER writing the agent's own config files (codex "
               "config.toml: hooks are appended; top-level keys written later would land inside the hooks table)."
               " Run `rfmcp stop` in the workspace after each session (helper idles out after 30 min otherwise).")
    return {"extra_args": extra_args, "extra_env": env, "notes": notes}


if __name__ == "__main__":  # manual use: python install.py AGENT WORKSPACE AGENT_HOME VENV_BIN
    import sys

    print(json.dumps(install(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])), indent=1))
