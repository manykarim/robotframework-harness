"""Unit-level verification of the hook harness (rf_harness.runtime, ported from the v3.2 prototype hookpkg32: v3 + output
profiles, scenario K, v3.2 scenario L) with simulated agent payloads (no LLM). The 224 checks are the prototype's; the
hook runs as `python -m rf_harness.runtime.hook` with this interpreter (tests/simulation/test_simulation.py runs it).
Ported from v2's verify_hooks.py: the v2 checks keep their intent with the v3 lean output format (one line per passed
block, failing line + verdict + NEXT:, captures only on failure / after the last step, kw docs on demand, warnings
instead of uncertain denials); scenario I adds the v3 policy checks (round-5 A/B + round-6 diagnosis) and J the
per-agent context budgets.

  uv run python tests/simulation/verify_hooks.py [WORKROOT]     (ONLY=abc... selects scenarios)
PLAYWRIGHT_BROWSERS_PATH is set like the runtime does (hookcore.playwright_env) when the Browser library has no
bundled chromium but ~/.cache/ms-playwright has it.
Scenarios: A Browser journey (Claude shapes: incremental writes, failing line + fix + resume, iframe, changed
earlier line -> restart, deny on planted errors, deprecated-syntax rewrite, Stop gate block/allow, plain robot run
summary), B repair of an existing failing suite (robot run -> live reproduction -> fix -> resume -> green),
C RequestsLibrary against a local http.server API, D Codex/Copilot/OpenCode payload shapes (apply_patch gate,
rewrite, run), E long step -> "still running" -> delivered later, SessionEnd cleanup (0 orphans);
v2: F failing-keyword docs, page capture (latest + history + dedup), short timeout + slow/missing recheck, import
docs, no timeout leak; G REPL/debugger format (card, rewrites, denials, output parsing, .save strip) for all 4
payload shapes; H guards (install, -P, big read, suite weakening, valves), loop hint, prompt context, OpenCode caps.
Writes WORKROOT/results_hooks.json (and WORKROOT/profile_samples.json). Exit 0 when every check passes.
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

from rf_harness.runtime import guards, hookcore, procs, profiles, proto

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from simlib import Sim, read_with_hooks, shell_with_hooks  # noqa: E402

VENV = Path(sys.executable).parent          # robot / robotcode of the interpreter running the suite
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
    check(f"A SessionStart returns context fast ({ms:.0f} ms)", ms < 1500 and "live RF session" in ctx, out)
    time.sleep(4)
    f = ws / "tests" / "shop.robot"
    r = s.edit("write", f, content=JOURNEY_HEAD)
    t = r.get("text", "")
    check("A1 first write: suite setup + 3 lines PASS as ONE block line + one page line (<= 250 chars)",
          r["decision"] == "allow" and "L3-L12 PASS (4 lines)" in t and 'Page "Shop - Sign in"' in t
          and len(t) <= 250, t)
    r = s.edit("edit", f, old="    Fill Text    id=username    alice\n",
               new="    Fill Text    id=username    alice\n    Fill Text    id=password    secret\n"
                   "    Click    data-test=signin\n    Get Text    id=greeting    ==    Hello, alice\n")
    t = r.get("text", "")
    check("A2 appended lines run (only the new ones), navigation summary", "L13-L15 PASS" in t
          and "L12" not in t and "order.html" in t and "iframes: id=pay-frame" in t, t)
    r = s.edit("edit", f, old="    Get Text    id=greeting    ==    Hello, alice\n",
               new="    Get Text    id=greeting    ==    Hello, alice\n    Check Checkbox    id=ship-express\n"
                   "    Select Options By    id=country    label    Norway\n")
    t = r.get("text", "")
    check("A3 failing line: hidden radio -> NOT RUN NOT_VISIBLE with the label to click", "L16 NOT RUN" in t
          and "NOT_VISIBLE" in t and 'label[for="ship-express"]' in t and "NEXT: line 16" in t, t)
    r = s.edit("edit", f, old="    Check Checkbox    id=ship-express\n", new="    Click    label[for=\"ship-express\"]\n")
    t = r.get("text", "")
    check("A4 fix -> resumes AT the fixed line in the open page (L16, L17 only)", "L16-L17 PASS" in t
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
    check("A6 async confirmation read too early -> fails at L22 with the read value", "L18-L21 PASS" in t
          and "Processing" in t and ("L22 FAIL" in t), t)
    r = s.edit("edit", f, old="    ${msg}=    Get Text    id=result\n",
               new="    Wait For Condition    Text    id=result    contains    Done    timeout=10s\n"
                   "    ${msg}=    Get Text    id=confirmation\n")
    t = r.get("text", "")
    check("A7 replacing an executed PROBE line (Get Text) by a wait + new getter -> no restart needed, continues "
          "in the page; stops at L23: actual (the real confirmation text) vs expected", "restarted" not in t
          and "L21-L22 PASS" in t and "L23 FAIL" in t and "actual 'Order ORD-" in t and "expected 'Done'" in t, t)
    r = s.edit("edit", f, old="    Should Contain    ${msg}    Done\n", new="    Should Contain    ${msg}    confirmed\n")
    t = r.get("text", "")
    check("A7b fix the expected text -> resumes at L23, all pass", "L23 PASS" in t and "All lines pass live" in t, t)
    # changed earlier (already executed) line -> restart
    r = s.edit("edit", f, old="    Fill Text    id=username    alice\n", new="    Fill Text    id=username    bob\n")
    t = r.get("text", "")
    check("A8 changed an executed earlier line -> test restarted (L10 New Page re-ran), stops at the stale greeting",
          "restarted" in t and ("L10 PASS" in t or "L10-" in t) and "L15 FAIL" in t and "Hello, bob" in t, t)
    r = s.edit("edit", f, old="    Get Text    id=greeting    ==    Hello, alice\n",
               new="    Get Text    id=greeting    ==    Hello, bob\n")
    t = r.get("text", "")
    check("A9 fix the assertion -> resumes from L15 to the end", "L15-L23 PASS" in t and "L10" not in t, t)
    # deny on planted errors (file unchanged)
    before = f.read_text()
    r = s.edit("edit", f, old="    Should Contain    ${msg}    confirmed\n",
               new="    Should Contain    ${msg}    confirmed\n    Clik    id=place\n    Fill Text    id=card\n"
                   "    FOR    ${i}    IN RANGE    2\n        Log    ${i}\n")
    rs = r.get("reason", "")
    check("A10 PreToolUse denies only the CERTAIN hard error (missing END: ModelError) with its line number and "
          "lists the uncertain ones (typo, arg count) as not blocking; file unchanged",
          r["decision"] == "deny" and ":26 ModelError" in rs and "END" in rs and "not blocking" in rs
          and "L24 KeywordNotFound" in rs and "L25 DataError" in rs and f.read_text() == before
          and r["pre_ms"] < 1000, rs)
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
    check("A16 whole-file write: test 1 passes, test 2 runs (fresh Test Setup page) and fails at L17: actual vs "
          "expected", "'Login Requires Password' L3-L10 PASS" in t and "L17 FAIL" in t and "actual 'Hello, carol'" in t, t)
    r = s.edit("edit", w, old="Hello, Carol", new="Hello, carol")
    t = r.get("text", "")
    check("A17 fix -> only L17 re-runs", "L17 PASS" in t and "L13" not in t and "All lines pass live" in t, t)
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
    check("B1 failing plain run -> failure summary + live reproduction stopped at the failing line with a similar "
          "control (<= 700 chars)", b["rc"] != 0 and "2 failed" in t and "Reproduced live" in t and "L13 NOT RUN" in t
          and "data-test=signin" in t and "no element matched `id=signin-button`" in t and len(t) <= 700, t)
    r = s.edit("edit", f, old="    Click    id=signin-button\n", new="    Click    data-test=signin\n")
    t = r.get("text", "")
    check("B2 fix the reproduced line -> resumes at L13 in the open page and passes", "L13-L14 PASS" in t
          and "L11" not in t, t)
    r = s.edit("edit", f, old="label    Sweden", new="label    Norway")
    t = r.get("text", "")
    check("B3 edit inside the never-run second test -> runs it from its setup (setup L4 .. L20)",
          "L4-L20 PASS" in t or "L19" in t, t)
    b2 = s.bash(f"{VENV}/robot -d results tests/broken.robot", fail_event=True)
    check("B4 plain run green after repair -> verified", b2["rc"] == 0 and "verified" in b2["text"], b2)
    out, _ = s.hook("stop", {"stop_hook_active": False})
    check("B5 Stop allows after the green run", not out, out)
    r = s.edit("edit", f, old="    Fill Text    id=username    ${name}\n",
               new="    Fill Text    id=username    ${name}\n    Log    signing in ${name}\n")
    t = r.get("text", "")
    check("B6 edit inside a user keyword -> the first test calling it re-runs from the top", "keyword" in t
          and "changed: first test using it re-run" in t and "L3-L20 PASS" in t, t)
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
          "L7 FAIL" in t and "(inside Click at tests/kwfail.robot:14)" in t and "or tests/kwfail.robot:14" in t, t)
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
        check("C1 API test: GET passes, wrong expected value fails at L9: actual vs expected", "L3-L8 PASS" in t
              and "L9 FAIL" in t and "actual 'Apple' vs expected 'Pear'" in t, t)
        r = s.edit("edit", f, old="[0][name]    Pear", new="[0][name]    Apple")
        t = r.get("text", "")
        check("C2 fix -> resumes at L9", "L9 PASS" in t and "L7" not in t, t)
        r = s.edit("edit", f, old="[0][name]    Apple\n", new="[0][name]    Apple\n    ${resp}=    POST On Session    api    /api/items    json=${{ {'name': 'Kiwi'} }}    expected_status=201\n    Should Be Equal    ${resp.json()}[name]    Kiwi\n")
        t = r.get("text", "")
        check("C3 POST with json= body appended -> PASS (returned value shown)", "L10-L11 PASS" in t
              and "<Response [201]>" in t, t)
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
        check(f"D[{agent}] planted typo in a new file -> v3: allowed with a one-line 'not blocking' warning (L8 "
              "KeywordNotFound) delivered to the agent; the live run stops at L8", r["decision"] == "allow"
              and "L8 KeywordNotFound" in (r.get("reason", "") + r.get("text", "")) and "not blocking" in
              (r.get("reason", "") + r.get("text", "")) and "L8 NOT RUN" in r.get("text", "") and f.exists(), r)
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
    check("E2 next hook event delivers the earlier result, then runs the new line", "[earlier run " in t
          and "L5 PASS" in t and "L6 PASS" in t, t)
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
    check("F1 v3: ONE capture after the last step of the edit (not after every page-changing step): "
          "latest/{page.txt,controls.txt,aria.yaml,source.html,screenshot.jpg} + 1 history dir; the output names "
          ".rf/state/latest/ (first time) without sizes or source",
          {"page.txt", "controls.txt", "aria.yaml", "source.html", "screenshot.jpg"} <= set(names)
          and len(_dirs(ws)) == 1 and ".rf/state/latest/" in t and "<html" not in t and len(t) <= 250,
          {"names": names, "dirs": _dirs(ws), "text": t})
    check("F2 the end-of-run capture lands on the page AFTER the timer-triggered navigation (settle at the end "
          "only) and page.txt has the visible text", "order.html" in (latest / "page.txt").read_text(errors="replace")
          and "visible text" in (latest / "page.txt").read_text(errors="replace")
          and "Hello, alice" in (latest / "page.txt").read_text(errors="replace"),
          (latest / "page.txt").read_text(errors="replace"))
    n_dirs = len(_dirs(ws))
    r = s.edit("edit", f, old="    Click    data-test=signin\n", new="    Click    data-test=signin\n"
               "    Fill Text    id=pay-frame >>> id=card    4242\n")
    check("F3 a step that does not change the page (Fill Text) -> no new history dir (dedup)",
          len(_dirs(ws)) == n_dirs, {"before": n_dirs, "after": _dirs(ws), "text": r.get("text")})
    r = s.edit("edit", f, old="    Fill Text    id=pay-frame >>> id=card    4242\n",
               new="    Fill Text    id=pay-frame >>> id=card    4242\n    Click    id=no-such-button\n")
    t = r.get("text", "")
    kwf = ws / ".rf" / "docs" / "kw" / "Browser.Click.md"
    time.sleep(1.5)
    check("F4 bad locator on a stable page: NOT_FOUND after the SHORT timeout -> MISSING without a long re-check "
          "(< 6 s), signature inline, the keyword doc only ON DEMAND (no file yet)", "NOT RUN" in t
          and "verdict: MISSING" in t and "Click(" in t and ".rf/docs/kw/Browser.Click.md" in t and not kwf.is_file()
          and r["post_ms"] < 6000, {"t": t, "kw": kwf.exists(), "post_ms": r["post_ms"]})
    rr = read_with_hooks(s, str(kwf))
    check("F4b reading .rf/docs/kw/Browser.Click.md -> PreToolUse writes it on demand before the read",
          rr["decision"] == "allow" and kwf.is_file() and "Simulates mouse click" in kwf.read_text(errors="replace"),
          {"rr": rr, "exists": kwf.exists()})
    check("F5 failure output: no source inlined, <= 3 similar controls, page line", "<body" not in t
          and t.count("    \"") <= 3 and "Page " in t and len(t) <= 700, t)
    r = s.edit("edit", f, old="    Click    id=no-such-button\n", new="    Click    id=pay-frame >>> id=confirm-card\n"
               "    Click    label[for=\"ship-express\"]\n    Select Options By    id=country    label    Norway\n"
               "    Click    data-test=place-order\n    Get Text    id=confirmation    contains    Total: 55.00 EUR\n")
    t = r.get("text", "")
    tj = ws / ".rf" / "exec" / "timeouts.json"
    tmo = json.loads(tj.read_text()) if tj.is_file() else {}
    check("F6 genuinely late element (absent, appears 4 s after the navigation, timer scheduled at load): NOT an "
          "instant MISSING -> re-check -> SLOW, the line PASSES on the re-check, no wait advice (4 s << 10 s); the page "
          "keeps the normal timeout and the origin learns ~1.5 x 4 s", re.search(r"L21 PASS after [345]\.\d s", t)
          is not None and "Wait For Elements State" not in t and any("done.html" in k for k in tmo.get("no_shorten", {}))
          and any(5.0 <= v <= 10 for v in (tmo.get("origin_short") or {}).values()), {"t": t, "tmo": tmo})
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
          "restarted" not in t and "PASS" in t and "FAIL" not in t, t)
    r = s.edit("edit", f, old="    Fill Text    id=username    alice\n", new="    Fill Text    id=username    bob\n")
    t = r.get("text", "")
    check("F7c changing an executed line restarts the test in a FRESH browser context",
          "test restarted: line 13 changed, fresh browser context" in t, t)
    r = s.edit("edit", f, old="    Get Text    id=confirmation    contains    Total: 55.00 EUR\n",
               new="    Wait For Condition    Text    id=confirmation    contains    55.00    timeout=10s\n"
                   "    Get Text    id=confirmation    contains    Total: 55.00 EUR\n")
    t = r.get("text", "")
    check("F7d Wait For Condition keeps the normal timeout for its inner getter (not cut to 2.5 s)",
          re.search(r"L2\d(-L2\d)? PASS", t) is not None and "FAIL" not in t and "NOT RUN" not in t, t)
    ft = f.read_text()
    b = s.bash(f"{VENV}/robot -d results tests/v2.robot", fail_event=True)
    check("F8 the short timeout never leaks: the suite file has no timeout line and the plain run (normal 10 s "
          "timeout) passes with the slow element", "Timeout" not in ft and b["rc"] == 0 and "1 passed" in b["text"], b)
    log = [json.loads(x) for x in (ws / ".rf" / "hook" / "hooks.jsonl").read_text().splitlines()]
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
        s = Sim(agent, ws, env={"RFH_WATCH_PID": str(fake_agent.pid)} if fake_agent else None)
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
              "(Browser.Click), import docs, page-gone note", "failure(s)" in t and "Browser.Click" in t
              and "String.md" in t and "page is gone" in t and "[rfh] MISSING" in t, t)
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
                  and "BuiltIn.Should Be Equal" in t, r)
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
        check(f"H[{agent}] robot -P -> v3: allowed with a one-line warning naming the ${{CURDIR}} fix",
              r["decision"] == "allow" and "${CURDIR}" in r["reason"] and "not blocking" in r["reason"]
              and r["reason"].count("\n") == 0, r)
        r = shell_with_hooks(s, f"PYTHONPATH=lib {VENV}/robot -d results tests/checkout.robot")
        check(f"H[{agent}] PYTHONPATH=... robot -> v3: allowed with the warning", r["decision"] == "allow"
              and "PYTHONPATH" in r["reason"], r)
        big = ws / "results" / "output.xml"
        big.parent.mkdir(exist_ok=True)
        big.write_text("<robot>" + "x" * 300000 + "</robot>")
        decs = [read_with_hooks(s, str(big))["decision"] for _ in range(3)]
        rr = read_with_hooks(s, str(big))
        check(f"H[{agent}] Read of a 300 KB output.xml -> v3: allowed with a one-line warning (robotcode results / "
              "Grep)", decs == ["allow", "allow", "allow"] and "not blocking" in rr["reason"]
              and "robotcode results" in rr["reason"], {"decs": decs, "rr": rr})
        f = ws / "tests" / "checkout.robot"
        r = s.edit("edit", f, old="Greeting Shows The User\n    Get Text    id=greeting    ==    Hello, erik\n\n", new="")
        check(f"H[{agent}] deleting a test of the existing suite -> deny", r["decision"] == "deny"
              and "removed" in r.get("reason", ""), r)
        r = s.edit("edit", f, old="    Get Text    id=total    ==    Total: 55.00 EUR\n",
                   new="    Run Keyword And Ignore Error    Get Text    id=total    ==    Total: 55.00 EUR\n")
        check(f"H[{agent}] wrapping an assertion in Run Keyword And Ignore Error -> deny", r["decision"] == "deny"
              and "failure-hiding" in r.get("reason", ""), r)
        r = s.edit("edit", f, old="    Get Text    id=result    contains    Total: 40.00 EUR\n", new="")
        check(f"H[{agent}] removing an assertion (uncertain: regex count) -> v3: allowed at once with a one-line "
              "warning", r["decision"] != "deny" and "fewer assertions" in (r.get("reason") or "")
              + json.dumps(r.get("pre")), r)
        txt = f.read_text()
        f.write_text(txt.replace("    Get Text    id=result    contains    confirmed\n",
                                 "    Get Text    id=result    contains    confirmed\n"
                                 "    Get Text    id=result    contains    Total: 40.00 EUR\n"))
        info = guards.suite_info(f.read_text())
        check(f"H[{agent}] suite_info counts tests/assertions of the restored suite", info["tests"] and
              info["asserts"] == 4, info)
        r = s.edit("edit", f, old="    Check Checkbox    id=ship-express\n", new="    Click    label[for=\"ship-express\"]\n")
        check(f"H[{agent}] a real repair edit (selector) -> allowed", r["decision"] in ("allow", "rewrite"), r)
        r = s.edit("edit", f, old="    Click    label[for=\"ship-express\"]\n",
                   new="    Click    label[for=\"ship-express\"]\n    Sleep    3s\n")
        check(f"H[{agent}] a new Sleep in a Browser suite -> v3: allowed with a warning naming the condition wait",
              r["decision"] != "deny" and "Wait For Elements State" in r.get("reason", "")
              and "not blocking" in r.get("reason", ""), r)
        nk = ws / "tests" / "nokw.robot"
        r = s.edit("write", nk, content="*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nT\n"
                   "    Open Shop\n\nOpen Shop\n    New Page    about:blank\n")
        check(f"H[{agent}] keyword defined without a *** Keywords *** header -> v3: allowed; the warning names that "
              "root cause", r["decision"] != "deny" and "Keywords ***` section header" in r.get("reason", ""), r)
        if agent == "opencode":
            img = ws / ".rf" / "state" / "latest" / "screenshot.jpg"
            img.parent.mkdir(parents=True, exist_ok=True)
            img.write_bytes(b"\xff\xd8\xff")
            rr = read_with_hooks(s, str(img))
            check("H[opencode] reading a screenshot (text-only model) -> v3: allowed with a warning pointing at "
                  "page.txt / controls.txt", rr["decision"] == "allow" and "page.txt" in rr["reason"], rr)
        texts = []
        for _ in range(3):
            b = shell_with_hooks(s, f"{VENV}/robot -d results tests/checkout.robot")
            texts.append(b.get("text", ""))
        loops = [l for x in texts for l in x.splitlines() if l.startswith("LOOP:")]
        check(f"H[{agent}] the same plain-run failure again and again (the -P / PYTHONPATH runs count too) -> exactly "
              "ONE specific LOOP hint (<= 200 chars, selector -> controls.txt), not repeated",
              len(loops) == 1 and "controls.txt" in loops[0] and len(loops[0]) <= 200, texts)
        if agent == "opencode":
            posts = [len(o["out"].get("text", "")) for o in s.outputs if isinstance(o["out"], dict) and o["ev"] == "post"
                     and "hook card" not in o["out"].get("text", "")]
            longest = max(posts) if posts else 0
            check(f"H[opencode] every PostToolUse output <= 600 chars (max {longest})", longest <= 600, longest)
        merge_lat(s)
        end_session(s, ws, f"H[{agent}]")

STYLED_HEAD = """*** Settings ***
Library    Browser
Suite Setup    New Browser    chromium    headless=True

