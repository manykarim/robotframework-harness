"""Interpreter probing and candidate exclusion (change fix-windows-python-detection, tasks 1.1/1.2)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from installer_helpers import IS_WINDOWS, Sandbox, make_venv, write_script

from rf_harness.installer import envfind

STORE_MESSAGE = ("Python was not found; run without arguments to install from the Microsoft Store, or disable this "
                 "shortcut from Settings > Apps > Advanced app settings > App execution aliases.")
PLACEHOLDER = f"import sys\nsys.stderr.write({STORE_MESSAGE!r} + '\\n')\nsys.exit(9009)\n"
SILENT_PLACEHOLDER = "import sys\nsys.exit(9009)\n"
TOO_OLD = "print('3.9.18')\nprint('/usr/bin/python3.9')\n"
CRASHING = ("import sys\nsys.stderr.write('Fatal Python error: init_fs_encoding: failed to get the Python codec\\n')\n"
            "sys.exit(1)\n")
GARBAGE = "print('hello')\n"
SLOW = "import time\ntime.sleep(3)\n"   # Windows: the .cmd wrapper's child keeps the pipes open


def fake_python(path: Path, body: str) -> Path:
    """A fake interpreter; on Windows the runnable file is the .cmd wrapper."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_script(path, body)
    return path.with_suffix(".cmd") if IS_WINDOWS else path


def env_on_path(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch, prefix: Path) -> Path:
    """A venv at ``prefix`` whose interpreter is the first ``python3`` (``python`` on Windows) on PATH."""
    python = make_venv(prefix)
    if not IS_WINDOWS:
        (python.parent / "python3").symlink_to(python.name)
    monkeypatch.setenv("PATH", str(python.parent) + os.pathsep + os.environ["PATH"])
    return python


# ------------------------------------------------------------------------------------------------ probe (1.1)
def test_probe_real_interpreter():
    result = envfind.probe(sys.executable)
    assert result.usable and result.status == "usable"
    assert result.version == ".".join(map(str, sys.version_info[:3]))
    assert result.executable


@pytest.mark.parametrize("body", [PLACEHOLDER, SILENT_PLACEHOLDER], ids=["message", "exit-9009"])
def test_probe_store_placeholder(tmp_path: Path, body: str):
    result = envfind.probe(fake_python(tmp_path / "python3", body))
    assert result.status == "store-placeholder" and not result.usable
    assert result.reason() == envfind.STORE_PLACEHOLDER


def test_probe_too_old(tmp_path: Path):
    result = envfind.probe(fake_python(tmp_path / "python3", TOO_OLD))
    assert (result.status, result.version) == ("too-old", "3.9.18")
    assert result.reason() == "Python 3.9.18 is too old (the harness needs 3.10 or newer)"


def test_probe_broken(tmp_path: Path):
    result = envfind.probe(fake_python(tmp_path / "python3", CRASHING))
    assert result.status == "broken"
    assert result.reason() == "does not run (exit 1: Fatal Python error: init_fs_encoding: failed to get the Python codec)"
    assert envfind.probe(fake_python(tmp_path / "garbage", GARBAGE)).detail == "unexpected output: hello"
    missing = envfind.probe(tmp_path / "nowhere" / "python3")
    assert missing.status == "broken" and missing.detail


def test_probe_timeout(tmp_path: Path):
    result = envfind.probe(fake_python(tmp_path / "python3", SLOW), timeout=0.5)
    assert result.status == "broken" and result.detail == "no answer within 0.5 s"


class _Stat:
    def __init__(self, tag: int) -> None:
        self.st_reparse_tag = tag


@pytest.mark.parametrize(("folder", "tag", "expected"), [
    ("WindowsApps", envfind.APPEXECLINK, True),
    ("windowsapps", envfind.APPEXECLINK, True),
    ("Scripts", envfind.APPEXECLINK, False),
    ("WindowsApps", 0, False),
])
def test_app_alias_detection_by_reparse_tag(monkeypatch, folder, tag, expected):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os, "lstat", lambda _p: _Stat(tag))
    assert envfind.is_app_alias(f"/Users/me/AppData/Local/Microsoft/{folder}/python3.exe") is expected


def test_failing_app_alias_is_a_placeholder(monkeypatch):
    """A WindowsApps alias that fails without the known exit code or message still counts as the placeholder."""
    def run(*_a, **_k):
        raise OSError(1920, "The file cannot be accessed by the system")

    monkeypatch.setattr(envfind.subprocess, "run", run)
    monkeypatch.setattr(envfind, "is_app_alias", lambda _p: True)
    assert envfind.probe("python3.exe").status == "store-placeholder"
    monkeypatch.setattr(envfind, "is_app_alias", lambda _p: False)
    assert envfind.probe("python3.exe").status == "broken"


def test_explain_failure(tmp_path: Path):
    assert envfind.explain_failure(fake_python(tmp_path / "python3", PLACEHOLDER)) == envfind.STORE_PLACEHOLDER
    assert "package report failed" in envfind.explain_failure(Path(sys.executable))


