"""End-to-end check of the `rfmcp` CLI (no agent): Browser file:// page with iframe + shadow DOM, RequestsLibrary
against a local http.server, planted static errors, runtime failure + hint, long step job/wait, hook, final robot
run + robotcode results, latency, stop/kill -9 orphan checks.

  PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright .venv/bin/python verify/verify_cli.py [WORKDIR]
Writes verify/results_cli.json (small). Exit 0 if all checks pass.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN = Path(sys.executable).parent
RFMCP = os.environ.get("RFMCP_BIN") or str(BIN / "rfmcp")  # RFMCP_BIN: shim for another venv
SITE = (HERE / "site" / "index.html").as_uri()
checks: list = []
timings: dict = {}


def sh(*args: str, stdin: str | None = None, env: dict | None = None, timeout: float = 120):
    t0 = time.perf_counter()
    r = subprocess.run(list(args), input=stdin, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, **(env or {})})
    ms = (time.perf_counter() - t0) * 1000
    return r, ms


def rf(*args: str, stdin: str | None = None, env: dict | None = None):
    r, ms = sh(RFMCP, *args, stdin=stdin, env=env)
    try:
        j = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
    except ValueError:
        j = {"_raw": r.stdout[-500:]}
    return j, r.returncode, ms


def check(name: str, cond: bool, detail=None):
    checks.append({"check": name, "ok": bool(cond), **({"detail": detail} if detail is not None and not cond else {})})
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {json.dumps(detail)[:600]}"))


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def token_procs(ws: Path) -> list:
    st = json.loads((ws / ".rf" / "rfmcp.json").read_text())
    tok = f"RFMCP_SKILL_TOKEN={st['token_env']}".encode()
    out = []
    for d in Path("/proc").iterdir():
        if d.name.isdigit():
            try:
                if tok in (d / "environ").read_bytes().split(b"\0"):
                    out.append(int(d.name))
            except OSError:
                pass
    return out


def browser_scenario(ws: Path) -> None:
    j, rc, ms = rf("start")
    timings["start_ms"] = round(ms)
    check("start", j.get("ok") and j.get("started"), j)
    j, rc, _ = rf("start")
    check("start idempotent", j.get("already_running"), j)
    for cell in ("Import Library    Browser", "New Browser    chromium    headless=True", f"New Page    {SITE}"):
        j, rc, _ = rf("step", cell)
        check(f"step {cell.split()[0]} {cell.split()[1] if len(cell.split())>1 else ''}", j.get("ok"), j)
    # guard + iframe suggestion
    j, rc, ms = rf("step", "Fill Text    id=card    4242")
    s = (j.get("steps") or [{}])[0]
    check("guard NOT_FOUND suggests frame >>> selector", s.get("status") == "NOT RUN"
          and "id=pay-frame >>> id=card" in json.dumps(s.get("guard")), j)
    timings["guard_not_found_ms"] = round(ms)
    j, _, _ = rf("step", "Fill Text    id=pay-frame >>> id=card    4242")
    check("iframe >>> fill", j.get("ok"), j)
    j, _, _ = rf("step", "Click    css=#shadow-btn")
    check("shadow DOM css click", j.get("ok"), j)
    j, _, _ = rf("step", "Get Text    text=Shadow clicked")
    check("shadow DOM text= get", j.get("ok") and j["steps"][0].get("ret") == "Shadow clicked", j)
    j, _, _ = rf("step", '-', stdin="${n}=    Get Element Count    css=.item\nIF    ${n} == 3\n    Log    three items\nEND\n")
    check("heredoc multi-line cell (IF block)", j.get("ok") and len(j.get("steps", [])) == 2, j)
    # runtime failure with hint
    j, rc, _ = rf("step", "Click    .item")
    s = (j.get("steps") or [{}])[0]
    check("runtime failure (strict mode) has localized hint", s.get("status") == "FAIL" and s.get("hints")
          and "get_session_state" not in json.dumps(s) and "nth=0" in json.dumps(s["hints"]), j)
    # state
    j, _, ms = rf("state", "aria")
    check("state aria includes iframe section", j.get("ok") and "id=pay-frame" in json.dumps(j.get("iframes"))
          and Path(j.get("path", "/nonexistent")).is_file(), j)
    timings["state_aria_ms"] = round(ms)
    for what in ("url", "source", "screenshot"):
        j, _, _ = rf("state", what)
        check(f"state {what}", j.get("ok") and (what == "url" or Path(j.get("path", "/x")).is_file()), j)
    # keyword docs
    j, _, ms = rf("search", "type text into an input field")
    top = [r["kw"] for r in j.get("results", [])]
    # Browser 20.x docs rank Fill Secret between them -> both in the top 3, one of them first
    check("search finds Fill Text/Type Text (top-1 + both in top-3)", top[:1] in (["Fill Text"], ["Type Text"])
          and {"Fill Text", "Type Text"} <= set(top[:3]), j)
    timings["search_ms"] = round(ms)
    j, _, _ = rf("search", "switch to iframe")
    check("search iframe note points to >>>", ">>>" in j.get("note", ""), j)
    j, _, _ = rf("doc", "Clik")
    check("doc typo -> did_you_mean Click", any(x.startswith("Click ") for x in j.get("did_you_mean", [])), j)
    j, _, _ = rf("doc", "POST On Session", "--lib", "RequestsLibrary")
    check("doc repairs *args/**kwargs signature", "expected_status" in json.dumps(j), j)

    # file-based steps with planted errors
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)
    f = tests / "shop.robot"
    f.write_text(f"""*** Settings ***
