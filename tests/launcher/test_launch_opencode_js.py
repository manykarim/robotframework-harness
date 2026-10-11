"""The OpenCode JS plugin drives the launcher: loaded under node with a fake OpenCode context and a fake runtime."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from launch_helpers import BIN, IS_WINDOWS, REPO, make_venv, site_packages

NODE = shutil.which("node")
PLUGIN_JS = REPO / "plugins" / "rf-harness" / "variants" / "opencode" / "plugins" / "rf-harness.js"
OPENCODE_HOOK = r'''
import json, sys
payload = json.loads(sys.stdin.read() or "{}")
event, agent = sys.argv[1], sys.argv[3]
if event == "PreToolUse" and "deny" in json.dumps(payload.get("tool_input")):
    print(json.dumps({"action": "deny", "text": "denied by fake"}))
else:
    print(json.dumps({"action": "context", "text": f"[fake {agent}] {event} {payload.get('tool_name', '')}".strip()}))
'''
DRIVER = r'''
const mod = await import(process.argv[2]);
const dir = process.argv[3];
const prompts = [];
const client = { session: { prompt: async (req) => { prompts.push(req.body.parts[0].text); } } };
const hooks = await mod.RfHarness({ directory: dir, client });
const msg = { parts: [{ type: "text", text: "write a test" }] };
await hooks["chat.message"]({ sessionID: "s1", model: { providerID: "x", modelID: "m" } }, msg);
const out = { title: "", output: "file written", metadata: {} };
const args = { filePath: dir + "/tests/a.robot", content: "*** Test Cases ***" };
await hooks["tool.execute.before"]({ tool: "write", sessionID: "s1", callID: "c1" }, { args });
await hooks["tool.execute.after"]({ tool: "write", sessionID: "s1", callID: "c1", args }, out);
let denied = "";
try {
  await hooks["tool.execute.before"]({ tool: "write", sessionID: "s1", callID: "c2" },
    { args: { filePath: dir + "/tests/deny.robot", content: "deny" } });
} catch (e) { denied = String(e.message); }
console.log(JSON.stringify({ prompt: msg.parts[0].text, after: out.output, denied }));
'''

pytestmark = pytest.mark.skipif(NODE is None or IS_WINDOWS, reason="needs node (POSIX paths)")


def install_opencode(project: Path) -> Path:
    root = project / ".opencode"
    (root / "plugins").mkdir(parents=True)
    shutil.copytree(BIN, root / "rf-harness" / "bin", ignore=shutil.ignore_patterns("__pycache__"))
    target = root / "plugins" / "rf-harness.js"
    shutil.copy(PLUGIN_JS, target)
    return target


def run_driver(plugin: Path, project: Path, env: dict[str, str]) -> dict:
    driver = project / "driver.mjs"
    driver.write_text(DRIVER, encoding="utf-8")
    assert NODE is not None
    proc = subprocess.run([NODE, str(driver), plugin.as_uri(), str(project)], capture_output=True, text=True,
                          env={**env, "RF_HARNESS_LAUNCHER_PYTHON": sys.executable}, cwd=str(project), timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_session_start_hint_reaches_the_first_prompt(project, clean_env):
    plugin = install_opencode(project)
    result = run_driver(plugin, project, clean_env)
    assert "uvx robotframework-harness install --runtime-only" in result["prompt"]
    assert result["after"] == "file written"     # no runtime: hooks stay silent
    assert result["denied"] == ""


def test_hooks_reach_the_runtime(project, clean_env):
    plugin = install_opencode(project)
    python = make_venv(project / ".venv")
    (site_packages(python.parent.parent) / "rf_harness" / "runtime" / "hook.py").write_text(OPENCODE_HOOK)
    result = run_driver(plugin, project, clean_env)
    assert result["prompt"].endswith("[fake opencode] UserPromptSubmit")
    assert result["after"].startswith("[Robot Framework hook]\n[fake opencode] PostToolUse write")
    assert "[fake opencode] PreToolUse write" in result["after"]
    assert result["denied"] == "denied by fake"
