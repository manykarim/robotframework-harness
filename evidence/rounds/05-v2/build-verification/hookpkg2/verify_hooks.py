"""Unit-level verification of the hook harness v2 (rfharness2) with simulated agent payloads (no LLM).

  PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 verify/verify_hooks.py [WORKROOT]
Scenarios: A Browser journey (Claude shapes: incremental writes, failing line + fix + resume, iframe, changed
earlier line -> restart, deny on planted errors, deprecated-syntax rewrite, Stop gate block/allow, plain robot run
summary), B repair of an existing failing suite (robot run -> live reproduction -> fix -> resume -> green),
C RequestsLibrary against a local http.server API, D Codex/Copilot/OpenCode payload shapes (apply_patch gate,
rewrite, run), E long step -> "still running" -> delivered later, SessionEnd cleanup (0 orphans);
v2: F failing-keyword docs, page capture (latest + history + dedup), short timeout + slow/missing recheck, import
docs, no timeout leak; G REPL/debugger format (card, rewrites, denials, output parsing, .save strip) for all 4
payload shapes; H guards (install, -P, big read, suite weakening, valves), loop hint, prompt context, OpenCode caps.
Writes verify/results_hooks.json. Exit 0 when every check passes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "rfharness2"))
from simlib import Sim, read_with_hooks, shell_with_hooks  # noqa: E402
import proto  # noqa: E402
import procs  # noqa: E402

VENV = Path("~/workspace/rf-mcp-robotcode/.venv/bin")
CHECKS: list = []
LAT: dict = {}


def check(name, cond, detail=None):
    CHECKS.append({"check": name, "ok": bool(cond), **({"detail": str(detail)[:1500]} if not cond else {})})
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     -> {str(detail)[:1500]}"), flush=True)


def merge_lat(s: Sim):
    for k, v in s.lat.items():
        LAT.setdefault(f"{s.agent}:{k}", []).extend(v)


def new_ws(root: Path, name: str) -> Path:
    ws = root / name
    shutil.rmtree(ws, ignore_errors=True)
    (ws / "tests").mkdir(parents=True)
    shutil.copytree(HERE / "site", ws / "site")
    subprocess.run(["git", "init", "-q"], cwd=ws)
    return ws


def tokens(ws: Path):
    out = []
    for k in ("exec2", "lint2"):
        st = proto.read_state(ws / ".rf" / k) or {}
        if st.get("token_env"):
            out.append(st["token_env"])
    return out


def _pids_mentioning(text: str) -> list:
    out = []
    for n in os.listdir("/proc"):
        if not n.isdigit():
            continue
        try:
            with open(f"/proc/{n}/cmdline", "rb") as f:
                cl = f.read().decode(errors="replace")
            cwd = os.readlink(f"/proc/{n}/cwd")
        except OSError:
            continue
        if (text in cl or cwd.startswith(text)) and "verify_hooks" not in cl:
            out.append(int(n))
    return out


def end_session(s: Sim, ws: Path, label: str):
    toks = tokens(ws)
    out, ms = s.hook("end", {"reason": "other"})
    t_end = time.time() + 8
    left = []
    while time.time() < t_end:
        left = [p for t in toks for p in procs.token_procs(t)]
        if not left:
            break
        time.sleep(0.2)
    t_end = time.time() + 5
    strays = []
    while time.time() < t_end:   # any process still pointing at this workspace (also duplicate daemons)
        strays = [p for p in _pids_mentioning(str(ws)) if p != os.getpid()]
        if not strays:
            break
        time.sleep(0.2)
    check(f"{label}: no process mentions the workspace any more", not strays, strays)
    if strays:
        procs.terminate(strays)
    gens = list(ws.rglob(".*.live.resource")) + list(ws.rglob(".*rfh-gate*"))
    check(f"{label}: SessionEnd < 1.5 s ({ms:.0f} ms) and 0 orphans after it", ms < 1500 and not left,
          {"ms": ms, "left": left})
    check(f"{label}: no generated files left in the workspace", not gens, gens)
    if left:
        procs.terminate(left)


JOURNEY_HEAD = """*** Settings ***
Library    Browser
Suite Setup    New Browser    chromium    headless=True

*** Variables ***
${URL}    file://${CURDIR}/../site/login.html

*** Test Cases ***
Order Journey
    New Page    ${URL}
    Click    text=Accept all
    Fill Text    id=username    alice
