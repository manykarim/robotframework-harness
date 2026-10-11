#!/usr/bin/env python3
"""Direct LSP probe for `robotcode language-server --stdio` (round 3, agent_lsp).

Measures: spawn->initialize latency, time to first publishDiagnostics, diagnostics for a file with
planted errors, hover / workspaceSymbol results, RSS of the server process tree.

  python3 lsp_probe.py --proj DIR [--pull] [--no-reply] [--out FILE.jsonl] [--tag NAME]

--pull      advertise textDocument.diagnostic (pull) capability (VS Code-like); default = push only
--no-reply  do NOT answer server->client requests (workspace/configuration etc.) -> dumb-client case
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"

PLANTED = """
Planted Errors
    Launch Storefront
    Clik    id=search-button
    Type Into Product Finder    shoes    extra-arg
    Hit Count Should Be    ${undefined}
"""


def rss_tree_kb(pid):
    """Sum VmRSS of pid and all descendants."""
    kids = {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            st = (d / "stat").read_text()
            ppid = int(st[st.rindex(")") + 2:].split()[1])
            kids.setdefault(ppid, []).append(int(d.name))
        except Exception:
            pass
    total, stack, seen = 0, [pid], []
    while stack:
        p = stack.pop()
        seen.append(p)
        try:
            for line in Path(f"/proc/{p}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1])
        except Exception:
            pass
        stack.extend(kids.get(p, []))
    return total, seen


class Client:
    def __init__(self, proj, reply=True, log=None):
        self.t0 = time.time()
        self.proj = proj
        self.reply = reply
        self.log = log
        cmd = json.loads(os.environ["SERVER_CMD"]) if os.environ.get("SERVER_CMD") else [RC, "language-server", "--stdio"]
        self.p = subprocess.Popen(cmd, cwd=proj, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.next_id = 1
        self.pending = {}
        self.events = []  # (t, msg)
        self.lock = threading.Condition()
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._stderr, daemon=True).start()

    def t(self):
        return round(time.time() - self.t0, 3)

    def _write(self, msg):
        body = json.dumps(msg).encode()
        self.p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.p.stdin.flush()
        self._log("out", msg)

    def _log(self, d, msg):
        if self.log:
            self.log.write(json.dumps({"t": self.t(), "dir": d, "msg": msg}) + "\n")
            self.log.flush()

    def _stderr(self):
        for line in self.p.stderr:
            self._log("stderr", line.decode(errors="replace").rstrip())

    def _reader(self):
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
            msg = json.loads(body)
            self._log("in", msg)
            with self.lock:
                self.events.append((self.t(), msg))
                if "id" in msg and "method" not in msg:
                    self.pending[msg["id"]] = msg
                self.lock.notify_all()
            if "id" in msg and "method" in msg and self.reply:
                m = msg["method"]
                if m == "workspace/configuration":
                    res = [None for _ in msg["params"]["items"]]
                elif m == "workspace/workspaceFolders":
                    res = [{"uri": Path(self.proj).as_uri(), "name": "proj"}]
                else:
                    res = None
                self._write({"jsonrpc": "2.0", "id": msg["id"], "result": res})

    def request(self, method, params, timeout=120):
        i = self.next_id
        self.next_id += 1
        self._write({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
        end = time.time() + timeout
        with self.lock:
            while i not in self.pending:
                left = end - time.time()
                if left <= 0:
                    return {"timeout": True}
                self.lock.wait(left)
            return self.pending.pop(i)

    def notify(self, method, params):
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def wait_diag(self, uri, after_t, timeout=120, settle=1.5):
        """Wait for publishDiagnostics for uri after after_t; return (t_first, last_diags)."""
        end = time.time() + timeout
        first, last, last_t = None, None, None
        with self.lock:
            while time.time() < end:
                for t, m in self.events:
                    if t >= after_t and m.get("method") == "textDocument/publishDiagnostics" \
                            and m["params"]["uri"] == uri:
                        if first is None:
                            first = t
                        last, last_t = m["params"]["diagnostics"], t
                if last_t is not None and self.t() - last_t > settle:
                    break
                self.lock.wait(0.25)
        return first, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proj", required=True)
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--no-reply", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tag", default="probe")
    ap.add_argument("--langid", default="robotframework")
    ap.add_argument("--linger", type=float, default=0)
    ap.add_argument("--change", default="incremental", choices=["full", "incremental", "save", "fullsave", "reopen"])
    a = ap.parse_args()
    proj = str(Path(a.proj).resolve())
    log = open(a.out, "w") if a.out else None
    c = Client(proj, reply=not a.no_reply, log=log)
    res = {"tag": a.tag, "pull": a.pull, "reply": not a.no_reply}
    caps = {"textDocument": {"publishDiagnostics": {"relatedInformation": True, "codeDescriptionSupport": True},
                             "hover": {"contentFormat": ["markdown", "plaintext"]},
                             "synchronization": {"didSave": True}},
            "workspace": {"configuration": True, "workspaceFolders": True, "symbol": {}}}
    if a.pull:
        caps["textDocument"]["diagnostic"] = {"dynamicRegistration": False}
    r = c.request("initialize", {"processId": os.getpid(), "rootUri": Path(proj).as_uri(),
                                 "workspaceFolders": [{"uri": Path(proj).as_uri(), "name": "proj"}],
                                 "capabilities": caps, "clientInfo": {"name": "lsp_probe"}})
    res["t_initialize"] = c.t()
    sc = r.get("result", {}).get("capabilities", {})
    res["server_caps"] = sorted(sc.keys())
    res["diagnosticProvider"] = sc.get("diagnosticProvider")
    c.notify("initialized", {})
    test = Path(proj) / "tests" / "shop.robot"
    uri = test.as_uri()
    text = test.read_text()
    t_open = c.t()
    c.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": a.langid,
                                                        "version": 1, "text": text}})
    if a.pull:
        rr = c.request("textDocument/diagnostic", {"textDocument": {"uri": uri}}, timeout=180)
        res["t_first_diag_clean"] = round(c.t() - t_open, 3)
        res["clean_diags"] = rr.get("result", {}).get("items", rr)
    else:
        first, diags = c.wait_diag(uri, t_open, timeout=180)
        res["t_first_diag_clean"] = round(first - t_open, 3) if first else None
        res["clean_diags"] = diags
    res["rss_after_open_kb"], pids = rss_tree_kb(c.p.pid)
    res["pids"] = pids
    # planted errors via didChange (full sync)
    text2 = text + PLANTED
    t_chg = c.t()
    res["change_mode"] = a.change
    if a.change in ("full", "fullsave"):
        c.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                                             "contentChanges": [{"text": text2}]})
    elif a.change == "incremental":
        nl = len(text.splitlines())
        c.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                                             "contentChanges": [{"range": {"start": {"line": 0, "character": 0},
                                                                           "end": {"line": nl + 1, "character": 0}},
                                                                 "text": text2}]})
    elif a.change == "reopen":
        c.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
        c.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": a.langid,
                                                            "version": 2, "text": text2}})
    if a.change in ("save", "fullsave"):
        test.write_text(text2)
        c.notify("textDocument/didSave", {"textDocument": {"uri": uri}, "text": text2})
    if a.pull:
        rr = c.request("textDocument/diagnostic", {"textDocument": {"uri": uri}}, timeout=180)
        res["t_diag_after_change"] = round(c.t() - t_chg, 3)
        res["planted_diags"] = rr.get("result", {}).get("items", rr)
    else:
        first, diags = c.wait_diag(uri, t_chg, timeout=60)
        res["t_diag_after_change"] = round(first - t_chg, 3) if first else None
        res["planted_diags"] = diags
    if a.linger:
        time.sleep(a.linger)
        res["pushes_during_linger"] = [(t, m["params"].get("version"), len(m["params"]["diagnostics"]))
                                       for t, m in c.events if m.get("method") == "textDocument/publishDiagnostics"]
    # hover on 'Probe Catalog Endpoint' (line 7, 0-based) and on 'Clik' line
    lines = text2.splitlines()
    ln = next(i for i, l in enumerate(lines) if "Probe Catalog Endpoint" in l)
    col = lines[ln].index("Probe Catalog Endpoint") + 3
    res["hover_project_kw"] = c.request("textDocument/hover", {"textDocument": {"uri": uri},
                                                               "position": {"line": ln, "character": col}}).get("result")
    ln2 = next(i for i, l in enumerate(lines) if "Should Be Equal As Integers" in l)
    res["hover_builtin_kw"] = c.request("textDocument/hover", {"textDocument": {"uri": uri},
                                                               "position": {"line": ln2, "character": 8}}).get("result")
    res_uri = (Path(proj) / "resources" / "shop.resource").as_uri()
    rtext = (Path(proj) / "resources" / "shop.resource").read_text()
    c.notify("textDocument/didOpen", {"textDocument": {"uri": res_uri, "languageId": "robotframework",
                                                        "version": 1, "text": rtext}})
    rl = rtext.splitlines()
    ln3 = next(i for i, l in enumerate(rl) if "Fill Text" in l)
    res["hover_library_kw"] = c.request("textDocument/hover", {"textDocument": {"uri": res_uri},
                                                               "position": {"line": ln3, "character": 6}}).get("result")
    for q in ("Product", "Fill Text", "Get Element Count", "Probe"):
        r = c.request("workspace/symbol", {"query": q})
        res[f"wsym_{q}"] = [(s.get("name"), s.get("containerName"), s.get("location", {}).get("uri", "")[-40:])
                            for s in (r.get("result") or [])][:10]
    res["rss_end_kb"], _ = rss_tree_kb(c.p.pid)
    c.request("shutdown", None, timeout=10)
    c.notify("exit", None)
    try:
        c.p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        c.p.kill()
    res["t_total"] = c.t()
    res["server_requests_seen"] = sorted({m.get("method") for _, m in c.events if "method" in m and "id" in m})
    res["notifications_seen"] = sorted({m.get("method") for _, m in c.events if "method" in m and "id" not in m})
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
