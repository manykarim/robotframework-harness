"""Minimal stdlib LSP client for `robotcode language-server --stdio` (round 3).

Fixes vs round-1 probe:
  * robotcode advertises INCREMENTAL sync -> full-text didChange without `range` raises
    LanguageServerDocumentError; we always send ranged edits.
  * `textDocument/diagnostic` (pull) is a stub in robotcode 2.7 (always returns []);
    diagnostics arrive only via publishDiagnostics from the workspace loop.
  * settings are passed as initializationOptions {"settings": {"robotcode": {...}}}.

Every process is started in its own session and tagged with RFMCP_R3_LSPQ=<tag> so the
cleanup can find leftovers without touching other agents' processes.
"""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TAG_ENV = "RFMCP_R3_LSPQ"


def tree_rss_mb(pid: int) -> float:
    try:
        import psutil
    except ImportError:
        return -1.0
    try:
        p = psutil.Process(pid)
        procs = [p, *p.children(recursive=True)]
        return round(sum(x.memory_info().rss for x in procs if x.is_running()) / 2**20, 1)
    except psutil.Error:
        return -1.0


def tree_pids(pid: int) -> List[int]:
    try:
        import psutil

        p = psutil.Process(pid)
        return [p.pid, *[c.pid for c in p.children(recursive=True)]]
    except Exception:
        return [pid]