"""


def scenario_a(root: Path):
    ws = new_ws(root, "a_journey")
    s = Sim("claude", ws)
    out, ms = s.hook("start", {"source": "startup"})
    ctx = (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    check(f"A SessionStart returns context fast ({ms:.0f} ms)", ms < 1500 and "live Robot Framework session" in ctx, out)
    time.sleep(4)
    f = ws / "tests" / "shop.robot"
    r = s.edit("write", f, content=JOURNEY_HEAD)
    t = r.get("text", "")
    check("A1 first write: suite setup + 3 lines PASS + page summary", r["decision"] == "allow" and "L12 PASS" in t
          and "L3 PASS" in t and "Page (" in t and "id=username" in t, t)
    r = s.edit("edit", f, old="    Fill Text    id=username    alice\n",
               new="    Fill Text    id=username    alice\n    Fill Text    id=password    secret\n"
                   "    Click    data-test=signin\n    Get Text    id=greeting    ==    Hello, alice\n")
    t = r.get("text", "")
    check("A2 appended lines run (only the new ones), navigation summary", "L13 PASS" in t and "L15 PASS" in t
          and "L12 PASS" not in t and "order.html" in t and "pay-frame >>>" in t, t)
    r = s.edit("edit", f, old="    Get Text    id=greeting    ==    Hello, alice\n",
               new="    Get Text    id=greeting    ==    Hello, alice\n    Check Checkbox    id=ship-express\n"
                   "    Select Options By    id=country    label    Norway\n")
    t = r.get("text", "")
    check("A3 failing line: hidden radio -> NOT RUN NOT_VISIBLE with the label to click", "L16 NOT RUN" in t
          and 'label[for="ship-express"]' in t and "Fix line 16" in t, t)
    r = s.edit("edit", f, old="    Check Checkbox    id=ship-express\n", new="    Click    label[for=\"ship-express\"]\n")
    t = r.get("text", "")
    check("A4 fix -> resumes AT the fixed line in the open page (L16, L17 only)", "L16 PASS" in t and "L17 PASS" in t
          and "L15" not in t and "L10" not in t, t)
    r = s.edit("edit", f, old="    Select Options By    id=country    label    Norway\n",
               new="    Select Options By    id=country    label    Norway\n    Fill Text    id=card    4242\n")
    t = r.get("text", "")
    check("A5 element inside iframe -> NOT_FOUND with the `frame >>> selector` fix", "id=pay-frame >>> id=card" in t
          and "NOT RUN" in t, t)
    r = s.edit("edit", f, old="    Fill Text    id=card    4242\n",
               new="    Fill Text    id=pay-frame >>> id=card    4242\n    Click    id=pay-frame >>> id=confirm-card\n"
                   "    Click    data-test=place-order\n    ${msg}=    Get Text    id=result\n"
                   "    Should Contain    ${msg}    Done\n")
    t = r.get("text", "")
    check("A6 async confirmation read too early -> fails at L22 with the read value", "L21 PASS" in t
          and "Processing" in t and ("L22 FAIL" in t), t)
    r = s.edit("edit", f, old="    ${msg}=    Get Text    id=result\n",
               new="    Wait For Condition    Text    id=result    contains    Done    timeout=10s\n"
                   "    ${msg}=    Get Text    id=confirmation\n")
    t = r.get("text", "")
    check("A7 replacing an executed PROBE line (Get Text) by a wait + new getter -> no restart needed, continues "
          "in the page; stops at L23 with the real confirmation text", ("restarted" in t or "no restart" in t)
          and "L21 PASS" in t and "L23 FAIL" in t and "ORD-" in t, t)
    r = s.edit("edit", f, old="    Should Contain    ${msg}    Done\n", new="    Should Contain    ${msg}    confirmed\n")
    t = r.get("text", "")
    check("A7b fix the expected text -> resumes at L23, all pass", "L23 PASS" in t and "All test lines passed" in t, t)
    # changed earlier (already executed) line -> restart
    txt = f.read_text()
    r = s.edit("edit", f, old="    Fill Text    id=username    alice\n", new="    Fill Text    id=username    bob\n")
    t = r.get("text", "")
    check("A8 changed an executed earlier line -> test restarted (L10 New Page re-ran), stops at the stale greeting",
          "restarted" in t and ("L10 PASS" in t or "L10-" in t) and "L15 FAIL" in t and "Hello, bob" in t, t)
    r = s.edit("edit", f, old="    Get Text    id=greeting    ==    Hello, alice\n",
               new="    Get Text    id=greeting    ==    Hello, bob\n")
    t = r.get("text", "")
    check("A9 fix the assertion -> resumes from L15 to the end", "L15 PASS" in t and "L23 PASS" in t
          and "L10" not in t, t)
    # deny on planted errors (file unchanged)
    before = f.read_text()
    r = s.edit("edit", f, old="    Should Contain    ${msg}    confirmed\n",
               new="    Should Contain    ${msg}    confirmed\n    Clik    id=place\n    Fill Text    id=card\n"
                   "    FOR    ${i}    IN RANGE    2\n        Log    ${i}\n")
    rs = r.get("reason", "")
    check("A10 PreToolUse denies NEW hard errors with line numbers (typo, arg count, missing END); file unchanged",
          r["decision"] == "deny" and ":24 KeywordNotFound" in rs and ":25 DataError" in rs and "END" in rs
          and f.read_text() == before and r["pre_ms"] < 1000, rs)
    LAT.setdefault("gate_deny_ms", []).append(r["pre_ms"])
    # deprecated syntax -> rewritten input
    r = s.edit("edit", f, old="    Should Contain    ${msg}    confirmed\n",
               new="    Should Contain    ${msg}    confirmed\n    Run Keyword If    1 == 1    Log    modern\n")
    t = r.get("text", "")
    ft = f.read_text()
    check("A11 deprecated `Run Keyword If` -> input rewritten to IF/END before writing; new lines run",
          r["decision"] == "rewrite" and "Run Keyword If" not in ft and "    IF    1 == 1" in ft and "PASS" in t,
          {"reason": r.get("reason"), "file_tail": ft[-200:], "text": t})
    # Stop gate
    out, ms = s.hook("stop", {"stop_hook_active": False})
    check("A12 Stop blocks: test changed and never ran plainly", out.get("decision") == "block"
          and "robot -d results tests/shop.robot" in out.get("reason", ""), out)
    out2, _ = s.hook("stop", {"stop_hook_active": True})
    check("A13 Stop with stop_hook_active -> allow (no loop)", not out2, out2)
    b = s.bash(f"{VENV}/robot -d results tests/shop.robot", fail_event=True)
    check("A14 plain robot run (green) -> summary + verified recorded", b["rc"] == 0 and "verified" in b["text"]
          and "1 passed" in b["text"], b)
    out3, _ = s.hook("stop", {"stop_hook_active": False})
    check("A15 Stop after the green plain run -> allow", not out3, out3)
    # whole-file write, 2 tests, second fails -> fix -> resume
    w = ws / "tests" / "whole.robot"
    content = """*** Settings ***
