#!/usr/bin/env python3
"""Client for daemon.py.  Usage: python3 client.py ping|stop|status [--via unix|tcp|both] [--port N]
Prints one line per transport tried: '<via>: <reply>' or '<via>: ERR ...'.  Exit 0 if any transport answered."""
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = os.path.join(HERE, "d.sock")


def send(via, port, line):
    if via == "unix":
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        addr = SOCK
    else:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        addr = ("127.0.0.1", port)
    s.settimeout(5)
    try:
        s.connect(addr)
        s.sendall(line.encode() + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        return data.decode().strip()
    finally:
        s.close()


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "ping"
    via = args[args.index("--via") + 1] if "--via" in args else "both"
    port = int(args[args.index("--port") + 1]) if "--port" in args else 6800
    if not os.path.exists(os.path.join(HERE, "port")) and "--port" not in args:
        pass
    elif "--port" not in args:
        port = int(open(os.path.join(HERE, "port")).read().strip())
    line = {"ping": f"PING from-{os.environ.get('PROBE_WHO', 'client')}", "stop": "STOP", "status": "STATUS"}[cmd]
    vias = ["unix", "tcp"] if via == "both" else [via]
    if cmd == "stop":  # stop through the first transport that works
        vias = vias
    ok = False
    for v in vias:
        try:
            print(f"{v}: {send(v, port, line)}")
            ok = True
            if cmd == "stop":
                break
        except Exception as e:  # noqa: BLE001
            print(f"{v}: ERR {type(e).__name__}: {e}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
