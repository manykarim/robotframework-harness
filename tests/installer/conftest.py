"""Fixtures for the installer tests: temporary HOME and project, restricted PATH, a fake codex CLI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from installer_helpers import AGENT_ENV, HERE, IS_WINDOWS, Sandbox, write_script

from rf_harness.installer import cli


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    project = tmp_path / "proj"
    for d in (home, bin_dir, project / "tests"):
        d.mkdir(parents=True)
    (project / "tests" / "login.robot").write_text(
        "*** Settings ***\nLibrary    Browser    timeout=5s\nLibrary    Collections\n\n*** Test Cases ***\nLogin\n"
        "    New Page    https://example.com\n", encoding="utf-8")
    for var in AGENT_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PATH", str(bin_dir) + (os.pathsep + os.environ.get("SystemRoot", "") if IS_WINDOWS else ""))
    monkeypatch.setenv("RF_HARNESS_CACHE_DIR", str(tmp_path / "cache"))
    # The plugin/files logic is tested on every OS; the Windows default mode has its own tests (test_installer_modes).
    monkeypatch.setattr(cli, "_is_windows", lambda: False)
    monkeypatch.chdir(project)
    return Sandbox(tmp_path, home, bin_dir, project)


@pytest.fixture
def fake_codex(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch) -> Path:
    log = sandbox.tmp / "codex-calls.jsonl"
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    source = (HERE / "fake_codex.py").read_text(encoding="utf-8")
    write_script(sandbox.bin / "codex", source)
    return log