Library    Browser
Test Setup    New Page    file://${CURDIR}/../site/login.html

*** Test Cases ***
Login Requires Password
    Click    text=Accept all
    Fill Text    id=username    carol
    Click    data-test=signin
    Get Text    id=msg    ==    Username and password are required

Login Works
    Click    text=Accept all
    Fill Text    id=username    carol
    Fill Text    id=password    pw
    Click    data-test=signin
    Get Text    id=greeting    ==    Hello, Carol
"""
    r = s.edit("write", w, content=content)
    t = r.get("text", "")
    check("A16 whole-file write: test 1 passes, test 2 runs (fresh Test Setup page) and fails at L17",
          ("L10 PASS" in t or "L3-L15 PASS" in t) and "L17 FAIL" in t and "Hello, carol" in t, t)
    r = s.edit("edit", w, old="Hello, Carol", new="Hello, carol")
    t = r.get("text", "")
    check("A17 fix -> only L17 re-runs", "L17 PASS" in t and "L13" not in t and "All test lines passed" in t, t)
    merge_lat(s)
    end_session(s, ws, "A")


BROKEN = """*** Settings ***
Library    Browser
Suite Setup    New Browser    chromium    headless=True
Test Setup    Open Shop

*** Variables ***
${URL}    file://${CURDIR}/../site/login.html

*** Test Cases ***
Customer Can Sign In
    Fill Text    id=username    dora
    Fill Text    id=password    pw
    Click    id=signin-button
    Get Text    id=greeting    ==    Hello, dora

Express Order Total
    Sign In As    erik
    Click    label[for="ship-express"]
    Select Options By    id=country    label    Sweden
    Get Text    id=total    ==    Total: 55.00 EUR

*** Keywords ***
Open Shop
    New Page    ${URL}
    Click    text=Accept all

Sign In As
    [Arguments]    ${name}
    Fill Text    id=username    ${name}
    Fill Text    id=password    pw
    Click    data-test=signin
"""


def scenario_b(root: Path):
    ws = new_ws(root, "b_repair")
    f = ws / "tests" / "broken.robot"
    f.write_text(BROKEN)
    s = Sim("claude", ws)
    s.hook("start", {"source": "startup"})
    time.sleep(3)
    b = s.bash(f"{VENV}/robot -d results tests/broken.robot", fail_event=True)
    t = b["text"]
    check("B1 failing plain run -> failure summary + live reproduction stopped at the failing line with page summary",
          b["rc"] != 0 and "2 failed" in t and "Reproduced live" in t and "L13 NOT RUN" in t and "L3-" in t
          and "data-test=signin" in t, t)
    r = s.edit("edit", f, old="    Click    id=signin-button\n", new="    Click    data-test=signin\n")
    t = r.get("text", "")
    check("B2 fix the reproduced line -> resumes at L13 in the open page and passes", "L13 PASS" in t
          and "L14 PASS" in t and "L11" not in t, t)
    r = s.edit("edit", f, old="label    Sweden", new="label    Norway")
    t = r.get("text", "")
    check("B3 edit inside the never-run second test -> runs it from its setup, then fails on the total (async/wrong?)",
          "L19" in t, t)
    b2 = s.bash(f"{VENV}/robot -d results tests/broken.robot", fail_event=True)
    check("B4 plain run green after repair -> verified", b2["rc"] == 0 and "verified" in b2["text"], b2)
    out, _ = s.hook("stop", {"stop_hook_active": False})
    check("B5 Stop allows after the green run", not out, out)
    r = s.edit("edit", f, old="    Fill Text    id=username    ${name}\n",
               new="    Fill Text    id=username    ${name}\n    Log    signing in ${name}\n")
    t = r.get("text", "")
    check("B6 edit inside a user keyword -> the first test calling it re-runs from the top", "keyword" in t
          and "Express Order Total" in t and "L19 PASS" in t, t)
    k = ws / "tests" / "kwfail.robot"
    r = s.edit("write", k, content="""*** Settings ***
