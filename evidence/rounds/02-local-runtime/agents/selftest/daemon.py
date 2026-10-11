#!/usr/bin/env python3
"""Stdlib-only probe daemon for the "long-lived local helper" channel test.

Usage (run from the project dir):
  python3 daemon.py start [--port N] [--label L]   # self-detach (double fork + setsid), wait until bound
  python3 daemon.py run   [--port N] [--label L]   # foreground (for `nohup ... &` / agent background tools)

Listens on BOTH ./d.sock (unix) and 127.0.0.1:<port> (TCP).  Every request line is
appended to ./pings.log.  Writes ./daemon.pid, ./daemon.log, ./heartbeat (epoch every 1 s)
and logs every catchable signal it receives (SIGHUP is logged and ignored, SIGTERM/SIGINT
are logged and end the daemon) so an external observer can tell how it died.
Protocol: one text line in, one line out: PING <who> -> PONG ..., STOP -> BYE, STATUS -> JSON.
"""
import json
import os
import selectors
import signal
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = os.path.join(HERE, "d.sock")
PINGS = os.path.join(HERE, "pings.log")
LOG = os.path.join(HERE, "daemon.log")
PIDF = os.path.join(HERE, "daemon.pid")
HB = os.path.join(HERE, "heartbeat")
READY = os.path.join(HERE, "ready.json")


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} pid={os.getpid()} {msg}\n")


def ctx():
    try:
        sid = os.getsid(0)
        pgid = os.getpgid(0)
    except Exception:
        sid = pgid = -1
    cg = ""
    try:
        cg = open("/proc/self/cgroup").read().strip().replace("\n", ";")
    except Exception:
        pass
    return {"pid": os.getpid(), "ppid": os.getppid(), "sid": sid, "pgid": pgid, "cgroup": cg,
            "pidns": os.readlink("/proc/self/ns/pid") if os.path.exists("/proc/self/ns/pid") else "",
            "netns": os.readlink("/proc/self/ns/net") if os.path.exists("/proc/self/ns/net") else ""}


def serve(port, label):
    stop = {"flag": False}

    def on_sig(signum, _frame):
        log(f"SIGNAL {signal.Signals(signum).name}")
        if signum in (signal.SIGTERM, signal.SIGINT):
            stop["flag"] = True

    for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT, signal.SIGUSR1, signal.SIGPIPE):
        signal.signal(s, on_sig)

    status = {"label": label, "port": port, "ctx": ctx(), "unix": None, "tcp": None,
              "started": time.time()}
    sel = selectors.DefaultSelector()
    # unix socket
    try:
        if os.path.exists(SOCK):
            os.unlink(SOCK)
        us = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        us.bind(SOCK)
        os.chmod(SOCK, 0o600)
        us.listen(8)
        us.setblocking(False)
        sel.register(us, selectors.EVENT_READ, "unix")
        status["unix"] = "ok"
    except Exception as e:  # noqa: BLE001
        status["unix"] = f"ERR {type(e).__name__}: {e}"
    # tcp socket
    try:
        ts = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ts.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ts.bind(("127.0.0.1", port))
        ts.listen(8)
        ts.setblocking(False)
        sel.register(ts, selectors.EVENT_READ, "tcp")
        status["tcp"] = "ok"
    except Exception as e:  # noqa: BLE001
        status["tcp"] = f"ERR {type(e).__name__}: {e}"

    with open(PIDF, "w") as f:
        f.write(str(os.getpid()))
    with open(READY, "w") as f:
        json.dump(status, f)
    log(f"READY {json.dumps(status)}")
    if status["unix"] != "ok" and status["tcp"] != "ok":
        log("no listener could bind -> exit 3")
        return 3

    n = 0
    last_hb = 0.0
    while not stop["flag"]:
        now = time.time()
        if now - last_hb >= 1.0:
            with open(HB, "w") as f:
                f.write(f"{now:.1f}\n")
            last_hb = now
        for key, _ in sel.select(timeout=0.5):
            try:
                conn, peer = key.fileobj.accept()
            except BlockingIOError:
                continue
            conn.settimeout(5)
            try:
                data = b""
                while not data.endswith(b"\n") and len(data) < 4096:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                line = data.decode("utf-8", "replace").strip()
                with open(PINGS, "a") as f:
                    f.write(f"{time.strftime('%H:%M:%S')} via={key.data} {line}\n")
                if line.startswith("PING"):
                    n += 1
                    reply = f"PONG pid={os.getpid()} n={n} via={key.data} up={now - status['started']:.1f}s"
                elif line == "STOP":
                    reply = "BYE"
                    stop["flag"] = True
                elif line == "STATUS":
                    reply = json.dumps({**status, "pings": n, "up": now - status["started"]})
                else:
                    reply = f"ERR unknown {line!r}"
                conn.sendall(reply.encode() + b"\n")
            except Exception as e:  # noqa: BLE001
                log(f"conn error {e}")
            finally:
                conn.close()
    log("STOPPING (clean)")
    try:
        os.unlink(SOCK)
    except OSError:
        pass
    try:
        os.unlink(PIDF)
    except OSError:
        pass
    return 0


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "start"
    port = int(args[args.index("--port") + 1]) if "--port" in args else 6800
    label = args[args.index("--label") + 1] if "--label" in args else "?"
    if mode == "run":
        sys.exit(serve(port, label))
    if mode != "start":
        print(__doc__)
        sys.exit(2)
    # self-detach: double fork + setsid, stdio -> daemon.log; parent waits for ready.json
    if os.path.exists(READY):
        os.unlink(READY)
    pid = os.fork()
    if pid == 0:
        os.setsid()
        if os.fork() != 0:
            os._exit(0)
        os.chdir(HERE)
        fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        null = os.open(os.devnull, os.O_RDONLY)
        os.dup2(null, 0)
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        os._exit(serve(port, label))
    os.waitpid(pid, 0)
    for _ in range(100):
        if os.path.exists(READY):
            time.sleep(0.05)
            st = json.load(open(READY))
            print(json.dumps({"started": True, "pid": st["ctx"]["pid"], "unix": st["unix"], "tcp": st["tcp"]}))
            return
        time.sleep(0.05)
    print(json.dumps({"started": False, "error": "daemon did not become ready in 5 s; see daemon.log"}))
    sys.exit(1)


if __name__ == "__main__":
    main()
