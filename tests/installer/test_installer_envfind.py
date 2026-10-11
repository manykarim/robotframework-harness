"""Project environment discovery and consented runtime provisioning (task 4.3)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from installer_helpers import IS_WINDOWS, REPO, Sandbox, make_venv, run_cli, write_script

from rf_harness import __version__
from rf_harness.installer import envfind

REAL_UV = shutil.which("uv")
REAL_UV_CACHE = os.environ.get("UV_CACHE_DIR") or (subprocess.run([REAL_UV, "cache", "dir"], capture_output=True,
                                                                  text=True).stdout.strip() if REAL_UV else "")
READY = {"python": "3.12", "sys_path": ["/x/site-packages"], "imports": {"robot": True, "robotcode": True,
         "rf_harness.runtime": True, "rf_harness.runtime.hook": True},
         "versions": {"robotframework": "7.5", "robotcode": "2.7.0", "robotframework-harness": __version__}}
EMPTY = {"python": "3.12", "sys_path": [], "imports": {}, "versions": {}}

pytestmark = pytest.mark.skipif(IS_WINDOWS, reason="symlinked venv layout")


# ------------------------------------------------------------------------------------------------ discovery
def test_find_env_order(sandbox: Sandbox, monkeypatch):
    path_py = sandbox.bin / "python3"
    os.symlink(sys.executable, path_py)
    assert envfind.find_env(sandbox.project).source == "PATH"

    envs = sandbox.tmp / "poetry-envs"
    (sandbox.project / "pyproject.toml").write_text('[tool.poetry]\nname = "rf-demo"\n', encoding="utf-8")
    monkeypatch.setenv("POETRY_VIRTUALENVS_PATH", str(envs))
    assert envfind._poetry_env_computed(sandbox.project, "") is None     # no project name -> no poetry env
    sys.path.insert(0, str(REPO / "plugins" / "rf-harness" / "bin"))
    sys.dont_write_bytecode = True
    import rfh_launch

    poetry_py = make_venv(envs / (rfh_launch.poetry_env_name("rf-demo", str(sandbox.project)) + "-py3.12"))
    choice = envfind.find_env(sandbox.project)
    assert (choice.source, choice.python) == ("poetry", poetry_py)

    uv_py = make_venv(sandbox.project / "uvenv")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "uvenv")
    assert envfind.find_env(sandbox.project).python == uv_py

    venv_py = make_venv(sandbox.project / ".venv")
    assert envfind.find_env(sandbox.project).python == venv_py

    active_py = make_venv(sandbox.tmp / "active")
    monkeypatch.setenv("VIRTUAL_ENV", str(sandbox.tmp / "active"))
    assert envfind.find_env(sandbox.project).python == active_py

    explicit_py = make_venv(sandbox.tmp / "explicit")
    assert envfind.find_env(sandbox.project, str(sandbox.tmp / "explicit")).python == explicit_py
    assert envfind.find_env(sandbox.project, str(explicit_py)).python == explicit_py


def test_scan_libraries(sandbox: Sandbox):
    (sandbox.project / "tests" / "api.robot").write_text(
        "*** Settings ***\nLibrary    RequestsLibrary\nLibrary    ../lib/custom.py\nLibrary    String\n"
        "Library    SeleniumLibrary    timeout=5s    AS    Sel\nResource    common.resource\n\n"
        "*** Test Cases ***\nT\n    Import Library    NotScanned\n", encoding="utf-8")
    (sandbox.project / "tests" / "common.resource").write_text(
        "*** Settings ***\nLibrary\tJSONLibrary\n", encoding="utf-8")
    (sandbox.project / ".venv").mkdir()
    (sandbox.project / ".venv" / "x.robot").write_text("*** Settings ***\nLibrary    Ignored\n", encoding="utf-8")
    libs = envfind.scan_libraries(sandbox.project)
    assert sorted(libs) == ["Browser", "JSONLibrary", "RequestsLibrary", "SeleniumLibrary"]
    assert libs["Browser"] == [str(Path("tests") / "login.robot")]


def test_library_report(sandbox: Sandbox, monkeypatch):
    python = Path("/env/bin/python")
    info = {"imports": {"Browser": True, "RequestsLibrary": False}, "sys_path": []}
    monkeypatch.setattr(envfind, "browser_binaries_present", lambda _info: False)
    report = {r.name: r for r in envfind.library_report(python, {"Browser": ["a.robot"],
                                                                  "RequestsLibrary": ["b.robot"]}, info)}
    assert not report["RequestsLibrary"].importable
    assert report["RequestsLibrary"].fix.endswith("-m pip install robotframework-requests")
    assert report["Browser"].importable and report["Browser"].fix == "rfbrowser init chromium"
    write_script(Path(os.environ["PATH"].split(os.pathsep)[0]) / "uv", "print('uv')\n")
    report = envfind.library_report(python, {"RequestsLibrary": ["b.robot"]}, info)
    assert report[0].fix == f"uv pip install --python {python} robotframework-requests"


def test_install_command(sandbox: Sandbox):
    python = Path("/env/bin/python")
    assert envfind.install_command(python) == [str(python), "-m", "pip", "install",
                                               f"robotframework-harness[runtime]=={__version__}"]
    write_script(sandbox.bin / "uv", "print('uv')\n")
    cmd = envfind.install_command(python, source=str(REPO))
    assert cmd[1:5] == ["pip", "install", "--python", str(python)] and cmd[-1] == f"{REPO}[runtime]"


# ------------------------------------------------------------------------------------------------ provisioning
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


def test_runtime_needs_consent(sandbox: Sandbox, capsys, fake_inspect):
    venv_py = make_venv(sandbox.project / ".venv")
    rc, out = run_cli(capsys, "install", "--runtime-only", "--no-input")
    assert rc == 0 and "Runtime not installed; run:" in out and fake_inspect["installs"] == []
    assert not (sandbox.project / ".rf").exists()
    assert str(venv_py) in out


def test_runtime_installed_with_yes(sandbox: Sandbox, capsys, fake_inspect):
    venv_py = make_venv(sandbox.project / ".venv")
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 0, out
    assert fake_inspect["installs"] == [(venv_py, __version__, None)]
    harness = json.loads((sandbox.project / ".rf/harness.json").read_text())
    assert harness["python"] == str(venv_py) and harness["version"] == __version__ and harness["source"] == ".venv"
    assert harness["site_packages"] == ["/x/site-packages"]
    assert ".rf/" in (sandbox.project / ".gitignore").read_text()
    assert "MISSING library Browser" in out


@pytest.mark.parametrize("layout", ["uv", "poetry"])
def test_runtime_lands_in_managed_environment(sandbox: Sandbox, capsys, fake_inspect, monkeypatch, layout):
    if layout == "uv":
        target = make_venv(sandbox.project / "custom-env")
        monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "custom-env")
    else:
        sys.path.insert(0, str(REPO / "plugins" / "rf-harness" / "bin"))
        sys.dont_write_bytecode = True
        import rfh_launch

        (sandbox.project / "pyproject.toml").write_text('[tool.poetry]\nname = "suite"\n', encoding="utf-8")
        envs = sandbox.tmp / "pp"
        monkeypatch.setenv("POETRY_VIRTUALENVS_PATH", str(envs))
        target = make_venv(envs / (rfh_launch.poetry_env_name("suite", str(sandbox.project)) + "-py3.13"))
    rc, _ = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 0 and fake_inspect["installs"][0][0] == target


def test_runtime_already_present_is_not_reinstalled(sandbox: Sandbox, capsys, fake_inspect):
    make_venv(sandbox.project / ".venv")
    fake_inspect["info"] = READY
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes")
    assert rc == 0 and fake_inspect["installs"] == [] and "recorded in" in out


def test_runtime_dry_run(sandbox: Sandbox, capsys, fake_inspect):
    make_venv(sandbox.project / ".venv")
    rc, out = run_cli(capsys, "install", "--runtime-only", "--yes", "--dry-run")
    assert rc == 0 and "[dry-run] would run:" in out and fake_inspect["installs"] == []
    assert not (sandbox.project / ".rf").exists()


def test_user_scope_outside_a_project_skips_the_runtime(sandbox: Sandbox, capsys, fake_inspect):
    bare = sandbox.tmp / "bare"
    bare.mkdir()
    rc, out = run_cli(capsys, "install", "--agent", "claude-code", "--scope", "user", "--project", str(bare))
    assert rc == 0 and "Runtime: not provisioned (no project here)" in out


@pytest.mark.slow
@pytest.mark.skipif(REAL_UV is None, reason="needs uv")
def test_real_runtime_install_changes_no_other_package(sandbox: Sandbox, capsys, monkeypatch):
    """uv venv + robotframework + robotcode from the local uv cache, then the runtime from this checkout."""
    assert REAL_UV is not None
    os.symlink(REAL_UV, sandbox.bin / "uv")
    monkeypatch.setenv("UV_OFFLINE", "1")
    monkeypatch.setenv("UV_CACHE_DIR", REAL_UV_CACHE)
    env = dict(os.environ)
    venv_dir = sandbox.project / ".venv"
    subprocess.run([REAL_UV, "venv", "-q", str(venv_dir), "--python", sys.executable], check=True, env=env)
    python = venv_dir / "bin" / "python"
    pre = subprocess.run([REAL_UV, "pip", "install", "-q", "--python", str(python), "robotframework>=7",
                          "robotcode[repl,runner,analyze]>=2.7,<2.8"], capture_output=True, text=True, env=env)
    if pre.returncode != 0:
        pytest.skip(f"offline uv cache lacks the runtime dependencies: {pre.stderr[-200:]}")

    def freeze() -> set[str]:
        out = subprocess.run([REAL_UV, "pip", "freeze", "--python", str(python)], capture_output=True, text=True,
                             env=env, check=True).stdout
        return {line.strip() for line in out.splitlines() if line.strip()}

    before = freeze()
    rc, out = run_cli(capsys, "install", "--runtime-only", "--runtime-source", str(REPO), "--yes")
    assert rc == 0, out
    added = freeze() - before
    assert len(added) == 1 and next(iter(added)).startswith("robotframework-harness")
    assert before <= freeze()
    harness = json.loads((sandbox.project / ".rf/harness.json").read_text())
    assert harness["python"] == str(python) and harness["version"] == __version__


@pytest.mark.parametrize("agent", ["claude-code", "codex", "copilot-cli", "vscode", "opencode"])
def test_eval_harness_command_line(sandbox: Sandbox, capsys, fake_inspect, agent):
    """The A/B eval harness's exact invocation (eval/): keep it working."""
    ws = sandbox.tmp / "ws"
    (ws / "tests").mkdir(parents=True)
    venv_py = make_venv(sandbox.tmp / "cellvenv")
    rc, out = run_cli(capsys, "install", "--agents", agent, "--mode", "files", "--scope", "project", "--project",
                      str(ws), "--yes", "--runtime-source", str(REPO), "--python", str(venv_py), "--no-input")
    assert rc == 0, out
    assert fake_inspect["installs"] == [(venv_py, __version__, str(REPO))]
    harness = json.loads((ws / ".rf/harness.json").read_text())
    assert harness["python"] == str(venv_py) and harness["source"] == "--python"
    assert (ws / ".rf-harness/manifest.json").is_file()
    assert any(p.name == "rfh-launch" for p in ws.rglob("rfh-launch"))
