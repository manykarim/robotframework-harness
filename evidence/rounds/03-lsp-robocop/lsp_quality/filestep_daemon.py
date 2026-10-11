"""Round-3 shim on top of the round-2 helper: FILE-based step execution + in-helper warm analyzer.

New ops (queued to the RF main thread like `step`):
  filestep {path, mode: new|lines|all, lines:[a,b], test, check:bool, force:bool}
  check    {path, mode, lines, test}                     -> static diagnostics only (no execution)

The request carries only a path and a line range -- never RF syntax. The helper
  1. parses the file with RF's own parser (robot.api.get_model) -> test-body items with line ranges,
  2. mirrors Settings imports / *** Variables *** / *** Keywords *** of the live file into a generated
     resource with IDENTICAL line numbers (test section blanked) and (re)imports it when it changed,
  3. statically checks the file with an in-process WarmAnalyzer (robotcode `analyze code` engine),
     then filters each selected item's diagnostics against the LIVE RF state just before running it
     (variables that exist now, keywords the live namespace resolves) -> no dynamic-variable FPs,
  4. runs the selected items in the live session, maps results to file line numbers, stops on the
     first failure, and records executed items (content hashes) in .rf/filestep.json.

Run:  PYTHONPATH=<round2 pkg>:<this dir> python -m filestep_daemon --dir .rf [daemon opts]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from robot.api import get_model
from robot.libraries.BuiltIn import BuiltIn
from robot.running import TestSuite
from robot.running.context import EXECUTION_CONTEXTS
from robot.running.signalhandler import _StopSignalMonitor

from robotcode.plugin import Application
from robotcode.repl.run import run_repl

from rfmcp_local import daemon as D
from rfmcp_local import procs, proto
from rfmcp_local.hooks import build_hooks, resolve_owner

HERE = Path(__file__).resolve().parent
SKIP_TYPES = {"EOL", "COMMENT", "DOCUMENTATION", "TAGS", "SETUP", "TEARDOWN", "TEMPLATE", "TIMEOUT"}
KEEP_SETTINGS = {"LibraryImport", "ResourceImport", "VariablesImport", "SectionHeader", "EmptyLine", "Comment"}
VAR_RE = re.compile(r"Variable '([$@&%]\{[^']+\})' not found")
SETVAR_KWS = {"settestvariable", "setsuitevariable", "setglobalvariable", "settaskvariable", "setlocalvariable"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", "")).strip().lower()


def _h(text: str) -> str:
    return hashlib.sha1("\n".join(l.rstrip() for l in text.splitlines()).encode()).hexdigest()[:12]


class FileHelper(D.HelperInterpreter):
    def __init__(self, *a: Any, sd: Path, cli_vars: Dict[str, str], **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.sd = sd
        self.cli_vars = cli_vars
        self.analyzer: Any = None
        self.state_path = sd / "filestep.json"
        try:
            self.state: Dict[str, Any] = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            self.state = {"files": {}}
        self.gen_imported: Dict[str, str] = {}  # gen resource path -> hash of imported content

    # ------------------------------------------------------------------ main-thread dispatch
    def run_input(self) -> None:  # same as round-2, plus filestep/check
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
                self.busy = {"id": req.id, "since": time.time(), "cell": D._t(req.data.get("cells"), 120)}
                resp = self._run_cells(req)
            elif req.op in ("filestep", "check"):
                self.busy = {"id": req.id, "since": time.time(), "cell": f"{req.op} {req.data.get('path')}"}
                resp = self._filestep(req.data, execute=req.op == "filestep")
            elif req.op == "vars":
                resp = self._vars(req.data)
            else:
                resp = {"ok": False, "error": f"unknown op {req.op}"}
        except (SystemExit, KeyboardInterrupt):
            req.reply({"ok": False, "error": "helper exiting"})
            raise
        except BaseException as e:
            import traceback

            resp = {"ok": False, "error": D._t(f"{type(e).__name__}: {e}"), "tb": traceback.format_exc()[-1500:]}
        finally:
            self.busy = None
        self.results[req.id] = resp
        while len(self.results) > 50:
            self.results.popitem(last=False)
        req.reply(resp)

    # ------------------------------------------------------------------ parsing
    def _items(self, path: Path, test: Optional[str]) -> Tuple[Any, List[Dict[str, Any]], List[str], Any]:
        text = path.read_text()
        lines = text.splitlines()
        model = get_model(str(path))
        model.source = str(path)
        tsec = [s for s in model.sections if type(s).__name__ in ("TestCaseSection", "TaskSection")]
        tests = [t for s in tsec for t in s.body if type(t).__name__ == "TestCase"]
        if not tests:
            raise ValueError("no test case in file")
        tc = next((t for t in tests if test and t.name == test), tests[0])
        items = []
        for n in tc.body:
            if getattr(n, "type", None) in SKIP_TYPES:
                continue
            end = n.end_lineno
            while end > n.lineno and not lines[end - 1].strip():  # trailing blank lines of an unclosed block
                end -= 1
            src = "\n".join(lines[n.lineno - 1:end])
            items.append({"line": n.lineno, "end": end, "hash": _h(src), "src": src})
        return model, items, lines, tc

    def _gen_resource(self, path: Path, model: Any, lines: List[str]) -> Optional[Path]:
        """Settings imports + Variables + Keywords of the live file -> resource with identical line numbers."""
        keep = [""] * len(lines)
        has = False
        for sec in model.sections:
            kind = type(sec).__name__
            if kind in ("KeywordSection", "VariableSection"):
                for i in range(sec.lineno, sec.end_lineno + 1):
                    keep[i - 1] = lines[i - 1]
                has = True
            elif kind == "SettingSection":
                for st in [sec.header, *sec.body]:
                    if type(st).__name__ in KEEP_SETTINGS:
                        for i in range(st.lineno, st.end_lineno + 1):
                            keep[i - 1] = lines[i - 1]
                        has = has or type(st).__name__.endswith("Import")
        if not has:
            return None
        gen = path.with_name(f".{path.stem}.live.resource")
        content = "\n".join(keep) + "\n"
        h = _h(content)
        if self.gen_imported.get(str(gen)) == h:
            return gen
        gen.write_text(content)
        ns = EXECUTION_CONTEXTS.current.namespace
        if str(gen) in self.gen_imported:
            self._autoreload()  # round-2: re-imports cached resources whose mtime changed
        else:
            ns.import_resource(str(gen))
            try:
                self._res_mtime[str(gen)] = os.stat(gen).st_mtime_ns
            except OSError:
                pass
        self.gen_imported[str(gen)] = h
        return gen

    # ------------------------------------------------------------------ static check + live filter
    def _analyzer(self) -> Any:
        if self.analyzer is None:
            sys.path.insert(0, str(HERE))
            from warm_analyzer import WarmAnalyzer

            self.analyzer = WarmAnalyzer(Path.cwd(), variables=self.cli_vars)
        return self.analyzer

    def _live_filter(self, item: Dict[str, Any], diags: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        keep, dropped = [], []
        bi = BuiltIn()
        first = item["src"].split("\n")[0].strip()
        cells = [c for c in re.split(r"\s{2,}|\t", first) if c]
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
                    why = f"live namespace resolves '{m.group(1)}' -> {resolve_owner(m.group(1))}"
            if why:
                dropped.append(f"L{d['line']} {d['code']} ({why})")
            else:
                keep.append(d)
        return keep, dropped

    # ------------------------------------------------------------------ the op
    def _filestep(self, data: Dict[str, Any], execute: bool) -> Dict[str, Any]:
        t0 = time.perf_counter()
        path = Path(data["path"]).resolve()
        key = str(path)
        model, items, lines, tc = self._items(path, data.get("test"))
        fstate = self.state["files"].setdefault(key, {"done": []})
        done: List[str] = fstate["done"]
        k = 0
        while k < len(items) and k < len(done) and items[k]["hash"] == done[k]:
            k += 1
        mode = data.get("mode", "new")
        resp: Dict[str, Any] = {"ok": True, "file": os.path.relpath(path)}
        if mode == "new":
            if k < len(done):
                changed = items[k] if k < len(items) else None
                return {"ok": False, "file": resp["file"], "error": "already-executed lines changed",
                        "first_changed_line": changed["line"] if changed else None, "executed_items": len(done),
                        "hint": "run them explicitly with --lines A-B (re-executes), or --rebase to accept the "
                                "current file as executed up to the last unchanged line"}
            sel = items[k:]
        elif mode == "rebase":
            fstate["done"] = [it["hash"] for it in items if it["line"] <= int(data.get("through", 10**9))]
            self._save()
            return {"ok": True, "rebased_items": len(fstate["done"])}
        elif mode == "lines":
            a, b = data["lines"]
            sel = [it for it in items if it["line"] >= a and it["end"] <= b or a <= it["line"] <= b]
        else:
            sel = items
        resp["selected"] = [[it["line"], it["end"]] for it in sel]
        if not sel:
            resp["note"] = "nothing new to run"
            return resp
        t1 = time.perf_counter()
        gen = self._gen_resource(path, model, lines) if execute else None
        t2 = time.perf_counter()
        diags_by_item: Dict[int, List[Dict[str, Any]]] = {}
        check = data.get("check", True)
        if check:
            res = self._analyzer().check(path, text="\n".join(lines) + "\n", min_severity=1)
            resp["check_ms"] = res["ms"]
            for it in sel:
                ds = [d for d in res["diags"] if it["line"] <= d["line"] <= it["end"]]
                if ds:
                    diags_by_item[it["line"]] = ds
            # errors outside the test body (Settings / Variables / *** Keywords *** of the live file):
            # reported (not blocking) -- a typo inside a live-file keyword only fails when called
            outside = [d for d in res["diags"] if not (tc.lineno <= d["line"] <= tc.end_lineno)]
            if outside:
                resp["file_diags"] = outside[:10]
        t3 = time.perf_counter()
        if not execute:
            out = []
            for it in sel:
                keep, dropped = self._live_filter(it, diags_by_item.get(it["line"], []))
                for d in keep:
                    out.append(d)
                if dropped:
                    resp.setdefault("dropped", []).extend(dropped)
            resp["diags"] = out
            resp["ok"] = not out
            resp["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            return resp
        suite = TestSuite.from_model(model)
        rtest = next((t for t in suite.tests if t.name == tc.name), suite.tests[0])
        by_line = {it.lineno: it for it in rtest.body}
        ran: List[Dict[str, Any]] = []
        ok = True
        for it in sel:
            keep, dropped = self._live_filter(it, diags_by_item.get(it["line"], []))
            if dropped:
                resp.setdefault("dropped", []).extend(dropped)
            if keep and not data.get("force"):
                resp.update(ok=False, blocked={"line": it["line"], "end": it["end"], "src": it["src"][:300],
                                               "diags": keep},
                            hint=f"fix line {it['line']} (static check, not executed); --force to run anyway")
                ok = False
                break
            node = by_line.get(it["line"])
            if node is None:
                resp.update(ok=False, error=f"no runnable item at line {it['line']}")
                ok = False
                break
            rec, passed = self._run_one(node)
            rec = {"line": it["line"], **({"end": it["end"]} if it["end"] != it["line"] else {}), **rec}
            ran.append(rec)
            if passed:
                if k == len(fstate["done"]) and k < len(items) and items[k] is it:
                    fstate["done"].append(it["hash"])
                    k += 1
            else:
                ok = False
                resp["failed"] = {"line": it["line"], "end": it["end"], "src": it["src"][:300], "msg": rec.get("msg")}
                resp["hint"] = f"edit line {it['line']} and run --new again"
                break
        self._save()
        resp["ok"] = ok
        resp["ran"] = ran
        resp["timing_ms"] = {"parse": round((t1 - t0) * 1000, 1), "gen_resource": round((t2 - t1) * 1000, 1),
                             "check": round((t3 - t2) * 1000, 1), "total": round((time.perf_counter() - t0) * 1000, 1)}
        if gen is not None:
            resp["live_resource"] = os.path.basename(gen)
        self._journal_file(data, resp)
        return resp

    def _save(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        os.replace(tmp, self.state_path)

    def _journal_file(self, data: Dict[str, Any], resp: Dict[str, Any]) -> None:
        line = {"ts": round(time.time(), 3), "request": data, "ok": resp.get("ok"),
                "ran": [(r["line"], r.get("kw"), r.get("status")) for r in resp.get("ran", [])]}
        with open(self.sd / "filestep_journal.jsonl", "a") as f:
            f.write(json.dumps(line) + "\n")


class FileServer(D.Server):
    def _dispatch(self, req: Dict[str, Any]) -> Dict[str, Any]:
        if req.get("op") in ("filestep", "check"):
            it = self.interp
            with open(it.sd / "raw_requests.log", "a") as f:  # evidence: what travels over the socket
                f.write(json.dumps(req) + "\n")
            if not it.ready.is_set():
                it.ready.wait(120)
            r = D.Request(req["op"], req)
            it.requests.put(r)
            if not r.done.wait(float(req.get("timeout", 600))):
                return {"ok": None, "pending": True, "id": r.id}
            return r.resp or {"ok": False, "error": "no response"}
        return super()._dispatch(req)


def serve(app: Application, opts: Any) -> int:
    """round-2 serve() with FileHelper/FileServer; also copies the filestep client into the state dir."""
    sd = proto.state_dir(opts.dir)
    proto.ensure_private_dir(sd)
    outdir = Path(opts.outputdir or (sd / "out")).absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    token = os.environ.setdefault(procs.TOKEN_ENV, os.urandom(8).hex())
    if opts.pdeathsig:
        D.install_pdeathsig()
    hooks = build_hooks([h for h in (opts.hooks or "").split(",") if h], fast_timeout=opts.fast_timeout)
    state: Dict[str, Any] = {}

    def on_ready() -> None:
        state.update(ready=True, ready_at=time.time())
        proto.write_state(sd, state)

    cli_vars = dict(v.split(":", 1) if ":" in v else (v, "") for v in (opts.variable or []))
    interp = FileHelper(hooks, sd / "journal.jsonl", on_ready=on_ready, log_levels=tuple(opts.log_levels.split(",")),
                        sd=sd, cli_vars=cli_vars)

    def _sig_call(self_: Any, signum: int, frame: Any) -> None:
        if signum == signal.SIGTERM:
            interp.stop_flag.set()
        if self_._running_keyword:
            self_._stop_execution_gracefully()

    _StopSignalMonitor.__call__ = _sig_call
    signal.signal(signal.SIGTERM, lambda s, f: interp.stop_flag.set())
    srv = FileServer(interp, sd, tcp=opts.tcp)
    state.update(pid=os.getpid(), pgid=os.getpgrp(), sid=os.getsid(0), token_env=token, ready=False,
                 started=time.time(), python=sys.executable, cwd=os.getcwd(), outdir=str(outdir),
                 hooks=[h.name for h in hooks], **srv.endpoint())
    proto.write_state(sd, state)
    ep = srv.endpoint()
    ep_txt = f"tcp {ep['port']} {ep['token']}" if opts.tcp else f"unix {ep['sock']}"
    fd = os.open(sd / "endpoint", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(ep_txt + "\n")
    import shutil

    shutil.copyfile(Path(D.__file__).with_name("fast.py"), sd / "fast.py")
    shutil.copyfile(HERE / "filestep.py", sd / "filestep.py")
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
        left = list(procs.descendants(os.getpid()))
        left += [p for p in procs.token_procs(token) if p != os.getpid() and p not in left]
        forced = procs.terminate(left, grace=2.0) if left else []
        state.update(ready=False, stopped=time.time(), leftover=len(left), forced=len(forced), **interp.stop_info,
                     cleanup_ms=round((time.time() - t_fin) * 1000))
        proto.write_state(sd, state)
    return rc


def main(argv: Optional[List[str]] = None) -> int:
    opts = D.build_parser().parse_args(argv)
    app = Application()
    app.config.profiles = opts.profiles
    if opts.root:
        app.config.root = Path(opts.root)
    return serve(app, opts)


if __name__ == "__main__":
    sys.exit(main())
