"""Live RF session daemon for the hooks: engine.Helper (robotcode REPL) + the file-step engine + page snapshots.

op hookrun {path, mode: edit|reproduce|resume, test?, baseline?, diags?}
  edit       the file changed on disk. Changed lines = diff(last text this daemon saw | hook baseline, disk).
             Touched tests (a changed line inside the test or one of its items) run like this:
               * only lines AFTER the executed prefix changed / were appended -> run from the first new line
                 (resume: a fixed failing line re-runs in the still-open page);
               * an already-executed line changed / was removed / a line was inserted before it -> RESTART the
                 test: [Suite Setup, only if the test opens no page/session itself] + test setup + all lines;
               * Settings / Keywords / Variables changed -> imports re-imported; the last failed test resumes;
             tests queued behind an earlier failure (whole-file writes) continue after the touched ones.
             Stops at the first failure; [Teardown] is not run (page stays open for the next edit).
  reproduce  a plain robot run failed: run that test from the top (clean), stop at its first failure.
  resume     a .resource changed: re-import, re-run the last failed line.
After a run that navigated or failed: page snapshot -> .rf/state/{controls.txt,aria.yaml,source.html,
screenshot.png,page.txt} + a compact summary in the reply.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from robot.libraries.BuiltIn import BuiltIn
from robot.running import TestSuite
from robot.running.context import EXECUTION_CONTEXTS
from robot.running.signalhandler import _StopSignalMonitor

from robotcode.plugin import Application
from robotcode.repl.run import run_repl

from . import engine, procs, proto
from .engine import Helper, Server, _Tee, _t
from .hookcore import changed_line_numbers
from .rthooks import build_hooks

engine.MAIN_OPS.update({"hookrun", "snapshot"})
NAV_KWS = {"newbrowser", "newcontext", "newpage", "newpersistentcontext", "openbrowser", "goto", "createsession",
           "connecttobrowser", "createclientcertsession", "createdigestsession", "createntlmsession"}


def _nk(name: str) -> str:
    return re.sub(r"[\s_]", "", name.split(".")[-1]).lower()


def _norm(src: str) -> str:
    return "\n".join(re.sub(r"\s{2,}|\t", "  ", l.strip()) for l in src.splitlines() if l.strip())


def _hash(kind: str, src: str) -> str:
    return kind + ":" + hashlib.sha1(_norm(src).encode()).hexdigest()[:12]


def _kw_of(src: str) -> str:
    cells = [c for c in re.split(r"\s{2,}|\t", src.strip().split("\n")[0].strip()) if c]
    while cells and (cells[0].endswith("=") or cells[0].startswith(("${", "@{", "&{")) and cells[0].rstrip("= ").endswith("}")):
        cells = cells[1:]
    if cells and cells[0].lower() in ("[setup]", "test setup", "suite setup", "task setup"):
        cells = cells[1:]
    return cells[0] if cells else ""


_ROW_SUBS = [
    (re.compile(r"\(HIDDEN styled input: click its label; assert on the input: Get Checkbox State\s+(\S+)\s+==\s+checked\)"),
     r"(hidden styled input: click the label; assert on \1)"),
    (re.compile(r"\(native select \[([^\]]*)\] -> Select Options By\s+\S+\s+label\s+<option>\)"), r"(native select: \1)"),
    (re.compile(r"custom dropdown -> Click it, then Click\s+role=option\[name=\"<option>\"\]"),
     'custom dropdown: click it, then role=option[name="..."]'),
    (re.compile(r"HIDDEN native select: a custom dropdown is shown instead, click that"), "hidden select: use the custom dropdown"),
    (re.compile(r"  +"), "  "),
]


def _short_row(l: str) -> str:
    for rx, rep in _ROW_SUBS:
        l = rx.sub(rep, l)
    return l


def _nk2(s: str) -> str:
    return re.sub(r"[\s_]", "", s).lower()


def _changed_keywords(model: Any, changed: set) -> set:
    """normalized names of user keywords (Keywords section of this file) whose lines changed."""
    out = set()
    for sec in model.sections:
        if type(sec).__name__ != "KeywordSection":
            continue
        for kw in sec.body:
            if type(kw).__name__ == "Keyword" and kw.name and changed & set(range(kw.lineno, kw.end_lineno + 1)):
                out.add(_nk2(kw.name))
    return out


class HookHelper(Helper):
    def __init__(self, hooks: List[Any], sd: Path, root: Path, cli_vars: Dict[str, str], idle_s: float,
                 on_ready=None) -> None:
        super().__init__(hooks, sd, cli_vars, idle_s=idle_s, on_ready=on_ready)
        self.root = root
        self.out_state = root / ".rf" / "state"
        self.last_seen: Dict[str, str] = {}
        self.failed: Optional[Dict[str, Any]] = None
        self.pending: Dict[str, List[str]] = {}
        if self.guard is not None:
            self.guard.cur_settle = self.guard.followup

    # ------------------------------------------------------------------ where inside a user keyword it failed
    def end_keyword(self, data, result) -> None:
        if (not self._in_hook and self._depth > 1 and result.status == "FAIL" and self._nested_fail is None
                and getattr(self, "_nested_loc", None) is None):
            src, ln = getattr(data, "source", None), getattr(data, "lineno", None)
            if src and ln:
                p = Path(str(src))
                if p.name.startswith(".") and p.name.endswith(".live.resource"):
                    p = p.with_name(p.name[1:-len(".live.resource")] + ".robot")   # same line numbers
                try:
                    self._nested_loc = f"{os.path.relpath(p, self.root)}:{ln}"
                except ValueError:
                    self._nested_loc = f"{p}:{ln}"
        super().end_keyword(data, result)

    def _run_one(self, kw: Any):
        self._nested_loc = None
        rec, passed = super()._run_one(kw)
        if rec.get("status") == "FAIL" and self._nested_loc and rec.get("failed_in"):
            rec["failed_at"] = self._nested_loc
        return rec, passed

    # ------------------------------------------------------------------ generated resource: never left on disk
    def _gen_resource(self, path: Path, model: Any, lines: List[str]) -> Optional[Path]:
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
                    if type(st).__name__ in engine.KEEP_SETTINGS:
                        for i in range(st.lineno, min(st.end_lineno, len(lines)) + 1):
                            keep[i - 1] = lines[i - 1]
                        has = has or type(st).__name__.endswith("Import")
        if not has:
            return None
        gen = path.with_name(f".{path.stem}.live.resource")
        content = "\n".join(keep) + "\n"
        h = hashlib.sha1(content.encode()).hexdigest()[:12]
        if self.gen_imported.get(str(gen)) == h:
            return gen
        try:
            gen.write_text(content)
            if gen not in self.gen_files:
                self.gen_files.append(gen)
            ns = EXECUTION_CONTEXTS.current.namespace
            if str(gen) in self.gen_imported:
                cache = engine._importer()._resource_cache
                if str(gen) in cache._keys:
                    idx = cache._keys.index(str(gen))
                    del cache._keys[idx]
                    del cache._items[idx]
                ns.import_resource(str(gen), overwrite=True)
            else:
                ns.import_resource(str(gen))
            self.gen_imported[str(gen)] = h
        finally:
            with contextlib.suppress(OSError):
                gen.unlink()
        return gen

    def _search_order(self, model: Any, gen: Optional[Path]) -> None:
        order: List[str] = []
        if gen is not None:
            order.append(gen.stem)  # ".name.live"
        for sec in model.sections:
            if type(sec).__name__ != "SettingSection":
                continue
            for st in sec.body:
                if type(st).__name__ == "LibraryImport" and st.name:
                    nm = getattr(st, "alias", None) or st.name
                    if nm.endswith(".py") or "/" in nm:
                        nm = Path(nm).stem
                    order.append(nm)
        with contextlib.suppress(Exception):
            BuiltIn().set_library_search_order(*order)

    # ------------------------------------------------------------------ parsing
    def _parse2(self, path: Path):
        model, lines, parsed = self._parse(path)
        ss, tests = parsed[0]["suite_setup"], parsed[1:]
        for t in tests:
            for it in t["items"]:
                it["hash"] = _hash(it["kind"], it["src"])
                it["nav"] = _nk(_kw_of(it["src"])) in NAV_KWS if it["kind"] == "body" else \
                    _nk(it["setup"][0]) in NAV_KWS or any(_nk(a) in NAV_KWS for a in it["setup"][1][:1])
        if ss is not None:
            ss["hash"] = _hash("suite", ss["src"])
        return model, lines, ss, tests

    # ------------------------------------------------------------------ page info / snapshot
    def _lib(self, name: str) -> Any:
        try:
            return BuiltIn().get_library_instance(name)
        except Exception:
            return None

    def _url(self) -> Optional[str]:
        br = self._lib("Browser")
        if br is not None:
            try:
                return str(br.get_url())
            except Exception:
                return None
        se = self._lib("SeleniumLibrary")
        if se is not None:
            try:
                return str(se.get_location())
            except Exception:
                return None
        return None

    def snapshot(self, why: str) -> Optional[Dict[str, Any]]:
        from .pagestate import state

        if self._url() is None:
            return None
        t0 = time.perf_counter()
        out = self.out_state
        out.mkdir(parents=True, exist_ok=True)
        res: Dict[str, Any] = {}
        br = self._lib("Browser")
        files = []
        if br is not None:
            c = state("controls", out)
            if c.get("ok"):
                res.update(url=c.get("url"), title=c.get("title"), n_controls=c.get("controls"),
                           iframes=c.get("iframes") or [])
                rows = [_short_row(l) for l in (c.get("content") or "").splitlines() if l and not l.startswith("# main")]
                res["controls_top"] = [l[:150] for l in rows[:14]]
                files.append("controls.txt")
            else:
                res["error"] = c.get("error")
            a = state("aria", out)
            if a.get("ok"):
                files.append("aria.yaml")
                if not res.get("controls_top"):
                    res["aria_head"] = (a.get("content") or "")[:600]
            s = state("source", out)
            if s.get("ok"):
                files.append("source.html")
            with contextlib.suppress(Exception):
                for old in out.glob("screenshot*.png"):
                    old.unlink()
                got = br.take_screenshot(filename=str(out / "screenshot"), fullPage=False)
                if got:
                    files.append(os.path.basename(str(got)))
        else:
            s = state("source", out)
            res.update(url=s.get("url"), title=s.get("title"))
            files.append("source.html")
            with contextlib.suppress(Exception):
                se = self._lib("SeleniumLibrary")
                se.capture_page_screenshot(str(out / "screenshot.png"))
                files.append("screenshot.png")
        res["files"] = [f".rf/state/{f}" for f in files]
        res["ms"] = round((time.perf_counter() - t0) * 1000)
        sig = hashlib.sha1(repr((res.get("url"), res.get("controls_top"))).encode()).hexdigest()
        if sig == getattr(self, "_last_page_sig", None):
            res["unchanged"] = True
        self._last_page_sig = sig
        with contextlib.suppress(OSError):
            (out / "page.txt").write_text(f"url: {res.get('url')}\ntitle: {res.get('title')}\nwhen: "
                                          f"{time.strftime('%H:%M:%S')} ({why})\nfiles: {', '.join(files)}\n")
        return res

    def _op_snapshot(self, req) -> Dict[str, Any]:
        snap = self.snapshot(req.data.get("why") or "requested")
        return {"ok": snap is not None, "page": snap}

    # ------------------------------------------------------------------ the file-step engine
    def _op_hookrun(self, req) -> Dict[str, Any]:
        d = req.data
        self.guard_off = False
        return self._hookrun(Path(d["path"]).resolve(), d.get("mode", "edit"), d.get("test"), d.get("baseline"),
                             d.get("diags"))

    def _hookrun(self, path: Path, mode: str, test: Optional[str], baseline: Optional[str],
                 diags: Optional[List[Dict[str, Any]]], _depth: int = 0) -> Dict[str, Any]:
        t0 = time.perf_counter()
        rel = os.path.relpath(path, self.root)
        resp: Dict[str, Any] = {"ok": True, "file": rel, "mode": mode, "notes": []}
        if not path.is_file():
            resp["notes"].append("file does not exist (deleted?)")
            return resp
        if self.guard is not None:
            self.guard.cur_settle = self.guard.followup
        try:
            reloaded = self._autoreload()
        except Exception:
            reloaded = []
        if reloaded:
            resp["reloaded"] = [os.path.relpath(r, self.root) for r in reloaded]
        if path.suffix == ".resource":
            self.last_seen[str(path)] = path.read_text(errors="replace")
            if self.failed and _depth == 0 and Path(self.failed["path"]).is_file():
                r = self._hookrun(Path(self.failed["path"]), "resume", self.failed["test"], None, None, 1)
                r["notes"].insert(0, f"{rel} re-imported; resumed the last failed test")
                return r
            resp["notes"].append("resource re-imported; no failed live test to resume")
            return resp
        text = path.read_text(errors="replace")
        model, lines, ss, tests = self._parse2(path)
        key = str(path)
        fstate = self.files.setdefault(key, {"tests": {}, "suite": None})
        prev = self.last_seen.get(key, baseline)
        changed = changed_line_numbers(prev, text) if (prev is not None and mode == "edit") else None
        self.last_seen[key] = text
        if changed is not None and not changed and mode == "edit":
            resp["notes"].append("no change since the last run")
            return resp
        gen = self._gen_resource(path, model, lines)
        self._search_order(model, gen)
        if not tests:
            resp["notes"].append("no test case in the file")
            return resp
        names = [t["name"] for t in tests]
        by_name = {t["name"]: t for t in tests}
        plan: List[Dict[str, Any]] = []
        ss_changed = bool(ss and changed and ss["line"] in changed)
        if mode in ("reproduce", "resume"):
            t = by_name.get(test or "")
            if t is None:
                return {**resp, "ok": False, "error": f"no test named {test!r} in {rel}", "tests": names}
            if mode == "reproduce":
                plan.append({"t": t, "start": 0, "restart": True, "suite": ss is not None, "why": "reproduce"})
            else:
                done = fstate["tests"].get(t["name"], [])
                plan.append({"t": t, "start": len(done), "restart": False, "why": "resume"})
        else:
            chg = set(changed) if changed is not None else None
            touched = []
            for t in tests:
                rng = set(range(t["line"], t["end"] + 1))
                for it in t["items"]:
                    rng.update(range(it["line"], it["end"] + 1))
                if chg is None or rng & chg:
                    touched.append(t)
            if not touched and self.failed and self.failed["path"] == key and self.failed["test"] in by_name:
                touched = [by_name[self.failed["test"]]]
                resp["notes"].append("Settings/Keywords/Variables changed: resuming the failed test")
            elif not touched and chg:
                kws = _changed_keywords(model, chg)
                users = [t for t in tests if kws and any(k in _nk2(it["src"]) for it in t["items"] for k in kws)]
                if users:      # a user keyword changed: re-run the first test that calls it, from the top
                    t = users[0]
                    own_nav = any(it.get("nav") for it in t["items"])
                    plan.append({"t": t, "start": 0, "restart": True, "suite": ss is not None and not own_nav,
                                 "why": f"keyword {', '.join(sorted(kws))[:60]} changed -> first test using it re-run"})
            for nm in self.pending.get(key, []):
                if nm in by_name and by_name[nm] not in touched and all(q["t"] is not by_name[nm] for q in plan):
                    touched.append(by_name[nm])
            touched.sort(key=lambda t: names.index(t["name"]))
            for t in touched:
                items = t["items"]
                done = fstate["tests"].get(t["name"], [])
                k = 0
                while k < len(items) and k < len(done) and items[k]["hash"] == done[k]:
                    k += 1
                if k < len(done):
                    own_nav = any(it.get("nav") for it in items)
                    first_changed = items[k]["line"] if k < len(items) else items[-1]["line"] if items else t["line"]
                    plan.append({"t": t, "start": 0, "restart": True, "suite": ss is not None and not own_nav,
                                 "why": f"line {first_changed} (already executed) changed -> test restarted"})
                elif k < len(items):
                    plan.append({"t": t, "start": k, "restart": False, "why": "new lines" if done else "first run"})
                else:
                    resp["notes"].append(f"'{t['name']}': no new lines (all {len(items)} already passed live)")
        if ss_changed and not plan:
            plan_ss_only = True
        else:
            plan_ss_only = False
        suite = TestSuite.from_model(model)
        by_test = {t.name: {it.lineno: it for it in t.body} for t in suite.tests}
        for rt in suite.tests:      # setups from the running model (${CURDIR} etc. already resolved)
            if rt.setup and rt.setup.name:
                by_test[rt.name]["__setup__"] = rt.setup
        by_test["__suite__"] = {"__setup__": suite.setup if suite.setup and suite.setup.name else None}
        ran: List[Dict[str, Any]] = []
        ok = True
        url0 = self._url()
        console: List[str] = []
        orig_stdout = sys.__stdout__
        sys.__stdout__ = _Tee(orig_stdout, console)
        failed_at = None
        try:
            if plan_ss_only and ss is not None:
                rec, passed = self._item(None, ss, by_test, diags, resp)
                ran.append(rec)
                ok = passed
                if passed:
                    fstate["suite"] = ss["hash"]
            for pi, p in enumerate(plan):
                if not ok:
                    break
                t = p["t"]
                resp["notes"].append(f"'{t['name']}': {p['why']}")
                if p["restart"]:
                    fstate["tests"][t["name"]] = []
                if ss is not None and (fstate["suite"] != ss["hash"] or (p["restart"] and p.get("suite"))):
                    rec, passed = self._item(None, ss, by_test, diags, resp)
                    ran.append(rec)
                    if not passed:
                        ok, failed_at = False, (t["name"], ss)
                        self.pending[key] = [q["t"]["name"] for q in plan[pi:]]
                        break
                    fstate["suite"] = ss["hash"]
                done = fstate["tests"].setdefault(t["name"], [])
                for it in t["items"][p["start"]:]:
                    rec, passed = self._item(t["name"] if len(tests) > 1 else None, it, by_test, diags, resp,
                                             tname=t["name"])
                    ran.append(rec)
                    if not passed:
                        ok, failed_at = False, (t["name"], it)
                        break
                    done.append(it["hash"])
                if not ok:
                    self.failed = {"path": key, "test": t["name"], "line": failed_at[1]["line"]}
                    self.pending[key] = [q["t"]["name"] for q in plan[pi + 1:]]
                    break
                if self.failed and self.failed["path"] == key and self.failed["test"] == t["name"]:
                    self.failed = None
                resp.setdefault("passed_tests", []).append(t["name"])
            if ok:
                self.pending.pop(key, None)
        finally:
            sys.__stdout__ = orig_stdout
            self._baseline_mtimes()
        resp["ok"] = ok
        resp["ran"] = ran
        if console:
            resp["console"] = self._scrub(_t("".join(console), 600))
        if any(t["teardown"] for t in tests) and ran:
            resp["notes"].append("[Teardown] is not run live (it runs in the plain robot run)")
        url1 = self._url()
        if ran and (not ok or (url1 and url1 != url0)):
            try:
                resp["page"] = self.snapshot("failure" if not ok else "navigation")
            except Exception as e:
                resp["page_error"] = f"{type(e).__name__}: {e}"[:200]
        elif url1:
            resp["url"] = url1
        complete = ok and all(len(fstate["tests"].get(t["name"], [])) == len(t["items"]) for t in tests)
        resp["file_complete"] = complete
        resp["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self._journal({"op": "hookrun", "file": rel, "mode": mode, "ok": ok,
                       "ran": [(r.get("line"), r.get("kw"), r.get("status")) for r in ran]})
        return resp

    def _item(self, tlabel: Optional[str], it: Dict[str, Any], by_test: Dict[str, Dict[int, Any]],
              diags: Optional[List[Dict[str, Any]]], resp: Dict[str, Any], tname: Optional[str] = None
              ) -> Tuple[Dict[str, Any], bool]:
        base = {"line": it["line"], **({"end": it["end"]} if it["end"] != it["line"] else {}),
                **({"test": tlabel} if tlabel else {}), **({"setup": True} if it["kind"] == "setup" else {})}
        if diags:
            ds = [x for x in diags if it["line"] <= x["line"] <= it["end"]]
            keep, dropped = self._live_filter(it["src"], ds)
            if keep:
                return {**base, "kw": _kw_of(it["src"]), "status": "NOT RUN",
                        "static": [{"line": x["line"], "code": x["code"], "msg": x["msg"][:200]} for x in keep[:3]]}, False
        if it["kind"] == "setup":
            node = by_test.get(tname if tname else "__suite__", {}).get("__setup__")
            if node is None:
                from robot.running.model import Keyword

                node = Keyword(name=it["setup"][0], args=tuple(it["setup"][1]))
        else:
            node = by_test.get(tname or "", {}).get(it["line"])
        if node is None:
            return {**base, "kw": _kw_of(it["src"]), "status": "NOT RUN", "msg": "no runnable item at this line"}, False
        rec, passed = self._run_one(node)
        return {**base, **rec}, passed


def serve(app: Application, opts: argparse.Namespace) -> int:
    sd = Path(opts.dir).absolute()
    proto.ensure_private_dir(sd)
    root = Path(opts.root).resolve()
    outdir = sd / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    token = os.environ.setdefault(procs.TOKEN_ENV, os.urandom(8).hex())
    engine.install_pdeathsig()
    hooks = build_hooks(["redact", "importhint", "hints", "guard"], settle=opts.settle, followup=opts.settle_followup)
    state: Dict[str, Any] = {}

    def on_ready() -> None:
        state.update(ready=True, ready_at=time.time())
        proto.write_state(sd, state)
        threading.Thread(target=_prewarm, args=(root,), daemon=True).start()

    it = HookHelper(hooks, sd, root, {}, idle_s=opts.idle, on_ready=on_ready)

    def _sig_call(self_, signum, frame):
        if signum == signal.SIGTERM:
            it.stop_flag.set()
        if self_._running_keyword:
            self_._stop_execution_gracefully()

    _StopSignalMonitor.__call__ = _sig_call
    signal.signal(signal.SIGTERM, lambda s, f: it.stop_flag.set())
    srv = Server(it, sd, tcp=False)
    state.update(pid=os.getpid(), pgid=os.getpgrp(), token_env=token, ready=False, started=time.time(),
                 python=sys.executable, cwd=os.getcwd(), outdir=str(outdir), kind="exec", watch_pid=opts.watch_pid,
                 **srv.endpoint())
    proto.write_state(sd, state)
    srv.start()
    if opts.watch_pid:
        def _watch() -> None:
            while not it.stop_flag.is_set():
                if not proto.pid_alive(opts.watch_pid):
                    it.stop_info["why"] = "agent exited"
                    it.stop_flag.set()
                    if it.busy:
                        os.kill(os.getpid(), signal.SIGINT)
                    return
                time.sleep(1.0)
        threading.Thread(target=_watch, daemon=True).start()
    rc = 0
    try:
        run_repl(it, app, variable=(), variablefile=(), pythonpath=(), outputdir=str(outdir), output=None,
                 log=None, report=None, source=root / "__rfh__.robot")
    except SystemExit as e:
        rc = int(e.code or 0) if isinstance(e.code, int) else 1
    finally:
        t_fin = time.time()
        srv.close()
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        left = list(procs.descendants(os.getpid()))
        left += [p for p in procs.token_procs(token) if p != os.getpid() and p not in left]
        mp = [p for p in left if b"multiprocessing" in engine._cmdline(p)]
        for p in mp:
            with contextlib.suppress(OSError):
                os.kill(p, signal.SIGKILL)
        rest = [p for p in left if p not in mp]
        forced = procs.terminate(rest, grace=1.5) if rest else []
        for g in it.gen_files:
            with contextlib.suppress(OSError):
                g.unlink()
        state.update(ready=False, stopped=time.time(), leftover=len(left), forced=len(forced), **it.stop_info,
                     cleanup_ms=round((time.time() - t_fin) * 1000))
        proto.write_state(sd, state)
    return rc


def _prewarm(root: Path) -> None:
    """import (not RF-import) the libraries the project uses, so the first live run starts faster."""
    libs = set()
    for dp, dns, fns in os.walk(root):
        dns[:] = [x for x in dns if not x.startswith(".") and x not in ("node_modules", "results")]
        for fn in fns:
            if fn.endswith((".robot", ".resource")):
                with contextlib.suppress(OSError):
                    for line in open(os.path.join(dp, fn), errors="replace"):
                        m = re.match(r"^Library\s{2,}(Browser|SeleniumLibrary|RequestsLibrary)\b", line)
                        if m:
                            libs.add(m.group(1))
    for lib in sorted(libs or {"Browser"}):
        with contextlib.suppress(Exception):
            importlib.import_module(lib)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="rfharness.execd")
    p.add_argument("--dir", required=True)
    p.add_argument("--root", required=True)
    p.add_argument("--watch-pid", type=int, default=0)
    p.add_argument("--idle", type=float, default=1200.0)
    p.add_argument("--settle", type=float, default=1.5)
    p.add_argument("--settle-followup", type=float, default=float(os.environ.get("RFH_GUARD_SETTLE", "5.0")))
    opts = p.parse_args(argv)
    os.chdir(opts.root)
    app = Application()
    app.config.root = Path(opts.root)
    return serve(app, opts)


if __name__ == "__main__":
    sys.exit(main())
