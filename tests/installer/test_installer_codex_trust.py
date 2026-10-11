"""Codex hook trust: exactly the installed rf-harness hooks get ``trusted_hash`` entries (task 4.4)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from fake_codex import fake_hash
from installer_helpers import IS_WINDOWS, Sandbox, run_cli

from rf_harness.installer import codex_trust
from rf_harness.installer import transforms as _x

REAL_CODEX = shutil.which("codex")
USER_HOOK = {"matcher": "Bash", "hooks": [{"type": "command", "command": "./my-audit.sh", "timeout": 5}]}


def expected_trust(hooks_file: Path) -> dict[str, str]:
    """What a correct provisioning writes: one entry per rf-harness hook in hooks_file (fake codex hash)."""
    data = json.loads(hooks_file.read_text())
    snake = {"SessionStart": "session_start", "UserPromptSubmit": "user_prompt_submit", "PreToolUse": "pre_tool_use",
             "PostToolUse": "post_tool_use", "Stop": "stop", "SessionEnd": "session_end"}
    out = {}
    for event, groups in data["hooks"].items():
        for gi, group in enumerate(groups):
            for hi, hook in enumerate(group["hooks"]):
                if "rfh-launch" in hook["command"]:
                    out[f"{hooks_file}:{snake[event]}:{gi}:{hi}"] = fake_hash(event, group, hook)
    return out


def test_user_scope_trust_matches_installed_hooks(sandbox: Sandbox, capsys, fake_codex):
    codex_home = sandbox.home / ".codex"
    hooks_file = codex_home / "hooks.json"
    hooks_file.parent.mkdir(parents=True)
    hooks_file.write_text(json.dumps({"hooks": {"PreToolUse": [USER_HOOK]}}, indent=2) + "\n", encoding="utf-8")
    config = codex_home / "config.toml"
    user_config = ('model = "gpt-5"\n\n[hooks.state."/elsewhere/hooks.json:stop:0:0"]\ntrusted_hash = "sha256:abc"\n')
    config.write_text(user_config, encoding="utf-8")

    rc, out = run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--scope", "user", "--no-runtime")
    assert rc == 0, out
    stored = _x.read_codex_trust(config)
    expected = expected_trust(hooks_file)
    assert len(expected) == 6
    assert {k: v for k, v in stored.items() if k != "/elsewhere/hooks.json:stop:0:0"} == expected
    assert f"{hooks_file}:pre_tool_use:0:0" not in stored          # the user's own hook is not trusted by us
    assert stored["/elsewhere/hooks.json:stop:0:0"] == "sha256:abc"
    statuses = {h["key"]: h["trustStatus"] for h in codex_trust.list_hooks(sandbox.project) or []}
    assert all(statuses[k] == "trusted" for k in expected)
    assert statuses[f"{hooks_file}:pre_tool_use:0:0"] == "untrusted"

    snapshot_config = config.read_bytes()
    rc, out = run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--scope", "user", "--no-runtime")
    assert rc == 0 and "no changes" in out and config.read_bytes() == snapshot_config

    run_cli(capsys, "uninstall", "--agent", "codex", "--scope", "user")
    assert config.read_text() == user_config
    assert json.loads(hooks_file.read_text()) == {"hooks": {"PreToolUse": [USER_HOOK]}}


def test_project_scope_untrusted_project_is_pretrusted(sandbox: Sandbox, capsys, fake_codex):
    rc, out = run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--no-runtime")
    assert rc == 0 and "Codex has not trusted this project yet" in out
    stored = _x.read_codex_trust(sandbox.home / ".codex/config.toml")
    assert stored == expected_trust(sandbox.project / ".codex/hooks.json")


def test_trust_follows_a_changed_hook(sandbox: Sandbox, capsys, fake_codex, monkeypatch):
    run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--scope", "user", "--no-runtime")
    config = sandbox.home / ".codex/config.toml"
    before = _x.read_codex_trust(config)
    (sandbox.project / ".claude").mkdir()   # no effect; then rf-agentskills appears -> commands change (--set)
    agentskills = sandbox.project / ".claude/settings.json"
    agentskills.write_text(json.dumps({"hooks": {"PostToolUse": [{"hooks": [
        {"type": "command", "command": "node /x/rf-agentskills-files/scripts/validate_robot.mjs"}]}]}}),
        encoding="utf-8")
    run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--scope", "user", "--no-runtime")
    after = _x.read_codex_trust(config)
    assert set(after) == set(before) and after != before
    assert after == expected_trust(sandbox.home / ".codex/hooks.json")


def test_no_codex_prints_the_hooks_step(sandbox: Sandbox, capsys):
    rc, out = run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--no-runtime")
    assert rc == 0 and "codex hook trust not provisioned" in out and "/hooks" in out
    assert not (sandbox.home / ".codex/config.toml").exists()


# ------------------------------------------------------------------------------------------------ TOML edits
def test_codex_trust_text_edits(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text('model = "x"\n\n[hooks.state."C:\\\\Users\\\\me\\\\h.json:stop:0:0"]\n'
                      'trusted_hash = "sha256:old"\nenabled = true\n', encoding="utf-8")
    key_win = "C:\\Users\\me\\h.json:stop:0:0"
    assert _x.read_codex_trust(config) == {key_win: "sha256:old"}
    assert _x.set_codex_trust(config, {key_win: "sha256:new", "/p/h.json:session_start:0:0": "sha256:1"})
    assert _x.read_codex_trust(config) == {key_win: "sha256:new", "/p/h.json:session_start:0:0": "sha256:1"}
    assert not _x.set_codex_trust(config, {key_win: "sha256:new"})
    assert _x.remove_codex_trust(config, [key_win, "/p/h.json:session_start:0:0"])
    text = config.read_text()
    assert "trusted_hash" not in text and "enabled = true" in text and text.startswith('model = "x"')
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        return
    tomllib.loads(text)


def test_probe_config_trusts_both_path_spellings():
    from pathlib import PurePosixPath, PureWindowsPath

    win = codex_trust.probe_config(PureWindowsPath(r"C:\Users\me\proj"))
    assert '[projects."C:\\\\Users\\\\me\\\\proj"]' in win and '[projects."C:/Users/me/proj"]' in win
    assert win.count('trust_level = "trusted"') == 2
    posix = codex_trust.probe_config(PurePosixPath("/home/me/proj"))
    assert posix == '[projects."/home/me/proj"]\ntrust_level = "trusted"\n'
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.10
        return
    assert set(tomllib.loads(win)["projects"]) == {"C:\\Users\\me\\proj", "C:/Users/me/proj"}


def test_project_trust_detection(tmp_path: Path):
    config = tmp_path / "config.toml"
    project = tmp_path / "proj"
    assert not _x.codex_project_trusted(config, project)
    config.write_text(f'[projects."{_x.native_path(project)}"]\ntrust_level = "trusted"\n', encoding="utf-8")
    assert _x.codex_project_trusted(config, project)


# ------------------------------------------------------------------------------------------------ real codex
@pytest.mark.skipif(REAL_CODEX is None or IS_WINDOWS, reason="needs the codex CLI")
def test_real_codex_trusts_exactly_our_hooks(sandbox: Sandbox, capsys):
    """Against the installed codex (verified on 0.162.1): after install, codex reports our hooks as trusted."""
    assert REAL_CODEX is not None
    os.symlink(REAL_CODEX, sandbox.bin / "codex")
    codex_home = sandbox.home / ".codex"
    codex_home.mkdir()
    (codex_home / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [USER_HOOK]}}), encoding="utf-8")
    rc, out = run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--scope", "user", "--no-runtime")
    assert rc == 0, out
    hooks = codex_trust.list_hooks(sandbox.project)
    assert hooks is not None
    ours = [h for h in hooks if "rfh-launch" in h["command"]]
    assert len(ours) == 6 and all(h["trustStatus"] == "trusted" for h in ours)
    assert [h["trustStatus"] for h in hooks if h["command"] == "./my-audit.sh"] == ["untrusted"]
    stored = _x.read_codex_trust(codex_home / "config.toml")
    assert stored == {h["key"]: h["currentHash"] for h in ours}
    run_cli(capsys, "uninstall", "--agent", "codex", "--scope", "user")
    assert not _x.read_codex_trust(codex_home / "config.toml")
