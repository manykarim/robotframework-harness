"""`python -m rf_harness.runtime.hook <Event> --agent <agent>` with stdin payloads: exit code, output shape, the
helper lifecycle (SessionStart starts the daemons, SessionEnd leaves no process behind)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="hook runtime + /proc checks: Linux")

if sys.platform.startswith("linux"):
    from rf_harness.runtime import procs, proto


def _env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "RFH_ROOT", "RFH_HOOK_LOG")}
    return {**env, "RFH_WATCH_PID": str(os.getpid()), **extra}


def _hook(event: str, payload: dict, cwd: Path, agent: str = "claude", **env: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "rf_harness.runtime.hook", event, "--agent", agent],
                          input=json.dumps(payload), capture_output=True, text=True, cwd=str(cwd), env=_env(**env),
                          timeout=120)


def _procs_under(path: Path) -> list:
    out = []
    for n in os.listdir("/proc"):
        if not n.isdigit() or int(n) == os.getpid():
            continue
        try:
            with open(f"/proc/{n}/cmdline", "rb") as f:
                cl = f.read().decode(errors="replace")
            cwd = os.readlink(f"/proc/{n}/cwd")
        except OSError:
            continue
        if str(path) in cl or cwd.startswith(str(path)):
            out.append(int(n))
    return out


def _wait_gone(find, timeout: float) -> list:
    t_end = time.time() + timeout
    left = find()
    while left and time.time() < t_end:
        time.sleep(0.25)
        left = find()
    return left


def _describe(pids: list) -> list:
    out = []
    for p in pids:
        try:
            with open(f"/proc/{p}/cmdline", "rb") as f:
                out.append((p, f.read().replace(b"\0", b" ").decode(errors="replace")[:160]))
        except OSError:
            out.append((p, "?"))
    return out


def test_unknown_event_is_a_silent_no_op(tmp_path):
    r = _hook("NoSuchEvent", {"cwd": str(tmp_path)}, tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    assert not (tmp_path / ".rf").exists()


def test_stop_outside_a_harness_session_creates_nothing(tmp_path):
    r = _hook("Stop", {"cwd": str(tmp_path), "stop_hook_active": False}, tmp_path)
    assert (r.returncode, r.stdout) == (0, "")
    assert not (tmp_path / ".rf").exists()


def test_empty_stdin_and_auto_agent_are_tolerated(tmp_path):
    r = subprocess.run([sys.executable, "-m", "rf_harness.runtime.hook", "Stop", "--agent", "auto"], input="",
                       capture_output=True, text=True, cwd=str(tmp_path), env=_env(), timeout=60)
    assert (r.returncode, r.stdout) == (0, "")


def test_pre_tool_read_of_a_normal_file_passes_silently(tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    r = _hook("PreToolUse", {"cwd": str(tmp_path), "tool_name": "Read",
                             "tool_input": {"file_path": str(tmp_path / "notes.txt")}}, tmp_path)
    assert (r.returncode, r.stdout) == (0, "")


def test_session_start_then_end_leaves_no_processes(tmp_path):
    ws = tmp_path / "ws"
    (ws / "tests").mkdir(parents=True)
    (ws / "tests" / "a.robot").write_text("*** Test Cases ***\nT\n    Log    hi\n")
    try:
        r = _hook("SessionStart", {"cwd": str(ws), "source": "startup", "session_id": "t"}, ws)
        assert r.returncode == 0, r.stderr
        ctx = json.loads(r.stdout)["hookSpecificOutput"]
        assert ctx["hookEventName"] == "SessionStart" and "live RF session" in ctx["additionalContext"]
        assert (ws / ".rf" / "hook" / "session.json").is_file()
        log = [json.loads(x) for x in (ws / ".rf" / "hook" / "hooks.jsonl").read_text().splitlines()]
        assert log[-1]["event"] == "session-start" and log[-1]["profile"] == "lean" and "error" not in log[-1]
        t_end = time.time() + 60
        states = {}
        while time.time() < t_end:
            states = {k: proto.read_state(ws / ".rf" / k) or {} for k in ("exec", "lint")}
            if all(s.get("ready") for s in states.values()):
                break
            time.sleep(0.2)
        assert all(s.get("ready") for s in states.values()), states
        tokens = [s["token_env"] for s in states.values()]
        r = _hook("SessionEnd", {"cwd": str(ws), "reason": "other"}, ws)
        assert (r.returncode, r.stdout) == (0, "")
        daemons = _wait_gone(lambda: [p for t in tokens for p in procs.token_procs(t)], 30)
        assert not daemons, _describe(daemons)        # daemons + their browsers / workers
        workers = _wait_gone(lambda: _procs_under(ws), 90)
        assert not workers, _describe(workers)        # short-lived doc workers finish on their own
    finally:
        stray = _procs_under(ws)
        if stray:
            procs.terminate(stray, grace=1.0)
