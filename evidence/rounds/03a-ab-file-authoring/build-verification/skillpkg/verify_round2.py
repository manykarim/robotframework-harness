"""Round-2 checks of the `rfmcp` CLI (no agent), complementing verify_cli.py:
  A economy   : `stop` no-op without a helper, `check` without starting a helper, new guide topics, SKILL.md size
  B debug     : a LOCAL failing toy suite (verify/debug/travel.robot on verify/site/widgets.html; planted stale
                locator + planted missing wait) repaired with the `rfmcp guide debug` workflow, final plain robot run
  C widgets   : guard COVERED / NOT_VISIBLE, `state controls`, custom dropdown hint, dates, dialogs, value-assert
                hint, follow-up settle and --no-guard -- through the helper on widgets.html
  D portable  : name-imported project library: `check`/hook/`run` warn with the fix, plain robot fails, fix passes

  PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright .venv/bin/python verify/verify_round2.py [WORKDIR]
  other venv: RFMCP_BIN=<shim running `python -m rfmcp_skill.cli`> <that venv>/bin/python verify/verify_round2.py
Writes verify/results_round2.json (small). Exit 0 if all checks pass.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN = Path(sys.executable).parent
RFMCP = os.environ.get("RFMCP_BIN") or str(BIN / "rfmcp")
checks: list = []
timings: dict = {}


def sh(*args: str, stdin: str | None = None, timeout: float = 180):
    t0 = time.perf_counter()
    r = subprocess.run(list(args), input=stdin, capture_output=True, text=True, timeout=timeout)
    return r, (time.perf_counter() - t0) * 1000


def rf(*args: str, stdin: str | None = None):
    r, ms = sh(RFMCP, *args, stdin=stdin)
    try:
        j = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
    except ValueError:
        j = {"_raw": r.stdout[-500:]}
    return j, r.returncode, ms


def check(name: str, cond, detail=None):
    checks.append({"check": name, "ok": bool(cond), **({"detail": detail} if detail is not None and not cond else {})})
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {json.dumps(detail, default=str)[:700]}"))


def robot(ws: Path, *args: str):
    return sh(str(BIN / "robot"), "-d", str(ws / "results"), "--console", "dotted", *args, timeout=300)


def line_of(f: Path, text: str) -> int:
    return next(i for i, l in enumerate(f.read_text().splitlines(), 1) if text in l)


def guard(j) -> dict:
    s = (j.get("steps") or j.get("ran") or [{}])[-1]
    return s.get("guard") or {}


def economy(ws: Path) -> None:
    j, rc, ms = rf("stop")
    check("A stop without helper: ok no-op, no .rf created", j.get("ok") and j.get("running") is False
          and not (ws / ".rf").exists(), j)
    timings["stop_noop_ms"] = round(ms)
    j, rc, ms = rf("check", "tests/travel.robot")
    st, _, _ = rf("status")
    check("A check without helper: static result, helper NOT started", j.get("ok") and "not running" in j.get("helper", "")
          and st.get("running") is False, {"check": j, "status": st})
    timings["check_static_ms"] = round(ms)
    for topic, needle in (("debug", "rfmcp run path/suite.robot --test"), ("explore", "rfmcp state controls"),
                          ("widgets", "label[for="), ("waits", "retry_assertions_for")):
        r, _ = sh(RFMCP, "guide", topic)
        check(f"A guide {topic}", r.returncode == 0 and needle in r.stdout, r.stdout[:200])
    skill = HERE.parent / "rfmcp_skill" / "skill" / "SKILL.md"
    timings["skill_md_bytes"] = skill.stat().st_size
    check("A SKILL.md <= 6200 bytes", skill.stat().st_size <= 6200, skill.stat().st_size)


def debug(ws: Path) -> None:
    f = ws / "tests" / "travel.robot"
    r, ms = robot(ws, str(f))
    check("B plain robot: toy suite fails 2 of 3", r.returncode == 2, r.stdout[-600:])
    timings["debug_first_robot_ms"] = round(ms)
    r, _ = sh(str(BIN / "robotcode"), "results", "show", "--failed", "-o", str(ws / "results" / "output.xml"))
    check("B robotcode results show --failed lists both failures", "Request Is Confirmed" in r.stdout
          and "Three Offers Are Listed" in r.stdout and "Missing Fields" not in r.stdout, r.stdout[-600:])
    stale = line_of(f, "Click    id=submit-request")
    j, rc, ms = rf("run", "tests/travel.robot", "--test", "Request Is Confirmed")
    last = (j.get("ran") or [{}])[-1]
    check("B rfmcp run --test reproduces: stops AT stale-locator line, NOT_FOUND", not j.get("ok")
          and last.get("line") == stale and last.get("status") == "NOT RUN" and guard(j).get("cls") == "NOT_FOUND", j)
    timings["debug_reproduce_ms"] = round(ms)
    j, _, _ = rf("state", "controls")
    check("B state controls at the failure shows the real button + stable selector",
          j.get("ok") and "=> data-test=send" in j.get("content", ""), j)
    j, _, _ = rf("step", "Click    data-test=send")
    check("B candidate fix tried live", j.get("ok"), j)
    f.write_text(f.read_text().replace("Click    id=submit-request", "Click    data-test=send"))
    j, _, _ = rf("run", "tests/travel.robot", "--test", "Request Is Confirmed")
    check("B fixed line resumes and the rest of the test passes", j.get("ok") and j["ran"][0]["line"] == stale, j)
    assert_line = line_of(f, "Should Be Equal As Integers    ${offers}    3")
    j, _, _ = rf("run", "tests/travel.robot", "--test", "Three Offers Are Listed")
    last = (j.get("ran") or [{}])[-1]
    check("B second failure reproduced at the assertion (0 != 3)", not j.get("ok") and last.get("line") == assert_line
          and "0 != 3" in (last.get("msg") or ""), j)
    j, _, _ = rf("step", "Wait For Condition    Element Count    css=#results li    ==    3    timeout=10s")
    check("B candidate wait tried live", j.get("ok"), j)
    # the naive operator-only fix still fails in a real run (assertion retry = 1 s) -- the guides warn about it
    naive = ws / "tests" / "naive.robot"
    naive.write_text(f.read_text().replace("    ${offers}=    Get Element Count    css=#results li\n"
                                           "    Should Be Equal As Integers    ${offers}    3\n",
                                           "    Get Element Count    css=#results li    ==    3\n"))
    r, _ = robot(ws, "-t", "Three Offers Are Listed", "--output", "NONE", "--log", "NONE", "--report", "NONE", str(naive))
    check("B naive fix (operator only, 1 s retry) still fails in plain robot", r.returncode == 1, r.stdout[-400:])
    naive.unlink()
    wait = "    Wait For Elements State    css=#results li >> nth=2    visible    timeout=10s\n"
    f.write_text(f.read_text().replace("    ${offers}=    Get Element Count", wait + "    ${offers}=    Get Element Count"))
    j, _, _ = rf("run", "tests/travel.robot", "--test", "Three Offers Are Listed")
    check("B insert before a line that already ran -> explains --lines/--rebase", not j.get("ok")
          and "--lines" in json.dumps(j), j)
    a, b = line_of(f, "Wait For Elements State    css=#results"), line_of(f, "Should Be Equal As Integers")
    j, _, _ = rf("run", "tests/travel.robot", "--test", "Three Offers Are Listed", "--lines", f"{a}-{b}")
    check("B --lines re-runs the fixed block", j.get("ok") and [x["line"] for x in j["ran"]] == [a, a + 1, b], j)
    j, _, _ = rf("stop")
    check("B stop: 0 orphans", j.get("ok") and j.get("orphans") == 0, j)
    r, ms = robot(ws, str(f))
    text = f.read_text()
    check("B final plain robot: 3/3 pass, no test removed, assertion kept", r.returncode == 0
          and "3 tests, 3 passed" in r.stdout
          and all(t in text for t in ("Request Is Confirmed", "Three Offers Are Listed", "Missing Fields Are Reported"))
          and "Should Be Equal As Integers    ${offers}    3" in text and "Get Text    id=status    contains    insurance no"
          in text, r.stdout[-600:])
    timings["debug_final_robot_ms"] = round(ms)


def widgets(ws: Path) -> None:
    site = (ws / "site" / "widgets.html").as_uri()
    j, _, _ = rf("step", "Import Library    Browser", "New Browser    chromium    headless=True", f"New Page    {site}")
    check("C open widgets page", j.get("ok"), j)
    j, _, ms = rf("step", "Click    id=traveller")
    g = guard(j)
    check("C COVERED: click under the cookie overlay refused fast with its button",
          g.get("cls") == "COVERED" and "Accept all" in (g.get("overlay_buttons") or []) and ms < 3000, j)
    timings["guard_covered_ms"] = round(ms)
    j, _, _ = rf("step", "Click With Options    id=send-request    force=True")
    check("C COVERED also for force=True (would hit the overlay)", guard(j).get("cls") == "COVERED"
          and "force=True would NOT help" in guard(j).get("fix", ""), j)
    j, _, _ = rf("step", "Click    text=Accept all")
    check("C close overlay", j.get("ok"), j)
    j, _, ms = rf("state", "controls")
    c = j.get("content", "")
    check("C state controls: hidden radio label, native vs custom dropdown, date format, new tab",
          all(x in c for x in ('label[for="trip-round"]', "native select [-- choose --|Berlin|Oslo|Rome]",
                               "custom dropdown", "Fill Text with YYYY-MM-DD", "Switch Page", "=> data-test=traveller")),
          c[:1500])
    timings["state_controls_ms"] = round(ms)
    j, _, ms = rf("step", "Check Checkbox    id=trip-round")
    g = guard(j)
    check("C NOT_VISIBLE: hidden styled radio -> names its label", g.get("cls") == "NOT_VISIBLE"
          and g.get("click_instead") == 'label[for="trip-round"]' and ms < 3000, j)
    timings["guard_not_visible_ms"] = round(ms)
    j, _, _ = rf("step", 'Click    label[for="trip-round"]', "Get Checkbox State    id=trip-round    ==    checked")
    check("C click label + assert hidden input state", j.get("ok"), j)
    j, _, _ = rf("step", "Select Options By    id=travel-class    label    Business")
    s = (j.get("steps") or [{}])[-1]
    check("C custom dropdown: Select Options By fails with the custom-dropdown hint", s.get("status") == "FAIL"
          and "custom dropdown" in json.dumps(s.get("hints", [{}])[0]), j)
    j, _, _ = rf("step", "Click    id=travel-class", 'Click    role=option[name="Business"]',
                 "Get Text    id=travel-class    ==    Business")
    check("C custom dropdown: click + role=option", j.get("ok"), j)
    j, _, _ = rf("step", "-", stdin="Import Library    DateTime\n"
                 "${d}=    Get Current Date    increment=7 days    result_format=%Y-%m-%d\n"
                 "Fill Text    id=depart    ${d}\nGet Property    id=depart    value    ==    ${d}\n")
    check("C date relative to today into <input type=date>", j.get("ok"), j)
    j, _, _ = rf("step", "Handle Future Dialogs    action=accept", "Click    id=reset-form",
                 "Get Text    id=status    ==    Form reset")
    check("C JS confirm accepted via Handle Future Dialogs", j.get("ok"), j)
    j, _, _ = rf("step", "Get Text    id=status    ==    Nope")
    s = (j.get("steps") or [{}])[-1]
    check("C value assertion failure -> Wait For Condition hint", s.get("status") == "FAIL"
          and "Wait For Condition    Text    id=status" in json.dumps(s.get("hints", [])), j)
    fill = ["Fill Text    id=traveller    Ann", "Click    text=One way", "Select Options By    id=dest    label    Oslo",
            "Click    id=travel-class", "Click    text=Economy", "Fill Text    id=depart    2099-01-01"]
    j, _, _ = rf("step", *fill)
    check("C fill a valid request", j.get("ok"), j)
    rf("step", "Click    id=send-request")
    j, _, ms = rf("step", "Click    css=#results li >> nth=0")
    check("C async element not there yet: NOT_FOUND after the 1.5 s step probe, fix mentions --no-guard",
          guard(j).get("cls") == "NOT_FOUND" and "--no-guard" in guard(j).get("fix", "") and ms < 2600, j)
    rf("step", "Wait For Elements State    css=#results li >> nth=2    visible    timeout=10s")  # earlier timers done
    rf("step", "Click    id=send-request")  # clears the list, new results after 2.5 s
    j, _, ms = rf("step", "--no-guard", "Click    css=#results li >> nth=0")
    check("C --no-guard: Browser's own 10 s auto-wait finds the async element", j.get("ok") and ms > 1000, j)
    timings["no_guard_async_click_ms"] = round(ms)
    j, _, _ = rf("step", "Click    id=send-request", "Click    css=#results li >> nth=0")
    check("C later keyword of one step uses the 5 s follow-up probe -> async element found", j.get("ok"), j)
    j, _, _ = rf("stop")
    check("C stop: 0 orphans", j.get("ok") and j.get("orphans") == 0, j)


def portable(ws: Path) -> None:
    (ws / "resources").mkdir(exist_ok=True)
    (ws / "resources" / "GreetingLib.py").write_text("def greeting():\n    return 'hello'\n")
    f = ws / "tests" / "portable.robot"
    f.write_text("*** Settings ***\nLibrary    GreetingLib\n\n*** Test Cases ***\nGreets\n"
                 "    ${g}=    Greeting\n    Should Be Equal    ${g}    hello\n")
    fix = "Library    ${CURDIR}/../resources/GreetingLib.py"
    j, _, _ = rf("check", "tests/portable.robot")
    st, _, _ = rf("status")
    check("D check: name import flagged NotPortable with the exact path fix, helper not started",
          not j.get("ok") and (j.get("portable") or [{}])[0].get("fix") == fix and st.get("running") is False, j)
    hook_in = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(f)}, "cwd": str(ws)})
    r, ms = sh(RFMCP, "hook", "--agent", "claude", stdin=hook_in)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
    check("D post-edit hook reports NOT PORTABLE with the fix", "NOT PORTABLE" in ctx and fix in ctx, ctx)
    timings["hook_portable_ms"] = round(ms)
    j, _, _ = rf("run", "tests/portable.robot")
    check("D the trap: passes in the helper (robotcode adds ./resources) but run reports `portable`",
          j.get("ok") and j.get("portable") and fix in j["portable"][0], j)
    rf("stop")
    r, _ = robot(ws, "--output", "NONE", "--log", "NONE", "--report", "NONE", str(f))
    check("D plain robot fails with the name import", r.returncode != 0, r.stdout[-300:])
    f.write_text(f.read_text().replace("Library    GreetingLib", fix))
    j, _, _ = rf("check", "tests/portable.robot")
    check("D after the fix: check clean", j.get("ok") and not j.get("portable"), j)
    r, _ = robot(ws, "--output", "NONE", "--log", "NONE", "--report", "NONE", str(f))
    check("D after the fix: plain robot passes", r.returncode == 0, r.stdout[-300:])


def main() -> int:
    ws = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="rfmcp-r2-"))
    shutil.rmtree(ws, ignore_errors=True)
    (ws / ".git").mkdir(parents=True)
    shutil.copytree(HERE / "site", ws / "site")
    (ws / "tests").mkdir()
    shutil.copy(HERE / "debug" / "travel.robot", ws / "tests" / "travel.robot")
    os.chdir(ws)
    try:
        economy(ws)
        debug(ws)
        widgets(ws)
        portable(ws)
    finally:
        rf("stop")
    ok = all(c["ok"] for c in checks)
    out = {"ok": ok, "passed": sum(c["ok"] for c in checks), "total": len(checks), "timings": timings,
           "python": sys.executable, "failed": [c for c in checks if not c["ok"]]}
    try:
        import importlib.metadata as md

        out["versions"] = {p: md.version(p) for p in ("robotframework", "robotframework-browser")}
    except Exception:
        pass
    name = os.environ.get("RFMCP_RESULTS_NAME", "results_round2.json")
    (HERE / name).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("ok", "passed", "total", "timings")}, indent=1))
    os.chdir(HERE)
    shutil.rmtree(ws, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
