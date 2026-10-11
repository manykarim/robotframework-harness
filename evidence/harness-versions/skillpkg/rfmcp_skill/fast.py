"""rfmcp per-call client. STDLIB ONLY (os/sys/socket/json): also copied to .rf/fast.py and runnable as
    python3 -S .rf/fast.py step 'Click    id=login'
Talks one JSON line to the helper's socket and prints the compact JSON reply.

  step [--no-guard] '<cell>' ['<cell2>' ...] | step -          (stdin, e.g. a quoted heredoc <<'RF')
  run FILE [--new|--lines A-B|--all|--rebase [--through N]] [--test NAME] [--no-check] [--force] [--no-guard]
  check FILE | wait JOB | status | search "<query>" [--lib L1,L2] [-n N] | doc "<Keyword>" [--full] [--lib L]
  state [controls|aria|source|url|screenshot] [--selector S] | vars [NAME ...] [--all] | interrupt
Exit: 0 ok, 1 failed, 2 usage, 3 no helper, 4 still running (use `wait JOB`).
"""
import json
import os
import socket
import sys

CALL_TIMEOUT = float(os.environ.get("RFMCP_CALL_TIMEOUT", "25"))


def state_dir():
    return os.environ.get("RFMCP_DIR") or os.path.join(os.getcwd(), ".rf")


def endpoint(d):
    try:
        with open(os.path.join(d, "endpoint")) as f:
            return f.read().split()
    except OSError:
        return None


def send(ep, req, timeout):
    if ep[0] == "tcp":
        req["token"] = ep[2]
        s = socket.create_connection(("127.0.0.1", int(ep[1])), timeout=timeout)
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(ep[1])
    try:
        s.sendall(json.dumps(req).encode() + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            c = s.recv(65536)
            if not c:
                break
            buf += c
    finally:
        s.close()
    return buf


def _opt(args, name, default=None, flag=False):
    if name in args:
        i = args.index(name)
        if flag:
            del args[i]
            return True
        v = args[i + 1] if i + 1 < len(args) else default
        del args[i:i + 2]
        return v
    return False if flag else default


def build(cmd, args):
    """-> request dict or (None, error string)"""
    args = list(args)
    noguard = _opt(args, "--no-guard", flag=True)
    if cmd == "step":
        cells = [sys.stdin.read() if a == "-" else a for a in args]
        if not cells:
            return None, "usage: rfmcp step '<Keyword>    <arg>' (or: rfmcp step - <<'RF' ... RF)"
        return {"op": "step", "cells": cells, **({"guard": False} if noguard else {})}, None
    if cmd in ("run", "check"):
        if not args:
            return None, f"usage: rfmcp {cmd} FILE"
        req = {"op": cmd, "path": os.path.abspath(args.pop(0)), "mode": "new"}
        if noguard:
            req["guard"] = False
        lines = _opt(args, "--lines")
        if lines:
            lo, _, hi = lines.partition("-")
            req.update(mode="lines", lines=[int(lo), int(hi or lo)])
        if _opt(args, "--all", flag=True):
            req["mode"] = "all"
        _opt(args, "--new", flag=True)
        if _opt(args, "--rebase", flag=True):
            req["mode"] = "rebase"
        thr = _opt(args, "--through")
        if thr:
            req["through"] = int(thr)
        t = _opt(args, "--test")
        if t:
            req["test"] = t
        if _opt(args, "--no-check", flag=True):
            req["check"] = False
        if _opt(args, "--force", flag=True):
            req["force"] = True
        return req, None
    if cmd == "wait":
        if not args:
            return None, "usage: rfmcp wait JOB"
        return {"op": "wait", "job": int(args[0])}, None
    if cmd == "search":
        libs = _opt(args, "--lib")
        n = _opt(args, "-n", "5")
        if not args:
            return None, 'usage: rfmcp search "what you want to do" [--lib Browser]'
        return {"op": "search", "query": " ".join(args), "limit": int(n),
                "libs": [x for x in (libs or "").split(",") if x]}, None
    if cmd == "doc":
        libs = _opt(args, "--lib")
        full = _opt(args, "--full", flag=True)
        if not args:
            return None, 'usage: rfmcp doc "Keyword Name" [--full]'
        return {"op": "doc", "name": " ".join(args), "full": full,
                "libs": [x for x in (libs or "").split(",") if x]}, None
    if cmd == "state":
        sel = _opt(args, "--selector")
        return {"op": "state", "what": (args[0] if args else "aria"), "selector": sel}, None
    if cmd == "vars":
        al = _opt(args, "--all", flag=True)
        return {"op": "vars", "names": args, "all": al}, None
    if cmd in ("status", "interrupt", "ping"):
        return {"op": cmd}, None
    return None, f"unknown command '{cmd}'"


def call(cmd, args, d=None):
    """-> (exit_code, raw_json_bytes)"""
    req, err = build(cmd, args)
    if req is None:
        return 2, json.dumps({"ok": False, "error": err}).encode() + b"\n"
    ep = endpoint(d or state_dir())
    if not ep:
        return 3, b'{"ok":false,"error":"no helper running","hint":"rfmcp start"}\n'
    req.setdefault("timeout", CALL_TIMEOUT)
    try:
        buf = send(ep, req, CALL_TIMEOUT + 15)
    except OSError as e:
        return 3, json.dumps({"ok": False, "error": "helper not reachable: %s" % e, "hint": "rfmcp start"}).encode() + b"\n"
    if not buf:
        return 3, b'{"ok":false,"error":"helper closed the connection"}\n'
    if buf.startswith(b'{"ok":null'):
        return 4, buf
    return (1 if buf.startswith(b'{"ok":false') else 0), buf


def main(argv):
    if argv[:1] == ["--dir"]:
        os.environ["RFMCP_DIR"], argv = argv[1], argv[2:]
    if not argv:
        sys.stdout.write(__doc__)
        return 2
    rc, buf = call(argv[0], argv[1:])
    sys.stdout.buffer.write(buf if buf.endswith(b"\n") else buf + b"\n")
    sys.stdout.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
