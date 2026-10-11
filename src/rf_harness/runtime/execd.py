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

from .. import config
from . import engine, procs, proto
from .engine import Helper, Server, _t, _Tee
from .hookcore import changed_line_numbers
from .livetmo import SEL_NOT_FOUND, LiveTimeouts, nk, touch
from .pwlog import actual_expected, classify
from .robotcode_adapter import Application, new_application, run_repl
from .rthooks import build_hooks, resolve_owner

engine.MAIN_OPS.update({"hookrun", "snapshot"})
MAX_CAPTURES = config.get_int("RFH_MAX_CAPTURES")   # v3: <= 2 per edit (failure + end of run)
HISTORY_KEEP = config.get_int("RFH_STATE_HISTORY")
# v3 (round-6 diagnosis: per-step settles + captures were hidden waits -> live pass / plain fail 13/20): capture ONLY
# on a failure and after the last executed step of an edit; never between steps, no per-step settle.
CAPTURE_MODE = config.get("RFH_CAPTURE")         # end (v3) | step (v2) | off
SETTLE_MAX = config.get_float("RFH_CAPTURE_SETTLE")
# v3: navigation-class keywords always capture (dedup by url+title+source hash); every other page-changing keyword
# (click, fill, select, ...) captures only when the URL or the DOM changed (MutationObserver counters, one cheap evaluate
# before and after the step); settle (wait for the DOM to go quiet) only after a URL change.
NAV_CAPTURE = {nk(k) for k in (
    "New Page", "Go To", "Go Back", "Go Forward", "Reload", "Switch Page", "Wait For Navigation", "Open Browser",
    "Reload Page", "Switch Window", "Select Frame", "Unselect Frame", "New Context")}
CAPTURE_GATE = config.get("RFH_CAPTURE_GATE") != "0"     # 0 = v2 behaviour (capture after every page kw)
# keywords after which the page may have changed -> page capture (deduplicated by url+title+source hash)
PAGE_KWS = {nk(k) for k in (
    # Browser
    "New Page", "Go To", "Go Back", "Go Forward", "Reload", "Click", "Click With Options", "Click Element", "Fill Text",
    "Fill Secret", "Type Text", "Type Secret", "Press Keys", "Keyboard Key", "Keyboard Input", "Select Options By",
    "Deselect Options", "Check Checkbox", "Uncheck Checkbox", "Upload File By Selector", "Upload File",
    "Handle Future Dialogs", "Switch Page", "Hover", "Drag And Drop", "Clear Text", "Tap", "Mouse Button",
    "Wait For Navigation",
    # SeleniumLibrary
    "Open Browser", "Reload Page", "Click Button", "Click Link", "Click Image", "Click Element At Coordinates",
    "Double Click Element", "Input Text", "Input Password", "Submit Form", "Select From List By Label",
    "Select From List By Value", "Select From List By Index", "Unselect From List By Label", "Select Checkbox",
    "Unselect Checkbox", "Select Radio Button", "Press Key", "Choose File", "Handle Alert", "Switch Window",
    "Select Frame", "Unselect Frame", "Mouse Over", "Drag And Drop By Offset")}
LOCATOR_FAIL = re.compile(r"strict mode violation|Timeout \d+ms exceeded|waiting for (?:locator|selector)|not visible|"
                          r"intercepts pointer events|Element with locator .* not found|did not match any elements|"
                          r"InvalidSelector|Unexpected token|is not a valid selector|not attached|not (?:enabled|editable)|"
                          r"Element locator .* did not match|is not a <select> element", re.I)

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


PROBE_KWS = {"log", "logtoconsole", "logmany", "logvariables", "comment", "nooperation", "geturl", "gettitle",
             "getelementcount", "getpagesource", "getsource", "getariasnapshot", "takescreenshot", "getelements",
             "getelement", "getlocation", "capturepagescreenshot", "gettext", "getattribute", "getproperty",
             "getelementstates", "getvalue", "getselectedoptions", "getcheckboxstate", "getboundingbox", "getstyle",
             "getclassnames", "getelementattribute", "getwebelements", "getwebelement"}
