"""Capture structured failure data from `robotcode repl-server` (JSON-RPC over TCP).

For each corpus mistake: start `robotcode repl-server --tcp 127.0.0.1:<port>`,
send `initialize`, then one `executeCell` per line (preamble + steps), then
`shutdown`/`exit`. Save every executeCell response (the
x-application/robotframework-repl-log JSON tree with keyword name/owner/args/
status/message) to runs/<id>/replserver/cells.json.

  python replserver_capture.py [ID ...]
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from corpus import CORPUS  # noqa: E402

ROBOTCODE = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
RUNS = HERE / "runs"
CWD = HERE / "scratch" / "cwd"


class Client:
    def __init__(self, port: int):
        deadline = time.monotonic() + 30
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        self.sock.settimeout(300)
        self.buf = b""
        self.next_id = 1

    def _read_message(self) -> dict:
        while True:
            sep = self.buf.find(b"\r\n\r\n")
            if sep >= 0:
                header = self.buf[:sep].decode()
                length = int([h for h in header.split("\r\n") if h.lower().startswith("content-length")][0].split(":")[1])
                if len(self.buf) >= sep + 4 + length:
                    body = self.buf[sep + 4: sep + 4 + length]
                    self.buf = self.buf[sep + 4 + length:]
                    return json.loads(body)
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("server closed")
            self.buf += chunk

    def call(self, method: str, params: dict | None = None):
        mid = self.next_id
        self.next_id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}).encode()
        self.sock.sendall(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        while True:
            msg = self._read_message()
            if msg.get("id") == mid:
                return msg


def run(m: dict, port: int) -> dict:
    out = RUNS / m["id"] / "replserver"
    out.mkdir(parents=True, exist_ok=True)
    cmd = [ROBOTCODE, "repl-server", "--tcp", f"127.0.0.1:{port}", "-d", str(out)]
    proc = subprocess.Popen(cmd, cwd=CWD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    cells = []
    try:
        c = Client(port)
        cells.append({"method": "initialize", "response": c.call("initialize", {"message": "hints"})})
        for line in m["preamble"] + m["steps"]:
            t0 = time.monotonic()
            resp = c.call("executeCell", {"source": line, "language_id": "robotframework"})
            cells.append({"source": line, "duration_s": round(time.monotonic() - t0, 2), "response": resp})
        try:
            c.call("shutdown")
            body = json.dumps({"jsonrpc": "2.0", "method": "exit", "params": {}}).encode()
            c.sock.sendall(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        except Exception as e:  # noqa: BLE001
            cells.append({"shutdown_error": repr(e)})
    finally:
        try:
            console, _ = proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            console, _ = proc.communicate()
    (out / "cells.json").write_text(json.dumps(cells, indent=2))
    (out / "console.txt").write_text(console or "")
    return {"id": m["id"], "exit": proc.returncode, "cells": len(cells)}


def main(ids: list[str]) -> None:
    CWD.mkdir(parents=True, exist_ok=True)
    todo = [m for m in CORPUS if not ids or m["id"] in ids]
    jobs = [(m, 6711 + i) for i, m in enumerate(todo)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(lambda mp: run(*mp), jobs):
            print(json.dumps(res), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
