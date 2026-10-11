"""``rf-harness doctor``: install / trust / probe / environment / live checks and the exit code (task 4.6)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from installer_helpers import IS_WINDOWS, Sandbox, make_venv, run_cli

from rf_harness import __version__
from rf_harness.installer import doctor

FAKE_HOOK = "import sys; sys.stdin.read(); print('{}')\n"

pytestmark = pytest.mark.skipif(IS_WINDOWS, reason="python3 symlink + venv layout")


def add_fake_runtime(python: Path) -> None:
    site = next(python.parent.parent.glob("lib/python*/site-packages"))
    pkg = site / "rf_harness" / "runtime"
    pkg.mkdir(parents=True)
    (site / "rf_harness" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "hook.py").write_text(FAKE_HOOK)
    (site / f"robotframework_harness-{__version__}.dist-info").mkdir()


def python3_on_path(sandbox: Sandbox) -> None:
    os.symlink(os.path.realpath(getattr(sys, "_base_executable", None) or sys.executable), sandbox.bin / "python3")


def use_suite_without_browser(sandbox: Sandbox) -> None:
    (sandbox.project / "tests" / "login.robot").write_text(
        "*** Settings ***\nLibrary    Collections\n\n*** Test Cases ***\nT\n    Log    hi\n", encoding="utf-8")


def test_doctor_fails_when_nothing_is_installed(sandbox: Sandbox, capsys):
    python3_on_path(sandbox)
    rc, out = run_cli(capsys, "doctor", "--no-live")
    assert rc == 1 and "not installed for any agent" in out and "fix: rf-harness install" in out


def test_doctor_fails_when_runtime_is_missing(sandbox: Sandbox, capsys):
    python3_on_path(sandbox)
    run_cli(capsys, "install", "--agent", "claude-code", "--mode", "files", "--no-runtime")
    rc, out = run_cli(capsys, "doctor")
    assert rc == 1
    assert "PASS  claude-code: installed" in out
    assert "FAIL  claude-code: probe event reaches the harness" in out
    assert "FAIL  harness runtime: not installed" in out
    assert "FAIL  live smoke" in out
    assert out.count("fix: uvx robotframework-harness install --runtime-only") >= 3


def test_doctor_fails_on_untrusted_codex_hooks_and_passes_after_trust(sandbox: Sandbox, capsys, monkeypatch):
    python3_on_path(sandbox)
    use_suite_without_browser(sandbox)
    fake_runtime = make_venv(sandbox.tmp / "fake-runtime")
    add_fake_runtime(fake_runtime)
    (sandbox.project / ".rf").mkdir()
    (sandbox.project / ".rf/harness.json").write_text(json.dumps({"python": str(fake_runtime)}), encoding="utf-8")

    # installed while codex was not on PATH -> no trust provisioned
    run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--scope", "user", "--no-runtime")
    from installer_helpers import HERE, write_script

    write_script(sandbox.bin / "codex", (HERE / "fake_codex.py").read_text(encoding="utf-8"))
    rc, out = run_cli(capsys, "doctor", "--agent", "codex", "--no-live", "--python", sys.executable)
    assert rc == 1, out
    assert "FAIL  codex: hooks trusted: 6 of 6 rf-harness hooks are not trusted" in out
    assert "/hooks" in out
    assert "PASS  codex: probe event reaches the harness" in out

    run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--scope", "user", "--no-runtime")
    rc, out = run_cli(capsys, "doctor", "--agent", "codex", "--no-live", "--python", sys.executable)
    assert "PASS  codex: hooks trusted: 6 rf-harness hooks trusted" in out
    assert "PASS  robot framework" in out and "PASS  robotcode" in out and "PASS  harness runtime" in out
    assert rc == 0, out


def test_doctor_reports_project_not_trusted_by_codex(sandbox: Sandbox, capsys, fake_codex):
    python3_on_path(sandbox)
    run_cli(capsys, "install", "--agent", "codex", "--mode", "files", "--no-runtime")
    rc, out = run_cli(capsys, "doctor", "--agent", "codex", "--no-live")
    assert rc == 1 and "Codex loads .codex/ only in trusted projects" in out and "accept the trust" in out
    config = sandbox.home / ".codex/config.toml"
    config.write_text(config.read_text() + f'\n[projects."{sandbox.project}"]\ntrust_level = "trusted"\n')
    rc, out = run_cli(capsys, "doctor", "--agent", "codex", "--no-live")
    assert "PASS  codex: hooks trusted" in out


def test_doctor_reports_missing_libraries(sandbox: Sandbox, capsys):
    python3_on_path(sandbox)
    run_cli(capsys, "install", "--agent", "opencode", "--no-runtime")
    rc, out = run_cli(capsys, "doctor", "--no-live", "--python", sys.executable)
    browser_line = [line for line in out.splitlines() if "library Browser" in line]
    assert browser_line, out
    if "FAIL" in browser_line[0]:
        assert "robotframework-browser" in out or "rfbrowser init chromium" in out


def test_doctor_unselected_agent(sandbox: Sandbox, capsys):
    python3_on_path(sandbox)
    rc, out = run_cli(capsys, "doctor", "--agent", "vscode", "--no-live")
    assert rc == 1 and "FAIL  vscode: installed: not installed" in out


def test_demo_page_is_bundled_identically():
    repo_page = Path(__file__).resolve().parents[2] / "demo" / "site" / "index.html"
    packaged = Path(doctor.__file__).resolve().parent / "demo_site" / "index.html"
    assert repo_page.read_bytes() == packaged.read_bytes()
    assert "<title>rf-harness demo</title>" in repo_page.read_text()


def test_smoke_suite_fallback_texts(tmp_path):
    page = tmp_path / "index.html"
    page.write_text("<h1>rf-harness demo</h1>")
    assert "New Page    file://" in doctor._smoke_suite(page, browser=True)
    assert "Get File" in doctor._smoke_suite(page, browser=False)
