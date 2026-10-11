"""Probe `robotcode language-server --stdio` as a warm, client-side validator daemon.

Measures time from didOpen/didChange to publishDiagnostics for single-step documents,
plus completion (keyword list) and hover (keyword doc) payload sizes.

Usage: <venv-python> lsp_probe.py <robotcode-bin> <project-root>
"""

from __future__ import annotations

import json
import os
import signal
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

RC, ROOT = sys.argv[1], Path(sys.argv[2]).resolve()
MODE = sys.argv[3] if len(sys.argv) > 3 else "reopen"
SETTLE = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
PULL = len(sys.argv) > 5 and sys.argv[5] == "pull"
DOC = ROOT / "cases" / "_lsp_step.robot"
URI = DOC.as_uri()


class Client:
    def __init__(self):
        self.p = subprocess.Popen([RC, "language-server", "--stdio"], cwd=ROOT, stdin=subprocess.PIPE, start_new_session=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.q: queue.Queue = queue.Queue()
        self.id = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
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
            body = f.read(int(headers["content-length"]))
            self.q.put((time.perf_counter(), json.loads(body)))

    def send(self, msg):
        b = json.dumps(msg).encode()
        self.p.stdin.write(f"Content-Length: {len(b)}\r\n\r\n".encode() + b)
        self.p.stdin.flush()

    def request(self, method, params, timeout=60):
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
            if "method" in m and "id" in m:  # server->client request: answer null
                self.send({"jsonrpc": "2.0", "id": m["id"], "result": None})
        raise TimeoutError(method)

    def notify(self, method, params):
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def wait_diags(self, t0, settle=SETTLE, timeout=60):
        """Collect publishDiagnostics for URI until quiet for `settle` s. Return (t_last, diags, n_pub)."""
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
                self.send({"jsonrpc": "2.0", "id": m["id"], "result": None})
        return (last - t0 if last else None), diags, n


STEPS = [
    ("v1 Fill Text missing arg", "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nStep\n    Fill Text    id=user\n"),
    ("v2 fixed", "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nStep\n    Fill Text    id=user    bob\n"),
    ("v3 typo Clik", "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nStep\n    Clik    id=user\n"),
    ("v4 add RequestsLibrary + undefined var", "*** Settings ***\nLibrary    Browser\nLibrary    RequestsLibrary\n\n*** Test Cases ***\nStep\n    POST On Session    api    /x    json=${body}\n"),
    ("v5 selenium kw in browser session", "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nStep\n    Input Text    id=user    bob\n"),
]


def main():
    c = Client()
    t0 = time.perf_counter()
    init = c.request("initialize", {
        "processId": None, "rootUri": ROOT.as_uri(),
        "workspaceFolders": [{"uri": ROOT.as_uri(), "name": "corpus"}],
        "capabilities": {"textDocument": {"publishDiagnostics": {"versionSupport": True}, "diagnostic": {"dynamicRegistration": False}, "hover": {"contentFormat": ["markdown"]},
                                          "completion": {"completionItem": {"snippetSupport": False}}}},
    })
    c.notify("initialized", {})
    t_init = time.perf_counter() - t0
    caps = sorted(init["result"]["capabilities"].keys())
    print(f"initialize: {t_init:.2f}s; server capabilities: {caps}; diagnosticProvider={init['result']['capabilities'].get('diagnosticProvider')}")
    rows = []
    for i, (label, text) in enumerate(STEPS, start=1):
        t = time.perf_counter()
        if MODE == "change" and i > 1:
            c.notify("textDocument/didChange", {"textDocument": {"uri": URI, "version": i}, "contentChanges": [{"text": text}]})
        else:
            if i > 1:
                c.notify("textDocument/didClose", {"textDocument": {"uri": URI}})
            c.notify("textDocument/didOpen", {"textDocument": {"uri": URI, "languageId": "robotframework", "version": i, "text": text}})
        if PULL:
            r = c.request("textDocument/diagnostic", {"textDocument": {"uri": URI}}, timeout=30)
            dt, n = time.perf_counter() - t, 1
            diags = (r.get("result") or {}).get("items", [])
        else:
            dt, diags, n = c.wait_diags(t, timeout=20)
        # drop robocop style/lint findings (codes like SPC02-..., DOC03-...) - keep robotcode analysis codes
        summary = [f"{d.get('code')}: {d['message'][:80]}" for d in (diags or []) if "-" not in str(d.get("code"))]
        rows.append({"step": label, "diag_s": dt, "publishes": n, "diags": summary})
        print(f"{label:<42} diagnostics after {dt if dt is None else round(dt, 3)} s ({n} publishes) {summary}")
    # completion at start of the step body line (keyword position) of last doc
    t = time.perf_counter()
    comp = c.request("textDocument/completion", {"textDocument": {"uri": URI}, "position": {"line": 5, "character": 4}})
    t_comp = time.perf_counter() - t
    items = comp["result"]["items"] if isinstance(comp["result"], dict) else (comp["result"] or [])
    print(f"completion at keyword position: {t_comp:.3f}s, {len(items)} items, {len(json.dumps(comp))} chars")
    t = time.perf_counter()
    hov = c.request("textDocument/hover", {"textDocument": {"uri": URI}, "position": {"line": 5, "character": 6}})
    t_hov = time.perf_counter() - t
    hv = json.dumps(hov.get("result"))
    print(f"hover on 'Input Text': {t_hov:.3f}s, {len(hv)} chars: {hv[:160]}")
    c.request("shutdown", None)
    c.notify("exit", None)
    try:
        c.p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:  # robotcode forks the real server; kill the whole process group
        os.killpg(c.p.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    out = Path(__file__).resolve().parent.parent / "outputs" / "q4" / "lsp_probe.json"
    out.write_text(json.dumps({"init_s": t_init, "capabilities": caps, "rows": rows, "completion_s": t_comp,
                               "completion_items": len(items), "hover_s": t_hov, "hover_chars": len(hv)}, indent=1))


if __name__ == "__main__":
    main()