*** Test Cases ***
Applicant
    New Page    file://${CURDIR}/../site/styled.html
    Fill Text    id=name    Alice
"""


def _hooklog(ws: Path) -> list:
    try:
        return [json.loads(x) for x in (ws / ".rf" / "hook" / "hooks.jsonl").read_text().splitlines()]
    except OSError:
        return []


def scenario_i(root: Path):
    """v3 policy (round-5 A/B + round-6 diagnosis): Playwright-log classes before any re-check, SLOW only for absent ->
    present, instant MISSING on a stable page, adaptive timeouts, live/plain parity (no hidden waits), captures only on
    failure + end of run, value failures as actual vs expected, page.txt visible text, specific loop hints, kw docs on
    demand, signature once, race-aware reproduction, Claude budgets."""
    ws = new_ws(root, "i_v3")
    s = Sim("claude", ws)
    s.hook("start", {"source": "startup"})
    time.sleep(3)
    f = ws / "tests" / "styled.robot"
    r = s.edit("write", f, content=STYLED_HEAD)
    t = r.get("text", "")
    log0 = len(_hooklog(ws))
    check("I0 first write passes: one block line + page line (<= 250 chars), exactly one capture (end of run)",
          "L3-L8 PASS" in t and len(t) <= 250 and len(_dirs(ws)) == 1, {"t": t, "dirs": _dirs(ws)})
    # ---- I1 styled radio covered by a span (in the viewport): guard sees the coverer -> COVERED + label, no re-check
    r = s.edit("edit", f, old="    Fill Text    id=name    Alice\n", new="    Fill Text    id=name    Alice\n"
               "    Click    id=gender-female\n")
    t = r.get("text", "")
    lg = _hooklog(ws)[log0:]
    check("I1 click on a radio covered by a styled <span> -> verdict COVERED with the input's label "
          "(`label[for=\"gender-female\"]`), NO re-check / SLOW, NEXT names the label",
          "COVERED" in t and 'label[for="gender-female"]' in t and "SLOW" not in t
          and not any(d.get("rechecks") for d in lg) and "NEXT:" in t, {"t": t, "log": lg[-1:]})
    r = s.edit("edit", f, old="    Click    id=gender-female\n", new="    Click    label[for=\"gender-female\"]\n")
    check("I2 fix with the label -> PASS", "L9 PASS" in r.get("text", ""), r.get("text"))
    # ---- I3 covered checkbox far below the fold: the guard cannot see it, Playwright's call log tells
    log0 = len(_hooklog(ws))
    r = s.edit("edit", f, old="    Click    label[for=\"gender-female\"]\n", new="    Click    label[for=\"gender-female\"]\n"
               "    Click    id=newsletter\n")
    t = r.get("text", "")
    lg = _hooklog(ws)[log0:]
    check("I3 covered checkbox below the fold -> Playwright log classified BEFORE any re-check: COVERED with the "
          "verbatim '... intercepts pointer events' fragment + label suggestion, no SLOW / re-check",
          "COVERED" in t and "intercepts pointer events" in t and 'label[for="newsletter"]' in t and "SLOW" not in t
          and not any(d.get("rechecks") for d in lg), {"t": t, "log": lg[-1:]})
    r = s.edit("edit", f, old="    Click    id=newsletter\n", new="    Click    label[for=\"newsletter\"]\n")
    check("I4 fix with the label -> PASS", "L10 PASS" in r.get("text", ""), r.get("text"))
    # ---- I5 genuinely late element (absent -> present after 4 s): SLOW, passes on the re-check, adaptive timeout
    log0 = len(_hooklog(ws))
    r = s.edit("edit", f, old="    Click    label[for=\"newsletter\"]\n", new="    Click    label[for=\"newsletter\"]\n"
               "    Click    id=load\n    Click    id=late-btn\n    Get Text    id=step    ==    Step 2\n")
    t = r.get("text", "")
    lg = _hooklog(ws)[log0:]
    tj = ws / ".rf" / "exec" / "timeouts.json"
    tmo = json.loads(tj.read_text()) if tj.is_file() else {}
    ch = [c for d in lg for c in (d.get("tmo_changes") or [])]
    check("I5 element absent then present after ~4 s -> SLOW only now (absent -> present), the line PASSES on the "
          "re-check; the page keeps the normal timeout, the origin learns ~1.5 x 4 s (logged as an adaptive change)",
          re.search(r"L12 PASS after [345]\.\d s", t) is not None and "L13 PASS" in t and ch
          and any("styled.html" in k for k in tmo.get("no_shorten", {}))
          and any(5.0 <= v <= 10.0 for v in (tmo.get("origin_short") or {}).values()), {"t": t, "tmo": tmo, "ch": ch})
    # ---- I6 value assertion: actual vs expected + is the expected text on the page; page.txt visible text
    r = s.edit("edit", f, old="    Get Text    id=step    ==    Step 2\n", new="    Get Text    id=step    ==    Step 2\n"
               "    Get Text    id=total    ==    Total: 99.00 EUR\n")
    t = r.get("text", "")
    pt = (ws / ".rf" / "state" / "latest" / "page.txt").read_text(errors="replace")
    check("I6 value failure -> inline actual vs expected + 'expected text is NOT on the page', no timing advice",
          "actual 'Total: 40.00 EUR' vs expected 'Total: 99.00 EUR'" in t and "NOT on the page" in t
          and "Wait For" not in t and "SLOW" not in t, t)
    check("I7 page.txt holds the visible page text (<= 4 KB)", "visible text" in pt and "Total: 40.00 EUR" in pt
          and "Applicant" in pt and len(pt) < 5000, pt[:400])
    # ---- I8 the same value failure again and again -> ONE specific loop hint (<= 200 chars), never timing advice
    loops = []
    for exp in ("98.00", "97.00", "96.00", "95.00"):
        cur = re.search(r"Total: \d\d\.00 EUR\n", f.read_text().split("id=total")[1]).group(0)
        r = s.edit("edit", f, old=f"id=total    ==    {cur}", new=f"id=total    ==    Total: {exp} EUR\n")
        loops.append(r.get("text", ""))
    hint_lines = [l for x in loops for l in x.splitlines() if l.startswith("LOOP:")]
    check("I8 the same value check failing again and again -> exactly ONE loop hint (<= 200 chars, actual vs "
          "expected, no wait advice), not repeated", len(hint_lines) == 1 and len(hint_lines[0]) <= 200
          and "actual" in hint_lines[0] and "Wait For" not in hint_lines[0], {"hints": hint_lines, "last": loops[-1]})
    r = s.edit("edit", f, old="Total: 95.00 EUR", new="Total: 40.00 EUR")
    # ---- I9 live vs plain parity on a racy step: no settle / capture between steps
    log0 = len(_hooklog(ws))
    r = s.edit("edit", f, old="    Get Text    id=total    ==    Total: 40.00 EUR\n",
               new="    Get Text    id=total    ==    Total: 40.00 EUR\n    Click    id=calc\n"
                   "    Get Text    id=result    ==    42\n")
    t = r.get("text", "")
    lg = _hooklog(ws)[log0:]
    caps = sum(int(d.get("captures") or 0) for d in lg)
    check("I9 racy step (result set 1.6 s after the click, assertion retries ~1 s): the live run FAILS like the "
          "plain run would (no hidden settle/capture between steps; one capture = the failure)",
          "L16 FAIL" in t and "L15 PASS" in t and caps <= 1, {"t": t, "captures": caps})
    race = ws / "tests" / "race.robot"
    race.write_text(STYLED_HEAD.replace("Applicant", "Race") + "    Click    id=calc\n    Get Text    id=result    ==    42\n")
    b = shell_with_hooks(s, f"{VENV}/robot -d results/race tests/race.robot")
    check("I9b the same racy steps fail the plain run too (parity) and the live reproduction reproduces it",
          b.get("rc") == 1 and "Reproduced live" in b.get("text", "") and "L10 FAIL" in b.get("text", ""), b.get("text"))
    r = s.edit("edit", f, old="    Get Text    id=result    ==    42\n",
               new="    Wait For Condition    Text    id=result    ==    42    timeout=10s\n")
    check("I9c the condition wait fixes it live", "L16 PASS" in r.get("text", ""), r.get("text"))
    # ---- I10 instant MISSING on a stable page (no long re-check) -- another page: styled.html keeps the normal timeout
    q = ws / "tests" / "quiet.robot"
    s.edit("write", q, content="*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nQuiet\n"
                               "    New Page    file://${CURDIR}/../site/login.html\n")
    time.sleep(6.5)
    log0 = len(_hooklog(ws))
    r = s.edit("edit", q, old="login.html\n", new="login.html\n    Click    id=no-such\n")
    t = r.get("text", "")
    lg = _hooklog(ws)[log0:]
    tmo = json.loads((ws / ".rf" / "exec" / "timeouts.json").read_text())
    probe_s = max([2.5] + list((tmo.get("origin_short") or {}).values()))   # file:// learned ~6 s in I5
    check(f"I10 missing selector on a quiet page -> MISSING right after the probe (origin short {probe_s} s), no "
          f"re-check wait (hook {r.get('post_ms')} ms < probe + 2.5 s; logged as an instant MISSING)",
          "verdict: MISSING" in t and "did not change" in t and r.get("post_ms", 99999) < (probe_s + 2.5) * 1000
          and any(d.get("rechecks_skipped") for d in lg), {"t": t, "post_ms": r.get("post_ms"), "log": lg[-1:]})
    r = s.edit("edit", f, old="    Wait For Condition    Text    id=result    ==    42    timeout=10s\n",
               new="    Wait For Condition    Text    id=result    ==    42    timeout=10s\n    Click    id=no-such\n")
    # ---- I11 kw docs on demand, signature once per session
    kwdir = ws / ".rf" / "docs" / "kw"
    sig_outs = [o for o in s.outputs if o["ev"] == "post" and "keyword: Click(" in json.dumps(o["out"])]
    check("I11 no keyword-doc files written by failures (on demand only); the Click signature appeared once",
          not (kwdir.is_dir() and list(kwdir.glob("*.md"))) and len(sig_outs) == 1,
          {"files": [x.name for x in kwdir.glob("*.md")] if kwdir.is_dir() else [], "sig_outs": len(sig_outs)})
    # ---- I12 budgets (Claude): success <= 250, failure <= 700 for every edit output
    posts = [_ctx_of(o) for o in s.outputs if o["ev"] == "post"]
    over = [(len(x), x[:80]) for x in posts if len(x) > 700 or ("FAIL" not in x and "NOT RUN" not in x
                                                               and "LOOP" not in x and len(x) > 250)]
    check(f"I12 Claude budgets: every PostToolUse output within 250 (pass) / 700 (fail) chars "
          f"(max {max((len(x) for x in posts), default=0)})", not over, over)
    # ---- I13 race-aware reproduction: plain fail, live pass -> NOT reproduced, then no more reproductions
    flag = ws / "tests" / "flag.txt"
    rf = ws / "tests" / "flaky.robot"
    rf.write_text("*** Settings ***\nLibrary    OperatingSystem\n\n*** Test Cases ***\nFlag Exists\n"
                  "    File Should Exist    ${CURDIR}/flag.txt\n")
    b = shell_with_hooks(s, f"{VENV}/robot -d results/flaky tests/flaky.robot; touch tests/flag.txt")
    t1 = b.get("text", "")
    flag.unlink()
    b = shell_with_hooks(s, f"{VENV}/robot -d results/flaky tests/flaky.robot")
    t2 = b.get("text", "")
    check("I13 plain run fails but the live reproduction PASSES -> 'NOT reproduced ... timing race' (not 'stopped at "
          "its first failure'); the next failing plain run is not reproduced again",
          "NOT reproduced" in t1 and "race" in t1 and "Reproduced live" not in t1 and "Reproduced" not in t2
          and "1 failed" in t2, {"t1": t1, "t2": t2})
    # ---- I14 denial relaxation summary: unknown keyword allowed + warned, live run shows the real error
    r = s.edit("edit", f, old="    Click    id=no-such\n", new="    Clikc    id=calc\n")
    check("I14 unknown keyword (uncertain) -> allowed + one-line warning, the live run reports RF's own error",
          r["decision"] == "allow" and "not blocking" in r.get("reason", "") and "L17 NOT RUN" in r.get("text", ""),
          r)
    merge_lat(s)
    end_session(s, ws, "I")


def _ctx_of(o: dict) -> str:
    out = o.get("out") or {}
    if "text" in out:
        return out.get("text") or ""
    h = out.get("hookSpecificOutput") or {}
    return h.get("additionalContext", "") or out.get("additionalContext", "") or out.get("reason", "")


def scenario_j(root: Path):
    """per-agent budgets on the same failing + passing edits: codex 250/700, opencode 250/600 with NEXT: first."""
    for agent, (ok_cap, fail_cap) in (("codex", (250, 700)), ("opencode", (250, 600))):
        ws = new_ws(root, f"j_{agent}")
        s = Sim(agent, ws)
        s.hook("start", {"source": "startup"})
        time.sleep(3)
        f = ws / "tests" / "budget.robot"
        r = s.edit("write", f, content=JOURNEY_HEAD)
        t_ok = r.get("text", "")
        r = s.edit("edit", f, old="    Fill Text    id=username    alice\n",
                   new="    Fill Text    id=username    alice\n    Click    id=no-such-signin\n")
        t_fail = r.get("text", "")
        first = t_fail.splitlines()[0] if t_fail else ""
        check(f"J[{agent}] pass output <= {ok_cap} ({len(t_ok)}), failure output <= {fail_cap} ({len(t_fail)}) with "
              "verdict + NEXT" + (" as the FIRST line" if agent == "opencode" else ""),
              len(t_ok) <= ok_cap and "PASS" in t_ok and len(t_fail) <= fail_cap and "verdict: MISSING" in t_fail
              and "NEXT:" in t_fail and (first.startswith("NEXT:") if agent == "opencode" else True),
              {"ok": t_ok, "fail": t_fail})
        merge_lat(s)
        end_session(s, ws, f"J[{agent}]")


# ------------------------------------------------------------------------------------------------ v3.1 profiles
_NOMODEL = {"ANTHROPIC_MODEL": "", "RFH_MODEL": "", "RFH_PROFILE": "", "OPENCODE_MODEL": "", "CODEX_MODEL": ""}


def _prof_log(ws: Path) -> list:
    return [(d.get("event"), d.get("profile"), d.get("profile_src"), d.get("model")) for d in _hooklog(ws)
            if d.get("profile")]


def scenario_k(root: Path):
    """v3.1 output profiles: selection rules (model id / env / agent default / payload / transcript), the rich
    rendering (controls list after navigation, <= 8 nearest controls, signature + first doc sentence and a
    failure-type hint EVERY time, NEXT, ~1,200 chars, OpenCode guidance first), lean unchanged, profile in the hook log."""
    table = {"claude-haiku-5-5": "lean", "anthropic/claude-haiku-5.5": "lean", "claude-sonnet-5": "lean",
             "gpt-5.6-luna": "lean", "openai/gpt-5.2-codex": "lean", "o3": "lean",
             "minimax-coding-plan/MiniMax-M2.5": "rich", "deepseek/deepseek-v4.1-flash": "rich",
             "qwen/qwen3.8-flash": "rich", "z-ai/glm-5.3-flash": "rich", "google/gemini-3.8-flash": "rich",
             "openrouter/google/gemini-3.8-flash": "rich", "moonshotai/kimi-k2.6": "rich",
             "mistralai/devstral-2": "rich"}
    got = {m: profiles.classify(m)[0] for m in table}
    check("K0 model id -> profile: anthropic/claude/GPT/codex -> lean; MiniMax/DeepSeek/Qwen/GLM/Gemini/Kimi/unknown "
          "-> rich; no model -> None", got == table and profiles.classify("")[0] is None,
          {m: (got[m], table[m]) for m in table if got[m] != table[m]})
    e0 = dict(_NOMODEL)
    d_env = profiles.detect("claude", {}, {}, {**e0, "RFH_PROFILE": "rich", "ANTHROPIC_MODEL": "claude-haiku-5-5"})
    d_def = {a: profiles.detect(a, {}, {}, {**e0, "CODEX_HOME": str(root)})["profile"]
             for a in ("claude", "codex", "opencode", "copilot")}
    d_pay = profiles.detect("opencode", {"model": {"providerID": "minimax-coding-plan", "modelID": "MiniMax-M2.5"}}, {},
                            e0)
    d_am = profiles.detect("claude", {}, {}, {**e0, "ANTHROPIC_MODEL": "z-ai/glm-5.3-flash"})
    tr = root / "k_transcript.jsonl"
    tr.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-haiku-5-5", "content": []}}) + "\n")
    d_tr = profiles.detect("claude", {"transcript_path": str(tr)}, {}, e0)
    check("K0b detection: RFH_PROFILE wins over the model; agent defaults claude/codex/copilot lean, opencode rich; "
          "OpenCode {providerID, modelID} payload; ANTHROPIC_MODEL (OpenRouter routing); Claude transcript model",
          d_env["profile"] == "rich" and d_env["src"] == "env"
          and d_def == {"claude": "lean", "codex": "lean", "opencode": "rich", "copilot": "lean"}
          and d_pay["profile"] == "rich" and d_pay["model"] == "minimax-coding-plan/MiniMax-M2.5"
          and d_pay["src"] == "model:payload" and d_am["profile"] == "rich" and d_am["src"] == "model:ANTHROPIC_MODEL"
          and d_tr["profile"] == "lean" and d_tr["src"] == "model:transcript",
          {"env": d_env, "def": d_def, "pay": d_pay, "am": d_am, "tr": d_tr})

    # ---- rich: Claude Code routed to an OpenRouter model (ANTHROPIC_MODEL)
    ws = new_ws(root, "k_rich")
    s = Sim("claude", ws, env={**_NOMODEL, "ANTHROPIC_MODEL": "deepseek/deepseek-v4.1-flash"})
    s.hook("start", {"source": "startup"})
    time.sleep(3)
    f = ws / "tests" / "rich.robot"
    r = s.edit("write", f, content=JOURNEY_HEAD)
    t = r.get("text", "")
    samples = {"claude_rich_ok_first_page": t}
    ents = [l for l in t.splitlines() if l.startswith("    ") and " => " in l]
    check("K1 rich success after navigation: block line + page line + a compact controls list (<= 8 controls, "
          "`kind \"name\" => selector`, no hrefs), <= 1,200 chars",
          "L3-L12 PASS" in t and "controls on this page" in t and 1 <= len(ents) <= 8
          and any("=> id=username" in l for l in ents) and "href" not in t and len(t) <= 1200, t)
    r = s.edit("edit", f, old="    Fill Text    id=username    alice\n",
               new="    Fill Text    id=username    alice\n    Click    id=no-such-signin\n")
    t1 = r.get("text", "")
    samples["claude_rich_fail_missing"] = t1
    near = [l for l in t1.splitlines() if l.startswith("    ") and "=>" in l]
    check("K2 rich failure: failing line, error, verdict MISSING, keyword signature + first doc sentence, failure-type "
          "hint, nearest controls (<= 8), NEXT, <= 1,200 chars",
          re.search(r"L13 (FAIL|NOT RUN)", t1) and "verdict: MISSING" in t1 and re.search(r"keyword: Click\(.*\) -- \S", t1) is not None
          and "hint: MISSING = no element matched" in t1 and "nearest controls" in t1 and 1 <= len(near) <= 8
          and "NEXT:" in t1 and len(t1) <= 1200, t1)
    r = s.edit("edit", f, old="    Click    id=no-such-signin\n", new="    Click    id=still-no-signin\n")
    t2 = r.get("text", "")
    check("K3 the same keyword fails again -> signature + first sentence and the hint AGAIN (lean: once per session)",
          re.search(r"L13 (FAIL|NOT RUN)", t2) and re.search(r"keyword: Click\(.*\) -- \S", t2) is not None and "hint: " in t2, t2)
    r = s.edit("edit", f, old="    Click    id=still-no-signin\n",
               new="    Fill Text    id=password    secret\n    Click    data-test=signin\n")
    t3 = r.get("text", "")
    samples["claude_rich_ok_after_navigation"] = t3
    ents3 = [l for l in t3.splitlines() if l.startswith("    ") and " => " in l]
    check("K4 navigation to the next page -> a new controls list for that page (form fields first, <= 8)",
          "L13-L14 PASS" in t3 and "controls on this page" in t3 and 1 <= len(ents3) <= 8 and len(t3) <= 1200
          and "href" not in t3, t3)
    res = shell_with_hooks(s, f"{VENV}/robot -d results --console dotted tests/rich.robot || true")
    f.write_text(f.read_text().replace("    Click    data-test=signin\n",
                                       "    Click    data-test=signin\n    Click    id=nope-place\n"))
    res = shell_with_hooks(s, f"{VENV}/robot -d results --console dotted tests/rich.robot")
    pt1 = res.get("text", "")
    res = shell_with_hooks(s, f"{VENV}/robot -d results --console dotted tests/rich.robot")
    pt2 = res.get("text", "")
    samples["claude_rich_plain_robot_fail"] = pt2
    check("K5 rich plain robot run failure: keyword signature + first sentence and the failure-type hint on EVERY run",
          all("Plain robot:" in x and re.search(r"keyword: Click\(.*\) -- \S", x) and "hint: MISSING" in x
              for x in (pt1, pt2)), {"run1": pt1, "run2": pt2})
    near2 = [l for l in pt2.split("nearest controls", 1)[-1].splitlines() if l.startswith("    ") and "=>" in l]
    check("K5b rich reproduction on a page with more controls: word matches first, then controls the keyword acts on "
          "(2..8 nearest controls), <= 1,200 chars", 2 <= len(near2) <= 8 and "Place order" in near2[0]
          and len(pt2) <= 1200, pt2)
    pl = _prof_log(ws)
    check("K6 hook log: profile=rich from ANTHROPIC_MODEL on every logged event, model id recorded",
          pl and all(p[1] == "rich" and p[2] == "model:ANTHROPIC_MODEL" and p[3] == "deepseek/deepseek-v4.1-flash"
                     for p in pl), pl[:6])
    merge_lat(s)
    end_session(s, ws, "K[rich]")

    # ---- lean: Claude subscription model found in the transcript
    ws = new_ws(root, "k_lean")
    s = Sim("claude", ws, env=dict(_NOMODEL))
    s.extra = {"transcript_path": str(tr)}
    s.hook("start", {"source": "startup"})
    time.sleep(3)
    f = ws / "tests" / "lean.robot"
    r = s.edit("write", f, content=JOURNEY_HEAD)
    t = r.get("text", "")
    r = s.edit("edit", f, old="    Fill Text    id=username    alice\n",
               new="    Fill Text    id=username    alice\n    Click    id=no-such-signin\n")
    tf = r.get("text", "")
    samples.update(claude_lean_ok_first_page=t, claude_lean_fail_missing=tf)
    pl = _prof_log(ws)
    check("K7 lean (claude-haiku-5-5 from the transcript): v3 output unchanged -- success <= 250 without a controls "
          "list, failure <= 700 without the rich hint; hook log profile=lean src=model:transcript",
          len(t) <= 250 and "controls on this page" not in t and "verdict: MISSING" in tf and len(tf) <= 700
          and "hint: MISSING =" not in tf and any(p[1:3] == ("lean", "model:transcript") for p in pl)
          and not any(p[1] == "rich" for p in pl), {"ok": t, "fail": tf, "log": pl[:5]})
    merge_lat(s)
    end_session(s, ws, "K[lean]")

    # ---- OpenCode: MiniMax via the plugin payload -> rich, guidance first; RFH_PROFILE=lean forces lean
    for forced in ("", "lean"):
        ws = new_ws(root, f"k_oc{forced}")
        s = Sim("opencode", ws, env={**_NOMODEL, "RFH_PROFILE": forced})
        s.extra = {"model": "minimax-coding-plan/MiniMax-M2.5"}
        s.hook("start", {})
        time.sleep(3)
        f = ws / "tests" / "oc.robot"
        r = s.edit("write", f, content=JOURNEY_HEAD)
        t = r.get("text", "")
        r = s.edit("edit", f, old="    Fill Text    id=username    alice\n",
                   new="    Fill Text    id=username    alice\n    Click    id=no-such-signin\n")
        tf = r.get("text", "")
        first = tf.splitlines()[0].strip() if tf else ""
        samples[f"opencode_{forced or 'rich'}_fail_missing"] = tf
        pl = _prof_log(ws)
        if not forced:
            check("K8 OpenCode + MiniMax (plugin payload model) -> rich: controls list on success; failure with the "
                  "guidance FIRST (hint, NEXT), verdict + signature, <= 1,200 chars; log profile=rich src=model:payload",
                  "controls on this page" in t and first.startswith("hint:") and "NEXT:" in tf.splitlines()[1]
                  and "verdict: MISSING" in tf and "keyword: Click(" in tf and len(tf) <= 1200
                  and any(p[1:3] == ("rich", "model:payload") for p in pl), {"ok": t, "fail": tf, "log": pl[:4]})
        else:
            check("K9 RFH_PROFILE=lean wins over the MiniMax model: OpenCode lean budgets 250/600, NEXT first; "
                  "log src=env", len(t) <= 250 and len(tf) <= 600 and first.startswith("NEXT:")
                  and "controls on this page" not in t and all(p[1:3] == ("lean", "env") for p in pl),
                  {"ok": t, "fail": tf, "log": pl[:4]})
        merge_lat(s)
        end_session(s, ws, f"K[opencode{':' + forced if forced else ''}]")

    # ---- Codex without any model id -> agent default lean
    ws = new_ws(root, "k_codex")
    s = Sim("codex", ws, env={**_NOMODEL, "CODEX_HOME": str(root / "k_empty_codex_home")})
    s.hook("start", {})
    time.sleep(3)
    f = ws / "tests" / "cx.robot"
    r = s.edit("write", f, content=JOURNEY_HEAD)
    pl = _prof_log(ws)
    check("K10 Codex without a model id -> agent default lean (log src=default), v3 success budget",
          len(r.get("text", "")) <= 250 and pl and all(p[1:3] == ("lean", "default") for p in pl),
          {"t": r.get("text"), "log": pl[:4]})
    merge_lat(s)
    end_session(s, ws, "K[codex]")
    (root / "profile_samples.json").write_text(json.dumps(samples, indent=1))


PRICE_HEAD = """*** Settings ***
Library    Browser
Suite Setup    New Browser    chromium    headless=True

