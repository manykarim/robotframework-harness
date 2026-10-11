"""Exp 4: file-based step execution end to end (Browser saucedemo + Requests restful-booker), edge cases,
latency vs `fast.py step`. "Agent edits" are plain file writes (what a Write/Edit tool does); every helper
call is `python3 -S .rf/filestep.py run .rf/live.robot ...` -- a path + line range only.

usage (any cwd): <rcexp-python> exp4_filestep.py
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from live_steps import CALL_LIVE_HELPER, HEADER, KEYWORDS_SECTION, STEPS  # noqa: E402

PY = "~/workspace/robotcode-experiments/.venv/bin/python"
PROJ = HERE / "proj"
LIVE = PROJ / ".rf" / "live.robot"
ENV = {k: v for k, v in os.environ.items() if k != "PLAYWRIGHT_BROWSERS_PATH"}
ENV["RFMCP_R3_LSPQ"] = "1"
LOG: list = []


def sh(args, **kw):
    t = time.perf_counter()
    p = subprocess.run(args, cwd=PROJ, capture_output=True, text=True, env=ENV, **kw)
    return round((time.perf_counter() - t) * 1000, 1), p


def fs(*args):
    ms, p = sh(["python3", "-S", ".rf/filestep.py", *args])
    try:
        r = json.loads(p.stdout)
    except json.JSONDecodeError:
        r = {"raw": p.stdout[-800:], "err": p.stderr[-800:]}
    return ms, r


def brief(r):
    out = {"ok": r.get("ok")}
    if r.get("ran"):
        out["ran"] = [f"L{x['line']}{'-' + str(x['end']) if 'end' in x else ''} {x.get('kw')} {x.get('status')}" for x in r["ran"]]
    for k in ("blocked", "failed", "error", "note", "dropped", "first_changed_line", "diags", "rebased_items"):
        if r.get(k):
            v = r[k]
            if k == "blocked":
                v = {"line": v["line"], "diags": [f"{d['code']}: {d['msg'][:90]}" for d in v["diags"]]}
            if k == "failed":
                v = {"line": v["line"], "msg": (v.get("msg") or "")[:140]}
            out[k] = v
    if r.get("timing_ms"):
        out["timing_ms"] = r["timing_ms"]
    return out


def record(label, ms, r):
    b = brief(r)
    LOG.append({"label": label, "client_wall_ms": ms, **b})
    print(f"[{ms:>7.1f} ms] {label}: {json.dumps(b)[:600]}", flush=True)
    return r


def write(text):
    LIVE.write_text(text)


def text():
    return LIVE.read_text()


def edit(old, new, count=1):
    t = text()
    assert old in t, old
    write(t.replace(old, new, count))


def main():
    sh([PY, str(HERE / "fs_ctl.py"), "stop"])
    for f in ("filestep.json", "raw_requests.log", "filestep_journal.jsonl", "journal.jsonl", ".live.live.resource"):
        try:
            (PROJ / ".rf" / f).unlink()
        except OSError:
            pass
    ms, p = sh([PY, str(HERE / "fs_ctl.py"), "start", "-v", "CLI_VAR:from-cli", "--hooks", "redact,hints"])
    print("start", ms, p.stdout.strip())
    write(HEADER)
    record("empty test", *fs("run", ".rf/live.robot", "--new"))
    # -------------------------------------------------- growing scenario
    for sid, probe, lines, expect in STEPS:
        write(text() + "\n".join(lines) + "\n")
        r = record(f"{sid} {probe}", *fs("run", ".rf/live.robot", "--new"))
        if sid == "s09":  # make later runtime failures fast
            pass
        if sid == "s13":
            edit("    Clik    id=login-button\n", "    Log    fixed typo line\n")
            record("s13 fix (Edit line) + --new", *fs("run", ".rf/live.robot", "--new"))
        if sid == "s14":
            edit("    Log    ${usrname}\n", "    Log    ${user}\n")
            record("s14 fix + --new", *fs("run", ".rf/live.robot", "--new"))
        if sid == "s15":
            edit("    Fill Text    id=user-name\n", "    ${url}=    Get Url\n")
            record("s15 fix + --new", *fs("run", ".rf/live.robot", "--new"))
    # runtime failure (not statically detectable)
    write(text() + "    Set Browser Timeout    1s\n    Get Text    id=does-not-exist\n")
    record("runtime failure: missing element", *fs("run", ".rf/live.robot", "--new"))
    edit("    Get Text    id=does-not-exist\n", "    Get Text    css=.title    ==    Products\n")
    record("runtime failure fixed + --new", *fs("run", ".rf/live.robot", "--new"))
    # -------------------------------------------------- edge cases
    # e1 editing an already executed line
    edit("    Log    loop ${i}\n", "    Log    loop no ${i}\n")
    r = record("e1 edit executed line (inside FOR) + --new", *fs("run", ".rf/live.robot", "--new"))
    fl = r.get("first_changed_line")
    if fl:
        lines = text().splitlines()
        end = next(i + 1 for i in range(fl - 1, len(lines)) if lines[i].strip() == "END")
        record(f"e1 explicit --lines {fl}-{end}", *fs("run", ".rf/live.robot", "--lines", f"{fl}-{end}"))
        record("e1 rebase", *fs("rebase", ".rf/live.robot"))
        record("e1 --new after rebase", *fs("run", ".rf/live.robot", "--new"))
    # e2 keywords section in the live file + call inserted before it
    write(text() + KEYWORDS_SECTION)
    record("e2 add *** Keywords *** at end, --new", *fs("run", ".rf/live.robot", "--new"))
    t = text()
    i = t.index("\n*** Keywords ***")
    write(t[:i + 1] + "\n".join(CALL_LIVE_HELPER) + "\n" + t[i + 1:])
    record("e2 call Live Helper (inserted above Keywords section)", *fs("run", ".rf/live.robot", "--new"))
    edit("    RETURN    ${x}-done\n", "    RETURN    ${x}-v2\n")
    t = text()
    i = t.index("\n*** Keywords ***")
    write(t[:i + 1] + "    ${h2}=    Live Helper    7\n    Should Be Equal    ${h2}    7-v2\n" + t[i + 1:])
    record("e2 edited keyword body, new call uses new body", *fs("run", ".rf/live.robot", "--new"))
    # e3 IF/ELSE + TRY/EXCEPT in one edit; WHILE across two edits
    t = text()
    i = t.index("\n*** Keywords ***")
    block = ("    IF    $h2 == '7-v2'\n        Log    if-branch\n    ELSE\n        Fail    wrong branch\n    END\n"
             "    TRY\n        Fail    boom\n    EXCEPT    boom\n        Log    caught\n    END\n"
             "    VAR    ${n}    0\n    WHILE    ${n} < 2\n")
    write(t[:i + 1] + block + t[i + 1:])
    record("e3 IF + TRY complete, WHILE header only", *fs("run", ".rf/live.robot", "--new"))
    t = text()
    i = t.index("\n*** Keywords ***")
    write(t[:i + 1] + "        ${n}=    Evaluate    ${n} + 1\n    END\n" + t[i + 1:])
    record("e3 WHILE completed", *fs("run", ".rf/live.robot", "--new"))
    # e4 *** Variables *** section inserted above the test (shifts every line number) + import added
    t = text()
    t = t.replace("Resource    shop.resource\n", "Resource    shop.resource\nLibrary    Collections\n", 1)
    t = t.replace("*** Test Cases ***", "*** Variables ***\n${LIVE_VAR}    hello\n\n*** Test Cases ***", 1)
    i = t.index("\n*** Keywords ***")
    t = t[:i + 1] + "    @{l}=    Create List    ${LIVE_VAR}\n    Append To List    ${l}    x\n    Length Should Be    ${l}    2\n" + t[i + 1:]
    write(t)
    record("e4 Variables section + new Library import (all lines shift)", *fs("run", ".rf/live.robot", "--new"))
    # check-only op (for agents without LSP), planted error, then remove it
    t = text()
    i = t.index("\n*** Keywords ***")
    write(t[:i + 1] + "    Lgo    oops\n    Should Be Equal    ${undefined_thing}    1\n" + t[i + 1:])
    record("check op on two planted lines", *fs("check", ".rf/live.robot", "--new"))
    write(t)
    # -------------------------------------------------- latency
    lat_fs, lat_fast, lat_chk, lat_nochk, inner = [], [], [], [], []
    for n in range(20):
        t = text()
        i = t.index("\n*** Keywords ***")
        write(t[:i + 1] + f"    ${{t{n}}}=    Get Title\n" + t[i + 1:])
        ms, r = fs("run", ".rf/live.robot", "--new")
        assert r.get("ok"), r
        lat_fs.append(ms)
        inner.append(r["timing_ms"])
        ms, p = sh(["python3", "-S", ".rf/fast.py", "step", "Get Title"])
        lat_fast.append(ms)
        ms, r = fs("check", ".rf/live.robot", "--all")
        lat_chk.append(ms)
    for n in range(10):
        t = text()
        i = t.index("\n*** Keywords ***")
        write(t[:i + 1] + f"    ${{u{n}}}=    Get Title\n" + t[i + 1:])
        ms, r = fs("run", ".rf/live.robot", "--new", "--no-check")
        lat_nochk.append(ms)
    lat = {"filestep_run_new_ms": {"median": statistics.median(lat_fs), "max": max(lat_fs)},
           "filestep_run_new_nocheck_ms": {"median": statistics.median(lat_nochk), "max": max(lat_nochk)},
           "fast_step_ms": {"median": statistics.median(lat_fast), "max": max(lat_fast)},
           "check_all_ms": {"median": statistics.median(lat_chk), "max": max(lat_chk)},
           "inner_median_ms": {k: statistics.median([x[k] for x in inner]) for k in inner[0]},
           "file_lines": text().count("\n")}
    print("latency", json.dumps(lat), flush=True)
    raw = (PROJ / ".rf" / "raw_requests.log").read_text().splitlines()
    print("raw request sample:", raw[0], "|", raw[-1])
    final = text()
    ms, p = sh([PY, str(HERE / "fs_ctl.py"), "stop"])
    print("stop", p.stdout.strip())
    # replay the live file as a real suite (it IS the deliverable)
    ms, p = sh(["~/workspace/robotcode-experiments/.venv/bin/robotcode", "robot", "-v", "CLI_VAR:from-cli",
                "--output", "NONE", "--report", "NONE", "--log", "NONE", ".rf/live.robot"])
    replay = {"rc": p.returncode, "ms": ms, "tail": p.stdout[-600:]}
    print("replay", replay)
    (HERE / "results" / "exp4_filestep.json").write_text(json.dumps(
        {"log": LOG, "latency": lat, "raw_requests_sample": raw[:3], "final_live_robot": final, "replay": replay}, indent=1))


if __name__ == "__main__":
    main()
