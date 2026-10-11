"""E7: reach keyword docs/search through `robotcode repl-server` executeCell (dot-commands are NOT available there;
the KwDocs helper library is). Starts a TCP repl-server, sends cells, measures latency and response size."""
import json, os, re, signal, socket, subprocess, sys, time
from pathlib import Path
K = Path(__file__).resolve().parents[1]
RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
PORT = 6791
OUT = K / "outputs/e7"; OUT.mkdir(parents=True, exist_ok=True)

def rpc(method, params, rid):
    body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}).encode()
    s = socket.create_connection(("127.0.0.1", PORT), timeout=120)
    s.sendall(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    buf = b""
    while True:
        while b"\r\n\r\n" not in buf:
            c = s.recv(65536)
            if not c: raise ConnectionError("closed")
            buf += c
        head, rest = buf.split(b"\r\n\r\n", 1)
        n = int(re.search(rb"Content-Length:\s*(\d+)", head, re.I).group(1))
        while len(rest) < n: rest += s.recv(65536)
        msg = json.loads(rest[:n]); buf = rest[n:]
        if msg.get("id") == rid:
            s.close(); return msg

proc = subprocess.Popen([RC, "repl-server", "--tcp", str(PORT), "-P", str(K / "helper"), "-d", str(OUT / "rs_out")],
                        cwd=K / "project", stdin=subprocess.DEVNULL, stdout=open(OUT / "rs.log", "w"), stderr=subprocess.STDOUT,
                        start_new_session=True)
t0 = time.time()
while True:
    try: socket.create_connection(("127.0.0.1", PORT), timeout=1).close(); break
    except OSError:
        if time.time() - t0 > 30: raise
        time.sleep(0.05)
startup = time.time() - t0
cells = [
    ("imports", "Import Library    Browser\nImport Library    RequestsLibrary\nImport Library    ${CURDIR}/libs/ShopApi.py    base_url=http://x\nImport Resource    ${CURDIR}/resources/shop.resource\nImport Library    KwDocs"),
    ("dotcmd_kw", ".kw Click"),
    ("search_post_json", "Search Keywords    post json    5"),
    ("search_post_json_again", "Search Keywords    post json    5"),
    ("search_wait_visible", "Search Keywords    wait until element visible    5"),
    ("doc_compact", "Keyword Doc    Fill Text"),
    ("doc_full", "Keyword Doc    Fill Text    full"),
    ("doc_resource_json", "Keyword Doc    shop.Login As User    json"),
]
rows = []
try:
    rpc("initialize", {"message": "hi"}, 1)
    for i, (name, src) in enumerate(cells, start=2):
        s = time.perf_counter(); r = rpc("executeCell", {"source": src, "language_id": "robotframework"}, i); dt = time.perf_counter() - s
        raw = json.dumps(r)
        (OUT / f"rs_{name}.json").write_text(json.dumps(r, indent=1))
        # extract printed text (INFO messages) from the repl log payload
        msgs = re.findall(r'"message":\s*"((?:[^"\\]|\\.)*)"', raw.replace('\\"', '"'))
        rows.append({"cell": name, "ms": round(dt * 1000, 1), "resp_bytes": len(raw), "success": (r.get("result") or {}).get("success")})
        print(f"{name:24} {dt*1000:8.1f} ms  resp={len(raw):6d} B  success={rows[-1]['success']}")
finally:
    try: rpc("shutdown", None, 99)
    except Exception: pass
    time.sleep(0.5)
    try: os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError: pass
(OUT / "e7_replserver.json").write_text(json.dumps({"startup_s": round(startup, 2), "rows": rows}, indent=1))
print("server startup to port open:", round(startup, 2), "s")