Library    Browser
Test Setup    New Page    file://${CURDIR}/../site/login.html

*** Test Cases ***
Sign In Via Keyword
    Sign In    ulla

*** Keywords ***
Sign In
    [Arguments]    ${name}
    Click    text=Accept all
    Fill Text    id=username    ${name}
    Click    id=sign-in
""")
    t = r.get("text", "")
    check("B7 failure inside a user keyword -> reported on the calling line with the keyword's file:line",
          "L7 FAIL" in t and "failed inside: Click at tests/kwfail.robot:14" in t and "keyword line" in t, t)
    merge_lat(s)
    end_session(s, ws, "B")


def _free_port() -> int:
    so = socket.socket()
    so.bind(("127.0.0.1", 0))
    p = so.getsockname()[1]
    so.close()
    return p


def scenario_c(root: Path):
    ws = new_ws(root, "c_api")
    port = _free_port()
    api = subprocess.Popen([sys.executable, str(HERE / "api_server.py"), str(port)])
    try:
        time.sleep(0.5)
        s = Sim("claude", ws)
        s.hook("start", {"source": "startup"})
        f = ws / "tests" / "api.robot"
        r = s.edit("write", f, content=f"""*** Settings ***
Library    RequestsLibrary
Suite Setup    Create Session    api    http://127.0.0.1:{port}

*** Test Cases ***
Items Can Be Listed
    ${{resp}}=    GET On Session    api    /api/items
    Status Should Be    200    ${{resp}}
    Should Be Equal As Strings    ${{resp.json()}}[0][name]    Pear
""")
        t = r.get("text", "")
        check("C1 API test: GET passes, wrong expected value fails at L9 with the real value", "L7 PASS" in t
              and "L9 FAIL" in t and "Apple" in t, t)
        r = s.edit("edit", f, old="[0][name]    Pear", new="[0][name]    Apple")
        t = r.get("text", "")
        check("C2 fix -> resumes at L9", "L9 PASS" in t and "L7" not in t, t)
        r = s.edit("edit", f, old="[0][name]    Apple\n", new="[0][name]    Apple\n    ${resp}=    POST On Session    api    /api/items    json=${{ {'name': 'Kiwi'} }}    expected_status=201\n    Should Be Equal    ${resp.json()}[name]    Kiwi\n")
        t = r.get("text", "")
        check("C3 POST with json= body appended -> PASS (returned value shown)", "L10 PASS" in t and "L11 PASS" in t, t)
        merge_lat(s)
        end_session(s, ws, "C")
    finally:
        api.terminate()


SHAPES_HEAD = """*** Settings ***
Library    Browser

*** Test Cases ***
Login Page Opens
    New Browser    chromium    headless=True
    New Page    file://${CURDIR}/../site/login.html
"""


def scenario_d(root: Path):
    for agent in ("codex", "copilot", "opencode"):
        ws = new_ws(root, f"d_{agent}")
        fake_agent = subprocess.Popen(["sleep", "600"]) if agent == "copilot" else None
        s = Sim(agent, ws, env={"RFH2_WATCH_PID": str(fake_agent.pid)} if fake_agent else None)
        out, ms = s.hook("start", {"source": "startup"})
        check(f"D[{agent}] SessionStart context ({ms:.0f} ms)", bool(out), out)
        time.sleep(3)
        f = ws / "tests" / "shapes.robot"
        r = s.edit("write", f, content=SHAPES_HEAD + "    Clik    text=Accept all\n")
        check(f"D[{agent}] planted typo in a new file -> deny with line number", r["decision"] == "deny"
              and ":8 KeywordNotFound" in r.get("reason", "") and not f.exists(), r)
        r = s.edit("write", f, content=SHAPES_HEAD + "    Click    text=Accept all\n")
        t = r.get("text", "")
        check(f"D[{agent}] corrected write -> allowed, lines run live", r["decision"] == "allow" and "L8 PASS" in t, r)
        r = s.edit("edit", f, old="    Click    text=Accept all\n",
                   new="    Click    text=Accept all\n    Run Keyword If    True    Log    x\n")
        ft = f.read_text()
        check(f"D[{agent}] deprecated syntax -> rewritten tool input ({r['decision']})",
              r["decision"] == "rewrite" and "Run Keyword If" not in ft and "IF    True" in ft, {"r": r, "ft": ft})
        merge_lat(s)
        if fake_agent is None:
            end_session(s, ws, f"D[{agent}]")
            continue
        toks = tokens(ws)
        out, ms = s.hook("end", {})
        time.sleep(1.0)
        alive = [p for t in toks for p in procs.token_procs(t)]
        check("D[copilot] sessionEnd keeps the session (it fires after every copilot run)", bool(alive), alive)
        fake_agent.kill()
        fake_agent.wait()
        t_end, left = time.time() + 10, alive
        while time.time() < t_end and left:
            time.sleep(0.3)
            left = [p for t in toks for p in procs.token_procs(t)]
        check("D[copilot] agent process gone -> daemons exit by themselves (watch-pid), 0 orphans", not left, left)
        if left:
            procs.terminate(left)


def scenario_e(root: Path):
    ws = new_ws(root, "e_long")
    s = Sim("claude", ws, env={"RFH2_BUDGET": "4"})
    s.hook("start", {"source": "startup"})
    time.sleep(2)
    f = ws / "tests" / "long.robot"
    r = s.edit("write", f, content="*** Test Cases ***\nSlow\n    Log    start\n    Sleep    7s\n    Log    end\n")
    t = r.get("text", "")
    check("E1 long step -> hook returns at the budget with 'still running'", "still running" in t
          and r["post_ms"] < 9000, r)
    time.sleep(5)
    r = s.edit("edit", f, old="    Log    end\n", new="    Log    end\n    Log    after\n")
    t = r.get("text", "")
    check("E2 next hook event delivers the earlier result, then runs the new line", "result of the live run" in t
          and "L4 PASS" in t and "L6 PASS" in t, t)
    merge_lat(s)
    end_session(s, ws, "E")


V2_HEAD = """*** Settings ***
Library    Browser
Library    Collections
Suite Setup    New Browser    chromium    headless=True

