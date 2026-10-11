"""Static-gate daemon: warm robotcode analyzer + robocop (agent profile) + portability, behind a unix socket.

Separate from the live-session daemon so a PreToolUse gate never waits for a long-running RF step.
Ops (one JSON line per connection): ping | status | gate {path, current, proposed, wait} | check {path} | stop.

gate = "is this proposed file content worse than the current one?":
  * robotcode diagnostics of the proposed text; HARD = KeywordNotFound, ModelError, TokenError, DataError (arg
    counts, missing resource, failed library import) that are NEW (not present in the current text);
  * robocop agent profile on a hidden temp copy: E findings on changed lines (deduped against robotcode),
    fixable findings (deprecated syntax, lowercase else ...) -> robocop's safe fix applied to the temp copy;
  * portability: imports that only resolve via ./lib, ./resources, -P (plain `robot` fails) -> HARD if new.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import signal
import socket
import struct
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import procs, proto
from .hookcore import changed_line_numbers

CONFIG = Path(__file__).with_name("data") / "robocop-agent.toml"
PROJECT_RULES = ["KW05", "KW06", "ARG08", "IMP07", "IMP09"]   # robotcode reports these (better messages)
HARD_CODES = {"KeywordNotFound", "ModelError", "TokenError", "DataError", "KeywordError", "ImportError",
              "ParsingError", "InvalidHeader"}
SOFT_DATAERROR = re.compile(r"variable|Variable", re.I)
WELL_KNOWN = ["Browser", "RequestsLibrary", "SeleniumLibrary", "Collections", "String", "DateTime", "OperatingSystem"]


def _cmdline(pid: int) -> bytes:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read()
    except OSError:
        return b""


class Lint:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.wa: Any = None
        self.cache: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        self.warm_ms: Optional[float] = None
        self.warm_error: Optional[str] = None
        self.n_gate = 0

    # ------------------------------------------------------------------ warm-up
    def warm(self) -> None:
        t0 = time.perf_counter()
        with self.lock:
            try:
                from .analyzer import WarmAnalyzer

                self.wa = WarmAnalyzer(self.root)
                from robocop.run import check_files  # noqa: F401  (import cost now, not in the first gate)

                libs = self._libs()
                synth = self.root / ".rf" / "lint" / "__warm__.robot"
                text = "*** Settings ***\n" + "".join(f"Library    {l}\n" for l in libs) + \
                       "\n*** Test Cases ***\nWarm\n    No Operation\n"
                self._analyze(synth, text)
                for f in self._rf_files()[:25]:
                    with contextlib.suppress(Exception):
                        self._analyze(f, f.read_text(errors="replace"))
            except Exception as e:
                self.warm_error = f"{type(e).__name__}: {e}"[:300]
            self.warm_ms = round((time.perf_counter() - t0) * 1000)
            self.ready.set()

    def _rf_files(self) -> List[Path]:
        out = []
        for dp, dns, fns in os.walk(self.root):
            dns[:] = [d for d in dns if not d.startswith(".") and d not in ("node_modules", "results", "venv")]
            out += [Path(dp) / f for f in fns if f.endswith((".robot", ".resource")) and not f.startswith(".")]
        return out

    def _libs(self) -> List[str]:
        import importlib.util

        found: List[str] = []
        for f in self._rf_files()[:200]:
            with contextlib.suppress(OSError):
                for line in f.read_text(errors="replace").splitlines():
                    m = re.match(r"^Library\s{2,}([\w.]+)\s*(?:$|\s{2})", line)
                    if m and not m.group(1).endswith(".py") and m.group(1) not in found:
                        found.append(m.group(1))
        out = []
        for l in found + ["Browser", "RequestsLibrary"]:
            if l in out:
                continue
            try:
                ok = l in ("Collections", "String", "DateTime", "OperatingSystem", "Process", "XML") or \
                    importlib.util.find_spec(l.split(".")[0]) is not None
            except (ImportError, ValueError):
                ok = False
            if ok:
                out.append(l)
        return out[:8]

    # ------------------------------------------------------------------ robotcode
    def _analyze(self, path: Path, text: str) -> List[Dict[str, Any]]:
        from robotcode.core.uri import Uri

        key = (str(path), str(hash(text)))
        if key in self.cache:
            return self.cache[key]
        wa = self.wa
        wa._refresh_resources()
        docs = wa.ca.workspace.documents
        uri = Uri.from_path(path).normalized()
        doc = docs.get(uri)
        if doc is None:
            if path.exists():
                doc = docs.get_or_open_document(path)
            else:
                doc = docs._append_document(document_uri=str(uri), language_id="robotframework", text=text,
                                            version=1)
        if doc.text() != text or doc.version is None:
            doc.apply_full_change((doc.version or 0) + 1, text)
        ns = wa.cache.get_namespace(doc)
        ns.analyze()
        raw = wa.cache.get_diagnostic_modifier(doc).modify_diagnostics(ns.diagnostics)
        out = []
        for d in raw:
            sev = int(d.severity or 1)
            if sev > 2:
                continue
            out.append({"line": d.range.start.line + 1, "col": d.range.start.character + 1, "sev": sev,
                        "code": str(d.code), "msg": d.message.splitlines()[0][:300]})
        if len(self.cache) > 400:
            self.cache.clear()
        self.cache[key] = out
        return out

    def _restore(self, path: Path) -> None:
        """after analyzing a proposed .resource text: put the disk text back (others import it)."""
        if path.suffix != ".resource" or self.wa is None:
            return
        with contextlib.suppress(Exception):
            from robotcode.core.uri import Uri

            doc = self.wa.ca.workspace.documents.get(Uri.from_path(path).normalized())
            if doc is not None and path.exists():
                t = path.read_text(errors="replace")
                if doc.text() != t:
                    doc.apply_full_change((doc.version or 0) + 1, t)

    # ------------------------------------------------------------------ robocop
    def _robocop(self, tmp: Path, fix: bool) -> list:
        from robocop.run import check_files

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return check_files(sources=[str(tmp)], root=self.root, configuration_file=CONFIG, fix=fix,
                               return_result=True, silent=True, skip_gitignore=True, exit_zero=True,
                               ignore=PROJECT_RULES, cache=False)

    def _robocop_text(self, path: Path, text: str, want_fix: bool) -> Tuple[List[Dict[str, Any]], Optional[str], List[Dict[str, Any]]]:
        """-> (issues, fixed_text|None, portability issues) on a hidden temp copy next to the file."""
        in_place = path.parent.is_dir()     # new file in a new dir: lint a copy under .rf/lint (no portability)
        base = path.parent if in_place else self.root / ".rf" / "lint"
        tmp = base / f".{path.stem}.rfh-gate{os.getpid()}{path.suffix}"
        issues: List[Dict[str, Any]] = []
        fixed = None
        port: List[Dict[str, Any]] = []
        try:
            tmp.write_text(text, encoding="utf-8")
            for d in self._robocop(tmp, False):
                issues.append({"line": d.range.start.line, "rule": d.rule.rule_id, "name": d.rule.name,
                               "sev": str(d.severity.value), "fixable": bool(getattr(d.rule, "fixable", False)),
                               "msg": str(d.message)[:200]})
            if in_place:
                try:
                    from .portable import issues as portable_issues

                    port = portable_issues(tmp, self.root)
                except Exception:
                    port = []
            if want_fix and any(i["fixable"] for i in issues):
                self._robocop(tmp, True)
                fixed = tmp.read_text(encoding="utf-8")
                if fixed == text:
                    fixed = None
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()
        return issues, fixed, port

    # ------------------------------------------------------------------ ops
    @staticmethod
    def _hard(d: Dict[str, Any]) -> bool:
        if d["code"] not in HARD_CODES or d["sev"] != 1:
            return False
        return not (d["code"] == "DataError" and SOFT_DATAERROR.search(d["msg"]) and "argument" not in d["msg"])

    def gate(self, req: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        if not self.ready.wait(float(req.get("wait", 1.5))):
            return {"ok": True, "ready": False, "note": "static gate warming up"}
        if self.wa is None:
            return {"ok": True, "ready": False, "note": f"static gate unavailable: {self.warm_error}"}
        path = Path(req["path"]).resolve()
        cur = req.get("current")
        new = req["proposed"]
        if not self.lock.acquire(timeout=float(req.get("wait", 1.5))):
            return {"ok": True, "ready": False, "note": "static gate busy"}
        try:
            self.n_gate += 1
            changed = changed_line_numbers(cur, new)
            chg = set(changed) if changed is not None else None
            lines = new.splitlines()
            d_new = self._analyze(path, new)
            t_an = time.perf_counter()
            d_cur: List[Dict[str, Any]] = []
            cur_lines = cur.splitlines() if cur else []
            if cur:
                d_cur = self._analyze(path, cur)
            self._restore(path)

            def key(d, ls):
                txt = ls[d["line"] - 1].strip() if 0 < d["line"] <= len(ls) else ""
                return (d["code"], d["msg"], txt)

            cur_keys: Dict[Tuple, int] = {}
            for d in d_cur:
                cur_keys[key(d, cur_lines)] = cur_keys.get(key(d, cur_lines), 0) + 1
            new_diags = []
            for d in d_new:
                k = key(d, lines)
                if cur_keys.get(k):
                    cur_keys[k] -= 1
                    continue
                new_diags.append(d)
            rc, fixed, port = self._robocop_text(path, new, want_fix=bool(req.get("fix", True)))
            t_rc = time.perf_counter()
            fix_lines = {i["line"] for i in rc if i["fixable"] and (chg is None or i["line"] in chg)}
            hard = [d for d in new_diags if self._hard(d) and d["line"] not in fix_lines]
            fixable_errors = [d for d in new_diags if self._hard(d) and d["line"] in fix_lines]
            hard_lines = {d["line"] for d in hard}
            warnings = [d for d in new_diags if not self._hard(d) and (chg is None or d["line"] in chg)]
            rc_err = [i for i in rc if i["sev"] == "E" and not i["fixable"] and i["line"] not in hard_lines
                      and (chg is None or i["line"] in chg) and not i["rule"].startswith("SPC")]
            for i in rc_err:
                hard.append({"line": i["line"], "code": i["rule"], "msg": i["msg"], "sev": 1, "src": "robocop"})
            fixes = [i for i in rc if i["fixable"] and (chg is None or i["line"] in chg)]
            port_new = []
            if port:
                cur_port = {p["msg"] for p in self._robocop_text(path, cur, want_fix=False)[2]} if cur else set()
                port_new = [p for p in port if p["msg"] not in cur_port]
            for p in port_new:
                hard.append({"line": p["line"], "code": "NotPortable", "msg": p["msg"], "sev": 1})
            hard.sort(key=lambda d: d["line"])
            return {"ok": True, "ready": True, "errors": hard[:12], "fixable_errors": fixable_errors[:6],
                    "fixes": [{"line": i["line"], "rule": i["rule"], "name": i["name"], "msg": i["msg"]}
                              for i in fixes][:10],
                    "fixed": fixed if fixes else None, "warnings": warnings[:6],
                    "changed": len(changed) if changed is not None else None,
                    "ms": {"total": round((time.perf_counter() - t0) * 1000, 1),
                           "analyze": round((t_an - t0) * 1000, 1), "robocop": round((t_rc - t_an) * 1000, 1)}}
        finally:
            self.lock.release()

    def check(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """diagnostics of the file on disk (errors only), for the live filter of the exec daemon."""
        if not self.ready.wait(float(req.get("wait", 1.0))) or self.wa is None:
            return {"ok": True, "ready": False}
        path = Path(req["path"]).resolve()
        if not self.lock.acquire(timeout=float(req.get("wait", 1.0))):
            return {"ok": True, "ready": False, "note": "busy"}
        try:
            t0 = time.perf_counter()
            text = path.read_text(errors="replace")
            ds = [d for d in self._analyze(path, text) if d["sev"] == 1]
            return {"ok": True, "ready": True, "diags": ds[:40], "ms": round((time.perf_counter() - t0) * 1000, 1)}
        finally:
            self.lock.release()


class Server(threading.Thread):
    def __init__(self, lint: Lint, sd: Path) -> None:
        super().__init__(name="rfh-lint", daemon=True)
        self.lint = lint
        self.path = proto.unix_sock_path(sd)
        if self.path.exists():
            self.path.unlink()
        old = os.umask(0o177)
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.bind(str(self.path))
        finally:
            os.umask(old)
        self.sock.listen(16)
        self.stop = threading.Event()
        self.last = time.time()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        try:
            if hasattr(socket, "SO_PEERCRED"):
                _p, uid, _g = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    return
            buf = bytearray()
            while not buf.endswith(b"\n"):
                c = conn.recv(65536)
                if not c:
                    return
                buf += c
            req = json.loads(buf)
            self.last = time.time()
            op = req.get("op")
            try:
                if op == "ping":
                    resp = {"ok": True, "pid": os.getpid(), "ready": self.lint.ready.is_set()}
                elif op == "status":
                    resp = {"ok": True, "pid": os.getpid(), "ready": self.lint.ready.is_set(),
                            "warm_ms": self.lint.warm_ms, "warm_error": self.lint.warm_error, "gates": self.lint.n_gate}
                elif op == "gate":
                    resp = self.lint.gate(req)
                elif op == "check":
                    resp = self.lint.check(req)
                elif op == "stop":
                    self.stop.set()
                    resp = {"ok": True, "stopping": True}
                else:
                    resp = {"ok": False, "error": f"unknown op {op!r}"}
            except Exception as e:
                resp = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300], "tb": traceback.format_exc()[-600:]}
            conn.sendall(json.dumps(resp, default=str).encode() + b"\n")
        except Exception:
            pass
        finally:
            conn.close()

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.close()
        with contextlib.suppress(OSError):
            self.path.unlink()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="rfharness31.lintd")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--watch-pid", type=int, default=0)
    ap.add_argument("--idle", type=float, default=1200.0)
    o = ap.parse_args(argv)
    sd = Path(o.dir)
    proto.ensure_private_dir(sd)
    root = Path(o.root).resolve()
    os.chdir(root)
    lint = Lint(root)
    srv = Server(lint, sd)
    state = {"pid": os.getpid(), "transport": "unix", "sock": str(srv.path), "ready": False, "started": time.time(),
             "token_env": os.environ.get(procs.TOKEN_ENV), "watch_pid": o.watch_pid, "kind": "lint"}
    proto.write_state(sd, state)
    signal.signal(signal.SIGTERM, lambda s, f: srv.stop.set())
    srv.start()
    state["ready"] = True          # socket answers; gate readiness is reported per request
    proto.write_state(sd, state)
    threading.Thread(target=lint.warm, daemon=True).start()
    why = "stop"
    while not srv.stop.wait(0.5):
        if o.watch_pid and not proto.pid_alive(o.watch_pid):
            why = "agent exited"
            break
        if o.idle and time.time() - srv.last > o.idle:
            why = "idle"
            break
    srv.close()
    kids = procs.descendants(os.getpid())   # robotcode's spawn workers ignore SIGTERM
    for p in kids:
        with contextlib.suppress(OSError):
            os.kill(p, signal.SIGKILL)
    state.update(ready=False, stopped=time.time(), why=why, killed=len(kids))
    proto.write_state(sd, state)
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
