"""Q3 bench: stock repl-server + robotcode.jsonrpc2 client (separate process per step)."""
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
from bench import SAUCE, summary  # noqa: E402
from rfmcp_local import procs  # noqa: E402

PY = sys.argv[1]
RC = str(Path(PY).with_name("robotcode"))
wd = HERE / "work" / "replserver"
wd.mkdir(parents=True, exist_ok=True)
(wd / "out").mkdir(exist_ok=True)
sock = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), f"rfmcp-rs-{os.getpid()}.sock")
if os.path.exists(sock):
    os.unlink(sock)
out = {}
t0 = time.perf_counter()
srv = subprocess.Popen([RC, "repl-server", "--pipe-server", sock, "-d", str(wd / "out")], cwd=wd,
                       stdin=subprocess.DEVNULL, stdout=open(wd / "server.log", "w"), stderr=subprocess.STDOUT,
                       start_new_session=True)
while not os.path.exists(sock):
    if srv.poll() is not None or time.perf_counter() - t0 > 30:
        sys.exit("repl-server failed: " + (wd / "server.log").read_text()[-500:])
    time.sleep(0.01)
out["listen_ms"] = round((time.perf_counter() - t0) * 1000)


def call(*a):
    t = time.perf_counter()
    p = subprocess.run([PY, str(HERE / "jsonrpc_client.py"), sock, *a], capture_output=True, text=True, timeout=120)
    ms = (time.perf_counter() - t) * 1000
    try:
        return ms, json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return ms, {"raw": p.stdout[-300:], "err": p.stderr[-600:]}


import atexit

atexit.register(lambda: (procs.alive([srv.pid]) and os.killpg(srv.pid, signal.SIGKILL)))
first_ms, o = call("exec", "Log  warmup")
out["first_exec_ms"] = round(first_ms)
for c in SAUCE[:6]:
    ms, o = call("exec", c)
    assert o.get("ok"), o
pids = procs.descendants(srv.pid)
w = [call("exec", "Get Title")[0] for _ in range(30)]
out["get_title_jsonrpc_client"] = summary(w)
print(out)
t = time.perf_counter()
ms, o = call("shutdown")
out["shutdown_rpc"] = {"reply_ms": round(ms), "reply": o}
try:
    srv.wait(timeout=40)
    out["shutdown_exit_ms"] = round((time.perf_counter() - t) * 1000)
except subprocess.TimeoutExpired:
    out["shutdown_exit_ms"] = None
time.sleep(0.5)
out["alive_after_shutdown"] = procs.alive(pids)
if procs.alive([srv.pid] + pids):
    os.killpg(srv.pid, signal.SIGKILL)
    procs.terminate(procs.alive(pids))
out["server_log_tail"] = (wd / "server.log").read_text()[-600:]
(HERE / "results" / "bench_replserver.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
