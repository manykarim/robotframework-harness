"""Coexistence with rf-agentskills, rf-mcp and the research prototypes (task 4.4, design D7)."""

from __future__ import annotations

import json
from pathlib import Path

from installer_helpers import Sandbox, run_cli

AGENTSKILLS_HOOK = {"matcher": "Write|Edit", "hooks": [
    {"type": "command", "command": 'node "/home/u/.claude/rf-agentskills-files/scripts/validate_robot.mjs"',
     "timeout": 45}]}
PROTO_HOOK = {"hooks": [{"type": "command", "command": "/v/bin/python -S /pkg/rfharness32/hook.py Stop --agent claude",
                         "timeout": 90}]}


def write_settings(path: Path, data: dict) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path.read_bytes()


def test_rf_agentskills_files_mode_keeps_its_entries(sandbox: Sandbox, capsys):
    settings = sandbox.project / ".claude/settings.json"
    original = {"hooks": {"PostToolUse": [AGENTSKILLS_HOOK]},
                "enabledPlugins": {"rf-agentskills@robotframework-agentskills": True}}
    original_bytes = write_settings(settings, original)
    rc, out = run_cli(capsys, "install", "--agent", "claude-code", "--mode", "files", "--no-runtime")
    assert rc == 0 and "rf-agentskills" in out and "RFH_STATIC=runtime-only" in out
    data = json.loads(settings.read_text())
    assert data["hooks"]["PostToolUse"][0] == AGENTSKILLS_HOOK
    assert data["enabledPlugins"] == original["enabledPlugins"]
    ours = [h["command"] for g in data["hooks"]["PostToolUse"][1:] for h in g["hooks"]]
    assert ours and all("--set RFH_STATIC=runtime-only" in c for c in ours)
    run_cli(capsys, "uninstall", "--agent", "claude-code")
    assert settings.read_bytes() == original_bytes


def test_rf_agentskills_plugin_mode_sets_harness_env(sandbox: Sandbox, capsys):
    settings = sandbox.project / ".claude/settings.json"
    original_bytes = write_settings(settings, {"hooks": {"PostToolUse": [AGENTSKILLS_HOOK]}})
    run_cli(capsys, "install", "--agent", "claude-code", "--no-runtime")
    harness = json.loads((sandbox.project / ".rf/harness.json").read_text())
    assert harness["env"] == {"RFH_STATIC": "runtime-only"}
    assert json.loads(settings.read_text())["hooks"]["PostToolUse"] == [AGENTSKILLS_HOOK]
    run_cli(capsys, "uninstall", "--agent", "claude-code")
    assert settings.read_bytes() == original_bytes
    assert "env" not in json.loads((sandbox.project / ".rf/harness.json").read_text())


def test_coexist_replace_runs_full_static_checks(sandbox: Sandbox, capsys):
    settings = sandbox.project / ".claude/settings.json"
    write_settings(settings, {"hooks": {"PostToolUse": [AGENTSKILLS_HOOK]}})
    run_cli(capsys, "install", "--agent", "claude-code", "--mode", "files", "--no-runtime", "--coexist", "replace")
    data = json.loads(settings.read_text())
    assert data["hooks"]["PostToolUse"][0] == AGENTSKILLS_HOOK
    assert "RFH_STATIC" not in settings.read_text()


def test_codex_agentskills_hooks_untouched(sandbox: Sandbox, capsys):
    codex_hooks = sandbox.home / ".codex/hooks.json"
    original = write_settings(codex_hooks, {"hooks": {"PostToolUse": [AGENTSKILLS_HOOK]}})
    run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--scope", "user", "--no-runtime")
    assert json.loads(codex_hooks.read_text())["hooks"]["PostToolUse"][0] == AGENTSKILLS_HOOK
    assert "--set RFH_STATIC=runtime-only" in codex_hooks.read_text()
    run_cli(capsys, "uninstall", "--agent", "codex", "--scope", "user")
    assert codex_hooks.read_bytes() == original


def test_rf_mcp_is_reported_not_modified(sandbox: Sandbox, capsys):
    mcp = sandbox.project / ".mcp.json"
    original = write_settings(mcp, {"mcpServers": {"robotmcp": {"command": "uv", "args": ["run", "robotmcp"]}}})
    rc, out = run_cli(capsys, "install", "--agent", "claude-code", "--no-runtime")
    assert rc == 0 and "rf-mcp: MCP server 'robotmcp'" in out and "both routes work" in out
    assert mcp.read_bytes() == original
    assert "RFH_STATIC" not in (sandbox.project / ".claude/settings.json").read_text()


def make_prototype(sandbox: Sandbox) -> dict[str, Path]:
    settings = sandbox.project / ".claude/settings.json"
    write_settings(settings, {"model": "opus", "hooks": {"Stop": [PROTO_HOOK, AGENTSKILLS_HOOK]}})
    claude_md = sandbox.project / "CLAUDE.md"
    claude_md.write_text("# My project\n\n<!-- rfharness32:begin -->\n## Robot Framework\nuse it\n"
                         "<!-- rfharness32:end -->\n\nMore of my notes.\n", encoding="utf-8")
    config = sandbox.home / ".codex/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('model = "gpt-5"\n\n# rfharness32:begin\n[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ntype = "command"\n'
                      'command = "/v/python -S /p/rfharness32/hook.py Stop --agent codex"\n# rfharness32:end\n',
                      encoding="utf-8")
    plugin = sandbox.project / ".opencode/plugins/rfharness32.js"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("// proto\n", encoding="utf-8")
    copilot = sandbox.home / ".copilot/rfharness32-plugin"
    copilot.mkdir(parents=True)
    (copilot / "hooks.json").write_text("{}", encoding="utf-8")
    return {"settings": settings, "claude_md": claude_md, "config": config, "plugin": plugin, "copilot": copilot}


def test_prototypes_reported_and_kept_by_default(sandbox: Sandbox, capsys):
    paths = make_prototype(sandbox)
    rc, out = run_cli(capsys, "install", "--agent", "claude-code", "--no-runtime", "--no-input")
    assert rc == 0
    assert out.count("prototype:") >= 5 and "research-prototype entries kept" in out
    assert "rfharness32" in paths["claude_md"].read_text() and paths["plugin"].exists()


def test_prototypes_removed_with_replace(sandbox: Sandbox, capsys):
    paths = make_prototype(sandbox)
    rc, out = run_cli(capsys, "install", "--agent", "claude-code", "--no-runtime", "--coexist", "replace")
    assert rc == 0
    data = json.loads(paths["settings"].read_text())
    assert data["model"] == "opus" and data["hooks"]["Stop"] == [AGENTSKILLS_HOOK]
    assert paths["claude_md"].read_text() == "# My project\n\nMore of my notes.\n"
    assert paths["config"].read_text() == 'model = "gpt-5"\n'
    assert not paths["plugin"].exists() and not paths["copilot"].exists()


def test_prototype_dry_run_removes_nothing(sandbox: Sandbox, capsys):
    paths = make_prototype(sandbox)
    before = paths["claude_md"].read_text()
    rc, out = run_cli(capsys, "install", "--agent", "claude-code", "--no-runtime", "--coexist", "replace", "--dry-run")
    assert rc == 0 and "would remove" in out
    assert paths["claude_md"].read_text() == before and paths["plugin"].exists()
