"""Manifest-based upgrade and uninstall: obsolete files removed, user-modified files kept and reported (task 4.5)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from installer_helpers import REPO, Sandbox, run_cli

PLUGIN = REPO / "plugins" / "rf-harness"


@pytest.fixture
def assets(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private copy of the plugin tree as the installer's source (a 'version' we can change)."""
    root = sandbox.tmp / "assets"
    shutil.copytree(PLUGIN, root, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setenv("RF_HARNESS_ASSETS_DIR", str(root))
    return root


def install(capsys, *extra: str) -> tuple[int, str]:
    return run_cli(capsys, "install", "--agent", "claude-code", "--mode", "files", "--no-runtime", *extra)


def test_upgrade_removes_obsolete_file(sandbox: Sandbox, assets: Path, capsys):
    (assets / "skills/rf-harness/references/old.md").write_text("old\n", encoding="utf-8")
    assert install(capsys)[0] == 0
    installed = sandbox.project / ".claude/skills/rf-harness/references/old.md"
    assert installed.is_file()
    (assets / "skills/rf-harness/references/old.md").unlink()
    rc, out = install(capsys)
    assert rc == 0 and f"removed {installed}" in out
    assert not installed.exists()
    manifest = json.loads((sandbox.project / ".rf-harness/manifest.json").read_text())
    assert str(installed) not in {f["path"] for f in manifest["installations"][0]["files"]}


def test_upgrade_keeps_modified_obsolete_file(sandbox: Sandbox, assets: Path, capsys):
    (assets / "skills/rf-harness/references/old.md").write_text("old\n", encoding="utf-8")
    install(capsys)
    installed = sandbox.project / ".claude/skills/rf-harness/references/old.md"
    installed.write_text("my notes\n", encoding="utf-8")
    (assets / "skills/rf-harness/references/old.md").unlink()
    rc, out = install(capsys)
    assert rc == 0 and f"kept {installed} (modified by you)" in out
    assert installed.read_text() == "my notes\n"


def test_upgrade_updates_unmodified_and_keeps_modified_files(sandbox: Sandbox, assets: Path, capsys):
    install(capsys)
    skill = sandbox.project / ".claude/skills/rf-harness/SKILL.md"
    waits = sandbox.project / ".claude/skills/rf-harness/references/waits.md"
    waits.write_text("edited by me\n", encoding="utf-8")
    (assets / "skills/rf-harness/SKILL.md").write_text("new skill text\n", encoding="utf-8")
    (assets / "skills/rf-harness/references/waits.md").write_text("new waits\n", encoding="utf-8")
    rc, out = install(capsys)
    assert rc == 0
    assert skill.read_text() == "new skill text\n"
    assert waits.read_text() == "edited by me\n" and f"kept {waits}" in out


def test_mode_switch_removes_the_files_install(sandbox: Sandbox, capsys):
    """files -> plugin: the hook groups and copied files of the earlier install go away, the plugin entries come."""
    run_cli(capsys, "install", "--agent", "claude-code", "--mode", "files", "--no-runtime")
    settings = sandbox.project / ".claude/settings.json"
    assert "rfh-launch" in settings.read_text()
    rc, _ = run_cli(capsys, "install", "--agent", "claude-code", "--mode", "plugin", "--no-runtime")
    assert rc == 0
    data = json.loads(settings.read_text())
    assert "hooks" not in data and data["enabledPlugins"]
    assert not (sandbox.project / ".claude/skills/rf-harness").exists()


def test_uninstall_keeps_modified_files_and_user_entries(sandbox: Sandbox, capsys):
    settings = sandbox.project / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    user = {"model": "opus", "permissions": {"allow": ["Bash(robot:*)"]},
            "hooks": {"PostToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "./mine.sh"}]}]}}
    settings.write_text(json.dumps(user, indent=2) + "\n", encoding="utf-8")
    original = settings.read_bytes()
    run_cli(capsys, "install", "--agent", "claude-code", "--mode", "files", "--no-runtime")
    edited = sandbox.project / ".claude/skills/rf-harness/references/browser.md"
    edited.write_text("my edit\n", encoding="utf-8")
    rc, out = run_cli(capsys, "uninstall", "--agent", "claude-code")
    assert rc == 0 and f"kept {edited} (modified by you)" in out
    assert edited.read_text() == "my edit\n"
    assert settings.read_bytes() == original
    assert not (sandbox.project / ".claude/rf-harness").exists()
    assert not (sandbox.project / ".rf-harness").exists()


def test_uninstall_keeps_hook_groups_the_user_changed(sandbox: Sandbox, capsys):
    run_cli(capsys, "install", "--agent", "claude-code", "--mode", "files", "--no-runtime")
    settings = sandbox.project / ".claude/settings.json"
    data = json.loads(settings.read_text())
    data["hooks"]["Stop"][0]["hooks"][0]["timeout"] = 300
    settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    rc, out = run_cli(capsys, "uninstall", "--agent", "claude-code")
    assert "Stop modified" in out
    remaining = json.loads(settings.read_text())["hooks"]
    assert list(remaining) == ["Stop"]


def test_uninstall_dry_run_changes_nothing(sandbox: Sandbox, capsys):
    from installer_helpers import snapshot

    run_cli(capsys, "install", "--agent", "opencode", "--no-runtime")
    before = snapshot(sandbox.home, sandbox.project)
    rc, out = run_cli(capsys, "uninstall", "--agent", "opencode", "--dry-run")
    assert rc == 0 and "would remove" in out
    assert snapshot(sandbox.home, sandbox.project) == before