*** Variables ***
${URL}    file://${CURDIR}/../site/login.html

*** Test Cases ***
Slow Confirmation
    New Page    ${URL}
    Click    text=Accept all
    Fill Text    id=username    alice
    Fill Text    id=password    secret
    Click    data-test=signin
"""


def _dirs(ws: Path) -> list:
    return sorted(d.name for d in (ws / ".rf" / "state").glob("step-*"))


def scenario_f(root: Path):
    """v2: page capture, docs of failing keywords, import docs, short timeout + recheck, no leak."""
    ws = new_ws(root, "f_v2")
    s = Sim("claude", ws)
    s.hook("start", {"source": "startup"})
    time.sleep(3)
    f = ws / "tests" / "v2.robot"
    r = s.edit("write", f, content=V2_HEAD)
    t = r.get("text", "")
    latest = ws / ".rf" / "state" / "latest"
    names = sorted(p.name for p in latest.iterdir()) if latest.is_dir() else []
    check("F1 page capture after page-changing steps: latest/{page.txt,controls.txt,aria.yaml,source.html,"
          "screenshot.jpg} + step history, files listed with sizes in the output",
          {"page.txt", "controls.txt", "aria.yaml", "source.html", "screenshot.jpg"} <= set(names)
          and len(_dirs(ws)) >= 2 and "controls.txt" in t and re.search(r"screenshot\.jpg \d", t) is not None
          and "<html" not in t, {"names": names, "dirs": _dirs(ws), "text": t})
    check("F2 capture lands on the page AFTER the click-triggered navigation (settle)", "order.html" in
          (latest / "page.txt").read_text(errors="replace"), (latest / "page.txt").read_text(errors="replace"))
    n_dirs = len(_dirs(ws))
    r = s.edit("edit", f, old="    Click    data-test=signin\n", new="    Click    data-test=signin\n"
               "    Fill Text    id=pay-frame >>> id=card    4242\n")
    check("F3 a step that does not change the page (Fill Text) -> no new history dir (dedup)",
          len(_dirs(ws)) == n_dirs, {"before": n_dirs, "after": _dirs(ws), "text": r.get("text")})
    t0 = time.time()
    r = s.edit("edit", f, old="    Fill Text    id=pay-frame >>> id=card    4242\n",
               new="    Fill Text    id=pay-frame >>> id=card    4242\n    Click    id=no-such-button\n")
    t = r.get("text", "")
    kwf = ws / ".rf" / "docs" / "kw" / "Browser.Click.md"
    time.sleep(1.5)
    check("F4 bad locator: NOT_FOUND after the SHORT timeout, recheck -> MISSING (normal timeout), docs file of the "
          "failing keyword + signature in the output", "NOT RUN" in t and "recheck: MISSING" in t
          and ".rf/docs/kw/Browser.Click.md" in t and "Click(" in t and kwf.is_file()
          and "Simulates mouse click" in kwf.read_text(errors="replace"), {"t": t, "kw": kwf.exists()})
    check("F5 failure capture lists the page files (no source inlined)", "Page (" in t and ".rf/state/latest/" in t
          and "<body" not in t, t)
    r = s.edit("edit", f, old="    Click    id=no-such-button\n", new="    Click    id=pay-frame >>> id=confirm-card\n"
               "    Click    label[for=\"ship-express\"]\n    Select Options By    id=country    label    Norway\n"
               "    Click    data-test=place-order\n    Get Text    id=confirmation    contains    Total: 55.00 EUR\n")
    t = r.get("text", "")
    check("F6 slow element (appears after 4 s > 2.5 s live timeout): recheck -> SLOW, the line PASSES on the "
          "re-check, advice = explicit wait", "recheck: SLOW" in t and "Wait For Elements State" in t
          and re.search(r"L2\d PASS\s+Get Text\s+id=confirmation", t) is not None, t)
    col = ws / ".rf" / "docs" / "Collections.full.md"
    t_end = time.time() + 15
    while time.time() < t_end and not col.is_file():
        time.sleep(0.5)
    check("F7 imported library -> .rf/docs/<Name>.md + .full.md written and mentioned once",
          col.is_file() and (ws / ".rf" / "docs" / "Collections.md").is_file()
          and "Append To List" in col.read_text(errors="replace"), [p.name for p in (ws / ".rf" / "docs").iterdir()])
    r = s.edit("edit", f, old="    Click    data-test=place-order\n", new="    ${u}=    Get Url\n"
               "    Click    data-test=place-order\n")
    t = r.get("text", "")
    check("F7b probe line inserted before executed lines -> run now in the current page, NO restart",
          "no restart" in t and "restarted" not in t and "PASS" in t, t)
    r = s.edit("edit", f, old="    Fill Text    id=username    alice\n", new="    Fill Text    id=username    bob\n")
    t = r.get("text", "")
    check("F7c changing an executed line restarts the test in a FRESH browser context",
          "restarted" in t and "fresh cookies" in t, t)
    r = s.edit("edit", f, old="    Get Text    id=confirmation    contains    Total: 55.00 EUR\n",
               new="    Wait For Condition    Text    id=confirmation    contains    55.00    timeout=10s\n"
                   "    Get Text    id=confirmation    contains    Total: 55.00 EUR\n")
    t = r.get("text", "")
    check("F7d Wait For Condition keeps the normal timeout for its inner getter (not cut to 2.5 s)",
          re.search(r"PASS\s+Wait For Condition", t) is not None, t)
    ft = f.read_text()
    b = s.bash(f"{VENV}/robot -d results tests/v2.robot", fail_event=True)
    check("F8 the short timeout never leaks: the suite file has no timeout line and the plain run (normal 10 s "
          "timeout) passes with the slow element", "Timeout" not in ft and b["rc"] == 0 and "1 passed" in b["text"], b)
    log = [json.loads(x) for x in (ws / ".rf" / "hook2" / "hooks.jsonl").read_text().splitlines()]
    caps = [ms for d in log for ms in (d.get("capture_ms") or [])]
    LAT.setdefault("capture_ms", []).extend(caps)
    check(f"F9 capture latency < 1.5 s (median {statistics.median(caps) if caps else None} ms, max "
          f"{max(caps) if caps else None})", caps and max(caps) < 1500, caps)
    merge_lat(s)
    end_session(s, ws, "F")


REPL_BODY = """Import Library    Browser
Import Library    String
New Browser    chromium    headless=True
New Page    file://{ws}/site/login.html
Click    text=Accept all
Get Text    h1    ==    Sign in
Click    id=nope
Should Be Equal    one    two
.save -t Saved tests/saved.robot"""


def scenario_g(root: Path):
    """v2: REPL / debugger format enforcement for all 4 payload shapes."""
    rc = f"{VENV}/robotcode"
    for agent in ("claude", "codex", "copilot", "opencode"):
        ws = new_ws(root, f"g_{agent}")
        fake_agent = subprocess.Popen(["sleep", "600"]) if agent == "copilot" else None
        s = Sim(agent, ws, env={"RFH2_WATCH_PID": str(fake_agent.pid)} if fake_agent else None)
        s.hook("start", {"source": "startup"})
        r = shell_with_hooks(s, f"{rc} repl")
        if agent in ("claude", "opencode"):
            check(f"G[{agent}] interactive REPL without piped input -> deny with the format card",
                  r["decision"] == "deny" and "INTERACTIVE" in r["reason"] and "<<'RF'" in r["reason"], r)
        else:
            check(f"G[{agent}] interactive REPL (agent can write stdin) -> allowed with a warning",
                  r["decision"] != "deny", r)
        r = shell_with_hooks(s, f"{rc} repl <<RF\n${{x}}=    Set Variable    5\nLog    ${{x}}\nRF")
        check(f"G[{agent}] unquoted heredoc whose only `$` are RF ${{...}} -> delimiter quoted automatically (research "
              "rule C04), the variable survives", r["decision"] == "rewrite" and "<<'RF'" in r.get("command", "")
              and "FAIL" not in r.get("stdout", "x"), r)
        r = shell_with_hooks(s, f"{rc} repl <<RF\n${{x}}=    Set Variable    $HOME\nRF")
        check(f"G[{agent}] unquoted heredoc that also uses shell $VARS -> deny", r["decision"] == "deny"
              and "unquoted heredoc" in r["reason"], r)
        body = REPL_BODY.format(ws=ws)
        r = shell_with_hooks(s, f"{rc} repl <<'RF'\n{body}\nRF")
        cmd = r.get("command", "")
        t = r.get("text", "")
        saved = ws / "tests" / "saved.robot"
        check(f"G[{agent}] REPL command rewritten: --plain --no-history -d .rf/out 2>&1 + .exit + REPL-only "
              "short-timeout listener (nothing typed into the session)", r["decision"] == "rewrite" and "--plain" in cmd
              and "--no-history" in cmd and "-d" in cmd and "2>&1" in cmd and cmd.rstrip().endswith(".exit\nRF")
              and "ROBOT_OPTIONS='--listener" in cmd and "Set Browser Timeout" not in cmd, r)
        check(f"G[{agent}] REPL output parsed: FAIL lines, listener recheck verdict, failing keyword docs "
              "(Browser.Click), import docs, page-gone note", "failure(s)" in t and ".rf/docs/kw/Browser.Click.md" in t
              and "String.md" in t and "page is gone" in t and "[rfh2] MISSING" in t, t)
        check(f"G[{agent}] .save output has no timeout line", saved.is_file()
              and "Timeout" not in saved.read_text() and "Click    text=Accept all" in saved.read_text(),
              saved.read_text() if saved.is_file() else None)
        check(f"G[{agent}] format card delivered exactly once", (t + r.get("pre_text", "")).count("hook card") <= 1
              and sum(o["out"].__repr__().count("hook card") for o in s.outputs) >= 1, [o["ev"] for o in s.outputs])
        if agent == "claude":
            dbg = ws / "tests" / "dbg.robot"
            dbg.write_text("*** Test Cases ***\nT\n    Log    one\n    Should Be Equal    a    b\n")
            r = shell_with_hooks(s, f"{rc} robot-debug tests/dbg.robot <<'RF'\n.where\n.print ${{TEST NAME}}\n"
                                    f".break \"tests/dbg.robot:3\"\n.continue\nRF")
            t = r.get("text", "")
            check("G[claude] robot-debug: flags added, quotes stripped from .break, nothing appended (EOF = continue), "
                  "`* exception` parsed with BuiltIn.Should Be Equal docs", r["decision"] == "rewrite"
                  and ".break tests/dbg.robot:3" in r.get("command", "") and ".exit" not in r.get("command", "")
                  and "Should Be Equal" in t and "BuiltIn.Should_Be_Equal.md" in t, r)
            r = shell_with_hooks(s, f"{rc} repl <<'RF'\nFOR    ${{i}}    IN RANGE    2\n    Log    ${{i}}\nRF")
            check("G[claude] unclosed FOR block in REPL input -> deny (an unclosed block runs nothing)",
                  r["decision"] == "deny" and "END" in r["reason"], r)
            r = shell_with_hooks(s, f"{rc} repl <<'RF'\nLog To Console single\n${{x}}=    Set Variable    1\n"
                                    f"${{d}}=    Create Dictionary    a=1\n...    b=2\n${{x}}\nRF")
            cm = r.get("command", "")
            check("G[claude] body auto-fixes: single space split (known keyword), `...` folded, bare ${x} -> Log To "
                  "Console", r["decision"] == "rewrite" and "Log To Console    single" in cm
                  and "a=1    b=2" in cm and "Log To Console    ${x}" in cm, cm)
            lat = [o["ms"] for o in s.outputs if o["ev"] == "pre"]
            LAT.setdefault("pre_bash_ms", []).extend(lat)
        merge_lat(s)
        if fake_agent is not None:
            fake_agent.kill()
            fake_agent.wait()
        end_session(s, ws, f"G[{agent}]")


def scenario_h(root: Path):
    """v2 guards: install, -P, big reads, suite weakening, valves, loop hint, prompt context, OpenCode caps."""
    for agent in ("claude", "opencode"):
        ws = new_ws(root, f"h_{agent}")
        shutil.copy2(HERE / "repair" / "checkout.robot", ws / "tests" / "checkout.robot")
        s = Sim(agent, ws)
        s.hook("start", {"source": "startup"})
        out, ms = s.hook("prompt", {"prompt": "repair the suite"})
        txt = json.dumps(out)
        check(f"H[{agent}] UserPromptSubmit -> project context (libraries + versions, suites) ({ms:.0f} ms)",
              "Browser 19" in txt and "checkout.robot (3:" in txt and ms < 1000, out)
        out2, _ = s.hook("prompt", {"prompt": "again"})
        check(f"H[{agent}] prompt context only once", not out2, out2)
        r = shell_with_hooks(s, "pip install robotframework-browser")
        check(f"H[{agent}] pip install -> deny", r["decision"] == "deny" and "already installed" in r["reason"], r)
        r = shell_with_hooks(s, "uv pip install requests && npx playwright install chromium")
        r = shell_with_hooks(s, "playwright install chromium")
        check(f"H[{agent}] third install attempt -> replaced by an echo (no deny loop), nothing installed",
              r["decision"] == "rewrite" and r.get("command", "").startswith("echo "), r)
        r = shell_with_hooks(s, f"{VENV}/robot -P lib -d results tests/checkout.robot")
        check(f"H[{agent}] robot -P -> deny with the ${{CURDIR}} fix", r["decision"] == "deny"
              and "${CURDIR}" in r["reason"], r)
        r = shell_with_hooks(s, f"PYTHONPATH=lib {VENV}/robot -d results tests/checkout.robot")
        check(f"H[{agent}] PYTHONPATH=... robot -> deny", r["decision"] == "deny", r)
        big = ws / "results" / "output.xml"
        big.parent.mkdir(exist_ok=True)
        big.write_text("<robot>" + "x" * 300000 + "</robot>")
        decs = [read_with_hooks(s, str(big))["decision"] for _ in range(3)]
        check(f"H[{agent}] Read of a 300 KB output.xml -> deny twice, then allowed (valve)",
              decs == ["deny", "deny", "allow"], decs)
        f = ws / "tests" / "checkout.robot"
        r = s.edit("edit", f, old="Greeting Shows The User\n    Get Text    id=greeting    ==    Hello, erik\n\n", new="")
        check(f"H[{agent}] deleting a test of the existing suite -> deny", r["decision"] == "deny"
              and "removed" in r.get("reason", ""), r)
        r = s.edit("edit", f, old="    Get Text    id=total    ==    Total: 55.00 EUR\n",
                   new="    Run Keyword And Ignore Error    Get Text    id=total    ==    Total: 55.00 EUR\n")
        check(f"H[{agent}] wrapping an assertion in Run Keyword And Ignore Error -> deny", r["decision"] == "deny"
              and "failure-hiding" in r.get("reason", ""), r)
        r = s.edit("edit", f, old="    Get Text    id=result    contains    Total: 40.00 EUR\n", new="")
        check(f"H[{agent}] third weakening attempt on the same file (removing an assertion) -> allowed with a "
              "warning (valve, no deny loop)", r["decision"] != "deny" and "weakens" in (r.get("reason") or "")
              + json.dumps(r.get("pre")), r)
        txt = f.read_text()
        f.write_text(txt.replace("    Get Text    id=result    contains    confirmed\n",
                                 "    Get Text    id=result    contains    confirmed\n"
                                 "    Get Text    id=result    contains    Total: 40.00 EUR\n"))
        info = __import__("guards").suite_info(f.read_text())
        check(f"H[{agent}] suite_info counts tests/assertions of the restored suite", info["tests"] and
              info["asserts"] == 4, info)
        r = s.edit("edit", f, old="    Check Checkbox    id=ship-express\n", new="    Click    label[for=\"ship-express\"]\n")
        check(f"H[{agent}] a real repair edit (selector) -> allowed", r["decision"] in ("allow", "rewrite"), r)
        r = s.edit("edit", f, old="    Click    label[for=\"ship-express\"]\n",
                   new="    Click    label[for=\"ship-express\"]\n    Sleep    3s\n")
        check(f"H[{agent}] a new Sleep in a Browser suite -> refused once with the condition-wait alternative",
              r["decision"] == "deny" and "Wait For Elements State" in r.get("reason", ""), r)
        nk = ws / "tests" / "nokw.robot"
        r = s.edit("write", nk, content="*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nT\n"
                   "    Open Shop\n\nOpen Shop\n    New Page    about:blank\n")
        check(f"H[{agent}] keyword defined without a *** Keywords *** header -> the denial names that root cause",
              r["decision"] == "deny" and "Keywords ***` section header" in r.get("reason", ""), r)
        if agent == "opencode":
            img = ws / ".rf" / "state" / "latest" / "screenshot.jpg"
            img.parent.mkdir(parents=True, exist_ok=True)
            img.write_bytes(b"\xff\xd8\xff")
            rr = read_with_hooks(s, str(img))
            check("H[opencode] reading a screenshot (text-only model) -> refused once, pointed at controls.txt",
                  rr["decision"] == "deny" and "controls.txt" in rr["reason"], rr)
        texts = []
        for i in range(3):
            b = shell_with_hooks(s, f"{VENV}/robot -d results tests/checkout.robot")
            texts.append(b.get("text", ""))
        check(f"H[{agent}] the same test failing 3 times -> exactly one focused LOOP hint (controls.txt, >>>, wait)",
              "LOOP:" in texts[2] and texts[2].count("LOOP:") == 1 and "controls.txt" in texts[2]
              and "LOOP:" not in texts[0], texts[2][:600])
        if agent == "opencode":
            longest = max(len(o["out"].get("text", "")) for o in s.outputs if isinstance(o["out"], dict))
            check(f"H[opencode] every hook output <= 1200 chars (max {longest})", longest <= 1200, longest)
        merge_lat(s)
        end_session(s, ws, f"H[{agent}]")


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rfh-verify").resolve()
    root.mkdir(parents=True, exist_ok=True)
    only = os.environ.get("ONLY", "abcdefgh")
    t0 = time.time()
    for k, fn in (("a", scenario_a), ("b", scenario_b), ("c", scenario_c), ("d", scenario_d), ("e", scenario_e),
                  ("f", scenario_f), ("g", scenario_g), ("h", scenario_h)):
        if k in only:
            try:
                fn(root)
            except Exception as e:
                import traceback
                check(f"scenario {k} crashed", False, traceback.format_exc()[-1500:])
    lat = {k: {"n": len(v), "median_ms": round(statistics.median(v)), "max_ms": round(max(v))} for k, v in LAT.items() if v}
    ok = all(c["ok"] for c in CHECKS)
    res = {"ok": ok, "passed": sum(c["ok"] for c in CHECKS), "total": len(CHECKS), "latency": lat,
           "wall_s": round(time.time() - t0), "checks": CHECKS}
    (HERE / "results_hooks.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("ok", "passed", "total", "wall_s")}), json.dumps(lat, indent=0))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
