"""Helper daemon: robotcode's REPL engine (run_repl + BaseInterpreter) fed from a local socket.

Main thread : run_repl() -> RF suite -> our interpreter.run_input() loop (all RF work happens here)
Thread      : socket server; enqueues step/vars/stop requests, answers ping/status/result itself
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import queue
import signal
import socket
import struct
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from robot.errors import ExecutionFailed, ExecutionPassed, ExecutionStatus
from robot.libraries.BuiltIn import BuiltIn
from robot.running.signalhandler import STOP_SIGNAL_MONITOR, _StopSignalMonitor

from robotcode.plugin import Application
from robotcode.repl.base_interpreter import BaseInterpreter
from robotcode.repl.run import run_repl

from . import procs, proto
from .hooks import Hook, Redactor, StepCtx, build_hooks, resolve_owner

_ids = itertools.count(1)
MAXT = 400


def _importer() -> Any:
    """RF-internal: the global Importer moved between RF 7.3 (namespace) and 7.5 (importer)."""
    try:
        from robot.running.importer import IMPORTER  # RF 7.5
    except ImportError:
        from robot.running.namespace import IMPORTER  # RF <= 7.4
    return IMPORTER


def _t(s: Any, n: int = MAXT) -> str:
    s = s if isinstance(s, str) else repr(s)
    return s if len(s) <= n else s[: n - 3] + "..."


class Request:
    def __init__(self, op: str, data: Dict[str, Any]) -> None:
        self.op, self.data, self.id = op, data, next(_ids)
        self.done = threading.Event()
        self.resp: Optional[Dict[str, Any]] = None

    def reply(self, resp: Dict[str, Any]) -> None:
        self.resp = resp
        self.done.set()


class _Tee:
    def __init__(self, orig: Any, sink: List[str]) -> None:
        self.orig, self.sink = orig, sink

    def write(self, s: str) -> int:
        self.sink.append(s)
        return len(s)

    def flush(self) -> None:
        pass

    def __getattr__(self, n: str) -> Any:
        return getattr(self.orig, n)


class HelperInterpreter(BaseInterpreter):
    def __init__(self, hooks: List[Hook], journal: Path, log_levels=("WARN", "ERROR"), on_ready=None) -> None:
        super().__init__()
        self.hooks = hooks
        self.redactor = next((h for h in hooks if isinstance(h, Redactor)), None)
        self.journal = journal
        self.log_levels = set(log_levels)
        self.on_ready = on_ready
        self.requests: "queue.Queue[Request]" = queue.Queue()
        self.stop_flag = threading.Event()
        self.ready = threading.Event()
        self.busy: Optional[Dict[str, Any]] = None
        self.results: "OrderedDict[int, Dict[str, Any]]" = OrderedDict()
        self.n_cells = 0
        self.t_start = time.time()
        self.baseline: set = set()
        self._depth = 0
        self._top: Any = None
        self._nested_fail: Optional[str] = None
        self._logs: Optional[List[str]] = None
        self._in_hook = False
        self._res_mtime: Dict[str, int] = {}
        self.graceful = False
        self.stop_info: Dict[str, Any] = {}

    # --- BaseInterpreter API -------------------------------------------------
    def get_input(self):  # not used: run_input is overridden
        return iter(())

    def run_input(self) -> None:
        if not self.ready.is_set():
            self.baseline = set(BuiltIn().get_variables().keys())
            self.ready.set()
            if self.on_ready:
                self.on_ready()
        req = self._next()
        if req is None:
            self._on_stop()
            raise EOFError
        try:
            if req.op == "step":
                self.busy = {"id": req.id, "since": time.time(), "cell": _t(req.data.get("cells"), 120)}
                resp = self._run_cells(req)
            elif req.op == "vars":
                resp = self._vars(req.data)
            else:
                resp = {"ok": False, "error": f"unknown op {req.op}"}
        except (SystemExit, KeyboardInterrupt):
            req.reply({"ok": False, "error": "helper exiting"})
            raise
        except BaseException as e:  # keep the daemon alive
            resp = {"ok": False, "error": _t(f"{type(e).__name__}: {e}")}
        finally:
            self.busy = None
        self.results[req.id] = resp
        while len(self.results) > 50:
            self.results.popitem(last=False)
        req.reply(resp)

    def _on_stop(self) -> None:
        """graceful=True: close Browser/Playwright in-process (flushes traces/videos) instead of
        relying on atexit (slow) or on the post-run SIGTERM sweep (fast)."""
        self.stop_info = {"graceful": self.graceful}
        if not self.graceful:
            return
        t0 = time.perf_counter()
        try:
            lib = BuiltIn().get_library_instance("Browser")
            lib.playwright.close()
            self.stop_info["browser_close_ms"] = round((time.perf_counter() - t0) * 1000)
        except Exception as e:
            self.stop_info["browser_close_error"] = _t(repr(e), 200)

    def _next(self) -> Optional[Request]:
        while True:
            if self.stop_flag.is_set():
                return None
            try:
                return self.requests.get(timeout=0.2)
            except queue.Empty:
                continue

    def log_message(self, message, level, html=False, timestamp=None) -> None:
        if self._in_hook or self._logs is None or level not in self.log_levels:
            return
        if len(self._logs) < 20:
            self._logs.append(f"{level}: {_t(message, 300)}")

    def message(self, message, level, html=False, timestamp=None) -> None:
        pass

    # observer: BaseInterpreter calls these for every keyword/control-structure start/end
    def start_keyword(self, data, result) -> None:
        if self._in_hook:
            return
        self._depth += 1
        if self._depth == 1:
            self._top = result

    def end_keyword(self, data, result) -> None:
        if self._in_hook:
            return
        if self._depth > 1 and result.status == "FAIL" and self._nested_fail is None:
            self._nested_fail = getattr(result, "name", None) or result.type
        self._depth -= 1

    # --- execution -------------------------------------------------------------
    def _run_cells(self, req: Request) -> Dict[str, Any]:
        cells = req.data.get("cells") or []
        t0 = time.perf_counter()
        console: List[str] = []
        orig_stdout = sys.__stdout__
        sys.__stdout__ = _Tee(orig_stdout, console)  # Log To Console -> response
        steps: List[Dict[str, Any]] = []
        ok: Optional[bool] = None
        errors: List[str] = []
        reloaded: List[str] = []
        try:
            try:
                reloaded = self._autoreload()
            except Exception as e:
                errors.append(f"autoreload failed: {e!r}")
            for ci, cell in enumerate(cells):
                try:
                    test, errs = self.get_test_body_from_string(cell)
                except SyntaxError as e:
                    errs, test = [str(e)], None
                if errs:
                    errors.extend(errs[:5])
                    ok = False
                    break
                for kw in test.body:
                    rec, passed = self._run_one(kw)
                    if len(cells) > 1:
                        rec["cell"] = ci
                    steps.append(rec)
                    ok = passed if ok is None else (ok and passed)
                    if not passed:
                        break
                if ok is False and req.data.get("stop_on_fail", True):
                    break
        finally:
            sys.__stdout__ = orig_stdout
            try:  # baseline mtimes of resources imported by this request
                for k in _importer()._resource_cache._keys:
                    if isinstance(k, str) and k not in self._res_mtime and os.path.isfile(k):
                        self._res_mtime[k] = os.stat(k).st_mtime_ns
            except Exception:
                pass
        resp: Dict[str, Any] = {"ok": ok, "id": req.id, "steps": steps,
                                "dur_ms": round((time.perf_counter() - t0) * 1000, 1)}
        if errors:
            resp["errors"] = [self._scrub(e) for e in errors]
        if reloaded:
            resp["reloaded"] = [os.path.basename(r) for r in reloaded]
        if console:
            resp["console"] = self._scrub(_t("".join(console), 1000))
        self.n_cells += len(cells)
        self._journal(req, resp)
        return resp

    def _autoreload(self) -> List[str]:
        """Re-import resource files edited since they were imported (stock REPL keeps stale copies)."""
        from robot.running.context import EXECUTION_CONTEXTS

        cache = _importer()._resource_cache
        changed = []
        for i, k in enumerate(list(cache._keys)):
            if not isinstance(k, str) or not os.path.isfile(k):
                continue
            m = os.stat(k).st_mtime_ns
            old = self._res_mtime.setdefault(k, m)
            if m != old:
                changed.append(k)
        if not changed:
            return []
        ns = EXECUTION_CONTEXTS.current.namespace
        for k in changed:
            idx = cache._keys.index(k)
            del cache._keys[idx]
            del cache._items[idx]
            ns.import_resource(k, overwrite=True)
            self._res_mtime[k] = os.stat(k).st_mtime_ns
        return changed

    def _scrub(self, s: str) -> str:
        return self.redactor.scrub(s) if self.redactor else s

    def _run_one(self, kw: Any):
        is_kw = kw.type == "KEYWORD"
        name = kw.name if is_kw else kw.type
        step = StepCtx(kw=kw, name=name, args=[str(a) for a in getattr(kw, "args", ()) or ()],
                       assign=[str(a) for a in getattr(kw, "assign", ()) or ()],
                       owner=resolve_owner(name) if is_kw else None)
        orig_args = list(step.args)
        rec: Dict[str, Any] = {"kw": name}
        self._in_hook = True
        try:
            for h in self.hooks:
                refusal = h.pre(step)
                if refusal:
                    rec.update(owner=step.owner, args=step.args, status="REFUSED", refused={"by": h.name, **refusal})
                    for h2 in reversed(self.hooks):
                        h2.post(step, rec)
                    return rec, False
        finally:
            self._in_hook = False
        if is_kw and step.args != orig_args:  # a hook rewrote arguments (e.g. timeout injection)
            kw.args = tuple(step.args)
        self._depth, self._top, self._nested_fail, self._logs = 0, None, None, []
        ret, err = None, None
        t0 = time.perf_counter()
        with STOP_SIGNAL_MONITOR:
            try:
                ret = self.run_keyword(kw)
            except ExecutionPassed:
                pass
            except ExecutionStatus as e:
                err = e
        ms = round((time.perf_counter() - t0) * 1000, 1)
        top = self._top
        status = getattr(top, "status", None) or ("FAIL" if err else "PASS")
        rec.update(owner=step.owner)
        if step.args:
            rec["args"] = [_t(a, 200) for a in step.args]
        if step.assign:
            rec["assign"] = step.assign
        rec["status"] = status
        if status == "FAIL":
            rec["msg"] = _t(getattr(top, "message", None) or (str(err) if err else ""), 600)
            if self._nested_fail:
                rec["failed_in"] = self._nested_fail
            if isinstance(err, ExecutionFailed) and getattr(err, "exit", False):
                rec["fatal"] = True
        if ret is not None:
            rec["ret"] = _t(ret, 300)
        rec["ms"] = ms
        if self._logs:
            rec["logs"] = self._logs
        self._logs = None
        self._in_hook = True
        try:
            for h in reversed(self.hooks):
                h.post(step, rec)
        finally:
            self._in_hook = False
        return rec, status != "FAIL"

    def _vars(self, data: Dict[str, Any]) -> Dict[str, Any]:
        bi = BuiltIn()
        names = data.get("names") or []
        if names:
            out = {n: _t(bi.get_variable_value(n if n[:1] in "$@&" else "${%s}" % n)) for n in names}
        else:
            allv = bi.get_variables()
            out = {k: _t(v, 200) for k, v in allv.items() if data.get("all") or k not in self.baseline}
        return {"ok": True, "vars": {k: self._scrub(v) for k, v in out.items()}}

    def _journal(self, req: Request, resp: Dict[str, Any]) -> None:
        line = {"id": req.id, "ts": round(time.time(), 3), "cells": req.data.get("cells"), "ok": resp["ok"],
                "steps": [{k: s.get(k) for k in ("kw", "owner", "status", "ms")} for s in resp["steps"]],
                "dur_ms": resp["dur_ms"]}
        fd = os.open(self.journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(line) + "\n")

    def status(self) -> Dict[str, Any]:
        b = self.busy
        return {"ok": True, "pid": os.getpid(), "pgid": os.getpgrp(), "ready": self.ready.is_set(),
                "busy": ({**b, "for_s": round(time.time() - b["since"], 1)} if b else None),
                "cells": self.n_cells, "uptime_s": round(time.time() - self.t_start, 1),
                "queued": self.requests.qsize()}


class Server(threading.Thread):
    def __init__(self, interp: HelperInterpreter, sd: Path, tcp: bool) -> None:
        super().__init__(name="rfmcp-server", daemon=True)
        self.interp, self.tcp = interp, tcp
        self.token: Optional[str] = None
        if tcp:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.bind(("127.0.0.1", 0))
            self.port = self.sock.getsockname()[1]
            self.token = os.urandom(16).hex()
            self.path = None
        else:
            self.path = proto.unix_sock_path(sd)
            if self.path.exists():
                self.path.unlink()  # caller verified no live daemon owns it
            old = os.umask(0o177)
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.bind(str(self.path))
            finally:
                os.umask(old)
            os.chmod(self.path, 0o600)
        self.sock.listen(16)
        self.closed = False

    def endpoint(self) -> Dict[str, Any]:
        if self.tcp:
            return {"transport": "tcp", "port": self.port, "token": self.token}
        return {"transport": "unix", "sock": str(self.path)}

    def run(self) -> None:
        while not self.closed:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self._serve_conn, args=(conn,), daemon=True).start()

    def _peer_ok(self, conn: socket.socket) -> bool:
        if self.tcp or not hasattr(socket, "SO_PEERCRED"):
            return True
        _pid, uid, _gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        return uid == os.getuid()

    def _serve_conn(self, conn: socket.socket) -> None:
        try:
            if not self._peer_ok(conn):
                return
            buf = bytearray()
            while not buf.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
            req = json.loads(buf)
            if self.token and req.get("token") != self.token:
                resp: Dict[str, Any] = {"ok": False, "error": "bad token"}
            else:
                resp = self._dispatch(req)
            conn.sendall(json.dumps(resp, default=str, separators=(",", ":")).encode() + b"\n")
        except Exception as e:  # pragma: no cover
            try:
                conn.sendall(json.dumps({"ok": False, "error": repr(e)}).encode() + b"\n")
            except OSError:
                pass
        finally:
            conn.close()

    def _dispatch(self, req: Dict[str, Any]) -> Dict[str, Any]:
        op = req.get("op")
        it = self.interp
        if op == "ping":
            return {"ok": True, "pid": os.getpid()}
        if op == "status":
            return it.status()
        if op == "interrupt":
            if it.busy:
                os.kill(os.getpid(), signal.SIGINT)
            return {"ok": True, "interrupted": bool(it.busy)}
        if op == "result":
            r = it.results.get(int(req.get("id", 0)))
            return r if r is not None else {"ok": None, "pending": True}
        if op == "stop":
            it.graceful = bool(req.get("graceful", False))
            it.stop_flag.set()
            if it.busy and req.get("interrupt", True):
                os.kill(os.getpid(), signal.SIGINT)
            return {"ok": True, "stopping": True, "pid": os.getpid()}
        if op in ("step", "vars"):
            if not it.ready.is_set():
                it.ready.wait(120)
            r = Request(op, req)
            it.requests.put(r)
            if not r.done.wait(float(req.get("timeout", 600))):
                return {"ok": None, "pending": True, "id": r.id}
            return r.resp or {"ok": False, "error": "no response"}
        return {"ok": False, "error": f"unknown op {op!r}"}

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.close()
        finally:
            if self.path is not None:
                try:
                    self.path.unlink()
                except OSError:
                    pass


def install_pdeathsig() -> None:
    """Linux: children forked from the main thread get SIGTERM when the helper dies (even kill -9)."""
    if not sys.platform.startswith("linux"):
        return
    import ctypes
    import subprocess

    libc = ctypes.CDLL(None, use_errno=True)
    orig_init = subprocess.Popen.__init__

    def _set():
        libc.prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG

    def __init__(self, *a, **kw):  # type: ignore[no-untyped-def]
        if (kw.get("preexec_fn") is None and not kw.get("start_new_session")
                and threading.current_thread() is threading.main_thread()):
            kw["preexec_fn"] = _set
        orig_init(self, *a, **kw)

    subprocess.Popen.__init__ = __init__  # type: ignore[method-assign]


def serve(app: Application, opts: argparse.Namespace) -> int:
    sd = proto.state_dir(opts.dir)
    proto.ensure_private_dir(sd)
    outdir = Path(opts.outputdir or (sd / "out")).absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    token = os.environ.setdefault(procs.TOKEN_ENV, os.urandom(8).hex())  # inherited by every child
    if opts.pdeathsig:
        install_pdeathsig()

    hooks = build_hooks([h for h in (opts.hooks or "").split(",") if h], fast_timeout=opts.fast_timeout)
    state: Dict[str, Any] = {}

    def on_ready() -> None:
        state.update(ready=True, ready_at=time.time())
        proto.write_state(sd, state)

    interp = HelperInterpreter(hooks, sd / "journal.jsonl", on_ready=on_ready,
                               log_levels=tuple(opts.log_levels.split(",")))

    # SIGTERM: idle -> clean stop; running keyword -> interrupt it, then clean stop.
    def _sig_call(self_, signum, frame):  # replaces robotcode's patched _StopSignalMonitor.__call__
        if signum == signal.SIGTERM:
            interp.stop_flag.set()
        if self_._running_keyword:
            self_._stop_execution_gracefully()

    _StopSignalMonitor.__call__ = _sig_call
    signal.signal(signal.SIGTERM, lambda s, f: interp.stop_flag.set())

    srv = Server(interp, sd, tcp=opts.tcp)
    state.update(pid=os.getpid(), pgid=os.getpgrp(), sid=os.getsid(0), token_env=token, ready=False,
                 started=time.time(), python=sys.executable, cwd=os.getcwd(), outdir=str(outdir),
                 hooks=[h.name for h in hooks], **srv.endpoint())
    proto.write_state(sd, state)
    ep = srv.endpoint()  # plain-text endpoint for the json-free fast client (+ a copy of it)
    ep_txt = f"tcp {ep['port']} {ep['token']}" if opts.tcp else f"unix {ep['sock']}"
    fd = os.open(sd / "endpoint", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(ep_txt + "\n")
    import shutil

    shutil.copyfile(Path(__file__).with_name("fast.py"), sd / "fast.py")
    srv.start()
    rc = 0
    try:
        run_repl(interp, app, variable=tuple(opts.variable or ()), variablefile=tuple(opts.variablefile or ()),
                 pythonpath=tuple(opts.pythonpath or ()), outputdir=str(outdir), output=opts.output,
                 log=None, report=None, source=Path.cwd() / "__rfmcp__.robot")
    except SystemExit as e:
        rc = int(e.code or 0) if isinstance(e.code, int) else 1
    finally:
        t_fin = time.time()
        srv.close()
        try:
            (sd / "endpoint").unlink()
        except OSError:
            pass
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        left = [p for p in procs.descendants(os.getpid())]
        left += [p for p in procs.token_procs(token) if p != os.getpid() and p not in left]
        forced = procs.terminate(left, grace=2.0) if left else []
        state.update(ready=False, stopped=time.time(), leftover=len(left), forced=len(forced), **interp.stop_info,
                     cleanup_ms=round((time.time() - t_fin) * 1000))
        proto.write_state(sd, state)
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rfmcp_local.daemon")
    p.add_argument("--dir")
    p.add_argument("-v", "--variable", action="append")
    p.add_argument("-V", "--variablefile", action="append")
    p.add_argument("-P", "--pythonpath", action="append")
    p.add_argument("-d", "--outputdir")
    p.add_argument("-o", "--output", default=None)
    p.add_argument("-p", "--profile", action="append", dest="profiles")
    p.add_argument("--root")
    p.add_argument("--hooks", default="redact,hints")
    p.add_argument("--fast-timeout", default=None)
    p.add_argument("--log-levels", default="WARN,ERROR")
    p.add_argument("--tcp", action="store_true")
    p.add_argument("--pdeathsig", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    opts = build_parser().parse_args(argv)
    app = Application()
    app.config.profiles = opts.profiles
    if opts.root:
        app.config.root = Path(opts.root)
    return serve(app, opts)


if __name__ == "__main__":
    sys.exit(main())
