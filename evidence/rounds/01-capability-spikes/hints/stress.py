"""Stress test for failure->line correlation: long sessions, failures in the middle,
repeated keywords, a nested (resource keyword) failure, console output in between.

Ground truth: repl-server, one executeCell per line (exact line->FAIL mapping).
Evaluated: parse_plain (v1), parse_plain_v2 (anchors), top_failures_k (-k).

  python stress.py            (robotcode venv python is fine; only subprocess + stdlib)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from parse_robotcode import parse_plain, parse_plain_v2, parse_replserver, top_failures_k  # noqa: E402
from replserver_capture import Client  # noqa: E402

ROBOTCODE = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
BOOKER_RES = "~/workspace/robotcode-experiments/experiments/resources/booker.resource"
S = "    "

SESSIONS = {
    "S1_api": [
        "Import Library    RequestsLibrary",
        "Import Library    Collections",
        f"Import Resource    {BOOKER_RES}",
        "Create Session    rb    https://restful-booker.herokuapp.com",
        "${ping}=    GET On Session    rb    /ping    expected_status=201",
        "Should Be Equal As Integers    ${ping.status_code}    201",
        "Log To Console    ping ok",
        "${missing}=    GET On Session    rb    /booking/99999999",
        "&{creds}=    Create Dictionary    username=admin    password=password123",
        "${auth}=    POST On Session    rb    /auth    json=${creds}",
        "Should Be Equal    ${auth.status_code}    200",
        "Should Be Equal As Integers    ${auth.status_code}    200",
        "${token}=    Set Variable    ${auth.json()}[token]",
        "Should Be Equal    ${token}    not-the-token",
        "Get From Dictionary    ${auth.json()}    access_token",
        "Log    ${auth.json().token}",
        "Log To Console    between failures",
        "Open Booker Session",
        "${t}=    Get Auth Token    admin    wrongpass",
        'Evaluate    {"a": true}',
        "${n}=    Evaluate    1 + 1",
        "Should Be Equal As Integers    ${n}    3",
        "Shuold Contain    abc    b",
        "Should Contain    abc    z",
        "GET On Session    rb    /booking/88888888",
        "Log To Console    done",
    ],
    "S2_browser": [
        "Import Library    Browser    timeout=5s",
        "New Browser    chromium    headless=True",
        "New Page    https://www.saucedemo.com",
        'Click    [data-test="login-btn"]',
        'Fill Text    [data-test="username"]    standard_user',
        'Fill Text    [data-test="password"]    secret_sauce',
        'Click    [data-test="login-button"]',
        'Get Text    [data-test="title"]    ==    Products',
        "Click    button.btn_inventory",
        'Click    [data-test="add-to-cart-sauce-labs-backpack"]',
        'Get Text    [data-test="shopping-cart-badge"]    ==    2',
        "Click    link=Sauce Labs Backpack",
        '${count}=    Get Element Count    [data-test="inventory-item"]',
        "Log To Console    items=${count}",
        'Fill Text    [data-test="username"]    again',
        "Get Title    ==    Swag Lab",
        'Click    [data-test="add-to-cart-sauce-labs-bike-light"]',
        "Get Url    contains    cart",
    ],
}


def run_repl(name, lines, k):
    out = HERE / "runs" / "stress" / name / ("k" if k else "plain")
    out.mkdir(parents=True, exist_ok=True)
    stdin = "\n".join(lines + [".exit"]) + "\n"
    (out / "stdin.txt").write_text(stdin)
    cmd = [ROBOTCODE, "repl", "--plain", "--no-history", "-d", str(out)] + (["-k"] if k else [])
    p = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       cwd=HERE / "scratch" / "cwd", timeout=400)
    (out / "stdout.txt").write_text(p.stdout)
    return p.stdout


def run_replserver(name, lines, port):
    out = HERE / "runs" / "stress" / name / "replserver"
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([ROBOTCODE, "repl-server", "--tcp", f"127.0.0.1:{port}", "-d", str(out)],
                            cwd=HERE / "scratch" / "cwd", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    cells = []
    try:
        c = Client(port)
        cells.append({"method": "initialize", "response": c.call("initialize", {"message": "stress"})})
        for line in lines:
            cells.append({"source": line, "response": c.call("executeCell", {"source": line, "language_id": "robotframework"})})
        c.call("shutdown")
    finally:
        try:
            proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
    (out / "cells.json").write_text(json.dumps(cells, indent=2))
    return cells


OFFLINE = "--offline" in sys.argv


def main():
    report = {}
    md = ["| session | true failures | parser | failures found | line correct | keyword+args correct | error correct (ws-norm) |",
          "|---|---|---|---|---|---|---|"]
    for i, (name, lines) in enumerate(SESSIONS.items()):
        base = HERE / "runs" / "stress" / name
        if OFFLINE:
            cells = json.loads((base / "replserver" / "cells.json").read_text())
            plain = (base / "plain" / "stdout.txt").read_text()
            ktxt = (base / "k" / "stdout.txt").read_text()
        else:
            cells = run_replserver(name, lines, 6801 + i)
            plain = run_repl(name, lines, k=False)
            ktxt = run_repl(name, lines, k=True)
        truth = parse_replserver(cells)
        norm = lambda s: " ".join((s or "").split())  # noqa: E731
        res = {"truth": [(t["line_index"], t["keyword"], t["error"].splitlines()[0][:100]) for t in truth]}
        for pname, steps in (("plain v1", parse_plain(plain, lines)), ("plain v2 (anchors)", parse_plain_v2(plain, lines)),
                             ("-k", top_failures_k(ktxt))):
            line_ok = kwargs_ok = err_ok = 0
            detail = []
            for j, t in enumerate(truth):
                s = steps[j] if j < len(steps) else None
                if not s:
                    detail.append((t["line_index"], None))
                    continue
                if pname == "-k":
                    lok = True  # -k needs no line mapping; judge by keyword+args
                else:
                    lok = s.get("line_index") == t["line_index"]
                kok = (s.get("keyword") or "").lower().split(".")[-1] == (t["keyword"] or "").lower().split(".")[-1] \
                    and (s.get("args") or []) == (t["args"] or [])
                eok = norm(s.get("error")) == norm(t["error"])
                line_ok += lok
                kwargs_ok += kok
                err_ok += eok
                detail.append((t["line_index"], s.get("line_index"), s.get("keyword"), s.get("confidence"), lok, kok, eok))
            res[pname] = {"n_found": len(steps), "line_ok": line_ok, "kwargs_ok": kwargs_ok, "err_ok": err_ok, "detail": detail}
            md.append(f"| {name} | {len(truth)} | {pname} | {len(steps)} | {line_ok if pname != '-k' else 'n/a'} | "
                      f"{kwargs_ok}/{len(truth)} | {err_ok}/{len(truth)} |")
        report[name] = res
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "stress_eval.json").write_text(json.dumps(report, indent=2, default=str))
    (HERE / "results" / "stress_eval.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    for name, r in report.items():
        print(name, "truth:", r["truth"])
        for p in ("plain v1", "plain v2 (anchors)", "-k"):
            print("  ", p, r[p]["detail"])


if __name__ == "__main__":
    main()
