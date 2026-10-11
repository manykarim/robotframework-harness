"""Fixtures for the hook launcher tests; helpers live in launch_helpers.py."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from launch_helpers import IS_WINDOWS


@pytest.fixture
def clean_env(tmp_path: Path) -> dict[str, str]:
    """Environment for launcher runs: isolated HOME and cache, no inherited venv / RFH settings, no python3 on PATH."""
    home = tmp_path / "home"
    home.mkdir()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("RFH_", "RF_HARNESS_", "VIRTUAL_ENV", "CONDA_", "UV_", "POETRY_", "PYTHON",
                                "COPILOT_", "CLAUDE", "CODEX_", "VSCODE_"))
           and k not in ("TERM_PROGRAM",)}
    env.update(HOME=str(home), USERPROFILE=str(home), PATH=str(empty_bin), RF_HARNESS_CACHE_DIR=str(tmp_path / "cache"),
               RF_HARNESS_DEDUPE_S="0", XDG_CACHE_HOME=str(tmp_path / "xdg-cache"))
    if IS_WINDOWS:
        env["PATH"] = str(empty_bin) + os.pathsep + os.environ.get("SystemRoot", r"C:\Windows")
    return env


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = \"demo\"\nversion = \"0.1\"\n", encoding="utf-8")
    (root / "tests" / "a.robot").write_text("*** Test Cases ***\nT\n    Log    hi\n", encoding="utf-8")
    return root
