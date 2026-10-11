"""quickstart_check.py --dry-run, the secret scan, and the eval.yml workflow (task 5.4: dry run, no secret in artifacts)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

import pytest
import secret_scan as SS
from eval_helpers import EVAL, ROOT

WORKFLOW = ROOT / ".github" / "workflows" / "eval.yml"
FAKE_OR_KEY = "sk-" + "or-v1-" + "0123456789abcdef" * 4
FAKE_ANTHROPIC = "sk-" + "ant-api03-" + "Z" * 40


@pytest.mark.parametrize("agent", ["claude", "codex", "copilot", "vscode", "opencode"])
def test_quickstart_dry_run_prints_the_plan_only(agent):
    before = set(os.listdir(tempfile.gettempdir()))
    p = subprocess.run([sys.executable, str(EVAL / "quickstart_check.py"), "--agent", agent, "--dry-run"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    plan = json.loads(p.stdout)
    assert plan["dry_run"] is True and plan["agent"] == agent
    assert [s["name"] for s in plan["steps"]] == ["project", "browsers", "install", "doctor", "robot"]
    assert plan["documented_commands"] <= plan["max_commands"] == 5
    install = next(s["cmd"] for s in plan["steps"] if s["name"] == "install")
    assert f"install --agents {agent} --mode files --scope project" in install
    assert "--yes" in install and f"--runtime-source {ROOT}" in install
    assert "doctor" in next(s["cmd"] for s in plan["steps"] if s["name"] == "doctor")
    assert "robot" in next(s["cmd"] for s in plan["steps"] if s["name"] == "robot")
    created = {d for d in set(os.listdir(tempfile.gettempdir())) - before if d.startswith("rfh-quickstart")}
    assert not created


def test_quickstart_dry_run_with_agent_session():
    p = subprocess.run([sys.executable, str(EVAL / "quickstart_check.py"), "--agent", "claude", "--dry-run",
                        "--with-agent"], capture_output=True, text=True, timeout=60)
    plan = json.loads(p.stdout)
    session = plan["steps"][-1]
    assert session["name"] == "session" and session["documented"] is False and session["cmd"].startswith("claude -p")
    p2 = subprocess.run([sys.executable, str(EVAL / "quickstart_check.py"), "--agent", "vscode", "--dry-run",
                         "--with-agent"], capture_output=True, text=True, timeout=60)
    assert "no headless session" in json.loads(p2.stdout)["steps"][-1]["note"]


# --------------------------------------------------------------------------- secret scan
def test_secret_scan_finds_a_planted_key_without_printing_it(tmp_path, monkeypatch, capsys):
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "row.jsonl").write_text(json.dumps({"stderr_tail": f"auth {FAKE_OR_KEY}"}) + "\n")
    import gzip
    with gzip.open(tmp_path / "t" / "tx.jsonl.gz", "wt") as g:
        g.write("x-api-key: " + FAKE_ANTHROPIC[:12] + "...\n")          # a truncated key is still a leak
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OR_KEY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    assert SS.main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert FAKE_OR_KEY not in out and FAKE_ANTHROPIC[:12] not in out
    assert "env:OPENROUTER_API_KEY" in out and "openrouter-key" in out
    assert "env:ANTHROPIC_API_KEY (prefix)" in out and "tx.jsonl.gz:1" in out


def test_secret_scan_clean_dir_passes(tmp_path, monkeypatch):
    (tmp_path / "report.md").write_text("model qwen/qwen3.8-flash, <redacted-openrouter-key>, cost $0.05\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OR_KEY)
    assert SS.main([str(tmp_path)]) == 0


def test_workflow_dry_run_outputs_contain_no_secret(tmp_path):
    """Local replay of the workflow's dry-run path with (fake) secrets in the environment: arm check, quick-start
    plans and the config summary are written to the artifact dir, then the scrub step must find nothing."""
    out = tmp_path / "runs"
    out.mkdir()
    env = dict(os.environ, OPENROUTER_API_KEY=FAKE_OR_KEY, ANTHROPIC_API_KEY=FAKE_ANTHROPIC, AB_OUT_DIR=str(out),
               ARMS="prototype-v32,rf-harness", AGENTS="cc-or:qwen3.8-flash", TAG="ghlocal")
    arms = subprocess.run([sys.executable, str(EVAL / "harness.py"), "check-arms", "--arms", env["ARMS"]], env=env,
                          capture_output=True, text=True, timeout=120)
    (out / "arms_ghlocal.json").write_text(arms.stdout)
    for a in ("claude", "codex", "opencode", "copilot", "vscode"):
        p = subprocess.run([sys.executable, str(EVAL / "quickstart_check.py"), "--agent", a, "--dry-run"], env=env,
                           capture_output=True, text=True, timeout=60)
        (out / f"quickstart_plan_{a}.json").write_text(p.stdout)
    steps = _workflow()["jobs"]["eval"]["steps"]
    dry = next(s["run"] for s in steps if s.get("name", "").startswith("Dry run"))
    py = dry.split("<<'EOF'\n", 1)[1].split("\nEOF", 1)[0]
    subprocess.run([sys.executable, "-c", py], env=env, check=True, capture_output=True, timeout=60)
    cfg = json.loads((out / "config_ghlocal.json").read_text())
    assert cfg["secrets_present"] == {"OPENROUTER_API_KEY": True, "ANTHROPIC_API_KEY": True}
    scan = subprocess.run([sys.executable, str(EVAL / "secret_scan.py"), str(out)], env=env, capture_output=True,
                          text=True, timeout=60)
    assert scan.returncode == 0, scan.stdout
    assert "0 finding(s)" in scan.stdout
    scrub = ROOT / "evidence" / "scrub.py"
    if scrub.exists():                       # the workflow's main path: scrubbed copy, then --check must be clean
        dst = tmp_path / "eval-upload"
        subprocess.run([sys.executable, str(scrub), "--apply", str(out), str(dst)], env=env, check=True,
                       capture_output=True, timeout=120)
        chk = subprocess.run([sys.executable, str(scrub), "--check", str(dst)], env=env, capture_output=True,
                             text=True, timeout=120)
        assert chk.returncode == 0, chk.stdout + chk.stderr
        assert sorted(p.name for p in dst.rglob("*.json")) == sorted(p.name for p in out.rglob("*.json"))
        assert subprocess.run([sys.executable, str(EVAL / "secret_scan.py"), str(dst)], env=env,
                              capture_output=True, timeout=60).returncode == 0


# --------------------------------------------------------------------------- workflow structure
def _workflow():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(WORKFLOW.read_text())


def test_workflow_is_manual_only_with_the_required_inputs():
    wf = _workflow()
    on = wf.get(True) or wf.get("on")                       # PyYAML reads `on:` as True
    assert set(on) == {"workflow_dispatch"}                  # never on push / pull_request
    inputs = on["workflow_dispatch"]["inputs"]
    assert {"arms", "agents", "reps", "scenarios"} <= set(inputs)
    text = WORKFLOW.read_text()
    assert re.search(r"^\s*#\s*schedule:", text, re.M) and re.search(r"^\s*#\s*-\s*cron:", text, re.M)
    assert "pull_request" not in text.split("on:", 1)[1].split("permissions:", 1)[0]


def test_workflow_secrets_are_env_only_and_never_echoed():
    text = WORKFLOW.read_text()
    refs = re.findall(r"\$\{\{\s*secrets\.(\w+)\s*\}\}", text)
    assert set(refs) == {"OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"}
    for line in text.splitlines():
        if "secrets." in line:
            assert re.match(r"^\s+[A-Z_]+: \$\{\{ secrets\.\w+ \}\}\s*$", line), line   # env mapping only
    assert not re.search(r"(echo|printf|cat)[^\n]*(OPENROUTER_API_KEY|ANTHROPIC_API_KEY)", text)
    assert "set -x" not in text
    for s in _workflow()["jobs"]["eval"]["steps"]:      # user inputs never interpolated into shell code
        assert "${{ inputs." not in (s.get("run") or "")


def test_workflow_scrubs_before_upload():
    steps = _workflow()["jobs"]["eval"]["steps"]
    names = [s.get("name") or s.get("uses") for s in steps]
    scrub = next(i for i, s in enumerate(steps) if s.get("name", "").startswith("Secret scrub"))
    upload = next(i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/upload-artifact"))
    assert scrub < upload, names
    run = steps[scrub]["run"]
    assert "if [ -f evidence/scrub.py ]" in run
    assert 'python evidence/scrub.py --apply "$AB_OUT_DIR" "$RUNNER_TEMP/eval-upload"' in run
    assert 'python evidence/scrub.py --check "$RUNNER_TEMP/eval-upload"' in run
    assert 'python3 eval/secret_scan.py "$upload"' in run
    assert "steps.scrub.outcome == 'success'" in steps[upload]["if"]
    assert steps[upload]["with"]["path"] == "${{ steps.scrub.outputs.dir }}"     # only the scrubbed copy
