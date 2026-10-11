"""Does robotcode's language server emit robocop findings as LSP diagnostics, and with which rule config?

usage: <venv-python> lsp_robocop_probe.py <robotcode-bin> <project-root> [settings-json]
Opens one document (deprecated syntax + keyword typo + arg-count error), waits for publishDiagnostics,
prints diagnostics grouped by source (robotcode vs robocop). Writes ../out/lsp_robocop_<tag>.json
"""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

RC, ROOT = sys.argv[1], Path(sys.argv[2]).resolve()
SETTINGS = json.loads(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
TAG = sys.argv[4] if len(sys.argv) > 4 else "default"
DOC = ROOT / "probe.robot"
URI = DOC.as_uri()
TEXT = """*** Settings ***
Library    Collections    WITH NAME    Coll
Force Tags    smoke

*** Test Cases ***
Probe
    ${x}=    Set Variable    5
    Run Keyword If    ${x} > 3    Log    big
    Shuold Be Equal    a    a
    Should Be Equal    a
    Log    ${undefined_var}
"""


class Client:
    def __init__(self) -> None:
        self.p = subprocess.Popen([RC, "language-server", "--stdio"], cwd=ROOT, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        self.q: queue.Queue = queue.Queue()
        self.id = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        f = self.p.stdout
        while True:
            headers = {}
            while True:
                line = f.readline()
                if not line:
                    return
                line = line.decode().strip()
                if not line:
                    break
                k, v = line.split(":", 1)
                headers[k.lower()] = v.strip()
            self.q.put((time.perf_counter(), json.loads(f.read(int(headers["content-length"])))))

    def send(self, msg: dict) -> None:
        b = json.dumps(msg).encode()
        self.p.stdin.write(f"Content-Length: {len(b)}\r\n\r\n".encode() + b)
        self.p.stdin.flush()

    def answer_server_request(self, m: dict) -> None:
        result = None
        if m.get("method") == "workspace/configuration":
            items = m["params"]["items"]
            result = []
            for it in items:
                sec = it.get("section", "")
                val = SETTINGS
                for part in sec.split(".") if sec else []:
                    val = val.get(part) if isinstance(val, dict) else None
                result.append(val)
        self.send({"jsonrpc": "2.0", "id": m["id"], "result": result})

    def request(self, method: str, params: dict | None, timeout: float = 60) -> dict:
        self.id += 1
        rid = self.id
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        end = time.time() + timeout
        while time.time() < end:
            try:
                _, m = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            if m.get("id") == rid and "method" not in m:
                return m
            if "method" in m and "id" in m:
                self.answer_server_request(m)
        raise TimeoutError(method)

    def notify(self, method: str, params: dict | None) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def wait_diags(self, t0: float, settle: float = 3.0, timeout: float = 60) -> tuple:
        last, diags, n = None, None, 0
        end = time.time() + timeout
        while time.time() < end:
            try:
                ts, m = self.q.get(timeout=settle if last else 1.0)
            except queue.Empty:
                if last:
                    break
                continue
            if m.get("method") == "textDocument/publishDiagnostics" and m["params"]["uri"] == URI:
                last, diags, n = ts, m["params"]["diagnostics"], n + 1
            elif "method" in m and "id" in m:
                self.answer_server_request(m)
        return (last - t0 if last else None), diags, n


def main() -> None:
    DOC.write_text(TEXT)
    c = Client()
    try:
        c.request("initialize", {
            "processId": None, "rootUri": ROOT.as_uri(),
            "workspaceFolders": [{"uri": ROOT.as_uri(), "name": "p"}],
            "capabilities": {"workspace": {"configuration": SETTINGS is not None},
                             "textDocument": {"publishDiagnostics": {"versionSupport": True}}},
        })
        c.notify("initialized", {})
        t = time.perf_counter()
        c.notify("textDocument/didOpen", {"textDocument": {"uri": URI, "languageId": "robotframework", "version": 1,
                                                           "text": TEXT}})
        dt, diags, n = c.wait_diags(t)
        rows = [{"source": d.get("source"), "line": d["range"]["start"]["line"] + 1, "code": d.get("code"),
                 "sev": d.get("severity"), "msg": d["message"][:110]} for d in (diags or [])]
        for r in sorted(rows, key=lambda r: (r["source"], r["line"])):
            print(f"{r['source']:<9} L{r['line']:<3} sev{r['sev']} {r['code']}: {r['msg']}")
        print(f"diagnostics after {dt and round(dt, 2)} s, {n} publishes, {len(rows)} diags")
        (Path(__file__).resolve().parent.parent / "out" / f"lsp_robocop_{TAG}.json").write_text(
            json.dumps({"diag_s": dt, "publishes": n, "rows": rows}, indent=1))
        c.request("shutdown", None, timeout=10)
        c.notify("exit", None)
    finally:
        try:
            c.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(c.p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    main()
