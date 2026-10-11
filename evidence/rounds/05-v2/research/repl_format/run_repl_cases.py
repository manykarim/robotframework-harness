#!/usr/bin/env python3
"""Round 5: verify robotcode repl --plain / robot-debug --plain input-format rules live.

Each case feeds bytes on stdin (pipe, non-TTY) and records stdout, stderr,
exit code and wall time. Results -> logs/repl_cases.jsonl (+ one .log per case).
Usage: python3 run_repl_cases.py [case-id-prefix ...]
"""
import json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE / "lab"
LOGS = HERE / "logs"
LOGS.mkdir(exist_ok=True)
RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
OUT = str(LAB / "out")

REPL = [RC, "repl", "--plain", "--no-history", "-d", OUT]
DBG = [RC, "robot-debug", "--plain", "--no-history", "-d", OUT]

CASES = [
    # --- separators ---
    ("R01_sep4", REPL, "Log To Console    four-spaces\n"),
    ("R02_sep2", REPL, "Log To Console  two-spaces\n"),
    ("R03_sep1", REPL, "Log To Console single-space\n"),
    ("R04_tab", REPL, "Log To Console\ttab-sep\n"),
    ("R05_assign_eq", REPL, "${x}=    Set Variable    5\nLog To Console    x=${x}\n"),
    ("R06_assign_noeq", REPL, "${x}    Set Variable    6\nLog To Console    x=${x}\n"),
    ("R06b_assign_sep1", REPL, "${x} = Set Variable 7\nLog To Console    x=${x}\n"),
    # --- continuation ---
    ("R07_continuation", REPL, "${d}    Create Dictionary    a=1\n...    b=2\nLog To Console    d=${d}\n"),
    ("R08_continuation_kwonly", REPL, "Log To Console\n...    continued-arg\n"),
    ("R08b_one_line", REPL, "${d}    Create Dictionary    a=1    b=2\nLog To Console    d=${d}\n"),
    # --- blocks ---
    ("R09_for_noblank", REPL, "FOR    ${i}    IN RANGE    3\n    Log To Console    i=${i}\nEND\nLog To Console    after\n"),
    ("R10_for_blank_inside", REPL, "FOR    ${i}    IN RANGE    3\n\n    Log To Console    i=${i}\nEND\nLog To Console    after\n"),
    ("R11_if_else", REPL, "${v}=    Set Variable    2\nIF    ${v} == 1\n    Log To Console    one\nELSE IF    ${v} == 2\n    Log To Console    two\nELSE\n    Log To Console    other\nEND\n"),
    ("R11b_inline_if", REPL, "${v}=    Set Variable    2\nIF    ${v} == 2    Log To Console    inline-two\n"),
    ("R12_try", REPL, "TRY\n    Fail    boom\nEXCEPT    boom\n    Log To Console    caught\nFINALLY\n    Log To Console    finally\nEND\n"),
    ("R13_while", REPL, "${n}=    Set Variable    ${0}\nWHILE    ${n} < 3    limit=10\n    ${n}=    Evaluate    ${n} + 1\nEND\nLog To Console    n=${n}\n"),
    ("R14_var", REPL, "VAR    ${who}    world\nVAR    @{lst}    a    b\nLog To Console    ${who} ${lst}\n"),
    ("R14b_group", REPL, "GROUP    g1\n    Log To Console    in-group\nEND\n"),
    ("R15_stray_end", REPL, "END\nLog To Console    next1\nLog To Console    next2\n\nLog To Console    after-blank\n"),
    ("R15b_bad_for", REPL, "FOR ${i} IN RANGE 3\n    Log To Console    i=${i}\nEND\nLog To Console    after\n"),
    ("R15c_unclosed_for_eof", REPL, "FOR    ${i}    IN RANGE    3\n    Log To Console    i=${i}\n"),
    ("R15d_nested", REPL, "FOR    ${i}    IN RANGE    2\n    IF    ${i} == 1\n        Log To Console    nested-${i}\n    END\nEND\n"),
    # --- failures / streams ---
    ("R16_fail_stream", REPL, "Log To Console    before\nShould Be Equal    1    2\nLog To Console    after-fail\n"),
    ("R16b_unknown_kw", REPL, "Clik Element    id=x\nLog To Console    after\n"),
    ("R16c_argcount", REPL, "Should Be Equal    1\n"),
    ("R16d_unknown_lib", REPL, "Library    NoSuchLibraryXyz\nLog To Console    after\n"),
    # --- termination ---
    ("R17_no_exit_eof", REPL, "Log To Console    eof-end\n"),
    ("R18_exit_middle", REPL, "Log To Console    one\n.exit\nLog To Console    never\n"),
    ("R18b_blank_fresh", REPL, "\n\nLog To Console    after-blanks\n"),
    # --- dot commands ---
    ("R19_kw_exact", REPL, ".kw Log To Console\n"),
    ("R19b_kw_case", REPL, ".kw log to console\n"),
    ("R19c_kw_search", REPL, ".kw console\n"),
    ("R19d_kw_qualified", REPL, ".kw BuiltIn.Log To Console\n"),
    ("R19e_kw_quoted", REPL, '.kw "Log To Console"\n'),
    ("R19f_kw_typo", REPL, ".kw Log To Consol\n"),
    ("R20_doc_lib", REPL, ".doc Collections\n"),
    ("R20b_doc_kw", REPL, ".doc Log To Console\n"),
    ("R20c_doc_resource", REPL, "Import Resource    ${CURDIR}/res/a.resource\n.doc a\n"),
    ("R21_imports", REPL, ".imports\n"),
    ("R21b_help", REPL, ".help\n"),
    ("R21c_unknown_dot", REPL, ".foo bar\n"),
    ("R21d_dot_indented", REPL, "    .imports\n"),
    ("R21e_vars", REPL, "${mine}=    Set Variable    1\n.vars --user\n"),
    ("R21f_dot_inside_block", REPL, "FOR    ${i}    IN RANGE    1\n.imports\nEND\n"),
    # --- agent mistakes ---
    ("R22_run_keyword_if", REPL, "Run Keyword If    ${True}    Log To Console    rki-ran\n"),
    ("R23_md_fence", REPL, "```robotframework\nLog To Console    inside-fence\n```\n"),
    ("R24_crlf", REPL, "Log To Console    crlf-line\r\n${x}=    Set Variable    abc\r\nShould Be Equal    ${x}    abc\r\nLog To Console    len=${{len($x)}}\r\n"),
    ("R25_pasted_test", REPL, "*** Test Cases ***\nMy Test\n    Log To Console    in-pasted-test\n"),
    ("R25b_settings_section", REPL, "*** Settings ***\nLibrary    Collections\n"),
    ("R25c_keywords_section", REPL, "*** Keywords ***\nMy Kw\n    Log To Console    mykw\n"),
    ("R26_indented", REPL, "    Log To Console    indented-4\n        Log To Console    indented-8\n"),
    ("R27_bare_var", REPL, "${x}=    Set Variable    1\n${x}\n"),
    ("R28_tags", REPL, "[Tags]    smoke\n[Documentation]    doc\nLog To Console    after-settings\n"),
    ("R29_comments", REPL, "# a comment\nLog To Console    with-trailing    # trailing comment\n"),
    ("R30_evaluate_dollar", REPL, "${x}=    Set Variable    ${41}\n${n}=    Evaluate    $x + 1\nLog To Console    n=${n}\n"),
    ("R31_log_vs_console", REPL, "Log    via-log\nLog    warn-msg    WARN\n"),
    ("R32_return_display", REPL, "Get Length    abcd\nSet Variable    hello\n"),
    ("R33_two_stmts_one_line", REPL, "Log To Console    a    Log To Console    b\n"),
    ("R34_curdir", REPL, "Log To Console    CURDIR=${CURDIR} EXECDIR=${EXECDIR} OUTDIR=${OUTPUT DIR}\n"),
    ("R35_resource_rel", REPL, "Import Resource    res/a.resource\nGreet    rel\n"),
    ("R35b_resource_setting", REPL, "Resource    ${CURDIR}/res/a.resource\n${r}=    Greet    abs\nLog To Console    r=${r}\n"),
    ("R36_unicode", REPL, "Log To Console    Grüße ✓\n"),
    ("R37_keyword_on_test_line_like", REPL, "Log To Console    x\\n    y\n"),
    ("R38_sleep_timing", REPL, "Sleep    0.2s\nLog To Console    slept\n"),
    ("R39_old_for", REPL, ":FOR    ${i}    IN RANGE    2\n\\    Log To Console    old-${i}\n"),
    ("R40_set_test_variable", REPL, "Set Test Variable    ${tv}    1\nSet Suite Variable    ${sv}    2\nLog To Console    ${tv} ${sv}\n"),
    ("R41_ignore_error", REPL, "${st}    ${msg}=    Run Keyword And Ignore Error    Fail    nope\nLog To Console    st=${st}\n"),
    ("R42_two_spaces_in_name", REPL, "Log  To  Console    x\n"),
    ("R43_trailing_spaces", REPL, "Log To Console    trail    \n"),
    ("R44_empty_arg", REPL, "Should Be Equal    ${EMPTY}    ${EMPTY}\nLog To Console    ok-empty\n"),
]