class LSP:
    def __init__(self, robotcode: str, root: Path, extra_args: Optional[List[str]] = None,
                 log: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> None:
        self.root = Path(root).resolve()
        e = dict(os.environ)
        e[TAG_ENV] = "1"
        e.update(env or {})
        self.t_spawn = time.perf_counter()
        self.p = subprocess.Popen([robotcode, *(extra_args or []), "language-server", "--stdio"], cwd=self.root,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=open(log, "ab") if log else subprocess.DEVNULL,
                                  start_new_session=True, env=e)
        self.q: "queue.Queue[Tuple[float, Dict[str, Any]]]" = queue.Queue()
        self.responses: Dict[int, Tuple[float, Dict[str, Any]]] = {}
        self.resp_cv = threading.Condition()
        self.diags: Dict[str, List[Tuple[float, Optional[int], List[Dict[str, Any]]]]] = {}
        self.diag_cv = threading.Condition()
        self.server_requests: List[str] = []
        self.logs: List[str] = []
        self.id = 0
        self.versions: Dict[str, int] = {}
        self.texts: Dict[str, str] = {}
        self._wlock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    # ---------------------------------------------------------------- transport
    def _read(self) -> None:
        f = self.p.stdout
        assert f is not None
        while True:
            headers: Dict[str, str] = {}
            while True:
                line = f.readline()
                if not line:
                    return
                s = line.decode().strip()
                if not s:
                    break
                k, v = s.split(":", 1)
                headers[k.lower()] = v.strip()
            body = f.read(int(headers["content-length"]))
            ts = time.perf_counter()
            m = json.loads(body)
            self._dispatch(ts, m)

    def _dispatch(self, ts: float, m: Dict[str, Any]) -> None:
        if "method" in m and "id" in m:  # server -> client request
            self.server_requests.append(m["method"])
            result: Any = None
            if m["method"] == "workspace/configuration":
                result = [None for _ in m["params"]["items"]]
            self.send({"jsonrpc": "2.0", "id": m["id"], "result": result})
            return
        if "method" in m:
            if m["method"] == "textDocument/publishDiagnostics":
                pr = m["params"]
                with self.diag_cv:
                    self.diags.setdefault(pr["uri"], []).append((ts, pr.get("version"), pr["diagnostics"]))
                    self.diag_cv.notify_all()
            elif m["method"] == "window/logMessage":
                self.logs.append(m["params"].get("message", "")[:300])
            return
        with self.resp_cv:
            self.responses[m.get("id")] = (ts, m)
            self.resp_cv.notify_all()

    def send(self, msg: Dict[str, Any]) -> None:
        b = json.dumps(msg).encode()
        with self._wlock:
            assert self.p.stdin is not None
            self.p.stdin.write(f"Content-Length: {len(b)}\r\n\r\n".encode() + b)
            self.p.stdin.flush()

    def request(self, method: str, params: Any, timeout: float = 120) -> Dict[str, Any]:
        self.id += 1
        rid = self.id
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        end = time.time() + timeout
        with self.resp_cv:
            while rid not in self.responses:
                left = end - time.time()
                if left <= 0:
                    raise TimeoutError(method)
                self.resp_cv.wait(left)
            return self.responses.pop(rid)[1]

    def notify(self, method: str, params: Any) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    # ---------------------------------------------------------------- lifecycle
    def initialize(self, settings: Optional[Dict[str, Any]] = None, pull: bool = False,
                   watch: bool = False) -> Dict[str, Any]:
        caps: Dict[str, Any] = {
            "textDocument": {
                "synchronization": {"didSave": True},
                "publishDiagnostics": {"versionSupport": True, "relatedInformation": True},
                "hover": {"contentFormat": ["markdown", "plaintext"]},
                "signatureHelp": {"signatureInformation": {"documentationFormat": ["markdown"],
                                                           "parameterInformation": {"labelOffsetSupport": True}}},
                "completion": {"completionItem": {"snippetSupport": False, "documentationFormat": ["markdown"],
                                                  "resolveSupport": {"properties": ["documentation", "detail"]}}},
                "definition": {"linkSupport": True},
            },
            "workspace": {"workspaceFolders": True, "symbol": {}},
        }
        if pull:
            caps["textDocument"]["diagnostic"] = {"dynamicRegistration": False}
        if watch:
            caps["workspace"]["didChangeWatchedFiles"] = {"dynamicRegistration": True}
        t0 = time.perf_counter()
        r = self.request("initialize", {
            "processId": os.getpid(), "rootUri": self.root.as_uri(), "rootPath": str(self.root),
            "workspaceFolders": [{"uri": self.root.as_uri(), "name": self.root.name}],
            "capabilities": caps,
            "initializationOptions": {"settings": {"robotcode": settings or {}}},
        })
        self.notify("initialized", {})
        self.t_init = time.perf_counter() - t0
        self.init_result = r.get("result") or {}
        return r

    def shutdown(self) -> None:
        pids = tree_pids(self.p.pid)
        try:
            self.request("shutdown", None, timeout=5)
            self.notify("exit", None)
        except Exception:
            pass
        try:
            self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(self.p.pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
            time.sleep(0.2)
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    # ---------------------------------------------------------------- documents
    @staticmethod
    def uri(path: Path) -> str:
        return Path(path).resolve().as_uri()

    def open(self, path: Path, text: Optional[str] = None) -> Tuple[str, int, float]:
        path = Path(path).resolve()
        text = path.read_text() if text is None else text
        u = self.uri(path)
        self.versions[u] = 1
        self.texts[u] = text
        t = time.perf_counter()
        self.notify("textDocument/didOpen", {"textDocument": {"uri": u, "languageId": "robotframework",
                                                              "version": 1, "text": text}})
        return u, 1, t

    def close(self, path: Path) -> None:
        u = self.uri(path)
        self.notify("textDocument/didClose", {"textDocument": {"uri": u}})

    def replace_all(self, path: Path, text: str) -> Tuple[str, int, float]:
        u = self.uri(path)
        old = self.texts[u]
        lines = old.split("\n")
        end = {"line": len(lines) - 1, "character": len(lines[-1])}
        return self._change(u, [{"range": {"start": {"line": 0, "character": 0}, "end": end}, "text": text}], text)

    def append(self, path: Path, added: str) -> Tuple[str, int, float]:
        """Ranged insert at end of document (what an editor/agent Edit produces)."""
        u = self.uri(path)
        old = self.texts[u]
        lines = old.split("\n")
        pos = {"line": len(lines) - 1, "character": len(lines[-1])}
        return self._change(u, [{"range": {"start": pos, "end": pos}, "text": added}], old + added)

    def _change(self, u: str, changes: List[Dict[str, Any]], new_text: str) -> Tuple[str, int, float]:
        self.versions[u] += 1
        self.texts[u] = new_text
        t = time.perf_counter()
        self.notify("textDocument/didChange", {"textDocument": {"uri": u, "version": self.versions[u]},
                                               "contentChanges": changes})
        return u, self.versions[u], t

    def save(self, path: Path) -> None:
        self.notify("textDocument/didSave", {"textDocument": {"uri": self.uri(path)}})

    # ---------------------------------------------------------------- diagnostics
    def wait_diags(self, u: str, version: int, t0: float, timeout: float = 60.0, settle: float = 0.6,
                   source: Optional[str] = "robotcode") -> Dict[str, Any]:
        """Wait for publishDiagnostics for `u` with version >= `version` (robotcode sends version).
        Return first/last publish latency, number of publishes and the final diagnostics."""
        end = time.time() + timeout
        first = last = None
        n = 0
        diags: List[Dict[str, Any]] = []
        seen = 0
        with self.diag_cv:
            # skip publishes that arrived before t0
            lst = self.diags.setdefault(u, [])
            seen = len([x for x in lst if x[0] < t0])
            while True:
                lst = self.diags[u]
                while seen < len(lst):
                    ts, ver, d = lst[seen]
                    seen += 1
                    if ts < t0 or (ver is not None and ver < version):
                        continue
                    n += 1
                    if first is None:
                        first = ts
                    last = ts
                    diags = d
                now = time.time()
                if now >= end:
                    break
                if last is not None and time.perf_counter() - last >= settle:
                    break
                self.diag_cv.wait(min(0.05, end - now))
        filt = [d for d in diags if source is None or str(d.get("source", "")).startswith(source)]
        return {"first_s": None if first is None else round(first - t0, 3),
                "last_s": None if last is None else round(last - t0, 3),
                "publishes": n, "diags": filt, "all_diags": diags}

    # ---------------------------------------------------------------- features
    def pos_req(self, method: str, path: Path, line: int, char: int, extra: Optional[Dict[str, Any]] = None,
                timeout: float = 60) -> Tuple[float, Dict[str, Any]]:
        t = time.perf_counter()
        r = self.request(method, {"textDocument": {"uri": self.uri(path)},
                                  "position": {"line": line, "character": char}, **(extra or {})}, timeout=timeout)
        return round(time.perf_counter() - t, 4), r


def short(d: Dict[str, Any]) -> str:
    sev = {1: "E", 2: "W", 3: "I", 4: "H"}.get(d.get("severity", 0), "?")
    return f"{sev} L{d['range']['start']['line'] + 1} {d.get('code')}: {d.get('message', '').splitlines()[0][:110]}"