# ------------------------------------------------------------------------------------------------ find_env (1.2)
def test_placeholder_first_on_path_is_skipped(sandbox: Sandbox):
    fake_python(sandbox.bin / "python3", PLACEHOLDER)
    choice = envfind.find_env(sandbox.project)
    assert choice.python is None and choice.source == "none" and choice.placeholder_skipped
    skip = choice.skipped[0]
    assert (skip.label, skip.status, skip.reason) == ("python3 on PATH", "store-placeholder", envfind.STORE_PLACEHOLDER)
    assert "python3" in skip.python.name
    lines = envfind.skipped_lines(choice)
    assert lines[0].startswith("  skipped  python3 on PATH") and lines[1].endswith(envfind.STORE_PLACEHOLDER)


def test_project_venv_wins_over_placeholder(sandbox: Sandbox):
    fake_python(sandbox.bin / "python3", PLACEHOLDER)
    venv_py = make_venv(sandbox.project / ".venv")
    choice = envfind.find_env(sandbox.project)
    assert (choice.python, choice.source, choice.skipped) == (venv_py, ".venv", [])


@pytest.mark.skipif(IS_WINDOWS, reason="fake interpreter inside a venv layout (bin/python)")
def test_unusable_candidate_falls_through_to_the_next_source(sandbox: Sandbox, monkeypatch):
    active = sandbox.tmp / "active"
    fake_python(active / "bin" / "python", CRASHING)
    monkeypatch.setenv("VIRTUAL_ENV", str(active))
    old = sandbox.tmp / "old"
    fake_python(old / "bin" / "python", TOO_OLD)
    monkeypatch.setenv("CONDA_PREFIX", str(old))
    venv_py = make_venv(sandbox.project / ".venv")
    choice = envfind.find_env(sandbox.project)
    assert (choice.python, choice.source) == (venv_py, ".venv")
    assert [(s.label, s.status) for s in choice.skipped] == [("VIRTUAL_ENV", "broken"), ("CONDA_PREFIX", "too-old")]


def test_uvx_environment_on_path_is_excluded(sandbox: Sandbox, monkeypatch):
    """uvx runs the installer from uv's cache (archive-v0) and puts that environment first on PATH."""
    uvx_env = sandbox.tmp / "uv-cache" / "archive-v0" / "Xk3Pq9"
    env_on_path(sandbox, monkeypatch, uvx_env)
    monkeypatch.setattr(sys, "prefix", str(uvx_env))
    choice = envfind.find_env(sandbox.project)
    assert choice.python is None
    assert [(s.status, s.reason) for s in choice.skipped][0] == ("excluded", "the installer's own (uvx) environment")
    monkeypatch.setattr(sys, "prefix", str(sandbox.tmp / "elsewhere"))
    assert envfind.find_env(sandbox.project).skipped[0].reason == "inside uv's cache (a throwaway environment)"


def test_installer_prefix_on_path_is_excluded(sandbox: Sandbox, monkeypatch):
    """pipx and similar: the installer's own environment, wherever it lives."""
    own = sandbox.tmp / "pipx" / "venvs" / "robotframework-harness"
    env_on_path(sandbox, monkeypatch, own)
    monkeypatch.setattr(sys, "prefix", str(own))
    assert envfind.find_env(sandbox.project).skipped[0].reason == "the installer's own environment"


@pytest.mark.parametrize("var", ["UV_TOOL_DIR", "UV_CACHE_DIR"])
def test_uv_tool_and_cache_dirs_are_excluded(sandbox: Sandbox, monkeypatch, var):
    root = sandbox.tmp / var.lower()
    monkeypatch.setenv(var, str(root))
    env_on_path(sandbox, monkeypatch, root / "robotframework-harness")
    reason = envfind.find_env(sandbox.project).skipped[0].reason
    assert reason == ("a uv tool environment" if var == "UV_TOOL_DIR" else "inside uv's cache (a throwaway environment)")


def test_project_venv_running_the_installer_is_kept(sandbox: Sandbox, monkeypatch):
    """The harness installed into the project's own .venv: that environment is the project environment."""
    venv_py = make_venv(sandbox.project / ".venv")
    monkeypatch.setattr(sys, "prefix", str(sandbox.project / ".venv"))
    choice = envfind.find_env(sandbox.project)
    assert (choice.python, choice.source) == (venv_py, ".venv")


def test_explicit_python_is_probed_but_never_excluded(sandbox: Sandbox, monkeypatch):
    uvx_env = sandbox.tmp / "uv-cache" / "archive-v0" / "Xk3Pq9"
    uvx_py = make_venv(uvx_env)
    monkeypatch.setattr(sys, "prefix", str(uvx_env))
    assert envfind.find_env(sandbox.project, str(uvx_py)).python == uvx_py
    placeholder = fake_python(sandbox.tmp / "WindowsApps" / "python3", PLACEHOLDER)
    choice = envfind.find_env(sandbox.project, str(placeholder))
    assert choice.python is None and choice.source == "--python" and choice.placeholder_skipped
    assert choice.detail == f"--python {placeholder} is {envfind.STORE_PLACEHOLDER}"
    empty = sandbox.tmp / "empty-env"
    empty.mkdir()
    assert envfind.find_env(sandbox.project, str(empty)).detail.endswith("no Python interpreter in this directory")