DEBUG_CASES = [
    # robot-debug: suite debug_target.robot (assertion 7 vs 6 fails)
    ("D01_default_pause_on_failure", DBG + [str(LAB / "debug_target.robot")], ".where\n${total}\n.pp ${total}\n.c\n"),
    ("D02_break_kw_noquotes", DBG + [str(LAB / "debug_target.robot")], ""),  # filled below with .break
    ("D03_break_kw_quotes", DBG + ["--stop-on-entry", str(LAB / "debug_target.robot")], '.break "Process Item"\n.c\n.c\n.c\n.c\n'),
    ("D04_break_cond_callsite", DBG + ["--stop-on-entry", str(LAB / "debug_target.robot")], ".break Process Item, ${i} == 2\n.c\n.vars\n.c\n.c\n"),
    ("D05_break_cond_kwarg", DBG + ["--stop-on-entry", str(LAB / "debug_target.robot")], ".break Process Item, ${item} == 2\n.c\n.c\n.c\n.c\n"),
    ("D06_step_next", DBG + ["--stop-on-entry", str(LAB / "debug_target.robot")], ".n\n.n\n.s\n.where\n.s\n.l\n.c\n.c\n"),
    ("D07_cli_break", DBG + ["--break", "Process Item", str(LAB / "debug_target.robot")], ".where\n.s\n.vars\n.c\n.c\n.c\n.c\n"),
    ("D08_eof_resumes", DBG + [str(LAB / "debug_target.robot")], ""),
    ("D09_for_at_rdb", DBG + [str(LAB / "debug_target.robot")], "FOR    ${j}    IN RANGE    2\n    Log To Console    j=${j}\nEND\n.c\n"),
    ("D10_library_at_rdb", DBG + [str(LAB / "debug_target.robot")], "Library    String\nImport Library    String\n${u}=    Convert To Upper Case    abc\n.print ${u}\n.c\n"),
    ("D11_abort", DBG + [str(LAB / "debug_target.robot")], ".abort\n"),
    ("D12_file_line_break", DBG + ["--break", str(LAB / "debug_target.robot") + ":18", str(LAB / "debug_target.robot")], ".vars\n.c\n.c\n.c\n.c\n"),
    ("D13_line_break_cmd", DBG + ["--stop-on-entry", str(LAB / "debug_target.robot")], ".break debug_target.robot:18\n.c\n.pp ${item}\n.c\n.c\n.c\n"),
    ("D14_eval_and_fix", DBG + [str(LAB / "debug_target.robot")], "${total}=    Set Variable    ${7}\n.set ${total} 7\n.c\n"),
    ("D15_print_expr", DBG + [str(LAB / "debug_target.robot")], ".print ${total} + 1\n.whatis ${total}\n.p ${{ $total * 2 }}\n.c\n"),
    ("D16_crlf", DBG + [str(LAB / "debug_target.robot")], ".where\r\n.c\r\n"),
    ("D17_no_debug_attached_repl", REPL + ["--no-debugger-attached"], "Fail    x\nLog To Console    after\n"),
    ("D18_repl_break_on_exception", REPL + ["--break-on-exception"], "Fail    x\n.where\n.c\nLog To Console    after\n"),
]
DEBUG_CASES[1] = ("D02_break_kw_noquotes", DBG + ["--stop-on-entry", str(LAB / "debug_target.robot")], ".break Process Item\n.c\n.c\n.c\n.c\n.c\n")


