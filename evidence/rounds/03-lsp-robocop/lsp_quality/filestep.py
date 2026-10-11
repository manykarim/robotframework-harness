"""File-based step client (stdlib only; run as `python3 -S .rf/filestep.py ...`).

  filestep.py run   FILE [--new | --lines A-B | --all] [--test NAME] [--no-check] [--force] [--text]
  filestep.py check FILE [--new | --lines A-B | --all] [--test NAME] [--text]
  filestep.py rebase FILE [--through N]

Only a file path and a line range go over the socket. The agent writes RF lines with its own
Write/Edit tool; nothing RF-shaped is ever passed through the shell.
"""
import json
import os
import socket
import sys


def main(argv):
    d = os.environ.get("RFMCP_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)))
    if argv[:1] == ["--dir"]:
        d, argv = argv[1], argv[2:]
    if len(argv) < 2:
        sys.stdout.write(__doc__)
        return 2
    cmd, path, rest = argv[0], os.path.abspath(argv[1]), argv[2:]
    req = {"op": "check" if cmd == "check" else "filestep", "path": path, "mode": "new"}
    text = False
    it = iter(rest)
    for a in it:
        if a == "--lines":
            lo, _, hi = next(it).partition("-")
            req.update(mode="lines", lines=[int(lo), int(hi or lo)])
        elif a == "--all":
            req["mode"] = "all"
        elif a == "--new":
            req["mode"] = "new"
        elif a == "--test":
            req["test"] = next(it)
        elif a == "--no-check":
            req["check"] = False
        elif a == "--force":
            req["force"] = True
        elif a == "--text":
            text = True
        elif a == "--through":
            req["through"] = int(next(it))
    if cmd == "rebase":
        req["mode"] = "rebase"
    try:
        with open(os.path.join(d, "endpoint")) as f:
            ep = f.read().split()
    except OSError:
        sys.stdout.write('{"ok":false,"error":"no helper running"}\n')
        return 3
    if ep[0] == "tcp":
        req["token"] = ep[2]
        s = socket.create_connection(("127.0.0.1", int(ep[1])))
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(ep[1])
    s.sendall(json.dumps(req).encode() + b"\n")
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(65536)
        if not c:
            break
        buf += c
    s.close()
    if not text:
        sys.stdout.buffer.write(buf)
        return 1 if buf.startswith(b'{"ok":false') else 0
    r = json.loads(buf)
    for x in r.get("ran", []):
        ln = f"L{x['line']}" + (f"-{x['end']}" if "end" in x else "")
        sys.stdout.write(f"{ln:<8} {x.get('status', '?'):5} {x.get('kw')}  {x.get('ms', '')}ms"
                         + (f"  -> {x['ret']}" if "ret" in x else "") + "\n")
    for k in ("blocked", "failed", "diags", "error", "hint", "note", "dropped"):
        if r.get(k):
            sys.stdout.write(f"{k}: {json.dumps(r[k])}\n")
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
