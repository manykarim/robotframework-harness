"""Benchmark + lifecycle driver for rfmcp_local. Each step = separate client process (like agent Bash calls).

usage: python3 bench.py --py VENV_PY --label NAME [--scenarios latency,requests,sigterm,kill9,pdeathsig,graceful]
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rfmcp_local import procs, proto  # noqa: E402

SAUCE = [
    "Import Library  Browser  timeout=10s",
    "New Browser  chromium  headless=True",
    "New Page  https://www.saucedemo.com",
    'Fill Text  [data-test="username"]  standard_user',
    'Fill Text  [data-test="password"]  secret_sauce',
    'Click  [data-test="login-button"]',
    "Get Url  ==  https://www.saucedemo.com/inventory.html",
    'Get Element Count  [data-test="inventory-item"]  ==  6',
    'Click  [data-test="add-to-cart-sauce-labs-backpack"]',
    'Get Text  [data-test="shopping-cart-badge"]  ==  1',
    'Click  [data-test="shopping-cart-link"]',
    "Get Url  *=  cart.html",
    'Get Element Count  [data-test="inventory-item"]  ==  1',
    "${title}=  Get Title",
    'Get Text  [data-test="shopping-cart-badge"]  ==  1',
]
BOOKER = [
    "Import Library  RequestsLibrary",
    "Import Library  Collections",
    'Create Session  booker  https://restful-booker.herokuapp.com  headers={"Accept": "application/json"}',
    "${auth}=  Create Dictionary  username=admin  password=password123",
    "${resp}=  POST On Session  booker  /auth  json=${auth}",
    "${token}=  Set Variable  ${resp.json()}[token]",
    "${dates}=  Create Dictionary  checkin=2026-10-01  checkout=2026-10-05",
    "${body}=  Create Dictionary  firstname=Robo  lastname=Step  totalprice=${123}  depositpaid=${True}  bookingdates=${dates}  additionalneeds=Breakfast",
    "${resp}=  POST On Session  booker  /booking  json=${body}",
    "${id}=  Set Variable  ${resp.json()}[bookingid]",
    "${resp}=  GET On Session  booker  /booking/${id}",
    "Should Be Equal  ${resp.json()}[firstname]  Robo",
    "${h}=  Create Dictionary  Cookie=token=${token}",
    "DELETE On Session  booker  /booking/${id}  headers=${h}  expected_status=201",
]


def pct(xs, p):
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


def summary(xs):
    return {"n": len(xs), "median": round(statistics.median(xs), 1), "p90": round(pct(xs, 90), 1),
            "min": round(min(xs), 1), "max": round(max(xs), 1)}


class Bench:
    def __init__(self, py: str, workdir: Path, client: list | None = None, env_extra: dict | None = None):
        self.py = py
        self.wd = workdir
        self.wd.mkdir(parents=True, exist_ok=True)
        self.env = dict(os.environ, PYTHONPATH=str(HERE), **(env_extra or {}))
        self.client = client or [py, "-m", "rfmcp_local"]
        self.d = workdir / ".rf"

    def run(self, *args, client=None, timeout=120):
        t0 = time.perf_counter()
        p = subprocess.run([*(client or self.client), *args], cwd=self.wd, env=self.env, capture_output=True,
                           text=True, timeout=timeout)
        ms = (time.perf_counter() - t0) * 1000
        try:
            out = json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:
            out = {"raw": p.stdout[-500:], "err": p.stderr[-800:]}
        return ms, out

    def state(self):
        return proto.read_state(self.d) or {}

    def tree(self):
        st = self.state()
        pid = st.get("pid")
        ds = procs.descendants(pid) if pid else []
        tok = procs.token_procs(st["token_env"]) if st.get("token_env") else []
        names = {}
        for p in set(ds) | set(tok):
            try:
                names[p] = Path(f"/proc/{p}/comm").read_text().strip()
            except OSError:
                pass
        return {"pid": pid, "pgid": st.get("pgid"), "procs": names}


def steps(b: Bench, cells, out, label):
    res = []
    for c in cells:
        ms, o = b.run("step", c)
        st = (o.get("steps") or [{}])[-1]
        res.append({"cell": c[:60], "wall_ms": round(ms, 1), "srv_ms": o.get("dur_ms"), "ok": o.get("ok"),
                    "status": st.get("status"), "msg": st.get("msg")})
    out[label] = res
    bad = [r for r in res if not r["ok"]]
    print(f"  {label}: {len(res)} steps, failures={len(bad)} {bad[:2]}")
    return res


def scenario_latency(b: Bench, out, n):
    ms, o = b.run("start", "--hooks", "redact,hints")
    out["start"] = {"wall_ms": round(ms), **o}
    print("  start", out["start"])
    steps(b, SAUCE, out, "sauce_flow")
    out["tree_running"] = b.tree()
    for label, cell in (("get_title", "Get Title"), ("log_x", "Log  x")):
        w, s = [], []
        for _ in range(n):
            ms, o = b.run("step", cell)
            w.append(ms)
            s.append(o.get("dur_ms") or 0)
        out[label] = {"wall": summary(w), "server": summary(s)}
        print(f"  {label}", out[label])
    pids = list(out["tree_running"]["procs"])
    ms, o = b.run("stop")
    time.sleep(0.5)
    out["stop"] = {"wall_ms": round(ms), **o, "alive_after": procs.alive([int(p) for p in pids])}
    print("  stop", out["stop"])


def scenario_clients(b: Bench, out, n, extra_clients=()):
    """Same step (`Get Title`, Browser logged in) through different client front-ends."""
    browser_up(b)
    fast = str(b.d / "fast.py")
    variants = {
        "full_cli": b.client,
        "fast_venv_S": [b.py, "-S", fast],
        "fast_sys_S": ["/usr/bin/python3", "-S", fast],
        "fast_sys": ["/usr/bin/python3", fast],
    }
    for name, cmd in extra_clients:
        variants[name] = cmd
    res = {}
    for name, cmd in variants.items():
        w = []
        okc = 0
        for _ in range(n):
            ms, o = b.run("step", "Get Title", client=cmd)
            w.append(ms)
            okc += bool(o.get("ok"))
        res[name] = {**summary(w), "ok": okc}
        print(f"  client {name}: {res[name]}")
    out["clients"] = res
    b.run("stop")


def scenario_requests(b: Bench, out, reps):
    ms, o = b.run("start", "--hooks", "redact,hints")
    out["start_req"] = {"wall_ms": round(ms), **o}
    allw, alls = [], []
    for r in range(reps):
        res = steps(b, BOOKER, out, f"booker_{r}")
        allw += [x["wall_ms"] for x in res]
        alls += [x["srv_ms"] or 0 for x in res]
    out["booker_all"] = {"wall": summary(allw), "server": summary(alls),
                         "client_overhead_median": round(statistics.median([w - s for w, s in zip(allw, alls)]), 1)}
    ms, o = b.run("vars", "${auth}", "${token}", "${h}")
    out["booker_vars_redacted"] = o
    ms, o = b.run("step", "POST On Session  booker  /auth  json=${auth}")
    out["booker_ret_redacted"] = o
    ms, o = b.run("stop")
    out["stop_req"] = {"wall_ms": round(ms), **o}
    print("  booker_all", out["booker_all"], "\n  stop", out["stop_req"])


def browser_up(b: Bench, extra=()):
    ms, o = b.run("start", "--hooks", "redact", *extra)
    for c in SAUCE[:6]:
        b.run("step", c)
    return o


def scenario_sigterm(b: Bench, out):
    browser_up(b)
    t = b.tree()
    pids = [int(p) for p in t["procs"]]
    t0 = time.perf_counter()
    os.kill(t["pid"], signal.SIGTERM)
    while proto.pid_alive(t["pid"]) and time.perf_counter() - t0 < 30:
        time.sleep(0.02)
    out["sigterm_idle"] = {"exit_ms": round((time.perf_counter() - t0) * 1000), "children": t["procs"],
                           "alive_after_500ms": (time.sleep(0.5), procs.alive(pids))[1],
                           "state": {k: b.state().get(k) for k in ("leftover", "cleanup_ms", "forced")}}
    print("  sigterm_idle", out["sigterm_idle"])
    # SIGTERM while a keyword runs
    browser_up(b)
    t = b.tree()
    pids = [int(p) for p in t["procs"]]
    p = subprocess.Popen([*b.client, "step", "Sleep  20s"], cwd=b.wd, env=b.env, stdout=subprocess.PIPE, text=True)
    time.sleep(1.0)
    t0 = time.perf_counter()
    os.kill(t["pid"], signal.SIGTERM)
    while proto.pid_alive(t["pid"]) and time.perf_counter() - t0 < 30:
        time.sleep(0.02)
    exit_ms = round((time.perf_counter() - t0) * 1000)
    step_out = p.communicate(timeout=30)[0]
    out["sigterm_busy"] = {"exit_ms": exit_ms, "step_reply": step_out.strip()[:400],
                           "alive_after_500ms": (time.sleep(0.5), procs.alive(pids))[1]}
    print("  sigterm_busy", out["sigterm_busy"])


def scenario_kill9(b: Bench, out, pdeathsig=False):
    label = "kill9_pdeathsig" if pdeathsig else "kill9"
    browser_up(b, ("--pdeathsig",) if pdeathsig else ())
    t = b.tree()
    pids = [int(p) for p in t["procs"]]
    os.kill(t["pid"], signal.SIGKILL)
    time.sleep(2.0)
    alive = procs.alive(pids)
    r = {"children": t["procs"], "alive_2s_after_kill9": {p: t["procs"][p] for p in alive}}
    ms, o = b.run("status")
    r["status_after"] = o
    ms, o = b.run("start", "--hooks", "redact")  # start must detect the stale helper and clean up
    r["restart"] = {"wall_ms": round(ms), **o}
    time.sleep(0.3)
    r["alive_after_restart"] = procs.alive(pids)
    b.run("stop")
    out[label] = r
    print(f"  {label}", r)


def scenario_graceful(b: Bench, out):
    browser_up(b)
    t = b.tree()
    pids = [int(p) for p in t["procs"]]
    ms, o = b.run("stop", "--graceful")
    time.sleep(0.3)
    out["stop_graceful"] = {"wall_ms": round(ms), **o, "alive_after": procs.alive(pids)}
    print("  stop_graceful", out["stop_graceful"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--py", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--scenarios", default="latency,requests,sigterm,kill9,pdeathsig,graceful")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--client", default=None, help="client command (space separated)")
    ap.add_argument("--robotcode", default=None, help="robotcode executable for plugin client variant")
    ap.add_argument("--uv", action="store_true")
    a = ap.parse_args()
    wd = HERE / "work" / a.label
    b = Bench(a.py, wd, client=a.client.split() if a.client else None,
              env_extra={"PLAYWRIGHT_BROWSERS_PATH": os.environ["PLAYWRIGHT_BROWSERS_PATH"]}
              if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else None)
    out = {"label": a.label, "py": a.py, "client": b.client, "ts": time.strftime("%F %T")}
    sc = a.scenarios.split(",")
    try:
        if "latency" in sc:
            scenario_latency(b, out, a.n)
        if "clients" in sc:
            extra = []
            if a.robotcode:
                extra.append(("robotcode_plugin", [a.robotcode, "rfmcp", "step"][:2]))
            if a.uv:
                extra.append(("uv_run", ["uv", "run", "--no-sync", "--project", "~/workspace/rf-mcp-robotcode", "python", "-m", "rfmcp_local"]))
            scenario_clients(b, out, a.n, extra)
        if "requests" in sc:
            scenario_requests(b, out, a.reps)
        if "graceful" in sc:
            scenario_graceful(b, out)
        if "sigterm" in sc:
            scenario_sigterm(b, out)
        if "kill9" in sc:
            scenario_kill9(b, out)
        if "pdeathsig" in sc:
            scenario_kill9(b, out, pdeathsig=True)
    finally:
        b.run("stop")
        b.run("cleanup")
        res = HERE / "results" / f"bench_{a.label}.json"
        res.write_text(json.dumps(out, indent=1))
        print("wrote", res)


if __name__ == "__main__":
    main()