Library    Browser
Suite Setup    New Browser    chromium    headless=True

*** Variables ***
${{URL}}    {SITE}

*** Test Cases ***
Login And Pay
    New Page    ${{URL}}
    Fill Text    id=username    alice
    Clik    id=login
""")
    j, rc, ms = rf("run", str(f.relative_to(ws)))
    check("run --new blocks planted typo before execution (L12)", j.get("blocked", {}).get("line") == 12
          and [r["line"] for r in j.get("ran", [])] == [3, 10, 11], j)
    timings["run_first_ms_cold_analyzer"] = round(ms)
    f.write_text(f.read_text().replace("    Clik    id=login", "    Click    id=login\n    Get Text    id=status    ==    Welcome, ${usr}"))
    j, rc, _ = rf("run", str(f.relative_to(ws)), "--new")
    check("run --new reruns only fixed line, blocks undefined var L13", [r["line"] for r in j.get("ran", [])] == [12]
          and j.get("blocked", {}).get("line") == 13, j)
    f.write_text(f.read_text().replace("${usr}", "alice") + "    Fill Text    id=card    4242\n")
    j, rc, _ = rf("run", str(f.relative_to(ws)))
    check("run: runtime NOT_FOUND at L14 with frame fix", j.get("ran", [{}])[-1].get("line") == 14
          and "pay-frame" in json.dumps(j), j)
    f.write_text(f.read_text().replace("    Fill Text    id=card    4242\n",
                                       "    Fill Text    id=pay-frame >>> id=card    4242\n"
                                       "    Click    id=pay-frame >>> text=Pay now\n"
                                       "    Get Text    id=pay-frame >>> id=paid    ==    Paid with 4242\n"))
    j, rc, _ = rf("run", str(f.relative_to(ws)))
    check("run: iframe lines pass", j.get("ok") and [r["line"] for r in j["ran"]] == [14, 15, 16], j)
    # latency of run --new (one appended line each time)
    lat = []
    for i in range(10):
        f.write_text(f.read_text() + f"    Get Text    id=status    ==    Welcome, alice\n")
        j, rc, ms = rf("run", str(f.relative_to(ws)), "--new")
        if j.get("ok"):
            lat.append(ms)
    timings["run_new_ms_median"] = round(statistics.median(lat)) if lat else None
    check("run --new latency measured (10/10 ok)", len(lat) == 10, len(lat))
    j, rc, _ = rf("check", str(f.relative_to(ws)))
    check("check clean file", j.get("ok"), j)
    bad = tests / "bad.robot"
    bad.write_text("*** Settings ***\nLibrary    Browser\nForce Tags    smoke\n\n*** Test Cases ***\nBad\n"
                   "    Run Keyword If    True    Log    hi\n    Clik    id=x\n    Log    ${nope}\n")
    j, rc, ms = rf("check", str(bad.relative_to(ws)))
    codes = {e["code"] for e in j.get("errors", [])}
    check("check catches typo + undefined var + robocop DEPR", {"KeywordNotFound", "VariableNotFound"} <= codes
          and any("DEPR08" in x for x in j.get("robocop", [])), j)
    timings["check_ms"] = round(ms)
    # hook (claude format) with helper running
    hook_in = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(bad)}, "cwd": str(ws)})
    r, ms = sh(RFMCP, "hook", "--agent", "claude", stdin=hook_in)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
    check("hook: auto-fixes Run Keyword If + reports errors <=1KB", "IF    True" in bad.read_text()
          and "Clik" in ctx and len(ctx) <= 1100, ctx)
    timings["hook_ms_helper"] = round(ms)
    bad.unlink()
    # long step -> job/wait
    j, rc, ms = rf("step", "Sleep    4s", env={"RFMCP_CALL_TIMEOUT": "1.5"})
    check("long step returns running job", rc == 4 and j.get("job"), j)
    if j.get("job"):
        j2, rc2, _ = rf("wait", str(j["job"]))
        check("wait collects job result", j2.get("ok"), j2)
    # vars / redaction
    j, _, _ = rf("step", "${password}=    Set Variable    s3cr3t-pw")
    j, _, _ = rf("step", "Log    ${password}    console=True")
    check("redaction hides secret in console", "s3cr3t-pw" not in json.dumps(j), j)
    # stop with Browser: 0 orphans
    procs_before = token_procs(ws)
    j, rc, ms = rf("stop")
    time.sleep(0.3)
    left = token_procs(ws)
    check("stop with Browser open -> 0 orphans", j.get("ok") and j.get("orphans") == 0 and not left,
          {"resp": j, "left": left, "had": len(procs_before)})
    timings["stop_ms"] = round(ms)
    timings["procs_in_session"] = len(procs_before)
    check("generated live resource removed at stop", not (tests / ".shop.live.resource").exists())
    # final full run with robot + robotcode results
    r, ms = sh(str(BIN / "robot"), "-d", str(ws / "results"), "--console", "dotted", str(f), timeout=180)
    check("final robot run passes", r.returncode == 0, r.stdout[-800:])
    timings["robot_final_ms"] = round(ms)
    r, _ = sh(str(BIN / "robotcode"), "results", "summary", "-o", str(ws / "results" / "output.xml"))
    check("robotcode results summary", r.returncode == 0 and "1" in r.stdout, r.stdout[-400:] + r.stderr[-400:])
    r, _ = sh(str(BIN / "robotcode"), "results", "show", "--failed", "-o", str(ws / "results" / "output.xml"))
    check("robotcode results show --failed", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
    # the ExecutionResult snippet printed by `rfmcp guide results` must run as written
    guide = sh(RFMCP, "guide", "results")[0].stdout
    snippet = guide.split("python - <<'PY'\n", 1)[1].split("\n  PY", 1)[0]
    snippet = "\n".join(l[2:] for l in snippet.splitlines()).replace("results/output.xml", str(ws / "results" / "output.xml"))
    r, _ = sh(sys.executable, "-c", snippet)
    check("guide results: ExecutionResult snippet runs", r.returncode == 0 and "passed 1" in r.stdout, r.stdout[-300:] + r.stderr[-300:])


def requests_scenario(ws: Path, port: int) -> None:
    base = f"http://127.0.0.1:{port}"
    j, _, _ = rf("start")
    for cell in ("Import Library    RequestsLibrary", f"Create Session    api    {base}"):
        j, _, _ = rf("step", cell)
        check(f"requests {cell.split('    ')[0]}", j.get("ok"), j)
    j, _, _ = rf("step", "${resp}=    GET On Session    api    /users.json")
    check("GET On Session", j.get("ok"), j)
    j, _, _ = rf("step", "Should Be Equal As Strings    ${resp.json()}[0][name]    Alice")
    check("assert json field", j.get("ok"), j)
    j, _, _ = rf("step", "Status Should Be    200    ${resp}")
    check("Status Should Be", j.get("ok"), j)
    j, rc, _ = rf("step", f"GET On Session    {base}/users.json")
    s = (j.get("steps") or [{}])[0]
    check("runtime failure (URL as alias) -> RequestsLibrary hint", s.get("status") == "FAIL"
          and "alias" in json.dumps(s.get("hints", [])).lower(), j)
    j, _, _ = rf("step", "${r}=    GET On Session    api    /missing.json    expected_status=404")
    check("expected_status=404", j.get("ok"), j)
    f = ws / "tests" / "api.robot"
    f.parent.mkdir(exist_ok=True)
    f.write_text(f"""*** Settings ***
