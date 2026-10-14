"""uv recovery, discovery messages and doctor wording (change fix-windows-python-detection, tasks 2.1-2.3)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from installer_helpers import Sandbox, make_venv, run_cli, write_script
from test_installer_probe import CRASHING, PLACEHOLDER, env_on_path, fake_python

from rf_harness import __version__
from rf_harness.installer import envfind, prompt

READY = {"python": "3.12", "sys_path": ["/x/site-packages"], "imports": {"robot": True, "robotcode": True,
         "rf_harness.runtime": True, "rf_harness.runtime.hook": True},
         "versions": {"robotframework": "7.5", "robotcode": "2.7.0", "robotframework-harness": __version__}}
EMPTY = {"python": "3.12", "sys_path": [], "imports": {}, "versions": {}}
UV_ERROR = ("error: Failed to create virtual environment\n  Caused by: failed to query the Python interpreter: "
            "untrusted mount point (os error 448)")
FAKE_UV = f'''
import json, os, sys, venv
with open(os.environ["FAKE_UV_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
mode = os.environ.get("FAKE_UV_MODE", "ok")
if mode == "fail":
    sys.stderr.write({UV_ERROR!r} + "\\n")
    sys.exit(2)
if sys.argv[1:2] == ["venv"] and mode == "ok":
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(sys.argv[-1])
sys.stderr.write("Using CPython 3.12.10\\nCreating virtual environment at: " + sys.argv[-1] + "\\n")
'''


@pytest.fixture
def fake_inspect(monkeypatch):
    state = {"info": EMPTY, "installs": []}

    def inspect(python, modules=None, timeout=60.0):
        return state["info"]

    def run_install(python, version=__version__, source=None):
        state["installs"].append((python, version, source))
        state["info"] = READY
        return True, "ok"

    monkeypatch.setattr(envfind, "inspect", inspect)
    monkeypatch.setattr(envfind, "run_install", run_install)
    return state


@pytest.fixture
def fake_uv(sandbox: Sandbox, monkeypatch) -> Path:
    log = sandbox.tmp / "uv-calls.jsonl"
    monkeypatch.setenv("FAKE_UV_LOG", str(log))
    write_script(sandbox.bin / "uv", FAKE_UV)
    return log


def uv_calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def placeholder_on_path(sandbox: Sandbox) -> Path:
    return fake_python(sandbox.bin / "python3", PLACEHOLDER)


# ------------------------------------------------------------------------------------------------ recovery (2.1)
def test_yes_creates_the_project_environment_with_uv(sandbox: Sandbox, capsys, fake_inspect, fake_uv):
    placeholder_on_path(sandbox)
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 0, out
    venv_dir = sandbox.project / ".venv"
    venv_py = envfind.venv_python(venv_dir)
    assert venv_py is not None and envfind.probe(venv_py).usable
    assert uv_calls(fake_uv) == [["venv", "--python", "3.12", str(venv_dir)]]
    assert fake_inspect["installs"] == [(venv_py, __version__, None)]
    harness = json.loads((sandbox.project / ".rf/harness.json").read_text())
    assert harness["python"] == str(venv_py) and harness["source"] == ".venv"
    assert f"Python environment: none usable in {sandbox.project}" in out
    assert "skipped  python3 on PATH" in out and envfind.STORE_PLACEHOLDER in out
    assert f"Creating the project environment: uv venv --python 3.12 {venv_dir}" in out
    assert "did not start" not in out


def test_venv_python_selects_the_version(sandbox: Sandbox, capsys, fake_inspect, fake_uv):
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes", "--venv-python", "3.11")
    assert rc == 0, out
    assert "Python environment: none found in" in out
    assert uv_calls(fake_uv) == [["venv", "--python", "3.11", str(sandbox.project / ".venv")]]


def test_uv_from_the_uv_variable_wins(sandbox: Sandbox, capsys, fake_inspect, fake_uv, monkeypatch):
    """uvx sets UV to its own binary; it is used even when PATH has none (or another) uv."""
    other = sandbox.tmp / "uvx-bin"
    other.mkdir()
    real = write_script(other / "uv", FAKE_UV)
    (sandbox.bin / "uv").unlink()
    if (sandbox.bin / "uv.cmd").exists():
        (sandbox.bin / "uv.cmd").unlink()
    runnable = real.with_suffix(".cmd") if os.name == "nt" else real
    monkeypatch.setenv("UV", str(runnable))
    assert envfind.uv_binary() == str(runnable)
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 0, out
    assert f"{runnable} venv --python 3.12" in out          # not on PATH: shown with its full path


def test_no_input_prints_the_command_and_exits_1(sandbox: Sandbox, capsys, fake_inspect, fake_uv):
    placeholder_on_path(sandbox)
    rc, out = run_cli(capsys, "install", "--runtime-only", "--no-input")
    assert rc == 1
    assert f"let uv create the project environment: uv venv --python 3.12 {sandbox.project / '.venv'}" in out
    assert "--python <path>" in out and envfind.ALIAS_TIP in out and "rerun with --yes" in out
    assert uv_calls(fake_uv) == [] and fake_inspect["installs"] == []
    assert not (sandbox.project / ".venv").exists() and not (sandbox.project / ".rf").exists()


def test_failing_uv_reports_its_error_and_installs_nothing(sandbox: Sandbox, capsys, fake_inspect, fake_uv,
                                                           monkeypatch):
    placeholder_on_path(sandbox)
    monkeypatch.setenv("FAKE_UV_MODE", "fail")
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 1
    assert "untrusted mount point (os error 448)" in out and "pass --python <path>" in out
    assert fake_inspect["installs"] == [] and not (sandbox.project / ".rf").exists()


def test_uv_success_without_an_interpreter_is_an_error(sandbox: Sandbox, capsys, fake_inspect, fake_uv, monkeypatch):
    monkeypatch.setenv("FAKE_UV_MODE", "empty")
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 1 and "created no interpreter" in out and fake_inspect["installs"] == []


@pytest.mark.parametrize("answer", [True, False])
def test_interactive_prompt(sandbox: Sandbox, capsys, fake_inspect, fake_uv, monkeypatch, answer):
    questions: list[str] = []
    monkeypatch.setattr(prompt, "is_tty", lambda: True)

    def confirm(question, default=True, input_fn=None):
        questions.append(question)
        return answer

    monkeypatch.setattr(prompt, "confirm", confirm)
    rc, out = run_cli(capsys, "install", "--runtime-only")
    assert rc == 0, out
    assert questions[0] == f"Create a project environment with uv?  uv venv --python 3.12 {sandbox.project / '.venv'}"
    if answer:
        assert (sandbox.project / ".venv").is_dir() and len(questions) == 2      # then the runtime-install question
    else:
        assert "Runtime not installed: no project environment" in out and uv_calls(fake_uv) == []


def test_dry_run_creates_nothing(sandbox: Sandbox, capsys, fake_inspect, fake_uv):
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes", "--dry-run")
    assert rc == 0 and f"[dry-run] would run: uv venv --python 3.12 {sandbox.project / '.venv'}" in out
    assert uv_calls(fake_uv) == [] and not (sandbox.project / ".venv").exists()


def test_existing_unusable_venv_is_not_replaced(sandbox: Sandbox, capsys, fake_inspect, fake_uv):
    (sandbox.project / ".venv" / "lib").mkdir(parents=True)
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 1 and "exists but is not usable" in out
    assert uv_calls(fake_uv) == [] and (sandbox.project / ".venv" / "lib").is_dir()


def test_uvx_environment_is_never_the_target(sandbox: Sandbox, capsys, fake_inspect, fake_uv, monkeypatch):
    uvx_env = sandbox.tmp / "uv-cache" / "archive-v0" / "Xk3Pq9"
    uvx_py = env_on_path(sandbox, monkeypatch, uvx_env)
    monkeypatch.setattr(sys, "prefix", str(uvx_env))
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 0, out
    assert "the installer's own (uvx) environment" in out
    assert fake_inspect["installs"][0][0] == envfind.venv_python(sandbox.project / ".venv") != uvx_py


@pytest.mark.skipif(os.name == "nt", reason="fake interpreter inside a venv layout (bin/python)")
def test_skipped_candidates_are_reported_when_a_later_one_is_used(sandbox: Sandbox, capsys, fake_inspect, monkeypatch):
    active = sandbox.tmp / "active"
    fake_python(active / "bin" / "python", CRASHING)
    monkeypatch.setenv("VIRTUAL_ENV", str(active))
    venv_py = make_venv(sandbox.project / ".venv")
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 0, out
    lines = out.splitlines()
    assert lines[0] == f"  skipped  VIRTUAL_ENV      {active / 'bin' / 'python'}"
    assert lines[1].startswith("           -> does not run (exit 1: Fatal Python error")
    assert lines[2] == f"Python environment: {venv_py} (project virtual environment)"


# ------------------------------------------------------------------------------------------------ messages (2.2)
def test_no_uv_and_only_the_placeholder(sandbox: Sandbox, capsys, fake_inspect):
    placeholder = placeholder_on_path(sandbox)
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 1
    assert f"skipped  python3 on PATH  {placeholder}".lower() in out.lower()     # Windows: which() gives python3.CMD
    assert f"-> {envfind.STORE_PLACEHOLDER}" in out
    assert "no usable Python environment and uv is not available" in out
    assert f"install uv ({envfind.UV_INSTALL_URL}) and rerun" in out
    assert "--python <path>" in out and envfind.ALIAS_TIP in out
    assert "did not start" not in out and fake_inspect["installs"] == []


def test_explicit_placeholder_is_explained(sandbox: Sandbox, capsys, fake_inspect):
    placeholder = fake_python(sandbox.tmp / "WindowsApps" / "python3", PLACEHOLDER)
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes", "--python", str(placeholder))
    assert rc == 1
    assert f"error: --python {placeholder} is {envfind.STORE_PLACEHOLDER}. Fixes:" in out
    assert envfind.ALIAS_TIP in out and "did not start" not in out


def test_package_report_failure_is_explained(sandbox: Sandbox, capsys, monkeypatch):
    make_venv(sandbox.project / ".venv")
    monkeypatch.setattr(envfind, "inspect", lambda *_a, **_k: None)
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 1 and "its package report failed" in out and "did not start" not in out


# ------------------------------------------------------------------------------------------------ doctor (2.3)
def test_doctor_reports_the_placeholder(sandbox: Sandbox, capsys):
    placeholder = placeholder_on_path(sandbox)
    run_cli(capsys, "doctor", "--no-live")
    rc, out = run_cli(capsys, "doctor", "--no-live")
    assert rc == 1
    line = next(x for x in out.splitlines() if "python environment" in x)
    assert line.startswith("FAIL  python environment: no usable Python environment (python3 on PATH")
    assert f"{placeholder} is {envfind.STORE_PLACEHOLDER}".lower() in line.lower()
    fix = out.splitlines()[out.splitlines().index(line) + 1]
    assert "offers to create the project environment with uv" in fix and envfind.ALIAS_TIP in fix
    assert "did not start" not in out


def test_doctor_reports_a_recorded_placeholder(sandbox: Sandbox, capsys):
    placeholder = placeholder_on_path(sandbox)
    envfind.write_harness_json(sandbox.project, {"python": str(placeholder)})
    rc, out = run_cli(capsys, "doctor", "--no-live")
    assert rc == 1
    assert f"FAIL  python environment: {placeholder} (.rf/harness.json) is {envfind.STORE_PLACEHOLDER}" in out
    assert envfind.ALIAS_TIP in out and "did not start" not in out
