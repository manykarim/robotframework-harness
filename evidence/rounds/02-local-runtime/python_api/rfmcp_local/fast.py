"""Minimal per-step client: imports only os/sys/socket (no json/re), runnable by path:
    python3 -S .rf/fast.py step '<cell>' ...   |  vars [NAME..]  |  status
Reads the endpoint from <dir>/endpoint (plain text written by the daemon), prints the raw JSON reply.
"""
import os
import sys


def _q(s):
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    if any(ord(c) < 32 for c in s):
        s = "".join(c if ord(c) >= 32 else "\\u%04x" % ord(c) for c in s)
    return '"' + s + '"'


def main(argv):
    d = os.environ.get("RFMCP_DIR") or ".rf"
    if argv[:1] == ["--dir"]:
        d, argv = argv[1], argv[2:]
    try:
        with open(os.path.join(d, "endpoint")) as f:
            ep = f.read().split()
    except OSError:
        sys.stdout.write('{"ok":false,"error":"no helper running"}\n')
        return 3
    cmd, args = (argv[0] if argv else "status"), argv[1:]
    if cmd == "step":
        req = '{"op":"step","cells":[' + ",".join(_q(sys.stdin.read() if a == "-" else a) for a in args) + "]"
    elif cmd == "vars":
        req = '{"op":"vars","names":[' + ",".join(_q(a) for a in args) + "]"
    else:
        req = '{"op":' + _q(cmd)
    import socket

    if ep[0] == "tcp":
        req += ',"token":' + _q(ep[2])
        s = socket.create_connection(("127.0.0.1", int(ep[1])))
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(ep[1])
        except OSError as e:
            sys.stdout.write('{"ok":false,"error":%s}\n' % _q("transport: " + str(e)))
            return 3
    s.sendall((req + "}\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(65536)
        if not c:
            break
        buf += c
    s.close()
    sys.stdout.buffer.write(buf)
    return 1 if buf.startswith(b'{"ok":false') else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
