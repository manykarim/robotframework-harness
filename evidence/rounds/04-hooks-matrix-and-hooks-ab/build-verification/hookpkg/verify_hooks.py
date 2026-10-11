"""Unit-level verification of the hook harness with simulated agent payloads (no LLM).

  PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright python3 verify/verify_hooks.py [WORKROOT]
Scenarios: A Browser journey (Claude shapes: incremental writes, failing line + fix + resume, iframe, changed
earlier line -> restart, deny on planted errors, deprecated-syntax rewrite, Stop gate block/allow, plain robot run
summary), B repair of an existing failing suite (robot run -> live reproduction -> fix -> resume -> green),
C RequestsLibrary against a local http.server API, D Codex/Copilot/OpenCode payload shapes (apply_patch gate,
rewrite, run), E long step -> "still running" -> delivered later, F SessionEnd cleanup (0 orphans).
Writes verify/results_hooks.json. Exit 0 when every check passes.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "rfharness"))
from simlib import Sim  # noqa: E402
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
    for k in ("exec", "lint"):
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
          and "L3 PASS" in t and "Page now" in t and "id=username" in t, t)
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
                   "    Should Contain    ${msg}    confirmed\n")
    t = r.get("text", "")
    check("A6 async confirmation read too early -> fails at L22 with the read value", "L21 PASS" in t
          and "Processing" in t and ("L22 FAIL" in t), t)
    r = s.edit("edit", f, old="    ${msg}=    Get Text    id=result\n",
               new="    Wait For Condition    Text    id=result    contains    confirmed    timeout=10s\n"
                   "    ${msg}=    Get Text    id=result\n")
    t = r.get("text", "")
    check("A7 wait inserted before an executed line -> test restarted cleanly, all pass", "restarted" in t
          and "L10 PASS" in t and "L23 PASS" in t and "All test lines passed live" in t and "ORD-" in t, t)
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
        s = Sim(agent, ws, env={"RFH_WATCH_PID": str(fake_agent.pid)} if fake_agent else None)
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
    s = Sim("claude", ws, env={"RFH_BUDGET": "4"})
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


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rfh-verify").resolve()
    root.mkdir(parents=True, exist_ok=True)
    only = os.environ.get("ONLY", "abcde")
    t0 = time.time()
    for k, fn in (("a", scenario_a), ("b", scenario_b), ("c", scenario_c), ("d", scenario_d), ("e", scenario_e)):
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
