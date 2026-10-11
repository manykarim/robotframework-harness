"""The ported harness end to end, offline: a stub `claude` binary, the file-only `results_complex` scenario, no
network, no real agent. Covers the cell pipeline (isolation, transcript archive, validity scan, exit codes, secret
scrubbing), the hook-arm availability checks and the contamination rules."""

from __future__ import annotations

import gzip
import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from eval_helpers import EVAL, posix_only

pytestmark = posix_only

FAKE_KEY = "sk-ant-api03-" + "Q" * 40          # not a real key; must never reach results or transcripts

STUB = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, sys
    mode = os.environ.get("STUB_MODE", "ok")
    def out(d):
        print(json.dumps(d), flush=True)
    out({"type": "system", "subtype": "init", "model": "stub-model", "mcp_servers": [], "skills": []})
    if mode == "ok":
        os.makedirs("reports", exist_ok=True)
        open("reports/summary.md", "w").write(
            "- Total tests: 8\\n- Passed: 4\\n- Failed: 3\\n- Skipped: 1\\n- Failed suites: Checkout, Regression\\n")
        out({"type": "assistant", "message": {"model": "stub-model", "content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": "reports/summary.md"}},
            {"type": "text", "text": "debug: key=" + os.environ.get("ANTHROPIC_API_KEY", "")}]}})
        sys.stderr.write("stub stderr key=" + os.environ.get("ANTHROPIC_API_KEY", "") + "\\n")
        out({"type": "result", "subtype": "success", "num_turns": 2, "total_cost_usd": 0.01, "result": "done",
             "usage": {"input_tokens": 10, "output_tokens": 5}})
    elif mode == "credits":
        msg = "API Error: 402 This request requires more credits, or fewer max_tokens."
        out({"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": msg}]}})
        out({"type": "result", "subtype": "success", "is_error": True, "api_error_status": 402, "result": msg})
    elif mode == "auth":
        msg = "Failed to authenticate. API Error: 401 invalid x-api-key"
        out({"type": "result", "subtype": "success", "is_error": True, "api_error_status": 401, "result": msg})