_GETTER_WITH_OP = {"gettext", "getattribute", "getproperty", "getelementstates", "getselectedoptions",
                   "getcheckboxstate", "getboundingbox", "getstyle", "getclassnames", "geturl", "gettitle",
                   "getelementcount"}


def _is_probe(it: Dict[str, Any]) -> bool:
    """a body line that only reads/logs (no assertion operator, no page action)."""
    if it.get("kind") != "body" or "\n" in it.get("src", ""):
        return False
    cells = [c for c in re.split(r"\s{2,}|\t", it["src"].strip()) if c]
    while cells and re.match(r"^[$@&]\{[^}]+\}\s*=?$", cells[0]):
        cells = cells[1:]
    if not cells:
        return False
    n = _nk(cells[0])
    if n not in PROBE_KWS:
        return False
    nargs = len(cells) - 1
    if n in ("geturl", "gettitle"):
        return nargs == 0
    if n in ("getattribute", "getproperty", "getstyle"):
        return nargs <= 2
    if n in _GETTER_WITH_OP:
        return nargs <= 1
    return True


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
        self.tmo = LiveTimeouts(state_file=sd / "timeouts.json")
        if self.guard is not None:
            if self.tmo.enabled:       # the probe waits as long as the (adaptive) short live timeout, then: recheck
                from .livetmo import SHORT_BROWSER_S
                self.guard.followup = min(self.guard.followup, SHORT_BROWSER_S)
                self.guard.settle = min(self.guard.settle, SHORT_BROWSER_S)
            self.guard.cur_settle = self.guard.followup
        self.cap_stats = {"captured": 0, "skipped_nochange": 0, "settles": 0}
        self.cap_no = max([int(m.group(1)) for d in self.out_state.glob("step-*")
                           for m in [re.match(r"step-(\d+)-", d.name)] if m] or [0])
        self.last_sig: Optional[str] = None
        self.last_capture: Optional[Dict[str, Any]] = None
        self.run_captures: List[Dict[str, Any]] = []
        self._deferred_capture: Optional[Tuple[str, str]] = None
        self._leaf: Optional[Dict[str, Any]] = None
        self._page_touched = False
        self._cur_line: Optional[int] = None
        self.rechecks = 0
        self._kw_stack: List[bool] = []
        self.last_change: Optional[float] = None
        self.probe_hashes: set = set()

    # ------------------------------------------------------------------ per keyword: live timeouts, page touch
    def start_keyword(self, data, result) -> None:
        if not self._in_hook:
            owner = getattr(result, "owner", None)
            name = getattr(result, "name", None) or ""
            normal = owner in ("Browser", "SeleniumLibrary") and self.tmo.is_normal(owner, name)
            self._kw_stack.append(normal)
            if owner in ("Browser", "SeleniumLibrary"):
                try:
                    self.tmo.before(owner, name, nested_normal=any(self._kw_stack[:-1]))
                except Exception:
                    pass
                if nk(name) in PAGE_KWS:
                    self._page_touched = True
        super().start_keyword(data, result)

    # ------------------------------------------------------------------ where inside a user keyword it failed
    def end_keyword(self, data, result) -> None:
        if not self._in_hook:
            if self._kw_stack:
                self._kw_stack.pop()
            owner = getattr(result, "owner", None)
            if owner in ("Browser", "SeleniumLibrary"):
                with contextlib.suppress(Exception):
                    self.tmo.after(owner, getattr(result, "name", ""), result.status != "FAIL")
                if result.status != "FAIL" and nk(getattr(result, "name", "")) in PAGE_KWS:
                    self.last_change = time.monotonic()
                    self.tmo.url_stale = True
            if result.status == "FAIL" and self._leaf is None and getattr(result, "name", None):
                self._leaf_msg = result.message or ""
                self._leaf = {"kw": result.name, "owner": owner, "full": getattr(result, "full_name", result.name),
                              "args": [str(a)[:200] for a in (getattr(result, "args", ()) or ())][:4],
                              "msg": (result.message or "")[:400]}
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

    def _run_raw(self, kw: Any):
        self._nested_loc = None
        self._leaf = None
        self._leaf_msg = ""
        self._kw_stack = []
        rec, passed = super()._run_one(kw)
        if rec.get("status") == "FAIL" and self._nested_loc and rec.get("failed_in"):
            rec["failed_at"] = self._nested_loc
        return rec, passed

    def _owner_source(self, full: str) -> Optional[str]:
        """file of a resource / project library keyword (None for installed libraries)."""
        try:
            ctx = EXECUTION_CONTEXTS.current
            try:
                runner = ctx.namespace.get_runner(full, recommend_on_failure=False)
            except TypeError:
                runner = ctx.namespace.get_runner(full)
            src = getattr(getattr(getattr(runner, "keyword", None), "owner", None), "source", None)
        except Exception:
            return None
        if not src:
            return None
        p = Path(str(src))
        if p.name.startswith(".") and p.name.endswith(".live.resource"):
            p = p.with_name(p.name[1:-len(".live.resource")] + ".robot")
        try:
            p.resolve().relative_to(self.root)
        except ValueError:
            return None
        return str(p)

    def _browser_open(self) -> Optional[str]:
        """'Browser' / 'SeleniumLibrary' when that library is imported in the live session (touch is worth a call)."""
        for lib in ("Browser", "SeleniumLibrary"):
            if self._lib(lib) is not None:
                return lib
        return None

    def _run_one(self, kw: Any):
        is_kw = getattr(kw, "type", "") in ("KEYWORD", "SETUP", "TEARDOWN")
        name = kw.name if is_kw else ""
        owner = resolve_owner(name) if is_kw else None
        self._page_touched = is_kw and owner in ("Browser", "SeleniumLibrary") and nk(name) in PAGE_KWS
        web = self._browser_open() if is_kw else None
        t_before = touch(web) if (web and self.tmo.enabled) else None   # DOM observer (installed per document): url
        if t_before and t_before.get("href"):
            self.tmo.cur_url, self.tmo.url_stale = str(t_before["href"]), False
        url0 = self.tmo.cur_url
        if self.guard is not None and self.tmo.enabled:
            self.guard.cur_settle = self.tmo.short_for("Browser", url0) if web == "Browser" else self.guard.followup
        t0 = time.monotonic()
        rec, passed = self._run_raw(kw)
        if not passed:
            self._failure(rec, kw, name, owner, web, url0, t0)
            if rec.get("_rerun"):
                rec2, passed2 = rec.pop("_rerun")
                rec, passed = rec2, passed2
        # ---- page capture: v3 only on failure (+ end of run, see _hookrun); v2 mode: after page-changing keywords
        locator_fail = (not passed) and bool(rec.get("guard") or LOCATOR_FAIL.search(rec.get("msg") or "")
                                             or (rec.get("pw") or {}).get("cls"))
        if CAPTURE_MODE == "step" and (self._page_touched or locator_fail):
            cap = self._capture(name or getattr(kw, "type", "step"), "failure" if not passed else "page-changing keyword",
                                settle=passed)
            if cap:
                rec["capture"] = {k: cap.get(k) for k in ("dir", "unchanged", "step") if cap.get(k) is not None}
        elif CAPTURE_MODE == "end" and not passed and web:
            cap = self._capture(name or getattr(kw, "type", "step"), "failure", force=True)
            if cap:
                rec["capture"] = {k: cap.get(k) for k in ("dir", "unchanged", "step") if cap.get(k) is not None}
        if not passed and is_kw and self.last_capture:
            self._failure_context(rec)
        return rec, passed

    # ------------------------------------------------------------------ v3 failure policy
    def _failure(self, rec: Dict[str, Any], kw: Any, name: str, owner: Optional[str], web: Optional[str],
                 url0: Optional[str], t0: float) -> None:
        """deepest failing keyword, Playwright-log class (BEFORE any re-check), absent -> quiet/recheck -> SLOW/MISSING."""
        is_kw = bool(name)
        leaf = self._leaf or ({"kw": name, "owner": owner, "full": f"{owner}.{name}" if owner else name}
                              if is_kw else None)
        if rec.get("guard") and is_kw:
            leaf = {"kw": name, "owner": owner, "full": f"{owner}.{name}" if owner else name}
        if leaf and leaf.get("kw"):
            src = self._owner_source(leaf.get("full") or leaf["kw"]) if leaf.get("owner") not in (
                "Browser", "SeleniumLibrary", "BuiltIn", "RequestsLibrary", "Collections", "String") else None
            rec["leaf"] = {k: v for k, v in {"kw": leaf["kw"], "owner": leaf.get("owner"), "source": src}.items() if v}
        if not is_kw:
            return
        full = self._leaf_msg or getattr(self._top, "message", "") or rec.get("msg") or ""
        lo = (leaf or {}).get("owner") or owner
        g = rec.get("guard") or {}
        pw: Dict[str, Any] = {}
        if g:
            pw = {"cls": {"NOT_FOUND": "absent", "NOT_VISIBLE": "hidden", "COVERED": "covered",
                          "INVALID_SELECTOR": "invalid"}.get(g.get("cls"), ""), "selector": g.get("selector"),
                  "first": f"refused before execution: {g.get('cls')}"}
            if g.get("inside_iframe"):
                pw["cls"] = "iframe"
                pw["frame"] = g["inside_iframe"][0]
            if g.get("cls") == "COVERED":
                pw["evidence"] = f"covered by {g.get('covered_by')}"
                if g.get("proxy"):
                    pw["proxy"] = g["proxy"]
        elif lo == "Browser":
            pw = classify(full)
            if pw.get("cls") == "covered" and pw.get("selector"):
                px = self._proxy(pw["selector"])
                if px:
                    pw["proxy"] = px
        elif lo == "SeleniumLibrary":
            m = SEL_NOT_FOUND.search(full)
            if m:
                pw = {"cls": "absent", "selector": m.group(1) or m.group(2), "first": full.split("\n", 1)[0][:200]}
        if not pw.get("cls"):
            ae = actual_expected(full)
            if ae:
                rec["value"] = ae
        if pw.get("cls"):
            rec["pw"] = {k: v for k, v in pw.items() if v not in (None, "")}
        if pw.get("cls") == "covered" and "intercepts pointer events" in full and \
                "intercepts pointer events" not in (rec.get("msg") or ""):
            rec["msg"] = f"{pw.get('first', '')} ... {pw.get('evidence', '')}"     # keep the decisive fragment
        # ---- absent element: the only case worth a timing re-check
        if pw.get("cls") != "absent" or not self.tmo.enabled or not pw.get("selector"):
            return
        leaf_kw = (leaf or {}).get("kw") or name
        if self.tmo.is_normal(lo, leaf_kw):            # an explicit wait already used the normal timeout
            rec["recheck"] = {"verdict": "missing", "selector": pw["selector"], "normal_s": round(self.tmo.normal_s(lo), 1),
                              "after_wait": True}
            return
        sel = pw["selector"]
        if lo == "Browser":
            try:
                sel = str(BuiltIn().replace_variables(sel))
            except Exception:
                pass
        waited = time.monotonic() - t0
        try:
            tq = touch(lo)
            rc = self.tmo.recheck(lo, sel, waited, False, touch_info=tq, started=t0)
            if rc.get("verdict") == "missing" and lo == "Browser" and ">>>" not in sel:
                fr = self._frame_probe(sel)
                if fr:
                    rc["frame"] = fr
            elif rc.get("verdict") == "slow":
                ch = self.tmo.learn(lo, url0, float(rc.get("appeared_after_s") or 0))
                if ch:
                    rc["adapt"] = ch
        except Exception as e:
            rc = {"verdict": "error", "error": str(e)[:160]}
        self.rechecks += 1
        if rc.get("verdict") == "slow" and not rec.get("failed_in"):
            rec2, passed2 = self._run_raw(kw)
            rec2["recheck"] = {**rc, "first_try": (rec.get("msg") or "")[:160]}
            if not passed2 and "leaf" in rec:
                rec2.setdefault("leaf", rec["leaf"])
            rec["_rerun"] = (rec2, passed2)
        else:
            rec["recheck"] = rc

    def _failure_context(self, rec: Dict[str, Any]) -> None:
        """<= 3 controls nearest the failing selector (v3.1 rich profile: <= 8, also for covered / disabled /
        animating; never the same selector); value failures: is the expected value on the page at all."""
        pw = rec.get("pw") or {}
        if rec.get("value"):
            text = " ".join(((self.last_capture or {}).get("text") or "").split())
            exp = " ".join(str(rec["value"].get("expected") or "").split())
            if text and exp:
                rec["value"]["on_page"] = exp in text
            return
        rich = getattr(self, "profile", "lean") == "rich"
        if pw.get("cls") in ("covered", "animating", "disabled") and not rich:
            return
        sel = pw.get("selector") or (rec.get("guard") or {}).get("selector") or ((rec.get("recheck") or {}).get("selector"))
        if not sel and rec.get("args"):
            sel = str(rec["args"][0])
        m = self._near_controls(sel or "", n=8 if rich else 3,
                                kw=(rec.get("leaf") or {}).get("kw") or rec.get("kw") or "", fill=rich)
        if m:
            rec["matches"] = m

    _PROXY_JS = """(el) => {
  try {
    const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect(); const st = getComputedStyle(e);
      return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
    const txt = (e) => (e.innerText || e.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 40);
    const uniq = (s) => { try { const n = document.querySelectorAll(s); return n.length === 1 ? n[0] : null; } catch (x) { return null; } };
    let label = null;
    const ls = el.labels ? Array.from(el.labels).filter(vis) : [];
    if (ls.length) {
      const l = ls.find((x) => txt(x)) || ls[0];
      label = l.htmlFor ? 'label[for="' + l.htmlFor + '"]' : (txt(l) ? 'text="' + txt(l) + '"' : null);
      // v3.2: wrapping label without for= / text -> label:has(#id) when unique
      if (!label && el.id && uniq('label:has(#' + CSS.escape(el.id) + ')') === l) label = 'label:has(#' + CSS.escape(el.id) + ')';
    }
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    let top = null;
    if (x >= 0 && y >= 0 && x < innerWidth && y < innerHeight) top = document.elementFromPoint(x, y);
    let cover = null;
    if (top && top !== el && !el.contains(top)) {
      const cls = (top.className && typeof top.className === 'string') ? top.className.trim().split(/\\s+/)[0] : '';
      if (top.id) cover = 'id=' + top.id;
      else if (cls && document.querySelectorAll(top.tagName.toLowerCase() + '.' + CSS.escape(cls)).length === 1)
        cover = 'css=' + top.tagName.toLowerCase() + '.' + cls;
      else if (el.id) {   // v3.2: non-unique coverer next to the input
        const t = top.tagName.toLowerCase() + (cls ? '.' + CSS.escape(cls) : '');
        for (const s of ['#' + CSS.escape(el.id) + ' + ' + t, '#' + CSS.escape(el.id) + ' ~ ' + t])
          if (uniq(s) === top) { cover = 'css=' + s; break; } }
      cover = cover || ('<' + top.tagName.toLowerCase() + (cls ? ' class="' + cls + '"' : '') + '>');
    }
    return {label: label, cover: cover, tag: el.tagName.toLowerCase(), type: el.type || ''};
  } catch (e) { return null; }
}"""

    def _proxy(self, sel: str) -> Optional[Dict[str, Any]]:
        """covered element: its visible label (radio/checkbox) and the covering element's selector."""
        br = self._lib("Browser")
        if br is None:
            return None
        try:
            s2 = str(BuiltIn().replace_variables(sel))
            if int(br.get_element_count(s2) or 0) != 1:
                return None
            r = br.evaluate_javascript(s2, self._PROXY_JS)
            return {k: v for k, v in (r or {}).items() if v} or None
        except Exception:
            return None

    def _probe_only(self, items: List[Dict[str, Any]], done: List[str]):
        """executed prefix differs only by inserted / changed / removed PROBE lines -> (probes, newdone, start)."""
        i = j = 0
        probes: List[Dict[str, Any]] = []
        newdone: List[str] = []
        while i < len(items) and j < len(done):
            if items[i]["hash"] == done[j]:
                newdone.append(done[j])
                i += 1
                j += 1
            elif _is_probe(items[i]):
                probes.append(items[i])
                newdone.append(items[i]["hash"])
                i += 1
            elif done[j] in self.probe_hashes:
                j += 1
            else:
                return None
        while j < len(done):
            if done[j] not in self.probe_hashes:
                return None
            j += 1
        if not probes and i == len(newdone) and len(newdone) == len(done):
            return None
        return probes, newdone, i

    _ROLE_OF_KW = (("click", ("button", "link", "checkbox", "radio", "tab", "menuitem", "option")),
                   ("check", ("checkbox", "radio")), ("fill", ("textbox", "input", "textarea", "searchbox")),
                   ("type", ("textbox", "input", "textarea", "searchbox")), ("select", ("select", "combobox", "listbox")),
                   ("upload", ("file",)))

    def _near_controls(self, sel: str, n: int = 5, kw: str = "", fill: bool = False) -> List[str]:
        """up to n controls of the last capture as `"name" => selector`: word overlap with the failing selector first,
        then controls of the role the keyword acts on (click -> buttons/links, fill -> text fields, ...).
        Same-origin hrefs are never shown (round-5 OpenCode finding: deep links into the journey)."""
        rows = (self.last_capture or {}).get("controls_all") or []
        rows = [r for r in rows if "   => " in r]
        if not rows:
            return []
        words = {w for w in re.split(r"[^a-z0-9]+", re.sub(r"^(id|css|text|xpath|data-test\w*|role)=", "", sel.lower()))
                 if len(w) > 2 and w not in ("button", "input", "div", "span", "class", "name", "nth", "text", "role")}
        roles = next((r for k, r in self._ROLE_OF_KW if k in nk(kw)), ())
        norm_sel = re.sub(r"\s+", "", sel)
        scored = []
        for i, r in enumerate(rows):
            if re.sub(r"\s+", "", r.split("   => ", 1)[1].split("   (")[0]) == norm_sel:
                continue                      # the failing selector itself is no suggestion (round-6 finding)
            rl = r.lower()
            hit = sum(1 for w in words if w in rl)
            head = rl.split("   => ")[0]
            role_hit = 1 if roles and any(x in head.split('"')[0] for x in roles) else 0
            if hit or role_hit:
                scored.append((-hit, -role_hit, i, r))
        scored.sort()
        if scored and scored[0][0] < 0 and not fill:   # word matches exist: no role-only filler (header / nav noise)
            scored = [x for x in scored if x[0] < 0]     # (v3.1 rich: word matches first, then controls of the role)
        out = []
        for _h, _r, _i, r in scored[:n]:
            m = re.search(r'"([^"]{1,40})"', r.split("   => ")[0])
            selx = r.split("   => ", 1)[1].split("   (")[0].strip()
            out.append(((f'"{m.group(1)}" ' if m else "") + "=> " + selx)[:120])
        return out

    def _frame_probe(self, sel: str) -> Optional[str]:
        br = self._lib("Browser")
        if br is None or ">>>" in sel:
            return None
        try:
            nfr = int(br.get_element_count("css=iframe") or 0)
            for i in range(min(nfr, 5)):
                cand = f"css=iframe >> nth={i} >>> {sel}"
                if int(br.get_element_count(cand) or 0):
                    return cand
        except Exception:
            return None
        return None

    def _fresh_context(self) -> Optional[str]:
        """a restarted test gets a fresh browser context (cookies, cart, storage) -- round-5 OpenCode finding."""
        br = self._lib("Browser")
        if br is not None:
            try:
                from Browser.utils.data_types import SelectionType  # type: ignore

                br.close_context(context=SelectionType.ALL, browser=SelectionType.CURRENT)
                self.last_sig = None
                return "browser context closed (fresh cookies/storage for the restart)"
            except Exception:
                return None
        return None

    def _settle(self) -> None:
        """END of a run only (never between steps): wait until the page is quiet for 0.3 s with no pending async work
        (a click that navigates via a timer / an XHR) -- max SETTLE_MAX s -- so the capture shows what the next line
        will see."""
        web = self._browser_open()
        if not web:
            return
        self.cap_stats["settles"] += 1
        t_end = time.monotonic() + SETTLE_MAX
        while time.monotonic() < t_end:
            t = touch(web)
            q = (t or {}).get("quiet")
            if t and not t.get("fresh") and not t.get("pend") and isinstance(q, (int, float)) and q >= 300:
                return
            time.sleep(0.15)

    def _capture(self, kw: str, why: str, force: bool = False, settle: bool = False) -> Optional[Dict[str, Any]]:
        from .pagestate import capture, page_sig

        try:
            if settle:
                self._settle()
            si = page_sig()
        except Exception:
            si = None
        if si is None:
            return None
        if si[0] == self.last_sig and self.last_capture:
            res = {**self.last_capture, "unchanged": True}
            self.run_captures.append({"dir": res.get("dir"), "unchanged": True, "kw": kw, "line": self._cur_line})
            return res
        if not force and len([c for c in self.run_captures if not c.get("unchanged")]) >= MAX_CAPTURES:
            self._deferred_capture = (kw, why)
            return None
        self._deferred_capture = None
        self.cap_no += 1
        try:
            res = capture(self.out_state, self.cap_no, kw, self._cur_line, why, si, keep=HISTORY_KEEP)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"[:200]}
        self.last_sig, self.last_capture = si[0], res
        self.cap_stats["captured"] += 1
        self.run_captures.append({"dir": res.get("dir"), "kw": kw, "line": self._cur_line, "ms": res.get("ms")})
        return res

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
        snap = self._capture("snapshot", req.data.get("why") or "requested", force=True)
        return {"ok": snap is not None, "page": snap}

    # ------------------------------------------------------------------ the file-step engine
    def _op_hookrun(self, req) -> Dict[str, Any]:
        d = req.data
        self.guard_off = False
        self.profile = d.get("profile") if d.get("profile") in ("lean", "rich") else "lean"   # v3.1 output profile
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
        self.run_captures = []
        self._deferred_capture = None
        cs0 = dict(self.cap_stats)
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
                pr = self._probe_only(items, done) if k < len(done) else None
                if pr is not None:       # only probe lines (Log, Get ... without assertion) inserted/changed
                    probes, newdone, start = pr
                    plan.append({"t": t, "start": start, "restart": False, "probes": probes, "newdone": newdone,
                                 "why": ("probe line(s) only -> run now in the current page, no restart" if probes
                                         else "an executed probe line (Log / Get ...) was changed or removed -> "
                                              "no restart, continuing in the current page")})
                elif k < len(done):
                    own_nav = any(it.get("nav") for it in items)
                    first_changed = items[k]["line"] if k < len(items) else items[-1]["line"] if items else t["line"]
                    plan.append({"t": t, "start": 0, "restart": True, "suite": ss is not None and not own_nav,
                                 "own_nav": own_nav,
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
                    ss_nav = bool(ss and p.get("suite") and _nk(ss["setup"][0]) in NAV_KWS)
                    if p.get("own_nav") or ss_nav:
                        fresh = self._fresh_context()
                        if fresh:
                            resp["notes"].append(fresh)
                if ss is not None and (fstate["suite"] != ss["hash"] or (p["restart"] and p.get("suite"))):
                    rec, passed = self._item(None, ss, by_test, diags, resp)
                    ran.append(rec)
                    if not passed:
                        ok, failed_at = False, (t["name"], ss)
                        self.pending[key] = [q["t"]["name"] for q in plan[pi:]]
                        break
                    fstate["suite"] = ss["hash"]
                done = fstate["tests"].setdefault(t["name"], [])
                for it in p.get("probes") or []:
                    rec, passed = self._item(t["name"] if len(tests) > 1 else None, it, by_test, diags, resp,
                                             tname=t["name"])
                    rec["probe_line"] = True
                    ran.append(rec)
                    if not passed:
                        ok, failed_at = False, (t["name"], it)
                        break
                    self.probe_hashes.add(it["hash"])
                if not ok:
                    self.failed = {"path": key, "test": t["name"], "line": failed_at[1]["line"]}
                    break
                if p.get("newdone") is not None:
                    fstate["tests"][t["name"]] = list(p["newdone"])
                    done = fstate["tests"][t["name"]]
                for it in t["items"][p["start"]:]:
                    rec, passed = self._item(t["name"] if len(tests) > 1 else None, it, by_test, diags, resp,
                                             tname=t["name"])
                    ran.append(rec)
                    if not passed:
                        ok, failed_at = False, (t["name"], it)
                        break
                    done.append(it["hash"])
                    if _is_probe(it):
                        self.probe_hashes.add(it["hash"])
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
        if ran and CAPTURE_MODE != "off":
            deferred = self._deferred_capture
            fresh = [c for c in self.run_captures if not c.get("unchanged")]
            if CAPTURE_MODE == "end":
                need = url1 is not None and not self.run_captures      # failure capture = the last step already
            else:
                need = deferred or (not fresh and (not ok or (url1 and url1 != url0)))
            if need:
                last_kw = (ran[-1].get("kw") if ran else None) or "end"
                try:      # after the LAST step: a settle here cannot hide a race between steps
                    self._capture(last_kw, "end of run", force=True, settle=True)
                except Exception as e:
                    resp["page_error"] = f"{type(e).__name__}: {e}"[:200]
            if self.run_captures and self.last_capture:
                page = {k: v for k, v in self.last_capture.items() if k not in ("controls_all", "text")}
                if getattr(self, "profile", "lean") == "rich":     # v3.1 rich: rows for the compact controls list
                    page["controls_pick"] = [x for x in (self.last_capture.get("controls_all") or [])
                                             if "   => " in x][:60]
                page["unchanged"] = bool(self.run_captures[-1].get("unchanged")) and not any(
                    not c.get("unchanged") for c in self.run_captures)
                resp["page"] = page
                resp["captures"] = self.run_captures
        if url1 and "page" not in resp:
            resp["url"] = url1
        resp["timeouts"] = {"switches": self.tmo.switches, "rechecks": self.rechecks,
                            "skipped_rechecks": self.tmo.skipped_rechecks, "changes": len(self.tmo.changes),
                            "origin_short": dict(self.tmo.origin_short), "no_shorten": len(self.tmo.no_shorten)}
        resp["capture_stats"] = {k: v - cs0.get(k, 0) for k, v in self.cap_stats.items()}
        complete = ok and all(len(fstate["tests"].get(t["name"], [])) == len(t["items"]) for t in tests)
        if mode == "reproduce":
            resp["reproduced"] = not ok
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
        self._cur_line = it["line"]
        rec, passed = self._run_one(node)
        return {**base, **rec}, passed


def serve(app: Application, opts: argparse.Namespace) -> int:
    sd = Path(opts.dir).absolute()
    proto.ensure_private_dir(sd)
    root = Path(opts.root).resolve()
    outdir = sd / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    token = config.get("RFH_TOKEN") or os.urandom(8).hex()
    os.environ[procs.TOKEN_ENV] = token          # children inherit it (cleanup by token)
    engine.install_pdeathsig()
    hooks = build_hooks(["desktop", "redact", "importhint", "hints", "guard"], settle=opts.settle,
                        followup=opts.settle_followup)
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
    p = argparse.ArgumentParser(prog="rf_harness.runtime.execd")
    p.add_argument("--dir", required=True)
    p.add_argument("--root", required=True)
    p.add_argument("--watch-pid", type=int, default=0)
    p.add_argument("--idle", type=float, default=1200.0)
    p.add_argument("--settle", type=float, default=1.5)
    p.add_argument("--settle-followup", type=float, default=config.get_float("RFH_GUARD_SETTLE"))
    opts = p.parse_args(argv)
    os.chdir(opts.root)
    app = new_application(Path(opts.root))
    return serve(app, opts)


if __name__ == "__main__":
    sys.exit(main())
