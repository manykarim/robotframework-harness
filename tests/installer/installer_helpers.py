"""Helpers for the installer tests: sandbox type, fake agent CLIs, CLI runner, snapshots, minimal venvs."""

from __future__ import annotations

import os
import stat
import sys
import sysconfig
import venv
from dataclasses import dataclass
from pathlib import Path

import pytest

from rf_harness.installer.cli import main

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
IS_WINDOWS = os.name == "nt"
AGENT_ENV = ("CODEX_HOME", "COPILOT_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "VIRTUAL_ENV",
             "CONDA_PREFIX", "UV_PROJECT_ENVIRONMENT", "POETRY_VIRTUALENVS_PATH", "POETRY_CACHE_DIR",
             "RF_HARNESS_MARKETPLACE_DIR", "RF_HARNESS_ASSETS_DIR", "RFH_PYTHON", "CLAUDECODE", "COPILOT_CLI",
             "PYTHONPATH", "UV", "UV_TOOL_DIR")


@dataclass
class Sandbox:
    tmp: Path
    home: Path
    bin: Path
    project: Path


def write_script(path: Path, body: str) -> Path:
    """An executable Python script runnable by name (plus a .cmd wrapper on Windows)."""
    path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if IS_WINDOWS:
        path.with_suffix(".cmd").write_text(f'@"{sys.executable}" "{path}" %*\r\n', encoding="utf-8")
    return path


def fake_agent(sandbox: Sandbox, name: str, version: str = "1.0.0") -> None:
    write_script(sandbox.bin / name, f"print('{name} {version}')\n")


def run_cli(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    rc = main(list(args))
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


def snapshot(*roots: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and "cache" not in path.relative_to(root).parts[:1]:
                files[str(path)] = path.read_bytes()
    return files


def make_venv(prefix: Path) -> Path:
    """Minimal venv (symlinked interpreter + pyvenv.cfg); a real one on Windows."""
    if IS_WINDOWS:
        venv.EnvBuilder(with_pip=False, symlinks=False).create(prefix)
        return prefix / "Scripts" / "python.exe"
    (prefix / "bin").mkdir(parents=True, exist_ok=True)
    real = os.path.realpath(getattr(sys, "_base_executable", None) or sys.executable)
    python = prefix / "bin" / "python"
    python.symlink_to(real)
    (prefix / "pyvenv.cfg").write_text(f"home = {os.path.dirname(real)}\ninclude-system-site-packages = false\n"
                                       f"version = {sysconfig.get_python_version()}\n", encoding="utf-8")
    (prefix / "lib" / f"python{sysconfig.get_python_version()}" / "site-packages").mkdir(parents=True)
    return python
