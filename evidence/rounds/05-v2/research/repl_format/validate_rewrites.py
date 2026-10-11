#!/usr/bin/env python3
"""Run original vs linter-rewritten commands live; check the rewrite fixes the failure."""
import json, subprocess, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import repl_lint
HERE = Path(__file__).resolve().parent; LAB = HERE / "lab"
RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
D = str(LAB / "debug_target.robot")
CASES = [
  ("unquoted_heredoc", "robotcode repl --plain --no-history -d out <<RF 2>&1\n${x}=    Set Variable    five\nLog To Console    x=${x}\nRF", "x=five"),
  ("single_space", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nLog To Console single-space-fixed\nRF", "single-space-fixed"),
  ("single_space_assign", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n${t} = Set Variable abc\nLog To Console    t=${t}\nRF", "t=abc"),
  ("continuation", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n${d}    Create Dictionary    a=1\n...    b=2\nLog To Console    ${d}\nRF", "'b': '2'"),
  ("blank_in_block", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nFOR    ${i}    IN RANGE    2\n\n    Log To Console    i=${i}\nEND\nRF", "i=1"),
  ("fences", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n```robotframework\nLog To Console    fenced\n```\nRF", "fenced"),
  ("pasted_settings", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n*** Settings ***\nLibrary    Collections\n${l}=    Create List    a\nAppend To List    ${l}    b\nLog To Console    l=${l}\nRF", "l=['a', 'b']"),
  ("bare_var", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n${x}=    Set Variable    shown\n${x}\nRF", "shown"),
  ("quit_word", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\nLog To Console    before-quit\nquit\nLog To Console    after-quit\nRF", "before-quit"),
  ("kw_quoted", "robotcode repl --plain --no-history -d out <<'RF' 2>&1\n.kw \"Log To Console\"\nRF", "Keyword *Log To Console*"),
  ("pipe_no_2to1", "robotcode repl --plain --no-history -d out <<'RF' | tail -3\nShould Be Equal    a    b\nRF", "[ FAIL ] a != b"),
  ("no_plain_missing_d", "robotcode repl -d out_new_r5 <<'RF'\nLog To Console    made-it\nRF", "made-it"),
  ("dbg_library", f"robotcode robot-debug --plain --no-history -d out {D} <<'RF' 2>&1\nLibrary    String\n${{u}}=    Convert To Upper Case    abc\n.c\nRF", "=> 'ABC'"),
  ("dbg_break_quotes", f"robotcode robot-debug --plain --no-history -d out --stop-on-entry {D} <<'RF' 2>&1\n.break \"Process Item\"\n.c\n.c\n.c\n.c\n.c\nRF", "* breakpoint  Process Item"),
  ("dbg_bare_var", f"robotcode robot-debug --plain --no-history -d out {D} <<'RF' 2>&1\n${{total}}\n.c\nRF", "(rdb) 6"),
]
rows = []
for cid, cmd, expect in CASES:
    r = repl_lint.lint(cmd, cwd=str(LAB))
    res = {"id": cid, "decision": r["decision"], "fired": r["fired"]}
    for label, c in (("original", cmd), ("rewritten", r["command"])):
        c2 = c.replace("robotcode ", RC + " ", 1)
        t0 = time.time()
        p = subprocess.run(["bash", "-c", c2], cwd=str(LAB), capture_output=True, text=True, timeout=120)
        res[label] = {"ok": expect in p.stdout and "[ FAIL ]" not in p.stdout.replace("[ FAIL ] a != b",""), "fails": p.stdout.count("[ FAIL ]") + p.stdout.count("! "), "secs": round(time.time() - t0, 2), "out": p.stdout[-300:], "err": p.stderr[-200:]}
    rows.append(res)
    print(f"{cid:20s} {r['decision']:8s} orig ok={res['original']['ok']!s:5s} fails={res['original']['fails']}  rewritten ok={res['rewritten']['ok']!s:5s} fails={res['rewritten']['fails']}")
(HERE / "logs" / "validate_rewrites.json").write_text(json.dumps(rows, indent=1))
