"""REPL / debugger command rewrite rules (rf_harness.runtime.replfmt), the cases of simulation scenario G."""

from __future__ import annotations

from pathlib import Path

import pytest

from rf_harness.runtime import replfmt

RC = "robotcode"


def _rw(cmd: str, agent: str = "claude", tmp: Path = Path("."), listener=None):
    return replfmt.rewrite(cmd, agent, tmp, None, tmp, listener=listener)


def test_find_ignores_plain_commands():
    assert replfmt.find("robot -d results tests/x.robot") is None
    assert replfmt.find("ls robotcode") is None
    inv = replfmt.find(f"cd tests && {RC} repl <<'RF'\nLog    x\nRF")
    assert inv is not None and inv.sub == "repl" and inv.heredoc["quoted"] and inv.heredoc["closed"]


def test_interactive_repl_is_refused_for_agents_that_cannot_type(tmp_path):
    new, fixes, deny, warns, _ = _rw(f"{RC} repl", "claude", tmp_path)
    assert deny and "INTERACTIVE" in deny and "<<'RF'" in deny and new is None


def test_interactive_repl_is_allowed_with_a_warning_for_codex(tmp_path):
    new, fixes, deny, warns, _ = _rw(f"{RC} repl", "codex", tmp_path)
    assert deny is None and warns and "--plain" in new


def test_unquoted_heredoc_with_only_rf_variables_gets_quoted(tmp_path):
    new, fixes, deny, _, _ = _rw(f"{RC} repl <<RF\n${{x}}=    Set Variable    5\nLog    ${{x}}\nRF", tmp=tmp_path)
    assert deny is None and "<<'RF'" in new and "quoted the heredoc delimiter" in fixes
    assert new.rstrip().endswith(".exit\nRF")
    for flag in ("--plain", "--no-history", "-d .rf/out", "2>&1"):
        assert flag in new


def test_unquoted_heredoc_with_shell_variables_is_refused(tmp_path):
    _, _, deny, _, _ = _rw(f"{RC} repl <<RF\n${{x}}=    Set Variable    $HOME\nRF", tmp=tmp_path)
    assert deny and "unquoted heredoc" in deny


def test_body_autofixes(tmp_path):
    new, fixes, deny, _, _ = _rw(f"{RC} repl <<'RF'\nLog To Console single\n${{x}}=    Set Variable    1\n"
                                 f"${{d}}=    Create Dictionary    a=1\n...    b=2\n${{x}}\nRF", tmp=tmp_path)
    assert deny is None
    assert "Log To Console    single" in new
    assert "a=1    b=2" in new
    assert "Log To Console    ${x}" in new
    assert any("single-space" in f for f in fixes)


def test_unclosed_block_is_refused(tmp_path):
    _, _, deny, _, _ = _rw(f"{RC} repl <<'RF'\nFOR    ${{i}}    IN RANGE    2\n    Log    ${{i}}\nRF", tmp=tmp_path)
    assert deny and "END" in deny


def test_robot_debug_strips_break_quotes_and_appends_nothing(tmp_path):
    new, fixes, deny, _, _ = _rw(f"{RC} robot-debug tests/dbg.robot <<'RF'\n.where\n.break \"tests/dbg.robot:3\"\n"
                                 ".continue\nRF", tmp=tmp_path)
    assert deny is None and ".break tests/dbg.robot:3" in new and ".exit" not in new


def test_browser_repl_gets_the_repl_only_listener_by_file_path(tmp_path):
    new, fixes, _, _, _ = _rw(f"{RC} repl <<'RF'\nImport Library    Browser\nNew Page    about:blank\nRF", tmp=tmp_path,
                              listener="2.5s:2s")
    assert new.startswith("ROBOT_OPTIONS='--listener ")
    assert f"{replfmt.LISTENER}:2.5s:2s'" in new
    assert replfmt.LISTENER.name == "rfh_repl_listener.py" and replfmt.LISTENER.is_file()
    assert "Set Browser Timeout" not in new


@pytest.mark.parametrize(("text", "kind"), [
    ("[ FAIL ] No keyword with name 'Clik' found.", "unknown"),
    ("  * exception Browser.Click (tests/x.robot:7) \u2014 TimeoutError: nope", "exception"),
])
def test_parse_output(text, kind):
    res = replfmt.parse_output(text)
    if kind == "unknown":
        assert res["fails"] and res["fails"][0]["unknown"] == "Clik"
    else:
        assert res["exceptions"] and res["exceptions"][0]["kw"] == "Click"


def test_imports_in_body():
    assert replfmt.imports_in(["Import Library    Browser", "Library    String", "Log    x",
                               "Import Resource    ${CURDIR}/a.resource"]) == [
        ("library", "Browser"), ("library", "String"), ("resource", "${CURDIR}/a.resource")]