Library    RequestsLibrary

*** Variables ***
${{BASE}}    {base}

*** Test Cases ***
Users Endpoint
    Create Session    api    ${{BASE}}
    ${{resp}}=    GET On Session    api    /users.json
    Should Be Equal As Strings    ${{resp.json()}}[1][role]    admin
""")
    j, rc, _ = rf("run", str(f))
    check("api run: assertion failure reported with line 11", not j.get("ok") and j.get("ran", [{}])[-1].get("line") == 11
          and j["ran"][-1].get("status") == "FAIL", j)
    f.write_text(f.read_text().replace("[1][role]    admin", "[1][role]    user"))
    j, rc, _ = rf("run", str(f))
    check("api run: fixed line passes", j.get("ok") and [r["line"] for r in j["ran"]] == [11], j)
    # multi-test file with Test Setup + [Setup] + teardown note
    m = ws / "tests" / "multi.robot"
    m.write_text("*** Settings ***\nTest Setup    Set Test Variable    ${who}    suite-default\n\n*** Test Cases ***\n"
                 "First\n    Should Be Equal    ${who}    suite-default\n\n"
                 "Second\n    [Setup]    Set Test Variable    ${who}    own\n    Should Be Equal    ${who}    own\n"
                 "    [Teardown]    Log    bye\n")
    j, rc, _ = rf("run", str(m))
    lines = [(r.get("line"), r.get("status")) for r in j.get("ran", [])]
    check("multi-test run: Test Setup, [Setup], both tests, teardown note", j.get("ok") and lines ==
          [(2, "PASS"), (6, "PASS"), (9, "PASS"), (10, "PASS")] and "Teardown" in j.get("note", ""), j)
    j, _, _ = rf("stop")
    check("stop requests helper", j.get("ok") and j.get("orphans") == 0, j)
    r, _ = sh(str(BIN / "robot"), "-d", str(ws / "results_api"), "--console", "none", str(f))
    check("final robot run api.robot passes", r.returncode == 0, r.stdout[-400:])


def latency(ws: Path) -> None:
    rf("start")
    rf("step", "Import Library    Browser")
    rf("step", "New Browser    chromium    headless=True")
    rf("step", f"New Page    {SITE}")
    a, b = [], []
    for _ in range(30):
        _, _, ms = rf("step", "Get Title")
        a.append(ms)
        _, ms = sh("python3", "-S", str(ws / ".rf" / "fast.py"), "step", "Get Title")
        b.append(ms)
    timings["step_get_title_rfmcp_ms"] = {"median": round(statistics.median(a)), "p90": round(sorted(a)[26])}
    timings["step_get_title_fastpy_ms"] = {"median": round(statistics.median(b)), "p90": round(sorted(b)[26])}
    check("per-step client latency rfmcp median <= 90 ms", statistics.median(a) <= 90, timings["step_get_title_rfmcp_ms"])
    # kill -9 the helper with a browser open -> next start cleans the orphans
    st = json.loads((ws / ".rf" / "rfmcp.json").read_text())
    n = len(token_procs(ws))
    os.kill(st["pid"], signal.SIGKILL)
    time.sleep(2.5)
    survivors = [p for p in token_procs(ws) if p != st["pid"]]
    j, _, _ = rf("start")
    time.sleep(0.3)
    j2, _, _ = rf("stop")
    left = token_procs(ws)
    check("kill -9 then start/stop -> 0 orphans", not left and j2.get("orphans") == 0,
          {"procs": n, "survivors_after_kill": len(survivors), "start": j, "left": left})
    timings["kill9_survivors_after_2_5s_pdeathsig"] = len(survivors)


def main() -> int:
    ws = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="rfmcp-verify-"))
    shutil.rmtree(ws, ignore_errors=True)
    ws.mkdir(parents=True)
    (ws / ".git").mkdir()  # project root marker (like a real repo)
    os.chdir(ws)
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
                            "--directory", str(HERE / "api")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        browser_scenario(ws)
        requests_scenario(ws, port)
        latency(ws)
    finally:
        srv.terminate()
        srv.wait(5)
        rf("stop")
    ok = all(c["ok"] for c in checks)
    out = {"ok": ok, "passed": sum(c["ok"] for c in checks), "total": len(checks), "timings": timings,
           "failed": [c for c in checks if not c["ok"]]}
    (HERE / os.environ.get("RFMCP_RESULTS_NAME", "results_cli.json")).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("ok", "passed", "total", "timings")}, indent=1))
    shutil.rmtree(ws, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
