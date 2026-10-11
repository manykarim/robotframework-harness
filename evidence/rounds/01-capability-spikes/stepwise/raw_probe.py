"""Raw repl-server probe: send one executeCell request, dump the full JSON response."""
import json, socket, sys

def call(port, method, params, rid=1, host="127.0.0.1", timeout=120):
    body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}).encode()
    s = socket.create_connection((host, port), timeout=timeout)
    s.sendall(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    buf = b""
    while True:
        while b"\r\n\r\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                raise SystemExit("connection closed")
            buf += chunk
        head, rest = buf.split(b"\r\n\r\n", 1)
        n = int([l.split(b":")[1] for l in head.split(b"\r\n") if l.lower().startswith(b"content-length")][0])
        while len(rest) < n:
            rest += s.recv(65536)
        msg = json.loads(rest[:n]); buf = rest[n:]
        if msg.get("id") == rid:
            s.close(); return msg

if __name__ == "__main__":
    port = int(sys.argv[1]); method = sys.argv[2]
    params = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    print(json.dumps(call(port, method, params), indent=1))
