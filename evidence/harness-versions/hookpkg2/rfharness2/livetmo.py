"""Short element timeouts for the LIVE session only (never written to any file, never used by a plain robot run).

Browser: element actions/getters run with RFH2_SHORT_TIMEOUT (default 2.5 s) instead of the suite's timeout (import
arg / `Set Browser Timeout`, default 10 s); navigation + explicit wait keywords keep the normal timeout. SeleniumLibrary:
the implicit wait is 0 for element keywords (explicit `Wait Until ...` keywords keep the normal timeout).
After a not-found / not-visible / timeout failure, recheck() waits ONCE up to the normal timeout: the element shows
up -> "slow" (the line is re-run; advice: add an explicit wait), never -> "missing".
The switch happens per keyword (also nested inside user keywords) from start_keyword in the live session.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, Optional

from robot.libraries.BuiltIn import BuiltIn


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


SHORT_BROWSER_S = _f("RFH2_SHORT_TIMEOUT", 2.5)
SHORT_SELENIUM_S = _f("RFH2_SHORT_TIMEOUT_SELENIUM", 2.0)
ENABLED = os.environ.get("RFH2_SHORT_TIMEOUTS", "1") != "0"


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


def _lib(name: str) -> Any:
    try:
        return BuiltIn().get_library_instance(name)
    except Exception:
        return None


class LiveTimeouts:
    def __init__(self) -> None:
        self.normal: Dict[int, float] = {}       # id(lib) -> normal Browser timeout (ms) / Selenium implicit wait (s)
        self.sel_timeout: Dict[int, float] = {}  # id(selenium lib) -> normal selenium timeout (s)
        self.applied: Dict[int, float] = {}
        self.switches = 0
        self.enabled = ENABLED

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
            want = normal if n in BROWSER_NORMAL or n.startswith("waitfor") else min(normal, SHORT_BROWSER_S * 1000)
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
            want = self.normal[k] if n.startswith("waituntil") or n.startswith("wait") else 0.0
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
        return SHORT_BROWSER_S if owner == "Browser" else SHORT_SELENIUM_S

    # ------------------------------------------------------------------ recheck
    def recheck(self, owner: str, sel: str, waited_s: float, need_visible: bool,
                since_change: Optional[float] = None) -> Dict[str, Any]:
        """wait ONCE for `sel` until the normal timeout has passed since the last page change (round-5 policy: a page
        that has been stable for longer than the normal timeout gets the verdict at once -- an element that did not
        appear within that time would fail the plain run too)."""
        normal = self.normal_s(owner)
        if since_change is None:
            budget = max(0.5, normal - waited_s)
        else:
            budget = normal - since_change
        lib = _lib(owner)
        t0 = time.monotonic()
        if budget <= 0.2:
            res = {"selector": sel, "normal_s": round(normal, 1), "short_s": self.short_s(owner),
                   "waited_s": round(waited_s, 1), "verdict": "missing", "settled_s": round(since_change or 0, 1)}
            return res
        seen = False
        while time.monotonic() - t0 < budget:
            try:
                if owner == "Browser":
                    n = int(lib.get_element_count(sel) or 0)
                    ok = n > 0
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
            time.sleep(0.15)
        took = time.monotonic() - t0
        res = {"selector": sel, "normal_s": round(normal, 1), "short_s": self.short_s(owner),
               "waited_s": round(waited_s + took, 1)}
        if seen:
            res.update(verdict="slow", appeared_after_s=round(waited_s + took, 1))
        else:
            res.update(verdict="missing")
        return res
