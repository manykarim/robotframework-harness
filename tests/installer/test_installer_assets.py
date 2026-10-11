"""The plugin tree and marketplace: versions, hook events / matchers / timeouts per agent, variants (tasks 3.1-3.3)."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from installer_helpers import REPO

from rf_harness import __version__
from rf_harness.installer import _assets

PLUGIN = REPO / "plugins" / "rf-harness"
LAUNCH = '"${CLAUDE_PLUGIN_ROOT}/bin/rfh-launch"'


def load(rel: str) -> dict:
    return json.loads((PLUGIN / rel).read_text(encoding="utf-8"))


def flat(hooks: dict) -> dict[str, tuple[str | None, str, int]]:
    out = {}
    for event, groups in hooks.items():
        assert len(groups) == 1
        group = groups[0]
        (hook,) = group["hooks"]
        assert hook["type"] == "command"
        out[event] = (group.get("matcher"), hook["command"], hook["timeout"])
    return out


def test_marketplace_lists_rf_harness_at_package_version():
    data = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert data["name"] == "robotframework-ai-engineering"
    (plugin,) = data["plugins"]
    assert plugin["name"] == "rf-harness" and plugin["source"] == "./plugins/rf-harness"
    assert plugin["version"] == __version__ == load(".claude-plugin/plugin.json")["version"]
    assert plugin["category"] == "testing" and plugin["license"] == "Apache-2.0"
    assert (REPO / plugin["source"]).is_dir()


def test_shared_hooks_json():
    hooks = flat(load("hooks/hooks.json")["hooks"])
    assert hooks == {
        "SessionStart": (None, f"python3 -S {LAUNCH} SessionStart --agent auto", 30),
        "UserPromptSubmit": (None, f"python3 -S {LAUNCH} UserPromptSubmit --agent auto", 10),
        "PreToolUse": ("Write|Edit|MultiEdit|Bash|Read", f"python3 -S {LAUNCH} PreToolUse --agent auto", 15),
        "PostToolUse": ("Write|Edit|MultiEdit|Bash", f"python3 -S {LAUNCH} PostToolUse --agent auto", 180),
        "PostToolUseFailure": ("Bash", f"python3 -S {LAUNCH} PostToolUseFailure --agent auto", 180),
        "Stop": (None, f"python3 -S {LAUNCH} Stop --agent auto", 90),
        "SessionEnd": (None, f"python3 -S {LAUNCH} SessionEnd --agent auto", 5),
    }


def test_codex_variant():
    hooks = flat(load("variants/codex/hooks.json")["hooks"])
    assert sorted(hooks) == sorted(["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop",
                                    "SessionEnd"])
    assert hooks["PreToolUse"][0] == hooks["PostToolUse"][0] == "apply_patch|Edit|Write|Bash"
    assert hooks["SessionEnd"][2] == 3
    assert all(cmd.endswith(f"{event} --agent codex") for event, (_, cmd, _) in hooks.items())


def test_copilot_variant():
    data = load("variants/copilot/hooks.json")
    assert data["version"] == 1
    hooks = data["hooks"]
    assert sorted(hooks) == sorted(["sessionStart", "userPromptSubmitted", "preToolUse", "postToolUse",
                                    "postToolUseFailure", "agentStop"])
    assert "sessionEnd" not in hooks              # fires after every run in Copilot CLI
    for event, (entry,) in hooks.items():
        assert entry["bash"] == f"python3 -S {LAUNCH} {event} --agent auto"
        assert entry["powershell"].endswith(f"rfh-launch.cmd\" {event} --agent auto")
        assert entry["timeoutSec"] >= 10
    assert hooks["postToolUse"][0]["timeoutSec"] == 180


def test_opencode_plugin():
    js = (PLUGIN / "variants/opencode/plugins/rf-harness.js").read_text(encoding="utf-8")
    for needle in ('"../rf-harness/bin/rfh-launch"', '"--agent", "opencode"', "noReply: true",
                   "[/*rf-harness:launch-args*/]", '"tool.execute.before"', '"tool.execute.after"', "dispose"):
        assert needle in js
    node = shutil.which("node")
    if node:
        proc = subprocess.run([node, "--check", str(PLUGIN / "variants/opencode/plugins/rf-harness.js")],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


def test_launcher_is_shipped():
    names = {p.name for p in _assets.iter_files(PLUGIN / "bin")}
    assert names == {"rfh-launch", "rfh_launch.py", "rfh-launch.cmd"}
    assert (PLUGIN / "bin" / "rfh-launch.cmd").read_bytes().count(b"\r\n") > 5


def test_assets_resolve_to_the_checkout():
    assert _assets.plugin_root() == PLUGIN
    assert _assets.bundle_version() == __version__


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("claude") is None, reason="needs the claude CLI")
def test_claude_plugin_validate():
    proc = subprocess.run(["claude", "plugin", "validate", str(REPO)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_windows_files_mode_commands(tmp_path):
    from rf_harness.installer import transforms as _x

    text = (PLUGIN / "variants/copilot/hooks.json").read_text(encoding="utf-8")
    data = _x.render_hooks_file(text, tmp_path / "support", ["--set", "RFH_STATIC=runtime-only"], windows=True)
    entry = data["hooks"]["preToolUse"][0]
    assert not entry["bash"].startswith("python3 ") and entry["bash"].endswith(
        "preToolUse --agent auto --set RFH_STATIC=runtime-only")
    assert entry["powershell"].startswith("& ") and "rfh-launch.cmd" in entry["powershell"]
    assert _x.windowsify({"command": "python3 -S /x/bin/rfh-launch Stop"}, "py -3 -S") == {
        "command": "py -3 -S /x/bin/rfh-launch Stop"}
    assert _x.windowsify({"command": "python3 -S other.py"}, "py -3 -S") == {"command": "python3 -S other.py"}
