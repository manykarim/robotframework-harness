"""Hook-side payload handling (rf_harness.runtime.hookcore): edit/shell/read shapes of every agent (incl. VS Code
native tools), robot invocations, output rendering per agent, root discovery and Playwright browser discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="hookcore uses fcntl (POSIX); Windows transport is "
                                                                "a later hardening step (design D5)")

if sys.platform != "win32":
    from rf_harness.runtime import hookcore as hc

SUITE = "*** Test Cases ***\nT\n    Log    one\n    Log    two\n"


@pytest.fixture
def suite(tmp_path: Path) -> Path:
    f = tmp_path / "tests" / "a.robot"
    f.parent.mkdir()
    f.write_text(SUITE)
    return f


def test_claude_write_and_edit(tmp_path, suite):
    [w] = hc.proposed_edits("Write", {"file_path": str(suite), "content": "x"}, tmp_path)
    assert (w.kind, w.current, w.new) == ("write", SUITE, "x")
    [e] = hc.proposed_edits("Edit", {"file_path": "tests/a.robot", "old_string": "one", "new_string": "1"}, tmp_path)
    assert e.kind == "edit" and e.new == SUITE.replace("one", "1") and e.path == suite.resolve()


def test_non_rf_files_are_ignored(tmp_path):
    assert hc.proposed_edits("Write", {"file_path": str(tmp_path / "x.py"), "content": "x"}, tmp_path) == []


def test_vscode_create_and_replace(tmp_path, suite):
    new_file = tmp_path / "tests" / "b.robot"
    [c] = hc.proposed_edits("create_file", {"filePath": str(new_file), "content": SUITE}, tmp_path)
    assert (c.kind, c.current, c.new) == ("write", None, SUITE)
    [r] = hc.proposed_edits("replace_string_in_file", {"filePath": str(suite), "oldString": "two", "newString": "2"},
                            tmp_path)
    assert r.new == SUITE.replace("two", "2") and r.edit["keys"] == ["oldString", "newString"]
    assert {"create_file", "replace_string_in_file", "multi_replace_string_in_file"} <= hc.EDIT_TOOLS
    assert "run_in_terminal" in hc.SHELL_TOOLS


def test_vscode_multi_replace(tmp_path, suite):
    inp = {"replacements": [{"filePath": str(suite), "oldString": "one", "newString": "1"},
                            {"filePath": str(suite), "oldString": "two", "newString": "2"},
                            {"filePath": str(tmp_path / "notes.md"), "oldString": "a", "newString": "b"}]}
    [m] = hc.proposed_edits("multi_replace_string_in_file", inp, tmp_path)
    assert m.kind == "multiedit" and m.new == SUITE.replace("one", "1").replace("two", "2")
    assert hc.edited_rf_files("multi_replace_string_in_file", inp, tmp_path) == [suite.resolve()]
    bad = {"replacements": [{"filePath": str(suite), "oldString": "missing", "newString": "x"}]}
    assert hc.proposed_edits("multi_replace_string_in_file", bad, tmp_path)[0].new is None


def test_apply_patch_roundtrip(tmp_path, suite):
    new = SUITE.replace("two", "2")
    patch = hc.make_patch(str(suite), SUITE, new)
    [p] = hc.proposed_edits("apply_patch", {"command": patch}, tmp_path)
    assert p.kind == "patch" and p.new.rstrip("\n") == new.rstrip("\n")
    add = hc.make_patch(str(tmp_path / "tests" / "c.robot"), None, SUITE)
    files = hc.parse_patch(add)
    assert files[0]["op"] == "add" and "\n".join(files[0]["lines"]) + "\n" == SUITE


def test_copilot_tool_args_as_json_string():
    assert hc.tool_input({"toolArgs": json.dumps({"command": "ls"})}) == {"command": "ls"}
    raw = "*** Begin Patch\n*** Add File: x.robot\n+a\n*** End Patch"
    assert hc.tool_input({"toolArgs": raw}) == {"command": raw, "_raw_patch": True}


@pytest.mark.parametrize(("cmd", "runs"), [
    ("robot -d results tests/x.robot", [["-d", "results", "tests/x.robot"]]),
    ("cd ws && python -m robot tests", [["tests"]]),
    (".venv/bin/robot --dryrun tests", []),
    ("rebot output.xml", []),
    ("robot --version", []),
])
def test_robot_invocations(cmd, runs):
    assert hc.robot_invocations(cmd) == runs


def test_output_xml_for(tmp_path):
    assert hc.output_xml_for(["-d", "results", "x.robot"], tmp_path) == (tmp_path / "results" / "output.xml").resolve()
    assert hc.output_xml_for(["-o", "NONE", "x.robot"], tmp_path) is None


def test_render_per_agent():
    deny = hc.Result("deny", "no")
    ctx = hc.Result("context", "hello")
    claude = json.loads(hc.render("claude", "pre-tool", deny, {}))
    assert claude["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert json.loads(hc.render("vscode", "pre-tool", deny, {})) == claude          # Claude format
    assert json.loads(hc.render("copilot", "pre-tool", deny, {})) == {"permissionDecision": "deny",
                                                                      "permissionDecisionReason": "no"}
    assert json.loads(hc.render("opencode", "post-tool", ctx, {})) == {"action": "context", "text": "hello"}
    post = json.loads(hc.render("claude", "post-tool", ctx, {"hook_event_name": "PostToolUseFailure"}))
    assert post["hookSpecificOutput"] == {"hookEventName": "PostToolUseFailure", "additionalContext": "hello"}
    assert hc.render("claude", "stop", hc.Result(), {}) == ""


def test_clip_keeps_whole_lines():
    text = "\n".join(f"line {i}" for i in range(500))
    out = hc.clip(text, 200)
    assert len(out) <= 200 and out.endswith("... (truncated)")


def test_find_root_prefers_initialized_parents(tmp_path, monkeypatch):
    monkeypatch.delenv("RFH_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    sub = tmp_path / "proj" / "tests"
    sub.mkdir(parents=True)
    assert hc.find_root({"cwd": str(sub)}) == sub.resolve()
    (tmp_path / "proj" / ".rf").mkdir()
    (tmp_path / "proj" / ".rf" / "harness.json").write_text("{}")
    assert hc.find_root({"cwd": str(sub)}) == (tmp_path / "proj").resolve()
    monkeypatch.setenv("RFH_ROOT", str(sub))
    assert hc.find_root({"cwd": str(tmp_path)}) == sub.resolve()


def test_changed_line_numbers():
    assert hc.changed_line_numbers(None, "a\n") is None
    assert hc.changed_line_numbers("a\nb\nc\n", "a\nB\nc\nd\n") == [2, 4]


def test_playwright_env_points_at_the_shared_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    venv = tmp_path / "venv"
    core = venv / "lib" / "python3.12" / "site-packages" / "Browser" / "wrapper" / "node_modules" / "playwright-core"
    core.mkdir(parents=True)
    (core / "browsers.json").write_text(json.dumps({"browsers": [{"name": "chromium-headless-shell",
                                                                  "revision": "1208"}]}))
    py = str(venv / "bin" / "python")
    assert hc.playwright_env(py) == {}                                  # nothing in the shared cache yet
    cache = tmp_path / "home" / ".cache" / "ms-playwright" / "chromium_headless_shell-1208"
    cache.mkdir(parents=True)
    assert hc.playwright_env(py) == {"PLAYWRIGHT_BROWSERS_PATH": str(cache.parent)}
    (core / ".local-browsers" / "chromium_headless_shell-1208").mkdir(parents=True)
    assert hc.playwright_env(py) == {}                                  # bundled browser present
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/somewhere")
    assert hc.playwright_env(py) == {}


def test_child_env_puts_this_package_first_on_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/x")
    env = hc.child_env()
    if hc.PKG_PARENT.name in ("site-packages", "dist-packages"):
        assert env["PYTHONPATH"] == "/x"
    else:
        assert env["PYTHONPATH"].split(":")[0] == str(hc.PKG_PARENT)
    assert (hc.PKG_PARENT / "rf_harness" / "runtime" / "hook.py").is_file()
