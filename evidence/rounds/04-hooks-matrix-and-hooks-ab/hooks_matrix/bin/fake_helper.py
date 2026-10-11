#!/usr/bin/env python3
"""Stand-in for the background RF helper: pid file + heartbeat + signal log; idle auto-exit after 300 s."""
import json
import os
import signal
import sys
import time
from pathlib import Path

cell = Path(sys.argv[1])
log = cell / "helper.log"
start = time.time()


def w(msg):
    with open(log, "a") as f:
        f.write(json.dumps({"wall": round(time.time(), 3), "pid": os.getpid(), "ppid": os.getppid(),
                            "sid": os.getsid(0), "msg": msg}) + "\n")


def on_sig(sig, _frm):
    w(f"signal {signal.Signals(sig).name} -> exit")
    try:
        (cell / "helper.pid").unlink()
    except FileNotFoundError:
        pass
    sys.exit(0)


signal.signal(signal.SIGTERM, on_sig)
signal.signal(signal.SIGINT, on_sig)
signal.signal(signal.SIGHUP, lambda s, f: w("SIGHUP ignored"))
(cell / "helper.pid").write_text(str(os.getpid()))
w("started")
while time.time() - start < 300:
    (cell / "helper.heartbeat").write_text(str(round(time.time(), 3)))
    time.sleep(0.5)
w("idle timeout -> exit")
(cell / "helper.pid").unlink(missing_ok=True)
