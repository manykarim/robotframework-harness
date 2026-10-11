"""Missing / incompatible runtime: one hint line on SessionStart, nothing otherwise, exit 0 always; never crash."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest
from launch_helpers import BIN, LAUNCHER, make_venv, output_json, run_launcher

sys.path.insert(0, str(BIN))
sys.dont_write_bytecode = True   # keep the plugin tree free of __pycache__
import rfh_launch  # noqa: E402

SHAPES = {
    "claude": lambda d: d["hookSpecificOutput"]["additionalContext"],
    "codex": lambda d: d["hookSpecificOutput"]["additionalContext"],
    "vscode": lambda d: d["hookSpecificOutput"]["additionalContext"],
    "copilot": lambda d: d["additionalContext"],
    "opencode": lambda d: d["text"],
}


@pytest.mark.parametrize("agent", sorted(SHAPES))
@pytest.mark.parametrize("event", ["SessionStart", "sessionStart"])
def test_missing_runtime_session_start_prints_one_hint(project, clean_env, agent, event):
    proc = run_launcher([event, "--agent", agent], {"cwd": str(project)}, clean_env, project)
    assert proc.returncode == 0
    lines = proc.stdout.decode().splitlines()
    assert len(lines) == 1
    text = SHAPES[agent](json.loads(lines[0]))
    assert rfh_launch.SETUP_COMMAND in text and "\n" not in text
    if agent in ("claude", "codex", "vscode"):
        assert json.loads(lines[0])["hookSpecificOutput"]["hookEventName"] == "SessionStart"


@pytest.mark.parametrize("event", ["UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop",
                                   "SessionEnd", "preToolUse", "postToolUse", "agentStop", "userPromptSubmitted"])
@pytest.mark.parametrize("agent", ["claude", "codex", "copilot", "vscode", "opencode", "auto"])
def test_missing_runtime_other_events_are_silent(project, clean_env, event, agent):
    payload = {"cwd": str(project), "tool_name": "Write", "tool_input": {"file_path": "a.robot", "content": "x"}}
    proc = run_launcher([event, "--agent", agent], payload, clean_env, project)
    assert proc.returncode == 0
    assert proc.stdout == b""


def test_incompatible_runtime_hint(project, clean_env):
    make_venv(project / ".venv", runtime="0.1.0")
    proc = run_launcher(["SessionStart", "--agent", "claude"], {"cwd": str(project)}, clean_env, project)
    text = output_json(proc)["hookSpecificOutput"]["additionalContext"]
    assert "0.1.0" in text and rfh_launch.LAUNCHER_VERSION in text and rfh_launch.SETUP_COMMAND in text
    silent = run_launcher(["PostToolUse", "--agent", "claude"], {"cwd": str(project)}, clean_env, project)
    assert (silent.returncode, silent.stdout) == (0, b"")


def test_dist_info_without_package_counts_as_missing(project, clean_env):
    make_venv(project / ".venv", with_package=False)
    proc = run_launcher(["SessionStart", "--agent", "codex"], {"cwd": str(project)}, clean_env, project)
    assert rfh_launch.SETUP_COMMAND in output_json(proc)["hookSpecificOutput"]["additionalContext"]


def test_copilot_session_end_is_dropped(project, clean_env):
    make_venv(project / ".venv")
    for args in (["SessionEnd", "--agent", "copilot"], ["sessionEnd", "--agent", "auto"]):
        proc = run_launcher(args, {"cwd": str(project)}, {**clean_env, "COPILOT_CLI": "1"}, project)
        assert (proc.returncode, proc.stdout) == (0, b"")


@pytest.mark.parametrize("stdin", [b"", b"not json", b"[1, 2]", b"\xff\xfe\x00garbage", b'{"cwd": 5}',
                                   b'{"cwd": "/definitely/not/here"}'])
def test_bad_input_never_fails(project, clean_env, stdin):
    for event in ("SessionStart", "PreToolUse"):
        proc = run_launcher([event, "--agent", "claude"], stdin, clean_env, project)
        assert proc.returncode == 0


def test_no_arguments_and_bad_rfh_python(project, clean_env):
    assert run_launcher([], None, clean_env, project).returncode == 0
    proc = run_launcher(["SessionStart"], {"cwd": str(project)}, {**clean_env, "RFH_PYTHON": str(project)}, project)
    assert proc.returncode == 0
    assert rfh_launch.SETUP_COMMAND in proc.stdout.decode()


def test_internal_error_exits_zero(project, clean_env):
    code = (f"import sys; sys.dont_write_bytecode = True; sys.path.insert(0, {str(BIN)!r}); import rfh_launch\n"
            "def boom(*a, **k):\n    raise RuntimeError('boom')\n"
            "rfh_launch.run = boom\nrfh_launch.main(['PreToolUse', '--agent', 'copilot'])\n")
    proc = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, env=clean_env, cwd=str(project))
    assert proc.returncode == 0 and proc.stdout == b""


def test_shim_without_module_exits_zero(tmp_path, project, clean_env):
    lonely = tmp_path / "bin"
    lonely.mkdir()
    shutil.copy(LAUNCHER, lonely / "rfh-launch")
    proc = subprocess.run([sys.executable, "-S", str(lonely / "rfh-launch"), "PreToolUse", "--agent", "copilot"],
                          input=b"{}", capture_output=True, env=clean_env, cwd=str(project))
    assert proc.returncode == 0 and proc.stdout == b""


def test_trace_records_the_decision(tmp_path, project, clean_env):
    trace = tmp_path / "trace.jsonl"
    run_launcher(["SessionStart", "--agent", "claude"], {"cwd": str(project)},
                 {**clean_env, "RF_HARNESS_LAUNCH_TRACE": str(trace)}, project)
    record = json.loads(trace.read_text().splitlines()[-1])
    assert record["action"] == "hint" and record["status"] == "missing" and record["agent"] == "claude"


def test_no_bytecode_written_into_the_plugin(tmp_path, project, clean_env):
    """Install dirs must stay byte-identical to what the manifest recorded (no __pycache__ next to the launcher)."""
    copy = tmp_path / "plugin-bin"
    shutil.copytree(BIN, copy, ignore=shutil.ignore_patterns("__pycache__"))
    proc = subprocess.run([sys.executable, "-S", str(copy / "rfh-launch"), "SessionStart", "--agent", "claude"],
                          input=json.dumps({"cwd": str(project)}).encode(), capture_output=True, env=clean_env,
                          cwd=str(project))
    assert proc.returncode == 0 and rfh_launch.SETUP_COMMAND in proc.stdout.decode()
    assert not (copy / "__pycache__").exists()
