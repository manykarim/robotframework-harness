"""Hand-off to the runtime: argv, stdin passed through unchanged, env switches, exit codes, dedupe, overhead."""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
import sys
import time

import pytest
from launch_helpers import IS_WINDOWS, LAUNCHER, make_venv, output_json, run_launcher


@pytest.mark.parametrize("size", [10, 20_000, 300_000])
def test_stdin_passes_through_unchanged(project, clean_env, size):
    make_venv(project / ".venv")
    payload = json.dumps({"cwd": str(project), "tool_input": {"content": "x" * size}}).encode()
    proc = run_launcher(["PostToolUse", "--agent", "claude"], payload, clean_env, project)
    data = output_json(proc)
    assert data["stdin_len"] == len(payload)
    assert data["stdin_sha"] == hashlib.sha256(payload).hexdigest()


def test_argv_and_env_switches(project, clean_env):
    make_venv(project / ".venv")
    (project / ".rf").mkdir()
    (project / ".rf" / "harness.json").write_text(json.dumps({"env": {"RFH_STATIC": "runtime-only",
                                                                       "RFH_PROFILE": "rich", "PATH": "x"}}),
                                                  encoding="utf-8")
    proc = run_launcher(["PreToolUse", "--agent", "codex", "--set", "RFH_LOOP_AT=5", "--future-flag"],
                        {"cwd": str(project)}, {**clean_env, "RFH_PROFILE": "lean"}, project)
    data = output_json(proc)
    assert data["argv"] == ["PreToolUse", "--agent", "codex", "--future-flag"]
    assert data["env"]["RFH_STATIC"] == "runtime-only"     # from harness.json
    assert data["env"]["RFH_PROFILE"] == "lean"            # the environment wins over harness.json
    assert data["env"]["RFH_LOOP_AT"] == "5"               # --set
    assert "RFH_PYTHON" not in data["env"]


@pytest.mark.parametrize(("code", "expected"), [(0, 0), (2, 2)])
def test_runtime_exit_code_is_forwarded(project, clean_env, code, expected):
    make_venv(project / ".venv")
    proc = run_launcher(["PreToolUse", "--agent", "claude"], {"cwd": str(project), "exit": code}, clean_env, project)
    assert proc.returncode == expected


def test_duplicate_delivery_runs_once(project, clean_env):
    make_venv(project / ".venv")
    env = {**clean_env, "RF_HARNESS_DEDUPE_S": "30"}
    payload = {"cwd": str(project), "tool_use_id": "t-1"}
    first = run_launcher(["PostToolUse", "--agent", "claude"], payload, env, project)
    second = run_launcher(["postToolUse", "--agent", "claude"], payload, env, project)
    other = run_launcher(["PostToolUse", "--agent", "claude"], {**payload, "tool_use_id": "t-2"}, env, project)
    assert output_json(first)["fake_runtime"]
    assert second.stdout == b"" and second.returncode == 0
    assert output_json(other)["fake_runtime"]


def _median_ms(cmd: list[str], data: bytes, env: dict[str, str], cwd, runs: int = 20) -> float:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        proc = subprocess.run(cmd, input=data, capture_output=True, env=env, cwd=str(cwd))
        samples.append((time.perf_counter() - start) * 1000)
        assert proc.returncode == 0, proc.stderr
    return statistics.median(samples)


def test_launcher_overhead_below_50ms(project, clean_env, capsys):
    """Median over 20 runs: launcher + fake runtime minus the fake runtime started directly."""
    python = make_venv(project / ".venv")
    data = json.dumps({"cwd": str(project), "hook_event_name": "PostToolUse"}).encode()
    args = ["PostToolUse", "--agent", "claude"]
    for _ in range(2):   # warm the OS caches
        run_launcher(args, data, clean_env, project)
    direct = _median_ms([str(python), "-m", "rf_harness.runtime.hook", *args], data, clean_env, project)
    launched = _median_ms([sys.executable, "-S", str(LAUNCHER), *args], data, clean_env, project)
    hint_only = _median_ms([sys.executable, "-S", str(LAUNCHER), *args], data,
                           {**clean_env, "RFH_PYTHON": str(project / "missing")}, project)
    overhead = launched - direct
    with capsys.disabled():
        print(f"\n[launcher overhead] direct runtime {direct:.1f} ms, via launcher {launched:.1f} ms, "
              f"overhead {overhead:.1f} ms, launcher alone (no runtime) {hint_only:.1f} ms")
    limit = 150 if IS_WINDOWS or os.environ.get("CI_SLOW") else 50
    assert overhead < limit
    assert hint_only < limit