def run(case_id, cmd, stdin, env_extra=None, timeout=120):
    env = dict(os.environ)
    env.update(env_extra or {})
    t0 = time.time()
    p = subprocess.run(cmd, input=stdin.encode(), cwd=str(LAB), capture_output=True, timeout=timeout, env=env)
    dt = time.time() - t0
    # combined ordering check: rerun with stderr merged into stdout
    p2 = subprocess.run(cmd, input=stdin.encode(), cwd=str(LAB), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, env=env)
    rec = {
        "id": case_id, "cmd": " ".join(c if " " not in c else repr(c) for c in cmd[1:]), "stdin": stdin,
        "rc": p.returncode, "secs": round(dt, 2),
        "stdout": p.stdout.decode(errors="replace"), "stderr": p.stderr.decode(errors="replace"),
        "combined": p2.stdout.decode(errors="replace"),
    }
    (LOGS / f"{case_id}.log").write_text(
        f"# {case_id}\n# cmd: {rec['cmd']}\n# stdin <<<\n{stdin}# >>>\n# rc={rec['rc']} secs={rec['secs']}\n"
        f"## stdout\n{rec['stdout']}\n## stderr\n{rec['stderr']}\n## combined (2>&1)\n{rec['combined']}\n")
    return rec


def main():
    sel = sys.argv[1:]
    out = LOGS / "repl_cases.jsonl"
    recs = []
    for cid, cmd, stdin in CASES + DEBUG_CASES:
        if sel and not any(cid.startswith(s) for s in sel):
            continue
        r = run(cid, cmd, stdin)
        recs.append(r)
        print(f"{cid:34s} rc={r['rc']} {r['secs']:5.2f}s  out={r['stdout'][:90]!r} err={r['stderr'][:90]!r}")
    mode = "a" if sel else "w"
    with out.open(mode) as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