*** Test Cases ***
Price
    New Page    file://${CURDIR}/../site/price.html
    Get Text    id=selectplatinum_price    ==    509.00
"""


def scenario_l(root: Path):
    """v3.2 (round v3.1 failures): a radio INSIDE a label without for= / text, covered by a styled <span> (Tricentis
    price table) -> controls.txt and the COVERED verdict give a concrete, unique click target (label:has(#id)) instead
    of nothing (agents fell back to `label.choosePrice >> nth=2`); a long Read streak gets one nudge."""
    ws = new_ws(root, "l_v32")
    s = Sim("claude", ws)
    s.hook("start", {"source": "startup"})
    time.sleep(3)
    f = ws / "tests" / "price.robot"
    r = s.edit("write", f, content=PRICE_HEAD)
    ctl = ws / ".rf" / "state" / "latest" / "controls.txt"
    ctxt = ctl.read_text() if ctl.is_file() else ""
    row = next((x for x in ctxt.splitlines() if "id=selectplatinum " in x or x.rstrip().endswith("id=selectplatinum")), "")
    check("L1 controls.txt marks the covered price radio and suggests its label `label:has(#selectplatinum)`",
          "PASS" in r.get("text", "") and "FAIL" not in r.get("text", "") and "covered by <span" in row and "=> label:has(#selectplatinum)" in row,
          {"row": row, "t": r.get("text")})
    r = s.edit("edit", f, old="    Get Text    id=selectplatinum_price    ==    509.00\n",
               new="    Get Text    id=selectplatinum_price    ==    509.00\n    Click    id=selectplatinum\n")
    t = r.get("text", "")
    check("L2 click on the covered radio -> COVERED with the concrete label target `label:has(#selectplatinum)`, "
          "no SLOW", "COVERED" in t and "label:has(#selectplatinum)" in t and "SLOW" not in t, {"t": t})
    r = s.edit("edit", f, old="    Click    id=selectplatinum\n",
               new="    Click    label:has(#selectplatinum)\n    Get Checkbox State    id=selectplatinum    ==    checked\n")
    check("L3 the suggested label selector selects the radio -> PASS incl. the checked assertion",
          "PASS" in r.get("text", "") and "FAIL" not in r.get("text", "") and "NOT RUN" not in r.get("text", ""),
          r.get("text"))
    # ---- L4 read streak: 8 reads in a row without an edit -> one nudge (not at 7, not at 9), reset by an edit
    outs = []
    for _i in range(9):
        o, _ = s.hook("pre", s._payload("Read", {"file_path": str(ctl)}))
        outs.append(json.dumps(o or {}))
    hit = [i + 1 for i, o in enumerate(outs) if "reads in a row" in o]
    check("L4 one read-streak nudge exactly at the 8th consecutive Read (grep controls.txt, write the next lines)",
          hit == [8] and "controls.txt" in outs[7], {"hit": hit, "o8": outs[7][:400]})
    s.edit("edit", f, old="    Get Checkbox State    id=selectplatinum    ==    checked\n",
           new="    Get Checkbox State    id=selectplatinum    ==    checked\n    Click    id=next\n")
    outs = [json.dumps(s.hook("pre", s._payload("Read", {"file_path": str(ctl)}))[0] or {}) for _ in range(7)]
    check("L5 an edit resets the streak (no nudge in the next 7 reads)", not any("reads in a row" in o for o in outs),
          outs[-1][:300])
    merge_lat(s)
    end_session(s, ws, "L")


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rfh-verify").resolve()
    # scenarios A-J are the ported v3 checks = the `lean` profile (OpenCode would otherwise default to `rich`);
    # scenario K sets / clears RFH_PROFILE itself.
    os.environ["RFH_PROFILE"] = os.environ.get("RFH_PROFILE") or "lean"
    os.environ.update(hookcore.playwright_env(sys.executable))
    root.mkdir(parents=True, exist_ok=True)
    only = os.environ.get("ONLY", "abcdefghijkl")
    t0 = time.time()
    for k, fn in (("a", scenario_a), ("b", scenario_b), ("c", scenario_c), ("d", scenario_d), ("e", scenario_e),
                  ("f", scenario_f), ("g", scenario_g), ("h", scenario_h), ("i", scenario_i), ("j", scenario_j), ("k", scenario_k), ("l", scenario_l)):
        if k in only:
            try:
                fn(root)
            except Exception:
                import traceback
                check(f"scenario {k} crashed", False, traceback.format_exc()[-1500:])
    lat = {k: {"n": len(v), "median_ms": round(statistics.median(v)), "max_ms": round(max(v))} for k, v in LAT.items() if v}
    ok = all(c["ok"] for c in CHECKS)
    res = {"ok": ok, "passed": sum(c["ok"] for c in CHECKS), "total": len(CHECKS), "latency": lat,
           "wall_s": round(time.time() - t0), "checks": CHECKS}
    (root / "results_hooks.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("ok", "passed", "total", "wall_s")}), json.dumps(lat, indent=0))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
