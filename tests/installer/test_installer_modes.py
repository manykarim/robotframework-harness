"""Install per agent x mode x scope against temporary homes and projects (tasks 4.1, 4.2, 4.5)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from installer_helpers import IS_WINDOWS, Sandbox, fake_agent, run_cli, snapshot

from rf_harness import __version__
from rf_harness.installer import prompt
from rf_harness.installer.adapters._base import MARKETPLACE_NAME, MARKETPLACE_REPO, PLUGIN_ID

AGENTS = ["claude-code", "codex", "copilot-cli", "vscode", "opencode"]


def expected_paths(s: Sandbox, agent: str, mode: str, scope: str) -> list[Path]:
    base = s.project if scope == "project" else s.home
    claude = base / ".claude"
    if agent in ("claude-code", "vscode") and mode == "files":
        return [claude / "skills/rf-harness/SKILL.md", claude / "rf-harness/bin/rfh-launch", claude / "settings.json"]
    if agent == "claude-code":
        return [claude / "settings.json"]
    if agent == "vscode":
        return [claude / "settings.json"] if scope == "project" else []
    if agent == "codex":
        cfg = s.project / ".codex" if scope == "project" else s.home / ".codex"
        if mode == "plugin":
            return []
        return [base / ".agents/skills/rf-harness/SKILL.md", cfg / "hooks.json", cfg / "rf-harness/bin/rfh-launch"]
    if agent == "copilot-cli":
        root = s.project / ".github" if scope == "project" else s.home / ".copilot"
        if mode == "plugin":
            return [s.project / ".claude/settings.json", s.project / ".github/copilot/settings.json"] \
                if scope == "project" else [s.home / ".copilot/settings.json"]
        return [root / "skills/rf-harness/SKILL.md", root / "hooks/rf-harness.json",
                root / "hooks/rf-harness/bin/rfh-launch"]
    root = s.project / ".opencode" if scope == "project" else s.home / ".config/opencode"
    return [root / "skills/rf-harness/SKILL.md", root / "plugins/rf-harness.js", root / "rf-harness/bin/rfh-launch"]


def check_content(s: Sandbox, agent: str, mode: str, paths: list[Path]) -> None:
    for path in paths:
        if path.name == "rfh-launch" and not IS_WINDOWS:
            assert os.access(path, os.X_OK), path
        if path.name == "settings.json" and (mode == "plugin" or agent == "copilot-cli"):
            data = json.loads(path.read_text())
            assert data["enabledPlugins"][PLUGIN_ID] is True
            assert data["extraKnownMarketplaces"][MARKETPLACE_NAME]["source"] == {"source": "github",
                                                                                   "repo": MARKETPLACE_REPO}
        elif path.name in ("settings.json", "hooks.json", "rf-harness.json"):
            text = path.read_text()
            launcher = [p for p in paths if p.name == "rfh-launch"][0]
            assert str(launcher).replace("\\", "/") in text.replace("\\\\", "/")
            assert " -S " in text and "${CLAUDE_PLUGIN_ROOT}" not in text
        elif path.suffix == ".js":
            assert "rf-harness/bin/rfh-launch" in path.read_text()


@pytest.mark.parametrize("scope", ["project", "user"])
@pytest.mark.parametrize("mode", ["plugin", "files"])
@pytest.mark.parametrize("agent", AGENTS)
def test_install_matrix(sandbox: Sandbox, capsys, agent, mode, scope):
    before = snapshot(sandbox.home, sandbox.project)
    args = ["install", "--agent", agent, "--mode", mode, "--scope", scope, "--no-runtime"]

    rc, out = run_cli(capsys, *args, "--dry-run")
    assert rc == 0 and "[dry-run]" in out
    assert snapshot(sandbox.home, sandbox.project) == before, "dry-run wrote files"

    rc, out = run_cli(capsys, *args)
    assert rc == 0, out
    paths = expected_paths(sandbox, agent, mode, scope)
    for path in paths:
        assert path.is_file(), f"{path} missing\n{out}"
    check_content(sandbox, agent, mode, paths)
    if agent == "opencode" and mode == "plugin":
        assert "no plugin marketplace, installing files instead" in out
    if agent == "vscode" and mode == "plugin":
        assert "chat.useHooks" in out and "chat.plugins.enabled" in out and "chat.plugins.marketplaces" in out
    if agent == "codex" and mode == "plugin":
        assert f"codex plugin marketplace add {MARKETPLACE_REPO}" in out and f"codex plugin add {PLUGIN_ID}" in out
        assert "/hooks" in out
    installed = snapshot(sandbox.home, sandbox.project)

    rc, out = run_cli(capsys, *args)
    assert rc == 0 and "no changes" in out, out
    assert snapshot(sandbox.home, sandbox.project) == installed, "second install changed files"

    rc, out = run_cli(capsys, "uninstall", "--agent", agent, "--scope", scope)
    assert rc == 0, out
    assert snapshot(sandbox.home, sandbox.project) == before, "uninstall left files behind"


def test_shared_claude_layout_survives_partial_uninstall(sandbox: Sandbox, capsys):
    """Claude Code and VS Code share .claude/: removing one keeps the files the other still uses."""
    assert run_cli(capsys, "install", "--agents", "claude-code,vscode", "--mode", "files", "--no-runtime")[0] == 0
    skill = sandbox.project / ".claude/skills/rf-harness/SKILL.md"
    settings = sandbox.project / ".claude/settings.json"
    assert run_cli(capsys, "uninstall", "--agent", "claude-code")[0] == 0
    assert skill.is_file() and "rfh-launch" in settings.read_text()
    assert run_cli(capsys, "uninstall", "--agent", "vscode")[0] == 0
    assert not skill.exists() and not settings.exists()


def test_shared_marketplace_entries(sandbox: Sandbox, capsys):
    assert run_cli(capsys, "install", "--agents", "claude-code,copilot-cli", "--no-runtime")[0] == 0
    settings = sandbox.project / ".claude/settings.json"
    run_cli(capsys, "uninstall", "--agent", "claude-code")
    assert PLUGIN_ID in json.loads(settings.read_text())["enabledPlugins"]
    run_cli(capsys, "uninstall", "--agent", "copilot-cli")
    assert not settings.exists()


def test_ref_pins_the_marketplace(sandbox: Sandbox, capsys):
    rc, _ = run_cli(capsys, "install", "--agent", "claude-code", "--ref", "v1.0.0", "--no-runtime")
    assert rc == 0
    source = json.loads((sandbox.project / ".claude/settings.json").read_text())["extraKnownMarketplaces"]
    assert source[MARKETPLACE_NAME]["source"]["ref"] == "v1.0.0"
    assert run_cli(capsys, "install", "--agent", "claude-code", "--ref", "v1", "--mode", "files")[0] == 2


def test_local_marketplace_dir(sandbox: Sandbox, capsys, monkeypatch):
    monkeypatch.setenv("RF_HARNESS_MARKETPLACE_DIR", str(sandbox.tmp))
    run_cli(capsys, "install", "--agent", "claude-code", "--no-runtime")
    source = json.loads((sandbox.project / ".claude/settings.json").read_text())["extraKnownMarketplaces"]
    assert source[MARKETPLACE_NAME]["source"]["source"] == "directory"


def test_targets_lists_all_five(sandbox: Sandbox, capsys):
    fake_agent(sandbox, "claude", "2.1.0 (Claude Code)")
    (sandbox.home / ".codex").mkdir()
    rc, out = run_cli(capsys, "targets")
    assert rc == 0
    lines = {line.split()[0]: line for line in out.splitlines()[1:]}
    assert sorted(lines) == sorted(AGENTS)
    assert " yes " in lines["claude-code"] and "2.1.0 (Claude Code)" in lines["claude-code"]
    assert " yes " in lines["codex"] and " no " in lines["opencode"]
    assert "files" in lines["opencode"] and "plugin" not in lines["opencode"]


def test_headless_detected_install(sandbox: Sandbox, capsys):
    rc, out = run_cli(capsys, "install", "--agents", "detected", "--yes", "--no-runtime")
    assert rc == 1 and "no agents detected" in out
    fake_agent(sandbox, "claude")
    rc, out = run_cli(capsys, "install", "--agents", "detected", "--yes", "--no-runtime")
    assert rc == 0 and (sandbox.project / ".claude/settings.json").is_file()


def test_headless_failure_exits_nonzero(sandbox: Sandbox, capsys):
    """Codex plugin mode with --yes but no codex CLI cannot be set up -> exit code 1."""
    rc, out = run_cli(capsys, "install", "--agent", "codex", "--yes", "--no-runtime")
    assert rc == 1 and "codex is not on PATH" in out


def test_codex_plugin_commands_run_with_yes(sandbox: Sandbox, capsys, fake_codex):
    rc, out = run_cli(capsys, "install", "--agent", "codex", "--yes", "--no-runtime", "--ref", "v1.0.0")
    assert rc == 0, out
    calls = [json.loads(line) for line in fake_codex.read_text().splitlines()]
    assert calls == [["plugin", "marketplace", "add", MARKETPLACE_REPO, "--ref", "v1.0.0"],
                     ["plugin", "add", PLUGIN_ID]]


def test_unknown_agent(sandbox: Sandbox, capsys):
    rc, out = run_cli(capsys, "install", "--agents", "cursor", "--no-runtime")
    assert rc == 2 and "unknown agent" in out


def test_interactive_multiselect_preselects_detected(sandbox: Sandbox, capsys, monkeypatch):
    fake_agent(sandbox, "claude")
    fake_agent(sandbox, "codex")
    answers = iter(["3", ""])      # toggle copilot-cli on, confirm
    monkeypatch.setattr(prompt, "is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _msg="": next(answers))
    rc, out = run_cli(capsys, "install", "--no-runtime", "--mode", "files")
    assert rc == 0, out
    assert "[x] 1. Claude Code" in out and "[x] 2. OpenAI Codex" in out and "[ ] 3. GitHub Copilot CLI" in out
    assert (sandbox.project / ".claude/skills/rf-harness/SKILL.md").is_file()
    assert (sandbox.project / ".codex/hooks.json").is_file()
    assert (sandbox.project / ".github/hooks/rf-harness.json").is_file()
    assert not (sandbox.project / ".opencode").exists()


def test_multiselect_and_confirm_helpers():
    answers = iter(["a", "2", "x", ""])
    out: list[str] = []
    chosen = prompt.multiselect("t", [("a", "A"), ("b", "B"), ("c", "C")], set(), lambda _m: next(answers), out.append)
    assert chosen == ["a", "c"]
    assert prompt.multiselect("t", [("a", "A")], {"a"}, lambda _m: "q", out.append) is None
    assert prompt.confirm("ok?", True, lambda _m: "") is True
    assert prompt.confirm("ok?", False, lambda _m: "") is False
    assert prompt.confirm("ok?", False, lambda _m: "yes") is True


def test_list_and_version(sandbox: Sandbox, capsys):
    rc, out = run_cli(capsys, "list")
    assert rc == 0 and "no rf-harness installations" in out
    run_cli(capsys, "install", "--agent", "opencode", "--no-runtime")
    rc, out = run_cli(capsys, "list")
    assert "opencode" in out and "files" in out
    rc, out = run_cli(capsys, "version")
    assert rc == 0 and f"rf-harness {__version__}" in out and "plugin " in out


def test_project_gitignore_and_manifest(sandbox: Sandbox, capsys):
    (sandbox.project / ".gitignore").write_text("results/\n", encoding="utf-8")
    run_cli(capsys, "install", "--agent", "claude-code", "--no-runtime", "--mode", "files")
    manifest = json.loads((sandbox.project / ".rf-harness/manifest.json").read_text())
    entry = manifest["installations"][0]
    assert entry["agent"] == "claude-code" and entry["mode"] == "files"
    assert all(len(f["sha256"]) == 64 for f in entry["files"])
    assert {e["kind"] for e in entry["entries"]} == {"json_hooks"}
    assert ".rf-harness/" in (sandbox.project / ".gitignore").read_text()
    run_cli(capsys, "uninstall", "--agent", "claude-code")
    assert (sandbox.project / ".gitignore").read_text() == "results/\n"
