"""Interpreter discovery (design D3 order), project root and agent detection of the hook launcher."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest
from launch_helpers import BIN, IS_WINDOWS, add_runtime, base_python, make_venv, output_json, run_launcher

sys.path.insert(0, str(BIN))
sys.dont_write_bytecode = True   # keep the plugin tree free of __pycache__
import rfh_launch  # noqa: E402

from rf_harness import __version__  # noqa: E402

PAYLOAD = {"hook_event_name": "UserPromptSubmit", "prompt": "hi", "session_id": "s1"}


def exec_record(proc) -> dict:
    data = output_json(proc)
    assert data.get("fake_runtime"), data
    return data


def same_python(a: str, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(str(b)))


# ------------------------------------------------------------------------------------------------ each D3 branch
def test_rfh_python_wins(tmp_path, project, clean_env):
    explicit = make_venv(tmp_path / "explicit")
    make_venv(project / ".venv")
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)},
                        {**clean_env, "RFH_PYTHON": str(explicit)}, project)
    assert proc.returncode == 0
    assert same_python(exec_record(proc)["python"], explicit)


def test_rfh_python_is_authoritative_without_runtime(tmp_path, project, clean_env):
    explicit = make_venv(tmp_path / "explicit", runtime=None, with_package=False)
    make_venv(project / ".venv")          # has a runtime, but RFH_PYTHON must not fall back to it
    proc = run_launcher(["SessionStart", "--agent", "claude"], {"cwd": str(project)},
                        {**clean_env, "RFH_PYTHON": str(explicit)}, project)
    hint = output_json(proc)["hookSpecificOutput"]["additionalContext"]
    assert rfh_launch.SETUP_COMMAND in hint and str(explicit) in hint


def test_harness_json(tmp_path, project, clean_env):
    recorded = make_venv(tmp_path / "recorded")
    make_venv(project / ".venv")
    (project / ".rf").mkdir()
    (project / ".rf" / "harness.json").write_text(json.dumps({"python": str(recorded)}), encoding="utf-8")
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)}, clean_env, project)
    assert same_python(exec_record(proc)["python"], recorded)


def test_incompatible_harness_json_falls_through(tmp_path, project, clean_env):
    old = make_venv(tmp_path / "old", runtime="0.1.0")
    good = make_venv(project / ".venv")
    (project / ".rf").mkdir()
    (project / ".rf" / "harness.json").write_text(json.dumps({"python": str(old)}), encoding="utf-8")
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)}, clean_env, project)
    assert same_python(exec_record(proc)["python"], good)


@pytest.mark.parametrize("var", ["VIRTUAL_ENV", "CONDA_PREFIX"])
def test_active_environment(tmp_path, project, clean_env, var):
    active = make_venv(tmp_path / "active")
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)},
                        {**clean_env, var: str(tmp_path / "active")}, project)
    assert same_python(exec_record(proc)["python"], active)


def test_project_venv(project, clean_env):
    python = make_venv(project / ".venv")
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)}, clean_env, project)
    assert same_python(exec_record(proc)["python"], python)


def test_uv_project_environment(project, clean_env):
    python = make_venv(project / "envs" / "uv")
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)},
                        {**clean_env, "UV_PROJECT_ENVIRONMENT": "envs/uv"}, project)
    assert same_python(exec_record(proc)["python"], python)


def test_poetry_environment(tmp_path, project, clean_env):
    (project / "pyproject.toml").write_text('[tool.poetry]\nname = "rf-demo"\nversion = "0.1.0"\n', encoding="utf-8")
    envs = tmp_path / "poetry-envs"
    name = rfh_launch.poetry_env_name("rf-demo", str(project))
    python = make_venv(envs / f"{name}-py3.12")
    make_venv(envs / "other-project-AAAAAAAA-py3.12")
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)},
                        {**clean_env, "POETRY_VIRTUALENVS_PATH": str(envs)}, project)
    assert same_python(exec_record(proc)["python"], python)


@pytest.mark.skipif(IS_WINDOWS, reason="python3 symlink on PATH")
def test_python3_on_path_uses_queried_sys_path(tmp_path, project, clean_env):
    """A non-venv interpreter: its sys.path is queried once (here PYTHONPATH carries the fake runtime) and cached."""
    path_dir = tmp_path / "path-bin"
    path_dir.mkdir()
    (path_dir / "python3").symlink_to(os.path.realpath(base_python()))
    site = tmp_path / "global-site"
    add_runtime(site)
    env = {**clean_env, "PATH": str(path_dir), "PYTHONPATH": str(site)}
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)}, env, project)
    assert same_python(exec_record(proc)["python"], path_dir / "python3")
    cache = Path(clean_env["RF_HARNESS_CACHE_DIR"]) / "launch-paths.json"
    assert str(site) in json.dumps(json.loads(cache.read_text()))


def test_editable_install_via_pth(tmp_path, project, clean_env):
    python = make_venv(project / ".venv", runtime=__version__, with_package=False)
    src = tmp_path / "checkout" / "src"
    add_runtime(src, version=None)
    site = python.parent.parent / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" \
        if not IS_WINDOWS else project / ".venv" / "Lib" / "site-packages"
    (site / "_editable_impl_robotframework_harness.pth").write_text(str(src), encoding="utf-8")
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)}, clean_env, project)
    assert same_python(exec_record(proc)["python"], python)


def test_order_without_anything_gives_hint(project, clean_env):
    proc = run_launcher(["SessionStart", "--agent", "claude"], {"cwd": str(project)}, clean_env, project)
    assert proc.returncode == 0
    assert rfh_launch.SETUP_COMMAND in output_json(proc)["hookSpecificOutput"]["additionalContext"]


class _Stat:
    def __init__(self, tag: int) -> None:
        self.st_reparse_tag = tag


def test_path_fallback_skips_store_placeholders(monkeypatch):
    """Change fix-windows-python-detection D5: App Execution Aliases are skipped by reparse tag, never started."""
    apps = "/Users/me/AppData/Local/Microsoft/WindowsApps"
    real = "/Python312"
    monkeypatch.setattr(rfh_launch, "IS_WINDOWS", True)
    monkeypatch.setattr(rfh_launch.os.path, "isfile", lambda _p: True)
    monkeypatch.setattr(rfh_launch.os, "access", lambda _p, _m: True)
    monkeypatch.setattr(rfh_launch.os, "lstat", lambda p: _Stat(rfh_launch.APPEXECLINK if apps in p else 0))
    assert rfh_launch.path_python({"PATH": os.pathsep.join([apps, real])}) == os.path.join(real, "python.exe")
    assert rfh_launch.path_python({"PATH": apps}) is None
    monkeypatch.setattr(rfh_launch.os, "lstat", lambda p: _Stat(0))       # a real file in a WindowsApps folder
    assert rfh_launch.path_python({"PATH": apps}) == os.path.join(apps, "python.exe")
    monkeypatch.setattr(rfh_launch, "IS_WINDOWS", False)
    assert not rfh_launch.is_app_alias(os.path.join(apps, "python.exe"))


def test_candidates_order(tmp_path, project):
    rec = make_venv(tmp_path / "rec")
    (project / ".rf").mkdir()
    (project / ".rf" / "harness.json").write_text(json.dumps({"python": str(rec)}), encoding="utf-8")
    venv_py = make_venv(project / ".venv")
    active = make_venv(tmp_path / "active")
    uv_py = make_venv(project / "uvenv")
    env = {"VIRTUAL_ENV": str(tmp_path / "active"), "UV_PROJECT_ENVIRONMENT": "uvenv", "PATH": ""}
    sources = [s for s, _ in rfh_launch.candidates(str(project), env)]
    assert sources == ["harness.json", "VIRTUAL_ENV", ".venv", "UV_PROJECT_ENVIRONMENT"]
    pythons = [p for _, p in rfh_launch.candidates(str(project), env)]
    assert [os.path.normcase(p) for p in pythons] == [os.path.normcase(str(p)) for p in (rec, active, venv_py, uv_py)]
    assert rfh_launch.candidates(str(project), {**env, "RFH_PYTHON": "/x/python"}) == [("RFH_PYTHON", "/x/python")]


@pytest.mark.skipif(IS_WINDOWS, reason="poetry hashes the normcased (lower-case, backslash) path on Windows")
@pytest.mark.parametrize(("name", "path", "expected"), [
    ("Demo Project!", "/opt/rfh-poetry-vector/demo", "demo_project_-SmeU_FRt"),
    ("rf-tests", "/srv/projects/rf-tests", "rf-tests-yPEX6IDY"),
])
def test_poetry_env_name_matches_poetry(name, path, expected):
    """Vectors from poetry 2.4.1 EnvManager.generate_env_name. Poetry hashes os.path.realpath(path), so the vectors use
    paths without symlinked parts (on macOS /tmp -> /private/tmp would change the hash, for poetry as well)."""
    if os.path.realpath(path) != path:
        pytest.skip(f"{path} resolves to {os.path.realpath(path)} on this machine")
    assert rfh_launch.poetry_env_name(name, path) == expected


# ------------------------------------------------------------------------------------------------ project root
def test_project_root(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    deep = root / "suites" / "web"
    deep.mkdir(parents=True)
    (deep / "login.robot").write_text("*** Test Cases ***\n", encoding="utf-8")
    assert rfh_launch.project_root(str(deep)) == str(root)
    (root / "suites" / ".rf").mkdir()
    assert rfh_launch.project_root(str(deep)) == str(root / "suites")
    loose = tmp_path / "loose" / "tests"
    loose.mkdir(parents=True)
    (loose / "a.robot").write_text("", encoding="utf-8")
    assert rfh_launch.project_root(str(loose)) in (str(loose), str(tmp_path))  # tmp_path may sit in a repo


def test_payload_cwd_selects_the_project(tmp_path, project, clean_env):
    python = make_venv(project / ".venv")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    proc = run_launcher(["UserPromptSubmit", "--agent", "claude"], {**PAYLOAD, "cwd": str(project)}, clean_env,
                        elsewhere)
    assert same_python(exec_record(proc)["python"], python)


# ------------------------------------------------------------------------------------------------ agent detection
@pytest.mark.parametrize(("event", "payload", "env", "expected"), [
    ("PostToolUse", {}, {"COPILOT_CLI": "1"}, "copilot"),
    ("PostToolUse", {"turn_id": "t"}, {"CLAUDECODE": "1"}, "claude"),
    ("PostToolUse", {"turn_id": "t", "tool_name": "apply_patch"}, {}, "codex"),
    ("SessionStart", {"model": "gpt-5", "transcript_path": "/x"}, {}, "codex"),
    ("PostToolUse", {"tool_name": "create_file", "tool_input": {"filePath": "/a.robot"}}, {}, "vscode"),
    ("PostToolUse", {"tool_name": "apply_patch", "tool_input": {"input": "*** Begin Patch"}}, {}, "vscode"),
    ("Stop", {}, {"VSCODE_PID": "1"}, "vscode"),
    ("postToolUse", {}, {}, "copilot"),
    ("Stop", {}, {}, "claude"),
])
def test_detect_agent(event, payload, env, expected):
    assert rfh_launch.detect_agent(event, payload, env, ancestry=lambda: None) == expected


def test_detect_agent_by_parent_process():
    assert rfh_launch.detect_agent("SessionEnd", {}, {}, ancestry=lambda: "codex") == "codex"


def test_auto_agent_reaches_runtime_as_concrete_agent(project, clean_env):
    make_venv(project / ".venv")
    proc = run_launcher(["PostToolUse", "--agent", "auto"], {"cwd": str(project), "turn_id": "t1"}, clean_env, project)
    assert exec_record(proc)["argv"][:3] == ["PostToolUse", "--agent", "codex"]


def test_parse_args():
    event, agent, sets, rest = rfh_launch.parse_args(
        ["PreToolUse", "--agent", "claude-code", "--set", "RFH_STATIC=runtime-only", "--set", "HOME=x", "--extra"])
    assert (event, agent, sets, rest) == ("PreToolUse", "claude", {"RFH_STATIC": "runtime-only"}, ["--extra"])
    assert rfh_launch.canonical_event("agentStop") == "Stop"
    assert rfh_launch.canonical_event("userPromptSubmitted") == "UserPromptSubmit"


def test_launcher_version_matches_package():
    assert rfh_launch.LAUNCHER_VERSION == re.sub(r"(?:\.?(?:a|b|rc)\d+)?(?:\.dev\d+)?$", "", __version__)


@pytest.mark.parametrize("value", [
    {"hook_event_name": "PostToolUse", "tool_input": {"content": "ä€😀\n\t\"q\" \\ \u0001", "n": [1, 2.5, -3e20]},
     "ok": True, "no": False, "none": None, "": {}},
    [], {}, "x", 0, 12345678901234567890, -0.5,
])
def test_json_helpers_match_the_json_module(value):
    text = json.dumps(value)
    assert rfh_launch.loads(text) == value
    assert rfh_launch.loads("  \n" + text + "\n ") == value
    assert json.loads(rfh_launch.dumps(value)) == value


@pytest.mark.parametrize("bad", ["", "{", '{"a": 1} trailing', "[1,]", "nul", "{'a': 1}"])
def test_json_helpers_reject_invalid_input(bad):
    with pytest.raises(ValueError):
        rfh_launch.loads(bad)
