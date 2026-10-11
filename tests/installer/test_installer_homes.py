"""Every agent lookup honours the agent's home override (isolated agent homes, e.g. evaluation cells)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from installer_helpers import Sandbox, run_cli, snapshot

from rf_harness.installer import coexist, homes
from rf_harness.installer.adapters import by_name

AGENTSKILLS = {"hooks": {"PostToolUse": [{"hooks": [
    {"type": "command", "command": 'node "/x/rf-agentskills-files/scripts/validate_robot.mjs"'}]}]}}
RF_MCP = {"mcpServers": {"robotmcp": {"command": "uvx", "args": ["rf-mcp"]}}}


def write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8") if not isinstance(data, str) else path.write_text(data)


@pytest.fixture
def overrides(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    dirs = {name: sandbox.tmp / f"iso-{name}" for name in ("claude", "codex", "copilot", "xdg")}
    for path in dirs.values():
        path.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(dirs["claude"]))
    monkeypatch.setenv("CODEX_HOME", str(dirs["codex"]))
    monkeypatch.setenv("COPILOT_HOME", str(dirs["copilot"]))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(dirs["xdg"]))
    return dirs


def test_homes_follow_the_overrides(sandbox: Sandbox, overrides, monkeypatch):
    assert homes.claude_home() == overrides["claude"]
    assert homes.claude_global_config() == overrides["claude"] / ".claude.json"
    assert homes.codex_home() == overrides["codex"]
    assert homes.copilot_home() == overrides["copilot"]
    assert homes.opencode_home() == overrides["xdg"] / "opencode"
    monkeypatch.setenv("OPENCODE_CONFIG", str(sandbox.tmp / "oc.json"))
    assert sandbox.tmp / "oc.json" in homes.opencode_config_files()


def test_coexistence_scan_ignores_the_default_homes(sandbox: Sandbox, overrides, monkeypatch):
    home = sandbox.home
    # tooling in the DEFAULT locations must not be reported while overrides are set
    write(home / ".copilot/mcp-config.json", RF_MCP)
    write(home / ".claude/settings.json", AGENTSKILLS)
    write(home / ".claude.json", RF_MCP)
    write(home / ".codex/hooks.json", AGENTSKILLS)
    write(home / ".config/opencode/plugins/rfharness32.js", "// proto")
    write(home / ".copilot/rfharness32-plugin/hooks.json", {})
    assert coexist.scan(sandbox.project).findings == []

    # ... and the same tooling in the override locations is reported
    write(overrides["copilot"] / "mcp-config.json", RF_MCP)
    write(overrides["claude"] / "settings.json", AGENTSKILLS)
    write(overrides["codex"] / "hooks.json", AGENTSKILLS)
    write(overrides["xdg"] / "opencode/plugins/rfharness32.js", "// proto")
    write(overrides["copilot"] / "rfharness32-plugin/hooks.json", {})
    oc = sandbox.tmp / "opencode-custom.json"
    write(oc, {"mcp": {"rf-mcp": {"type": "local", "command": ["rf-mcp"]}}})
    monkeypatch.setenv("OPENCODE_CONFIG", str(oc))
    found = {(f.tool, str(f.path)) for f in coexist.scan(sandbox.project).findings}
    assert ("rf-mcp", str(overrides["copilot"] / "mcp-config.json")) in found
    assert ("rf-agentskills", str(overrides["claude"] / "settings.json")) in found
    assert ("rf-agentskills", str(overrides["codex"] / "hooks.json")) in found
    assert ("prototype", str(overrides["xdg"] / "opencode/plugins/rfharness32.js")) in found
    assert ("prototype", str(overrides["copilot"] / "rfharness32-plugin")) in found
    assert ("rf-mcp", str(oc)) in found
    assert not any(str(home) in path and "iso-" not in path for _, path in found)


@pytest.mark.parametrize(("agent", "key"), [("claude-code", "claude"), ("codex", "codex"), ("copilot-cli", "copilot"),
                                            ("opencode", "xdg")])
def test_user_scope_installs_into_the_override(sandbox: Sandbox, overrides, capsys, agent, key):
    default_homes = snapshot(sandbox.home)
    rc, out = run_cli(capsys, "install", "--agent", agent, "--mode", "files", "--scope", "user", "--no-runtime")
    assert rc == 0, out
    written = snapshot(overrides[key])
    assert any("rfh-launch" in path for path in written), sorted(written)
    if agent != "codex":       # codex user skills live in ~/.agents/skills (no override exists for that folder)
        assert {p for p in snapshot(sandbox.home) if ".rf-harness" not in p} == set(default_homes)
    run_cli(capsys, "uninstall", "--agent", agent, "--scope", "user")
    assert not any("rfh-launch" in path for path in snapshot(overrides[key]))


def test_detection_uses_the_overrides(sandbox: Sandbox, overrides):
    overrides["codex"].rmdir()
    (sandbox.home / ".codex").mkdir()          # only the default home exists -> not detected (override wins)
    assert not by_name("codex").detect()
    overrides["codex"].mkdir()
    assert by_name("codex").detect() and by_name("copilot-cli").detect() and by_name("claude-code").detect()
