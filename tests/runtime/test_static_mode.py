"""RFH_STATIC through the real hook + lint/live daemons (no browser): `on` warns and modernizes, `runtime-only`
(rf-agentskills validates edits) refuses only certainly-wrong structure and reports the live run's own errors.
Also covers the `--agent vscode` payload shape (Claude format, VS Code tool names)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow,
              pytest.mark.skipif(not sys.platform.startswith("linux"), reason="hook runtime + /proc checks: Linux")]

if sys.platform.startswith("linux"):
    from rf_harness.runtime import procs, proto

PLANTED = ("*** Settings ***\nLibrary    Collections\n\n*** Test Cases ***\nT\n    Log    hi\n    Clik    x\n"
           "    Run Keyword If    1 == 1    Log    y\n")
UNCLOSED = "*** Test Cases ***\nT\n    FOR    ${i}    IN RANGE    2\n        Log    ${i}\n"


class Session:
    def __init__(self, ws: Path, agent: str, **env: str) -> None:
        self.ws, self.agent = ws, agent
        base = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "RFH_ROOT", "RFH_STATIC")}
        self.env = {**base, "RFH_WATCH_PID": str(os.getpid()), "RFH_PROFILE": "lean", **env}

    def hook(self, event: str, payload: dict) -> dict:
        r = subprocess.run([sys.executable, "-m", "rf_harness.runtime.hook", event, "--agent", self.agent],
                           input=json.dumps({"cwd": str(self.ws), "hook_event_name": event, **payload}),
                           capture_output=True, text=True, cwd=str(self.ws), env=self.env, timeout=200)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def log(self) -> list:
        return [json.loads(x) for x in (self.ws / ".rf" / "hook" / "hooks.jsonl").read_text().splitlines()]

    def wait_gate(self, tool: str, inp: dict, timeout: float = 90) -> dict:
        """PreToolUse until the lint daemon's gate is warm (the log then has gate timings and no 'not ready')."""
        t_end = time.time() + timeout
        while True:
            out = self.hook("PreToolUse", {"tool_name": tool, "tool_input": inp})
            last = self.log()[-1]
            if last.get("gate_ms") and "gate" not in last:
                return out
            assert time.time() < t_end, last
            time.sleep(0.5)

    def end(self) -> None:
        states = [proto.read_state(self.ws / ".rf" / k) or {} for k in ("exec", "lint")]
        tokens = [s["token_env"] for s in states if s.get("token_env")]
        self.hook("SessionEnd", {"reason": "other"})
        t_end = time.time() + 30
        left = [1]
        while left and time.time() < t_end:
            left = [p for t in tokens for p in procs.token_procs(t)]
            time.sleep(0.2)
        if left:
            procs.terminate(left, grace=1.0)
        assert not left, left


def _ws(tmp_path: Path, name: str) -> Path:
    ws = tmp_path / name
    (ws / "tests").mkdir(parents=True)
    return ws


def test_static_on_warns_and_modernizes(tmp_path):
    ws = _ws(tmp_path, "on")
    s = Session(ws, "claude")
    try:
        s.hook("SessionStart", {"source": "startup"})
        f = ws / "tests" / "t.robot"
        out = s.wait_gate("Write", {"file_path": str(f), "content": PLANTED})
        h = out["hookSpecificOutput"]
        assert h.get("permissionDecision") != "deny"
        assert "not blocking" in h["additionalContext"] and "KeywordNotFound" in h["additionalContext"]
        assert "Run Keyword If" not in h["updatedInput"]["content"] and "IF    1 == 1" in h["updatedInput"]["content"]
    finally:
        s.end()


def test_static_runtime_only_with_vscode_payloads(tmp_path):
    ws = _ws(tmp_path, "runtime_only")
    s = Session(ws, "vscode", RFH_STATIC="runtime-only")
    try:
        s.hook("SessionStart", {"source": "startup"})
        f = ws / "tests" / "t.robot"
        inp = {"filePath": str(f), "content": PLANTED}
        out = s.wait_gate("create_file", inp)
        assert out == {}, out                                     # no warning, no rewrite
        assert "KeywordNotFound" in s.log()[-1].get("static_suppressed", [])
        f.write_text(PLANTED)                                     # the agent's tool writes the file
        post = s.hook("PostToolUse", {"tool_name": "create_file", "tool_input": inp, "tool_response": "ok"})
        text = post["hookSpecificOutput"]["additionalContext"]
        assert "L6 PASS" in text and "L7 FAIL" in text, text
        assert "No keyword with name 'Clik' found" in text and "STATIC" not in text, text
        deny = s.hook("PreToolUse", {"tool_name": "replace_string_in_file",
                                     "tool_input": {"filePath": str(f), "oldString": PLANTED, "newString": UNCLOSED}})
        h = deny["hookSpecificOutput"]
        assert h["permissionDecision"] == "deny" and "ModelError" in h["permissionDecisionReason"], h
    finally:
        s.end()
