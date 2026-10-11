"""Live RF session engine (copied from the skillpkg prototype): robotcode's REPL engine (run_repl + BaseInterpreter) fed from a local socket.

Merges the round-2 helper (daemon: cell steps, hooks, journal, clean shutdown) with the
round-3 file-step shim (filestep_daemon: run/check lines of a .robot file the agent edits itself) and adds
keyword search/doc, page state, job/wait for long keywords and idle auto-exit.

Main thread : run_repl() -> one RF suite -> Helper.run_input() loop (ALL RF work happens here, serialized)
Thread      : socket server; enqueues main-thread ops, answers ping/status/wait/interrupt/stop itself
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import queue
import re
import shutil
import signal
import socket
import struct
import sys
import threading
import time
import traceback
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from robot.api import get_model
from robot.errors import ExecutionFailed, ExecutionPassed, ExecutionStatus
from robot.libraries.BuiltIn import BuiltIn
from robot.running import TestSuite
from robot.running.context import EXECUTION_CONTEXTS
from robot.running.signalhandler import STOP_SIGNAL_MONITOR, _StopSignalMonitor

from robotcode.plugin import Application
from robotcode.repl.base_interpreter import BaseInterpreter
from robotcode.repl.run import run_repl

from . import procs, proto
from .rthooks import Redactor, StepCtx, build_hooks, resolve_owner

_ids = itertools.count(1)
MAXT = 400
MAIN_OPS = {"step", "run", "check", "analyze", "search", "doc", "state", "vars"}
SKIP_TYPES = {"EOL", "COMMENT", "DOCUMENTATION", "TAGS", "SETUP", "TEARDOWN", "TEMPLATE", "TIMEOUT"}
KEEP_SETTINGS = {"LibraryImport", "ResourceImport", "VariablesImport", "SectionHeader", "EmptyLine", "Comment"}
VAR_RE = re.compile(r"Variable '([$@&%]\{[^']+\})' not found")
SETVAR_KWS = {"settestvariable", "setsuitevariable", "setglobalvariable", "settaskvariable", "setlocalvariable"}


def _importer() -> Any:
    try:
        from robot.running.importer import IMPORTER  # RF 7.5
    except ImportError:
        from robot.running.namespace import IMPORTER  # RF <= 7.4
    return IMPORTER


def _t(s: Any, n: int = MAXT) -> str:
    s = s if isinstance(s, str) else repr(s)
    return s if len(s) <= n else s[: n - 3] + "..."


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", "")).strip().lower()


def _h(text: str) -> str:
    return hashlib.sha1("\n".join(l.rstrip() for l in text.splitlines()).encode()).hexdigest()[:12]


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


class Helper(BaseInterpreter):
    def __init__(self, hooks: List[Any], sd: Path, cli_vars: Dict[str, str], idle_s: float = 1800.0,
                 log_levels=("WARN", "ERROR"), on_ready=None) -> None:
        super().__init__()
        self.hooks = hooks
        self.redactor = next((h for h in hooks if isinstance(h, Redactor)), None)
        self.sd = sd
        self.journal = sd / "journal.jsonl"
        self.cli_vars = cli_vars
        self.idle_s = idle_s
        self.log_levels = set(log_levels)
        self.on_ready = on_ready
        self.requests: "queue.Queue[Request]" = queue.Queue()
        self.stop_flag = threading.Event()
        self.ready = threading.Event()
        self.busy: Optional[Dict[str, Any]] = None
        self.results: "OrderedDict[int, Request]" = OrderedDict()
        self.n_ops = 0
        self.t_start = time.time()
        self.last_activity = time.time()
        self.baseline: set = set()
        self._depth = 0
        self._top: Any = None
        self._nested_fail: Optional[str] = None
        self._logs: Optional[List[str]] = None
        self._in_hook = False
        self._res_mtime: Dict[str, int] = {}
        self.graceful = True
        self.stop_info: Dict[str, Any] = {}
        self.analyzer: Any = None
        self.files: Dict[str, Dict[str, Any]] = {}  # executed-item hashes per file/test (in memory only)
        self.gen_imported: Dict[str, str] = {}
        self.gen_files: List[Path] = []
        self.guard = next((h for h in hooks if getattr(h, "name", "") == "guard"), None)
        self.guard_off = False  # per request: --no-guard

    # ------------------------------------------------------------------ BaseInterpreter API
    def get_input(self):
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
            self.busy = {"id": req.id, "since": time.time(), "op": req.op,
                         "what": _t(req.data.get("cells") or req.data.get("path") or req.data.get("query") or "", 100)}
            resp = getattr(self, "_op_" + req.op)(req)
        except (SystemExit, KeyboardInterrupt):
            req.reply({"ok": False, "error": "helper exiting"})
            raise
        except BaseException as e:  # keep the daemon alive
            resp = {"ok": False, "error": _t(f"{type(e).__name__}: {e}"), "tb": traceback.format_exc()[-800:]}
        finally:
            self.busy = None
            self.last_activity = time.time()
        self.n_ops += 1
        req.reply(resp)

    def _on_stop(self) -> None:
        """Close Browser/Playwright in-process (fast, flushes traces) instead of relying on atexit."""
        self.stop_info.setdefault("graceful", self.graceful)
        for g in self.gen_files:
            try:
                g.unlink()
            except OSError:
                pass
        if not self.graceful:
            return
        t0 = time.perf_counter()
        try:
            lib = BuiltIn().get_library_instance("Browser")
            lib.playwright.close()
            self.stop_info["browser_close_ms"] = round((time.perf_counter() - t0) * 1000)
        except Exception:
            pass
        try:
            BuiltIn().get_library_instance("SeleniumLibrary").close_all_browsers()
        except Exception:
            pass

    def _next(self) -> Optional[Request]:
        while True:
            if self.stop_flag.is_set():
                return None
            try:
                return self.requests.get(timeout=0.2)
            except queue.Empty:
                if self.idle_s and time.time() - self.last_activity > self.idle_s:
                    self.stop_info["idle_exit"] = True
                    return None

    def log_message(self, message, level, html=False, timestamp=None) -> None:
        if self._in_hook or self._logs is None or level not in self.log_levels:
            return
        if len(self._logs) < 10:
            self._logs.append(f"{level}: {_t(message, 300)}")

    def message(self, message, level, html=False, timestamp=None) -> None:
        pass

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

    # ------------------------------------------------------------------ one top-level item
    def _scrub(self, s: str) -> str:
        return self.redactor.scrub(s) if self.redactor else s

    def _run_one(self, kw: Any) -> Tuple[Dict[str, Any], bool]:
        is_kw = kw.type == "KEYWORD"
        name = kw.name if is_kw else kw.type
        step = StepCtx(kw=kw, name=name, args=[str(a) for a in getattr(kw, "args", ()) or ()],
                       assign=[str(a) for a in getattr(kw, "assign", ()) or ()],
                       owner=resolve_owner(name) if is_kw else None)
        rec: Dict[str, Any] = {"kw": name}
        self._in_hook = True
        try:
            for h in self.hooks:
                if self.guard_off and h is self.guard:
                    continue
                refusal = h.pre(step)
                if refusal:
                    rec.update(owner=step.owner, args=[_t(a, 200) for a in step.args], status="NOT RUN",
                               msg=f"refused before execution by the {h.name} probe: {refusal.get('cls')}",
                               guard=refusal)
                    for h2 in reversed(self.hooks):
                        h2.post(step, rec)
                    return rec, False
        finally:
            self._in_hook = False
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
        rec["status"] = status
        if status == "FAIL":
            rec["owner"] = step.owner
            if step.args:
                rec["args"] = [_t(a, 200) for a in step.args]
            rec["msg"] = _t(getattr(top, "message", None) or (str(err) if err else ""), 600)
            if self._nested_fail and self._nested_fail != name:
                rec["failed_in"] = self._nested_fail
            if isinstance(err, ExecutionFailed) and getattr(err, "exit", False):
                rec["fatal"] = True
        if step.assign:
            rec["assign"] = step.assign
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

    # ------------------------------------------------------------------ op: step (cells)
    def _op_step(self, req: Request) -> Dict[str, Any]:
        self.guard_off = req.data.get("guard") is False
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
                if not cell.strip():
                    continue
                try:
                    test, errs = self.get_test_body_from_string(cell)
                except SyntaxError as e:
                    errs, test = [str(e)], None
                if errs:
                    errors.extend(errs[:5])
                    ok = False
                    break
                for kw in test.body:
                    if self.guard is not None:
                        self.guard.cur_settle = self.guard.followup if steps else self.guard.settle
                    rec, passed = self._run_one(kw)
                    if len(cells) > 1:
                        rec["cell"] = ci
                    steps.append(rec)
                    ok = passed if ok is None else (ok and passed)
                    if not passed:
                        break
                if ok is False:
                    break
        finally:
            sys.__stdout__ = orig_stdout
            self._baseline_mtimes()
        resp: Dict[str, Any] = {"ok": bool(ok) if ok is not None else False, "steps": steps}
        if ok is None and not errors:
            resp["error"] = "nothing to run (empty cell?)"
        if errors:
            resp["errors"] = [self._scrub(e) for e in errors]
            resp["hint"] = ("RF syntax: separate keyword and arguments with 2+ spaces (use 4); "
                            "quote the cell in single quotes or a <<'RF' heredoc")
        if reloaded:
            resp["reloaded"] = [os.path.basename(r) for r in reloaded]
        if console:
            resp["console"] = self._scrub(_t("".join(console), 1000))
        resp["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self._journal({"op": "step", "cells": cells, "ok": resp["ok"],
                       "steps": [{k: s.get(k) for k in ("kw", "status", "ms")} for s in steps]})
        return resp

    def _baseline_mtimes(self) -> None:
        try:
            for k in _importer()._resource_cache._keys:
                if isinstance(k, str) and k not in self._res_mtime and os.path.isfile(k):
                    self._res_mtime[k] = os.stat(k).st_mtime_ns
        except Exception:
            pass

    def _autoreload(self) -> List[str]:
        """Re-import resource files edited since they were imported (stock REPL keeps stale copies)."""
        cache = _importer()._resource_cache
        changed = []
        for k in list(cache._keys):
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

    # ------------------------------------------------------------------ file parsing (round-3 filestep)
    def _parse(self, path: Path) -> Tuple[Any, List[str], List[Dict[str, Any]]]:
        """-> model, lines, tests[{name, line, end, items[{line,end,hash,src,kind,(setup)}]}]"""
        text = path.read_text()
        lines = text.splitlines()
        model = get_model(str(path), curdir=str(path.parent))   # ${CURDIR} resolved like a real run
        model.source = str(path)
        tests = []
        suite_test_setup = None
        suite_setup = None
        for sec in model.sections:
            if type(sec).__name__ == "SettingSection":
                for st in sec.body:
                    tn = type(st).__name__
                    if tn == "TestSetup" and st.name and st.name.upper() != "NONE":
                        suite_test_setup = st
                    elif tn == "SuiteSetup" and st.name and st.name.upper() != "NONE":
                        suite_setup = st
        for sec in model.sections:
            if type(sec).__name__ not in ("TestCaseSection", "TaskSection"):
                continue
            for tc in sec.body:
                if type(tc).__name__ != "TestCase":
                    continue
                items: List[Dict[str, Any]] = []
                own_setup = next((n for n in tc.body if type(n).__name__ == "Setup"), None)
                setup = own_setup if own_setup is not None else suite_test_setup
                if setup is not None and setup.name and setup.name.upper() != "NONE":
                    src = lines[setup.lineno - 1].strip()
                    items.append({"line": setup.lineno, "end": setup.lineno, "hash": "setup:" + _h(src),
                                  "src": src, "kind": "setup", "setup": (setup.name, list(setup.args))})
                for n in tc.body:
                    if getattr(n, "type", None) in SKIP_TYPES or type(n).__name__ in ("Setup", "Teardown"):
                        continue
                    end = n.end_lineno
                    while end > n.lineno and not lines[end - 1].strip():
                        end -= 1
                    src = "\n".join(lines[n.lineno - 1:end])
                    if not src.strip() or src.strip().startswith("#"):
                        continue
                    items.append({"line": n.lineno, "end": end, "hash": _h(src), "src": src, "kind": "body"})
                tests.append({"name": tc.name, "line": tc.lineno, "end": tc.end_lineno, "items": items,
                              "teardown": any(type(n).__name__ == "Teardown" for n in tc.body)})
        ss = None
        if suite_setup is not None:
            src = lines[suite_setup.lineno - 1].strip()
            ss = {"line": suite_setup.lineno, "end": suite_setup.lineno, "hash": "suite:" + _h(src), "src": src,
                  "kind": "setup", "setup": (suite_setup.name, list(suite_setup.args))}
        return model, lines, [{"suite_setup": ss}] + tests  # type: ignore[list-item]

    def _gen_resource(self, path: Path, model: Any, lines: List[str]) -> Optional[Path]:
        """Settings imports + Variables + Keywords of the file -> hidden resource with identical line numbers."""
        keep = [""] * len(lines)
        has = False
        for sec in model.sections:
            kind = type(sec).__name__
            if kind in ("KeywordSection", "VariableSection"):
                for i in range(sec.lineno, min(sec.end_lineno, len(lines)) + 1):
                    keep[i - 1] = lines[i - 1]
                has = True
            elif kind == "SettingSection":
                for st in [sec.header, *sec.body]:
                    if type(st).__name__ in KEEP_SETTINGS:
                        for i in range(st.lineno, min(st.end_lineno, len(lines)) + 1):
                            keep[i - 1] = lines[i - 1]
                        has = has or type(st).__name__.endswith("Import")
        if not has:
            return None
        gen = path.with_name(f".{path.stem}.live.resource")
        content = "\n".join(keep) + "\n"
        h = _h(content)
        if self.gen_imported.get(str(gen)) == h and gen.exists():
            return gen
        gen.write_text(content)
        if gen not in self.gen_files:
            self.gen_files.append(gen)
        ns = EXECUTION_CONTEXTS.current.namespace
        if str(gen) in self.gen_imported:
            self._autoreload()
        else:
            ns.import_resource(str(gen))
            try:
                self._res_mtime[str(gen)] = os.stat(gen).st_mtime_ns
            except OSError:
                pass
        self.gen_imported[str(gen)] = h
        return gen

    # ------------------------------------------------------------------ static check + live filter
    def _get_analyzer(self) -> Any:
        if self.analyzer is None:
            from .analyzer import WarmAnalyzer

            self.analyzer = WarmAnalyzer(Path.cwd(), variables=self.cli_vars)
        return self.analyzer

    def _live_filter(self, src: str, diags: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        keep, dropped = [], []
        bi = BuiltIn()
        first = src.split("\n")[0].strip()
        cells = [c for c in re.split(r"\s{2,}|\t", first) if c]
        if cells and _norm(cells[0]) in ("testsetup", "[setup]", "suitesetup", "tasksetup"):
            cells = cells[1:]  # setup items: the setting name is not part of the keyword call
        for d in diags:
            why = None
            if d["code"] == "VariableNotFound":
                m = VAR_RE.search(d["msg"])
                name = m.group(1) if m else None
                if name:
                    base = name[2:-1].split(".")[0].split("[")[0]
                    sentinel = object()
                    try:
                        exists = bi.get_variable_value("${%s}" % base, sentinel) is not sentinel
                    except Exception:
                        exists = False
                    if exists:
                        why = f"{name} exists in live session"
                    else:
                        kwc = next((c for c in cells if not c.endswith("=")), "")
                        args = cells[cells.index(kwc) + 1:] if kwc in cells else []
                        if _norm(kwc) in SETVAR_KWS and args and args[0].lstrip("\\")[2:-1].strip() == base:
                            why = f"{name} is being set by {kwc}"
            elif d["code"] in ("MultipleKeywords", "KeywordNotFound"):
                m = re.search(r"name '([^']+)'", d["msg"])
                if m and resolve_owner(m.group(1)):
                    why = f"live session resolves '{m.group(1)}'"
            if why:
                dropped.append(f"L{d['line']} {d['code']} ({why})")
            else:
                keep.append(d)
        return keep, dropped

    def _static(self, path: Path, lines: List[str]) -> Tuple[List[Dict[str, Any]], float]:
        res = self._get_analyzer().check(path, text="\n".join(lines) + "\n", min_severity=1)
        return [{k: d[k] for k in ("line", "col", "code", "msg")} for d in res["diags"]], res["ms"]

    # ------------------------------------------------------------------ op: run (file lines)
    def _select(self, req: Dict[str, Any], key: str, tests: List[Dict[str, Any]], ss: Optional[Dict[str, Any]]):
        """-> list of (test_name|None, item), error dict or None"""
        mode = req.get("mode", "new")
        fstate = self.files.setdefault(key, {"tests": {}, "suite": None})
        want = req.get("test")
        tsel = [t for t in tests if not want or t["name"] == want]
        if want and not tsel:
            return [], {"ok": False, "error": f"no test named '{want}'", "tests": [t["name"] for t in tests]}
        sel: List[Tuple[Optional[str], Dict[str, Any]]] = []
        if mode == "new":
            if ss is not None and fstate["suite"] != ss["hash"]:
                sel.append((None, ss))
            for t in tsel:
                done = fstate["tests"].get(t["name"], [])
                k = 0
                while k < len(t["items"]) and k < len(done) and t["items"][k]["hash"] == done[k]:
                    k += 1
                if k < len(done):
                    ch = t["items"][k] if k < len(t["items"]) else None
                    return [], {"ok": False, "error": "lines that already ran were changed/removed",
                                "test": t["name"], "first_changed_line": ch["line"] if ch else None,
                                "hint": "lines that already ran were changed"}
                sel += [(t["name"], it) for it in t["items"][k:]]
        elif mode == "lines":
            a, b = req["lines"]
            if ss is not None and a <= ss["line"] <= b:
                sel.append((None, ss))
            for t in tsel:
                sel += [(t["name"], it) for it in t["items"] if a <= it["line"] <= b or (it["line"] <= a <= it["end"])]
        else:  # all
            if ss is not None:
                sel.append((None, ss))
            for t in tsel:
                sel += [(t["name"], it) for it in t["items"]]
        return sel, None

    def _record(self, key: str, tests: List[Dict[str, Any]], tname: Optional[str], it: Dict[str, Any]) -> None:
        fstate = self.files[key]
        if tname is None:
            fstate["suite"] = it["hash"]
            return
        t = next(t for t in tests if t["name"] == tname)
        done = fstate["tests"].setdefault(tname, [])
        k = len(done)
        if k < len(t["items"]) and t["items"][k] is it and all(t["items"][i]["hash"] == done[i] for i in range(k)):
            done.append(it["hash"])

    def _op_run(self, req: Request) -> Dict[str, Any]:
        data = req.data
        self.guard_off = data.get("guard") is False
        if self.guard is not None:  # file lines run back to back: pages may still be loading
            self.guard.cur_settle = self.guard.followup
        t0 = time.perf_counter()
        path = Path(data["path"]).resolve()
        if not path.is_file():
            return {"ok": False, "error": f"no such file: {data['path']}"}
        key = str(path)
        rel = os.path.relpath(path)
        model, lines, parsed = self._parse(path)
        ss, tests = parsed[0]["suite_setup"], parsed[1:]
        if data.get("mode") == "rebase":
            fstate = self.files.setdefault(key, {"tests": {}, "suite": None})
            thr = int(data.get("through") or 10 ** 9)
            for t in tests:
                fstate["tests"][t["name"]] = [it["hash"] for it in t["items"] if it["line"] <= thr]
            if ss is not None:
                fstate["suite"] = ss["hash"]
            return {"ok": True, "file": rel, "rebased": {t["name"]: len(fstate["tests"][t["name"]]) for t in tests}}
        if not tests:
            return {"ok": False, "file": rel, "error": "no test case in file",
                    "hint": "resource file: no test case to run"}
        sel, err = self._select(data, key, tests, ss)
        if err:
            return {"file": rel, **err}
        resp: Dict[str, Any] = {"ok": True, "file": rel}
        if not sel:
            resp["note"] = "nothing new to run (all test lines already ran); --all or --lines A-B re-runs"
            return resp
        console: List[str] = []
        orig_stdout = sys.__stdout__
        try:
            self._autoreload()
        except Exception:
            pass
        gen = self._gen_resource(path, model, lines)
        diags: List[Dict[str, Any]] = []
        if data.get("check", True):
            diags, resp["check_ms"] = self._static(path, lines)
            body_lines = set()
            for t in tests:
                body_lines.update(range(t["line"], t["end"] + 1))
                body_lines.update(it["line"] for it in t["items"])  # setup lines (may live in *** Settings ***)
            if ss is not None:
                body_lines.add(ss["line"])
            outside = [d for d in diags if d["line"] not in body_lines]
            if outside:  # errors in Settings/Variables/Keywords: reported, not blocking (live filter can't judge)
                resp["file_errors"] = outside[:8]
        port = self._portable(path)
        if port:  # works in this session, fails in the final plain `robot` run
            resp["portable"] = port
        suite = TestSuite.from_model(model)
        by_test = {t.name: {it.lineno: it for it in t.body} for t in suite.tests}
        ran: List[Dict[str, Any]] = []
        ok = True
        sys.__stdout__ = _Tee(orig_stdout, console)
        try:
            for tname, it in sel:
                ds = [d for d in diags if it["line"] <= d["line"] <= it["end"]]
                keep, dropped = self._live_filter(it["src"], ds)
                if dropped:
                    resp.setdefault("dropped_static", []).extend(dropped)
                if keep and not data.get("force"):
                    resp.update(blocked={"line": it["line"], "src": it["src"][:300],
                                         "errors": [{"line": d["line"], "code": d["code"], "msg": d["msg"]} for d in keep]},
                                hint=f"static error, NOT executed: fix line {it['line']}")
                    ok = False
                    break
                if it["kind"] == "setup":
                    from robot.running.model import Keyword

                    node = Keyword(name=it["setup"][0], args=tuple(it["setup"][1]))
                else:
                    node = by_test.get(tname, {}).get(it["line"])
                if node is None:
                    resp.update(error=f"no runnable item at line {it['line']}")
                    ok = False
                    break
                rec, passed = self._run_one(node)
                rec = {"line": it["line"], **({"end": it["end"]} if it["end"] != it["line"] else {}),
                       **({"test": tname} if tname and len(tests) > 1 else {}), **rec}
                if it["kind"] == "setup":
                    rec["setup"] = True
                ran.append(rec)
                if passed:
                    self._record(key, tests, tname, it)
                else:
                    ok = False
                    resp["hint"] = f"fix line {it['line']} in {rel}"
                    break
        finally:
            sys.__stdout__ = orig_stdout
            self._baseline_mtimes()
        resp["ok"] = ok
        resp["ran"] = ran
        if console:
            resp["console"] = self._scrub(_t("".join(console), 1000))
        if any(t["teardown"] for t in tests):
            resp["note"] = "[Teardown] lines are not run here (they run in the final robot run)"
        resp["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self._journal({"op": "run", "file": rel, "mode": data.get("mode"), "ok": ok,
                       "ran": [(r["line"], r.get("kw"), r.get("status")) for r in ran]})
        return resp

    def _portable(self, path: Path) -> List[str]:
        """imports that resolve here (robotcode adds ./lib ./resources) but not in a plain `robot` run."""
        try:
            h = _h(path.read_text())
            cache = self.__dict__.setdefault("_port_cache", {})
            if cache.get(str(path), (None,))[0] != h:
                from .portable import lines

                cache[str(path)] = (h, lines(path, Path.cwd()))
            return cache[str(path)][1]
        except Exception:
            return []

    # ------------------------------------------------------------------ op: check / analyze
    def _op_check(self, req: Request) -> Dict[str, Any]:
        path = Path(req.data["path"]).resolve()
        if not path.is_file():
            return {"ok": False, "error": f"no such file: {req.data['path']}"}
        text = path.read_text()
        lines = text.splitlines()
        diags, ms = self._static(path, lines)
        resp: Dict[str, Any] = {"file": os.path.relpath(path), "check_ms": ms}
        keep: List[Dict[str, Any]] = []
        if path.suffix == ".robot" and diags:
            try:
                _, _, parsed = self._parse(path)
                items = [it for t in parsed[1:] for it in t["items"]]
            except Exception:
                items = []
            for d in diags:
                it = next((i for i in items if i["line"] <= d["line"] <= i["end"]), None)
                if it is None:
                    keep.append(d)
                    continue
                k, dropped = self._live_filter(it["src"], [d])
                keep += k
                if dropped:
                    resp.setdefault("dropped_static", []).extend(dropped)
        else:
            keep = diags
        resp["ok"] = not keep
        resp["errors"] = keep[:20]
        return resp

    def _op_analyze(self, req: Request) -> Dict[str, Any]:
        """static errors only, no live filter (used by the post-edit hook)."""
        path = Path(req.data["path"]).resolve()
        diags, ms = self._static(path, path.read_text().splitlines())
        return {"ok": not diags, "errors": diags[:20], "check_ms": ms}

    # ------------------------------------------------------------------ op: search / doc / state / vars
    def _op_search(self, req: Request) -> Dict[str, Any]:
        from . import kwdocs

        d = req.data
        return kwdocs.search(d.get("query", ""), int(d.get("limit") or 5), d.get("libs") or None)

    def _op_doc(self, req: Request) -> Dict[str, Any]:
        from . import kwdocs

        d = req.data
        return kwdocs.doc(d.get("name", ""), bool(d.get("full")), d.get("libs") or None)

    def _op_state(self, req: Request) -> Dict[str, Any]:
        from .pagestate import state

        return state(req.data.get("what") or "aria", self.sd / "state", req.data.get("selector"))

    def _op_vars(self, req: Request) -> Dict[str, Any]:
        bi = BuiltIn()
        names = req.data.get("names") or []
        if names:
            out = {n: _t(bi.get_variable_value(n if n[:1] in "$@&" else "${%s}" % n)) for n in names}
        else:
            allv = bi.get_variables()
            out = {k: _t(v, 200) for k, v in allv.items() if req.data.get("all") or k not in self.baseline}
        return {"ok": True, "vars": {k: self._scrub(v) for k, v in out.items()}}

    def _journal(self, line: Dict[str, Any]) -> None:
        line = {"ts": round(time.time(), 3), **line}
        fd = os.open(self.journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(line, default=str) + "\n")

    def status(self) -> Dict[str, Any]:
        b = self.busy
        return {"ok": True, "running": True, "pid": os.getpid(), "ready": self.ready.is_set(),
                "busy": ({**b, "for_s": round(time.time() - b["since"], 1)} if b else None),
                "ops": self.n_ops, "uptime_s": round(time.time() - self.t_start, 1),
                "idle_exit_s": self.idle_s, "queued": self.requests.qsize(), "cwd": os.getcwd()}


class Server(threading.Thread):
    def __init__(self, it: Helper, sd: Path, tcp: bool) -> None:
        super().__init__(name="rfh-server", daemon=True)
        self.it, self.tcp = it, tcp
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
                self.path.unlink()
            old = os.umask(0o177)
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.bind(str(self.path))
            finally:
                os.umask(old)
            os.chmod(self.path, 0o600)
        self.sock.listen(16)
        self.closed = False
        self.jobs: "OrderedDict[int, Request]" = OrderedDict()

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
            conn.sendall(json.dumps(resp, default=str, separators=(",", ":"), ensure_ascii=False).encode("utf-8", "replace") + b"\n")
        except Exception as e:  # pragma: no cover
            try:
                conn.sendall(json.dumps({"ok": False, "error": repr(e)}).encode() + b"\n")
            except OSError:
                pass
        finally:
            conn.close()

    def _wait(self, r: Request, timeout: float) -> Dict[str, Any]:
        if not r.done.wait(timeout):
            return {"ok": None, "status": "running", "job": r.id,
                    "hint": "still running"}
        self.jobs.pop(r.id, None)
        return r.resp or {"ok": False, "error": "no response"}

    def _dispatch(self, req: Dict[str, Any]) -> Dict[str, Any]:
        op = req.get("op")
        it = self.it
        it.last_activity = time.time()
        if op == "ping":
            return {"ok": True, "pid": os.getpid()}
        if op == "status":
            return it.status()
        if op == "interrupt":
            if it.busy:
                os.kill(os.getpid(), signal.SIGINT)
            return {"ok": True, "interrupted": bool(it.busy)}
        if op == "wait":
            r = self.jobs.get(int(req.get("job", 0)))
            if r is None:
                return {"ok": False, "error": "unknown or already collected job"}
            return self._wait(r, float(req.get("timeout", 25)))
        if op == "stop":
            it.graceful = bool(req.get("graceful", True))
            it.stop_flag.set()
            if it.busy and req.get("interrupt", True):
                os.kill(os.getpid(), signal.SIGINT)
            return {"ok": True, "stopping": True, "pid": os.getpid()}
        if op in MAIN_OPS:
            if not it.ready.is_set():
                it.ready.wait(120)
            r = Request(op, req)
            self.jobs[r.id] = r
            while len(self.jobs) > 50:
                self.jobs.popitem(last=False)
            it.requests.put(r)
            return self._wait(r, float(req.get("timeout", 25)))
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


def _cmdline(pid: int) -> bytes:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read()
    except OSError:
        return b""


def install_pdeathsig() -> None:
    """Linux: children forked from the main thread get SIGTERM when the helper dies (even kill -9)."""
    if not sys.platform.startswith("linux"):
        return
    import ctypes
    import subprocess

    libc = ctypes.CDLL(None, use_errno=True)
    orig_init = subprocess.Popen.__init__

    def _set():
        libc.prctl(1, signal.SIGTERM)

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
    token = os.environ.setdefault(procs.TOKEN_ENV, os.urandom(8).hex())
    install_pdeathsig()
    hooks = build_hooks([h for h in (opts.hooks or "").split(",") if h], settle=opts.settle,
                        followup=opts.settle_followup)
    state: Dict[str, Any] = {}

    def on_ready() -> None:
        state.update(ready=True, ready_at=time.time())
        proto.write_state(sd, state)

    cli_vars = dict(v.split(":", 1) if ":" in v else (v, "") for v in (opts.variable or []))
    it = Helper(hooks, sd, cli_vars, idle_s=opts.idle, on_ready=on_ready)

    def _sig_call(self_, signum, frame):  # replaces robotcode's patched _StopSignalMonitor.__call__
        if signum == signal.SIGTERM:
            it.stop_flag.set()
        if self_._running_keyword:
            self_._stop_execution_gracefully()

    _StopSignalMonitor.__call__ = _sig_call
    signal.signal(signal.SIGTERM, lambda s, f: it.stop_flag.set())
    srv = Server(it, sd, tcp=opts.tcp)
    state.update(pid=os.getpid(), pgid=os.getpgrp(), token_env=token, ready=False, started=time.time(),
                 python=sys.executable, cwd=os.getcwd(), outdir=str(outdir), hooks=[h.name for h in hooks],
                 **srv.endpoint())
    proto.write_state(sd, state)
    ep = srv.endpoint()
    ep_txt = f"tcp {ep['port']} {ep['token']}" if opts.tcp else f"unix {ep['sock']}"
    fd = os.open(sd / "endpoint", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(ep_txt + "\n")
    srv.start()
    rc = 0
    try:
        run_repl(it, app, variable=tuple(opts.variable or ()), variablefile=tuple(opts.variablefile or ()),
                 pythonpath=tuple(opts.pythonpath or ()), outputdir=str(outdir), output=None,
                 log=None, report=None, source=Path.cwd() / "__rfh__.robot")
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
        left = list(procs.descendants(os.getpid()))
        left += [p for p in procs.token_procs(token) if p != os.getpid() and p not in left]
        # robotcode analyzer workers (multiprocessing spawn / resource_tracker) ignore SIGTERM -> SIGKILL now
        mp = [p for p in left if b"multiprocessing" in _cmdline(p)]
        for p in mp:
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass
        rest = [p for p in left if p not in mp]
        forced = procs.terminate(rest, grace=1.5) if rest else []
        state.update(ready=False, stopped=time.time(), leftover=len(left), forced=len(forced), **it.stop_info,
                     cleanup_ms=round((time.time() - t_fin) * 1000))
        proto.write_state(sd, state)
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rfharness31.engine")
    p.add_argument("--dir")
    p.add_argument("-v", "--variable", action="append")
    p.add_argument("-V", "--variablefile", action="append")
    p.add_argument("-P", "--pythonpath", action="append")
    p.add_argument("-d", "--outputdir")
    p.add_argument("--root")
    p.add_argument("--hooks", default="redact,importhint,hints,guard")
    p.add_argument("--settle", type=float, default=1.5)
    p.add_argument("--settle-followup", type=float, default=5.0)
    p.add_argument("--idle", type=float, default=float(os.environ.get("RFH31_IDLE_EXIT", "1800")))
    p.add_argument("--tcp", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    opts = build_parser().parse_args(argv)
    app = Application()
    app.config.root = Path(opts.root or os.getcwd())
    return serve(app, opts)


if __name__ == "__main__":
    sys.exit(main())