''')


def _stub_env(tmp_path: Path, mode: str) -> dict:
    sbin = tmp_path / "stubbin"
    sbin.mkdir(exist_ok=True)
    claude = sbin / "claude"
    claude.write_text(STUB)
    claude.chmod(claude.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "vbin").mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AB_", "CLAUDE", "ANTHROPIC", "OPENROUTER"))}
    env.update({"PATH": f"{sbin}{os.pathsep}{env.get('PATH', '')}", "STUB_MODE": mode, "ANTHROPIC_API_KEY": FAKE_KEY,
                "AB_OUT_DIR": str(tmp_path / "out"), "AB_WORK_BASE": str(tmp_path / "work"),
                "AB_VENV_BIN": str(tmp_path / "vbin"), "AB_MIN_FREE_GB": "0.01", "AB_CLAUDE_AUTH": "api-key"})
    return env


def _run(tmp_path: Path, mode: str):
    p = subprocess.run([sys.executable, str(EVAL / "harness.py"), "run", "--scenarios", "results_complex",
                        "--agents", "claude", "--arms", "neither", "--reps", "1", "--tag", mode, "--concurrency", "1"],
                       env=_stub_env(tmp_path, mode), capture_output=True, text=True, timeout=300)
    res = tmp_path / "out" / f"results_rc_{mode}.jsonl"
    rows = [json.loads(ln) for ln in res.read_text().splitlines()] if res.exists() else []
    return p, rows


def test_ok_cell_is_graded_archived_and_scrubbed(tmp_path):
    p, rows = _run(tmp_path, "ok")
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "ok" and r["primary_pass"] is True and r["n_pass"] == r["n_checks"] == 7
    assert r["harness_version"] == "rfh-eval-1" and r["contaminated"] is False
    tx = tmp_path / "out" / r["transcript"]
    assert tx.is_file()
    text = gzip.open(tx, "rt").read()
    assert "reports/summary.md" in text
    # the key was in the agent's stdout and stderr: it must be gone from every artifact
    blob = (tmp_path / "out").rglob("*")
    for f in blob:
        if f.is_file():
            data = gzip.open(f, "rt").read() if f.suffix == ".gz" else f.read_text(errors="replace")
            assert FAKE_KEY not in data, f
            assert FAKE_KEY[:12] not in data, f
    assert "<redacted-secret>" in text
    scan = subprocess.run([sys.executable, str(EVAL / "secret_scan.py"), str(tmp_path / "out")],
                          env={**os.environ, "ANTHROPIC_API_KEY": FAKE_KEY}, capture_output=True, text=True)
    assert scan.returncode == 0, scan.stdout
    assert not list((tmp_path / "work").rglob("agent_home"))          # cells are pruned


def test_credit_failure_is_invalid_not_graded_and_not_done(tmp_path):
    p, rows = _run(tmp_path, "credits")
    assert p.returncode == 0                                  # subscription-style agent: no OpenRouter guard involved
    r = rows[0]
    assert r["status"] == "invalid" and r["invalid_kind"] == "credits"
    assert r["verdicts"] == [] and r["primary_pass"] is False
    assert "INVALID=provider error" in p.stdout
    # the next pass reruns it: completed_keys() only counts ok rows
    p2, rows2 = _run(tmp_path, "credits")
    assert len(rows2) == 2


def test_auth_failure_exits_2(tmp_path):
    p, rows = _run(tmp_path, "auth")
    assert p.returncode == 2, p.stdout[-1500:]
    assert rows[0]["status"] == "invalid" and rows[0]["invalid_kind"] == "auth"


def test_unknown_or_unavailable_arm_exits_6(tmp_path):
    env = _stub_env(tmp_path, "ok")
    for arms in ("hookpkg3", "prototype-v32"):
        e = dict(env, AB_PROTOTYPE_DIR=str(tmp_path / "no-prototype"))
        p = subprocess.run([sys.executable, str(EVAL / "harness.py"), "run", "--scenarios", "results_complex",
                            "--agents", "claude", "--arms", arms, "--reps", "1", "--tag", "x"],
                           env=e, capture_output=True, text=True, timeout=120)
        assert p.returncode == 6, (arms, p.stdout[-800:])


# --------------------------------------------------------------------------- hook arms: availability + adapter
def _fake_installer(tmp_path: Path, supports_install: bool, extra_json: dict | None = None) -> str:
    script = tmp_path / "fake_installer.py"
    script.write_text(textwrap.dedent(f'''\
        import json, os, sys
        args = sys.argv[1:]
        if not {supports_install!r} or not args or args[0] != "install":
            print("rf-harness: error: argument command: invalid choice: 'install' (choose from version)",
                  file=sys.stderr)
            sys.exit(2)
        if "--help" in args:
            print("usage: rf-harness install --agents A --mode M --scope S --project P --yes --runtime-source R --json")
            sys.exit(0)
        rec = {{"argv": args, "CODEX_HOME": os.environ.get("CODEX_HOME"), "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV"),
               "has_key": "ANTHROPIC_API_KEY" in os.environ or "OPENROUTER_API_KEY" in os.environ}}
        open(os.environ["FAKE_INSTALL_LOG"], "a").write(json.dumps(rec) + "\\n")
        print(json.dumps({json.dumps(extra_json or {})}))
    '''))
    return f"{sys.executable} {script}"


def test_rf_harness_unavailable_while_installer_lacks_install(tmp_path, monkeypatch):
    import harness as H

    monkeypatch.setenv("AB_RF_HARNESS_INSTALLER", _fake_installer(tmp_path, False))
    ok, reason, _ = H.rf_harness_available()
    assert not ok and "not available yet" in reason
    st = H.arm_status(["rf-harness"])
    assert st["rf-harness"]["available"] is False
    inst = H.load_hook_install("rf-harness")
    assert getattr(inst, "unavailable", None)
    with pytest.raises(NotImplementedError):
        inst("claude", tmp_path, tmp_path, tmp_path)


def test_real_installer_state_is_reported(tmp_path):
    """Whatever state the parallel installer work is in, check-arms answers with a reason (never crashes)."""
    import harness as H

    st = H.arm_status(["rf-harness", "neither"])
    assert isinstance(st["rf-harness"]["available"], bool) and st["rf-harness"]["reason"]
    assert st["neither"]["available"] is True


def test_install_rf_harness_adapter_runs_the_documented_command(tmp_path, monkeypatch):
    import harness as H

    log = tmp_path / "install.jsonl"
    monkeypatch.setenv("FAKE_INSTALL_LOG", str(log))
    monkeypatch.setenv("AB_RF_HARNESS_INSTALLER", _fake_installer(tmp_path, True, {"extra_env": {"RFH_X": "1"},
                                                                                  "extra_args": ["--flag"]}))
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("AB_RF_HARNESS_ARGS_CODEX", "--dangerously-bypass-hook-trust")
    ws, home, vbin = tmp_path / "ws", tmp_path / "home", tmp_path / "venv" / "bin"
    for d in (ws, home, vbin):
        d.mkdir(parents=True)
    inst = H.load_hook_install("rf-harness")
    assert not getattr(inst, "unavailable", None)
    res = inst("codex", ws, home, vbin)
    assert set(res) >= {"extra_args", "extra_env", "notes"}
    assert res["extra_args"] == ["--dangerously-bypass-hook-trust", "--flag"]
    assert res["extra_env"]["RFH_X"] == "1" and res["extra_env"]["PATH"].startswith(str(vbin))
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["argv"][:12] == ["install", "--agents", "codex", "--mode", "files", "--scope", "project", "--project",
                                str(ws), "--yes", "--runtime-source", str(H.RF_HARNESS_SOURCE)]
    assert "--json" in rec["argv"]
    assert rec["CODEX_HOME"] == str(home) and rec["VIRTUAL_ENV"] == str(vbin.parent)
    assert rec["has_key"] is False                            # the installer never sees API keys


def test_adapter_command_is_accepted_by_the_real_installer(tmp_path):
    """The exact per-cell command, with the installer's own --dry-run: accepted for every agent, nothing written."""
    venv_bin = Path(sys.executable).parent   # the default grading venv only exists on the research machine
    import harness as H

    ok, reason, help_text = H.rf_harness_available()
    if not ok:
        pytest.skip(f"rf-harness installer not ready: {reason}")
    ws, home = tmp_path / "ws", tmp_path / "home"
    ws.mkdir()
    home.mkdir()
    for agent in ("claude", "codex", "opencode", "copilot"):
        cmd = H.rf_harness_install_cmd(agent, ws, venv_bin, help_text) + ["--dry-run"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(ws),
                           env=H._installer_env(agent, home, venv_bin))
        assert p.returncode == 0, (agent, (p.stdout + p.stderr)[-800:])
        assert str(ws) in p.stdout                       # it plans writes into the cell workspace
    assert not [f for f in tmp_path.rglob("*") if f.is_file()]


def test_prototype_arm_availability(tmp_path):
    import harness as H

    stub = H.load_prototype_install(tmp_path / "missing")
    assert "no install.py" in stub.unavailable
    d = tmp_path / "proto"
    d.mkdir()
    (d / "install.py").write_text("def install(agent, workspace, agent_home, venv_bin):\n"
                                  "    return {'extra_args': [], 'extra_env': {}, 'notes': 'stub'}\n")
    fn = H.load_prototype_install(d)
    assert not getattr(fn, "unavailable", None) and fn("claude", d, d, d)["notes"] == "stub"


# --------------------------------------------------------------------------- contamination rules
def _calls(*inputs):
    return [{"tool": "Bash", "kind": "shell", "input": s} for s in inputs]


def test_own_arm_artifacts_and_cell_paths_are_not_contamination(tmp_path):
    import harness as H

    ws = tmp_path / "work_live_gate" / "claude" / "tricentis_quote-rf-harness-rep1-abc123" / "workspace"
    (ws / ".rf").mkdir(parents=True)
    (ws / ".rf" / "harness.json").write_text("{}")
    calls = _calls(f"cd {ws} && robot tests/auto_quote.robot", "python3 -m rf_harness.runtime.hook post-tool")
    c = H.contamination("rf-harness", calls, ws, 0)
    assert c["contaminated"] is False
    ws2 = tmp_path / "claude" / "x-prototype-v32-rep1-ab" / "workspace"
    ws2.mkdir(parents=True)
    assert H.contamination("prototype-v32", _calls(f"cat {ws2}/.rf/state/latest/page.txt", "rfharness32"), ws2,
                           0)["contaminated"] is False


def test_foreign_tools_are_contamination(tmp_path):
    import harness as H

    ws = tmp_path / "ws"
    ws.mkdir()
    assert H.contamination("mcp", _calls("python3 -m rf_harness.runtime.hook post-tool"), ws, 3)["contaminated"]
    assert H.contamination("neither", [], ws, 2)["contaminated"]                     # MCP calls outside mcp
    assert H.contamination("rf-harness", _calls("python rfharness32/hook.py"), ws, 0)["hook_cross_hits"] == 1
    assert H.contamination("prototype-v32", _calls("rfh-launch post-tool"), ws, 0)["contaminated"]
    assert H.contamination("rf-harness", _calls("rfmcp step 'Click  id=x'"), ws, 0)["helper_cli_calls"] == 1
    (ws / ".rf" / "hook3").mkdir(parents=True)                                        # a historical v3 install
    assert H.contamination("neither", [], ws, 0)["hook_usage_hits"] == 1
    assert H.contamination("rf-harness", [], ws, 0)["hook_cross_hits"] == 1
