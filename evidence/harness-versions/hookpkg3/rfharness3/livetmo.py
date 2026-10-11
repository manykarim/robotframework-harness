"""ADAPTIVE short element timeouts for the LIVE session only (never written to any file, never used by a plain run).

v3 (round-5 A/B + round-6 diagnosis: 110/111 v2 SLOW verdicts were clicks on PRESENT but covered elements; genuinely late
elements were 1/243):
* element keywords run with RFH3_SHORT_TIMEOUT (default 2.5 s) instead of the suite's timeout (import arg /
  `Set Browser Timeout`, default 10 s); navigation + explicit wait keywords (and keywords nested in them) keep the normal
  timeout -- always;
* a failure is classified from the Playwright call log first (execd + pwlog): covered / hidden / disabled / animating /
  present elements are never re-checked; only an ABSENT element (count 0) is:
  - the page is stable -- no DOM mutation for RFH3_STABLE_S (default 2 s), no fetch/XHR/long setTimeout started since
    the observer was installed still pending, document older than RFH3_FRESH_DOC_S (6 s: work scheduled by the page's
    load scripts is invisible) -> MISSING at once (wrong selector / iframe), no waiting;
  - else poll the count until the normal timeout after the keyword start, stopping as soon as the page has been quiet
    for RFH3_STABLE_S -> SLOW (absent -> present, latency from the keyword start) or MISSING;
* learning from a real absent -> present appearance: that page (origin + URL path) is never shortened again; its origin
  gets short = min(normal, max(base, RFH3_ADAPT_FACTOR x latency));
* SeleniumLibrary: implicit wait min(normal, short) for element keywords (explicit `Wait Until ...` keep the normal one).
Learned values are written to <exec state dir>/timeouts.json (read by the REPL listener; for the A/B metrics).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from robot.libraries.BuiltIn import BuiltIn


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


BASE_S = _f("RFH3_SHORT_TIMEOUT", 2.5)
SHORT_BROWSER_S = BASE_S                     # v2 name (execd / tests import it)
SHORT_SELENIUM_S = _f("RFH3_SHORT_TIMEOUT_SELENIUM", BASE_S)
STABLE_S = _f("RFH3_STABLE_S", 2.0)
ADAPT_FACTOR = _f("RFH3_ADAPT_FACTOR", 1.5)
ENABLED = os.environ.get("RFH3_SHORT_TIMEOUTS", "1") != "0"


def nk(name: str) -> str:
    return re.sub(r"[\s_]", "", (name or "").split(".")[-1]).lower()


# Browser keywords that keep the NORMAL timeout in the live session (navigation, explicit waits, setup)
BROWSER_NORMAL = {nk(k) for k in (
    "New Browser", "New Context", "New Page", "New Persistent Context", "Connect To Browser", "Go To", "Go Back",
    "Go Forward", "Reload", "Wait For Elements State", "Wait For Condition", "Wait For Function",
    "Wait For Navigation", "Wait For Load State", "Wait For Response", "Wait For Request", "Wait Until Network Is Idle",
    "Wait For All Promises", "Wait For Download", "Wait For Alert", "Set Browser Timeout", "Close Browser",
    "Close Context", "Close Page", "Switch Page", "Switch Context", "Switch Browser", "Take Screenshot",
    "Handle Future Dialogs", "Promise To", "Wait For", "Set Retry Assertions For")}
TIMEOUT_MSG = re.compile(r"Timeout \d+ms exceeded|TimeoutError|timed? ?out|did not (?:appear|become|disappear)|"
                         r"not (?:visible|found) after|waiting for (?:locator|selector)", re.I)
SEL_NOT_FOUND = re.compile(r"Element with locator '([^']+)' not found|Element locator '([^']+)' did not match", re.I)

# one evaluate per call: installs (once per document) a MutationObserver on the document and its open shadow roots
# plus counters of async work started afterwards (in-flight fetch / XHR, pending setTimeout >= 200 ms), then reports
# {href, quiet: ms since the last DOM mutation (-1 = just installed), n/a: structural/attribute mutation counters,
#  pend: pending async work, age: document age (ms), inst: document age at install (ms), fresh}.
TOUCH_JS = r"""() => {
  const w = window;
  if (!w.__rfh3) {
    const s = {t: performance.now(), n: 0, a: 0, p: 0, tm: new Set(), i: performance.now()};
    w.__rfh3 = s;
    try {
      const cfg = {subtree: true, childList: true, characterData: true, attributes: true,
                   attributeFilter: ['class', 'style', 'hidden', 'disabled', 'aria-hidden', 'aria-expanded', 'open']};
      const obs = new MutationObserver((ms) => {
        let structural = false;
        for (const m of ms) {
          if (m.type !== 'attributes') structural = true;
          if (m.addedNodes) m.addedNodes.forEach((nd) => { if (nd.shadowRoot) { try { obs.observe(nd.shadowRoot, cfg); } catch (e) {} } });
        }
        if (structural) s.n++; else s.a++;
        s.t = performance.now();
      });
      obs.observe(document, cfg);
      document.querySelectorAll('*').forEach((e) => { if (e.shadowRoot) { try { obs.observe(e.shadowRoot, cfg); } catch (x) {} } });
    } catch (e) {}
    try {
      const of = w.fetch;
      if (of) w.fetch = function () { s.p++; const pr = of.apply(w, arguments);
        const done = () => { s.p = Math.max(0, s.p - 1); }; pr.then(done, done); return pr; };
      const osend = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.send = function () { s.p++;
        this.addEventListener('loadend', () => { s.p = Math.max(0, s.p - 1); }, {once: true});
        return osend.apply(this, arguments); };
      const ost = w.setTimeout, oct = w.clearTimeout;
      w.setTimeout = function (fn, d) {
        if (typeof fn !== 'function' || !(d >= 200 && d <= 30000)) return ost.apply(w, arguments);
        const rest = Array.prototype.slice.call(arguments, 2);
        let id = null;
        id = ost.call(w, function () { s.tm.delete(id); return fn.apply(this, rest); }, d);
        s.tm.add(id);
        return id;
      };
      w.clearTimeout = function (id) { s.tm.delete(id); return oct.apply(w, arguments); };
    } catch (e) {}
    return {href: location.href, quiet: -1, n: 0, a: 0, pend: 0, age: Math.round(performance.now()),
            inst: Math.round(s.i), fresh: true};
  }
  const s = w.__rfh3;
  return {href: location.href, quiet: Math.round(performance.now() - s.t), n: s.n, a: s.a, pend: s.p + s.tm.size,
          age: Math.round(performance.now()), inst: Math.round(s.i), fresh: false};
}"""
FRESH_DOC_S = _f("RFH3_FRESH_DOC_S", 6.0)


def is_stable(t: Optional[Dict[str, Any]], stable_s: float = None) -> bool:
    """the page is quiet: no DOM mutation for STABLE_S, no pending fetch/XHR/long timer started since the observer was
    installed, and the document is at least FRESH_DOC_S old (the observer always comes after the page's own load
    scripts -- Browser 19 has no init scripts -- so timers/requests scheduled at load are invisible)."""
    if not t:
        return False
    q = t.get("quiet")
    if not isinstance(q, (int, float)) or q < 0 or q < (STABLE_S if stable_s is None else stable_s) * 1000:
        return False
    if t.get("pend"):
        return False
    if (t.get("age") or 0) < FRESH_DOC_S * 1000:     # work scheduled by the page's own load scripts is invisible
        return False
    return True


def _lib(name: str) -> Any:
    try:
        return BuiltIn().get_library_instance(name)
    except Exception:
        return None


def page_keys(url: Optional[str]) -> Tuple[str, str]:
    """-> (origin, origin + path) of a URL (query/fragment dropped; file:// -> the file path)."""
    if not url:
        return "?", "?"
    try:
        u = urlsplit(url)
    except ValueError:
        return url, url
    origin = f"{u.scheme}://{u.netloc}"
    return origin, origin + (u.path or "/")


def touch(owner: str = "Browser") -> Optional[Dict[str, Any]]:
    """{href, quiet (ms, -1 = unknown), n, a, fresh} of the open page; None without a page / library."""
    lib = _lib(owner)
    if lib is None:
        return None
    try:
        if owner == "Browser":
            r = lib.evaluate_javascript(None, TOUCH_JS)
        else:
            r = lib.execute_javascript("return (" + TOUCH_JS + ")();")
    except Exception:
        return None
    return r if isinstance(r, dict) else None


class LiveTimeouts:
    def __init__(self, state_file: Optional[Path] = None) -> None:
        self.normal: Dict[int, float] = {}       # id(lib) -> normal Browser timeout (ms) / Selenium implicit wait (s)
        self.sel_timeout: Dict[int, float] = {}  # id(selenium lib) -> normal selenium timeout (s)
        self.applied: Dict[int, float] = {}
        self.switches = 0
        self.enabled = ENABLED
        self.state_file = state_file
        self.cur_url: Optional[str] = None       # page of the current top-level step (set by the live session)
        self.url_stale = False
        self.no_shorten: Dict[str, float] = {}   # origin+path -> observed latency (s): never shortened again
        self.origin_short: Dict[str, float] = {}  # origin -> learned short timeout (s)
        self.changes: List[Dict[str, Any]] = []  # adaptive timeout changes (for the hook log / A/B metrics)
        self.skipped_rechecks = 0                # immediate MISSING verdicts (page quiet >= STABLE_S)

    # ------------------------------------------------------------------ policy
    def short_for(self, owner: str, url: Optional[str] = None, normal_s: Optional[float] = None) -> float:
        """the live element timeout (s) for a page: normal on pages with a SLOW verdict, else the learned origin value
        (or the base), never above the library's normal timeout."""
        normal = self.normal_s(owner) if normal_s is None else normal_s
        url = url if url is not None else self.cur_url
        origin, page = page_keys(url)
        if page in self.no_shorten:
            return normal
        base = BASE_S if owner == "Browser" else SHORT_SELENIUM_S
        return min(normal, max(base, self.origin_short.get(origin, base)))

    def learn(self, owner: str, url: Optional[str], appeared_after_s: float) -> Optional[Dict[str, Any]]:
        """a SLOW verdict on `url`: that page keeps the normal timeout, its origin gets factor x latency."""
        origin, page = page_keys(url)
        normal = self.normal_s(owner)
        before = self.short_for(owner, url, normal)
        self.no_shorten[page] = max(self.no_shorten.get(page, 0.0), round(appeared_after_s, 1))
        want = min(normal, max(BASE_S, ADAPT_FACTOR * appeared_after_s))
        old_origin = self.origin_short.get(origin, BASE_S)
        if want > old_origin:
            self.origin_short[origin] = round(want, 1)
        ch = {"page": page[:160], "origin": origin[:80], "appeared_after_s": round(appeared_after_s, 1),
              "page_s": round(before, 1), "page_s_new": round(normal, 1),
              "origin_s": round(old_origin, 1), "origin_s_new": round(self.origin_short.get(origin, old_origin), 1)}
        self.changes.append(ch)
        self._save()
        return ch

    def _save(self) -> None:
        if not self.state_file:
            return
        try:
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({"base_s": BASE_S, "stable_s": STABLE_S, "origin_short": self.origin_short,
                                       "no_shorten": self.no_shorten, "changes": self.changes[-50:]}, indent=1))
            os.replace(tmp, self.state_file)
        except OSError:
            pass

    # ------------------------------------------------------------------ Browser
    def _browser_normal(self, lib: Any) -> float:
        k = id(lib)
        if k not in self.normal:
            try:
                self.normal[k] = float(lib.timeout)
            except Exception:
                self.normal[k] = 10000.0
        return self.normal[k]

    def _set_browser(self, lib: Any, ms: float) -> None:
        try:
            cur = float(lib.timeout)
        except Exception:
            return
        if abs(cur - ms) < 1:
            return
        try:
            from Browser.utils.data_types import Scope
            lib.scope_stack["timeout"].set(ms, Scope.Global)
            self.switches += 1
        except Exception:
            pass

    def is_normal(self, owner: Optional[str], name: str) -> bool:
        n = nk(name)
        if owner == "Browser":
            return n in BROWSER_NORMAL or n.startswith("waitfor")
        return owner == "SeleniumLibrary" and n.startswith("wait")

    def _url_now(self, owner: str, lib: Any) -> Optional[str]:
        if self.url_stale or self.cur_url is None:
            try:
                self.cur_url = str(lib.get_url() if owner == "Browser" else lib.get_location())
            except Exception:
                return self.cur_url
            self.url_stale = False
        return self.cur_url

    def before(self, owner: Optional[str], name: str, nested_normal: bool = False) -> None:
        """called at start_keyword (every depth) of the live session. nested_normal: an enclosing keyword keeps the
        normal timeout (Wait For Condition runs Get Text inside: that inner getter must not be shortened)."""
        if not self.enabled or owner not in ("Browser", "SeleniumLibrary") or nested_normal:
            return
        n = nk(name)
        if owner == "Browser":
            lib = _lib("Browser")
            if lib is None:
                return
            normal = self._browser_normal(lib)
            if n in BROWSER_NORMAL or n.startswith("waitfor"):
                want = normal
            else:
                want = min(normal, self.short_for("Browser", self._url_now("Browser", lib), normal / 1000.0) * 1000)
            self._set_browser(lib, want)
            self.applied[id(lib)] = want
        else:
            lib = _lib("SeleniumLibrary")
            if lib is None:
                return
            k = id(lib)
            if k not in self.normal:
                self.normal[k] = float(getattr(lib, "implicit_wait", 0) or 0)
                self.sel_timeout[k] = float(getattr(lib, "timeout", 5) or 5)
            if n.startswith("wait"):
                want = self.normal[k]
            else:
                want = min(self.normal[k], self.short_for("SeleniumLibrary", self._url_now("SeleniumLibrary", lib),
                                                          self.normal_s("SeleniumLibrary")))
            if abs(float(getattr(lib, "implicit_wait", 0) or 0) - want) > 0.01:
                try:
                    lib.implicit_wait = want
                    for drv in lib._drivers.active_drivers:
                        drv.implicitly_wait(want)
                    self.switches += 1
                except Exception:
                    pass

    def after(self, owner: Optional[str], name: str, passed: bool) -> None:
        """a suite `Set Browser Timeout` / `Set Selenium Implicit Wait` defines the new NORMAL value."""
        if not passed:
            return
        n = nk(name)
        if owner == "Browser" and n == "setbrowsertimeout":
            lib = _lib("Browser")
            if lib is not None:
                try:
                    self.normal[id(lib)] = float(lib.timeout)
                except Exception:
                    pass
        elif owner == "SeleniumLibrary" and n in ("setseleniumimplicitwait", "setseleniumtimeout"):
            lib = _lib("SeleniumLibrary")
            if lib is not None:
                self.normal[id(lib)] = float(getattr(lib, "implicit_wait", 0) or 0)
                self.sel_timeout[id(lib)] = float(getattr(lib, "timeout", 5) or 5)

    def normal_s(self, owner: str) -> float:
        lib = _lib(owner)
        if lib is None:
            return 10.0
        if owner == "Browser":
            return self._browser_normal(lib) / 1000.0
        k = id(lib)
        return max(self.normal.get(k, 0.0), self.sel_timeout.get(k, float(getattr(lib, "timeout", 5) or 5)))

    def short_s(self, owner: str) -> float:
        return self.short_for(owner)

    # ------------------------------------------------------------------ recheck
    def recheck(self, owner: str, sel: str, waited_s: float, need_visible: bool,
                since_change: Optional[float] = None, touch_info: Optional[Dict[str, Any]] = None,
                started: Optional[float] = None) -> Dict[str, Any]:
        """an ABSENT element after the short timeout: stable page (is_stable) and no iframe selector -> MISSING at once;
        else poll until the element shows up (SLOW, latency from the keyword start) or the normal timeout after the
        keyword start has passed / the page became stable (MISSING)."""
        normal = self.normal_s(owner)
        short = self.short_for(owner)
        base = {"selector": sel, "normal_s": round(normal, 1), "short_s": round(short, 1), "waited_s": round(waited_s, 1)}
        frame_sel = ">>>" in sel
        if not frame_sel and is_stable(touch_info):
            self.skipped_rechecks += 1
            return {**base, "verdict": "missing", "settled_s": round((touch_info or {}).get("quiet", 0) / 1000.0, 1),
                    "skipped": True}
        lib = _lib(owner)
        t_start = started if started is not None else time.monotonic() - waited_s
        deadline = t_start + normal
        t0 = time.monotonic()
        seen = False
        last_touch = 0.0
        quiet_end = None
        while time.monotonic() < deadline:
            try:
                if owner == "Browser":
                    ok = int(lib.get_element_count(sel) or 0) > 0
                    if ok and need_visible:
                        ok = "visible" in [str(x).lower() for x in (lib.get_element_states(sel) or [])]
                else:
                    els = lib.find_elements(sel)
                    ok = bool(els)
                    if ok and need_visible:
                        ok = any(e.is_displayed() for e in els)
            except Exception:
                ok = False
            if ok:
                seen = True
                break
            if not frame_sel and time.monotonic() - last_touch > 0.5:
                last_touch = time.monotonic()
                t = touch(owner)
                if is_stable(t):
                    quiet_end = (t or {}).get("quiet", 0) / 1000.0
                    break
            time.sleep(0.15)
        took = time.monotonic() - t0
        res = {**base, "waited_s": round(waited_s + took, 1), "recheck_s": round(took, 1)}
        if seen:
            res.update(verdict="slow", appeared_after_s=round(time.monotonic() - t_start, 1))
        else:
            res.update(verdict="missing")
            if quiet_end is not None:
                res["settled_s"] = round(quiet_end, 1)
        return res
