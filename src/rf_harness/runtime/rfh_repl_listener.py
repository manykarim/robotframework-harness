"""REPL-only short locator timeouts + one-time slow/missing re-check (listener API 3).

Loaded by the hook through ROBOT_OPTIONS="--listener <rf_harness/runtime>/rfh_repl_listener.py:<short>:<settle>" on agent-run
`robotcode repl|shell` commands that import Browser/SeleniumLibrary (adapted from the round-5 research prototype
timeouts/rfh_repl_timeouts.py).
* Active ONLY when the process is a robotcode REPL (`repl`/`shell` in argv): plain `robot`, `robotcode robot` and
  `robot-debug` runs are untouched; nothing is typed into the session, so `.save` never copies a timeout.
* Browser: element keywords run with <short> (default 2.5 s); navigation and Wait* keywords (and keywords nested in
  them, e.g. Get Text inside Wait For Condition) keep the suite's timeout. SeleniumLibrary: implicit wait 0, Selenium
  timeout <short> for element keywords, normal for Wait Until*.
* After a locator failure (v3, round-6 diagnosis): the Playwright call log is read FIRST -- "locator resolved to" means
  the element exists (covered / not visible / disabled / not stable is reported as such, never as slow); only an
  element that never resolved is re-checked: page stable >= <settle> (default 2 s) before the keyword -> "wrong locator"
  at once; else poll Get Element Count until the normal timeout after the last page change -> "appeared after N s"
  (absent -> present) or "missing" (+ iframe probe). Messages are printed as `[rfh] ...` lines into the REPL output.
* <short> defaults to 2.5 s; a learned per-origin value of the live hook session (<state file>, 3rd argument) raises it.
This file is loaded by path into the agent's robotcode process: it must not depend on rf_harness being importable there.
"""
import os
import re
import sys
import time

ROBOT_LISTENER_API_VERSION = 3

BROWSER_LOCATOR_TIMEOUT = re.compile(r"TimeoutError: locator\.(?P<op>\w+): Timeout (?P<ms>\d+)ms exceeded", re.S)
BROWSER_LOC = re.compile(r"waiting for (?:locator|selector)\(['\"](?P<loc>.+?)['\"]\)")
SELENIUM_LOCATOR_FAIL = re.compile(r"(?:Element|Button|Link|Image|List|Checkbox|Radio button|Text field|Text area) with "
                                   r"locator '(?P<l1>.+?)' not found|Element '(?P<l2>.+?)' (?:not visible after|did not "
                                   r"appear in)")
NAV = {"newpage", "goto", "goback", "goforward", "reload", "waitfornavigation", "waitforloadstate", "newbrowser",
       "newcontext", "newpersistentcontext", "closebrowser", "closecontext", "closepage", "takescreenshot",
       "setbrowsertimeout"}
PAGE_CHANGING = {"newpage", "goto", "goback", "goforward", "reload", "click", "clickwithoptions", "filltext",
                 "fillsecret", "typetext", "presskeys", "keyboardkey", "selectoptionsby", "checkcheckbox",
                 "uncheckcheckbox", "uploadfilebyselector", "newcontext", "switchpage", "handlefuturedialogs", "hover",
                 "tap", "openbrowser", "reloadpage", "clickelement", "clickbutton", "clicklink", "clickimage",
                 "submitform", "inputtext", "inputpassword", "selectfromlistbyvalue", "selectfromlistbylabel",
                 "selectfromlistbyindex", "selectcheckbox", "selectradiobutton", "switchwindow", "selectframe",
                 "unselectframe"}


def _nk(name):
    return re.sub(r"[\s_]", "", (name or "").split(".")[-1]).lower()


def _say(msg):
    sys.__stdout__.write(f"[rfh] {msg}\n")
    sys.__stdout__.flush()


def _classify(msg):
    """Playwright call log -> a verdict line for an element that EXISTS (no re-check), or None."""
    if "locator resolved to" not in msg and "strict mode violation" not in msg:
        return None
    m = re.search(r"(<[^\n]{0,160}?>(?:[^<\n]{0,60}</\w+>)?) intercepts pointer events", msg)
    if m:
        return (f"COVERED: {m.group(1)} intercepts pointer events -> click the input's label or the element on top "
                "(no wait / force needed)")
    for needle, verdict in (("element is not visible", "NOT_VISIBLE: the element exists but is hidden"),
                            ("element is not enabled", "DISABLED: the element exists but is disabled"),
                            ("element is not stable", "ANIMATING: the element kept moving"),
                            ("strict mode violation", "AMBIGUOUS: the selector matches several elements")):
        if needle in msg:
            return verdict
    return "PRESENT: the element exists (locator resolved); the action failed for another reason -- not timing"


def _force_repl():
    """RFH_FORCE_REPL=1 (registered in rf_harness.config; read directly when the package is not importable here)."""
    try:
        from rf_harness import config
    except ImportError:
        return os.environ.get("RFH_FORCE_REPL") == "1"
    return config.get("RFH_FORCE_REPL") == "1"


def _secs(v):
    from robot.utils import timestr_to_secs
    return timestr_to_secs(v)


class rfh_repl_listener:
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self, short="2.5s", settle="2s", state=None):
        argv = [a for a in sys.argv[1:8]]
        self.active = (any(a in ("repl", "shell") for a in argv) and not any(a in ("robot-debug", "run-debug", "robot",
                                                                                    "run") for a in argv)) \
            or _force_repl()
        self.short = _secs(short)
        self.settle = _secs(settle)
        if state:                     # learned per-origin timeouts of the live hook session (max over origins)
            try:
                import json
                with open(state) as f:
                    learned = json.load(f).get("origin_short") or {}
                if learned:
                    self.short = max(self.short, max(float(v) for v in learned.values()))
            except (OSError, ValueError):
                pass
        self.normal = {}
        self.stack = []
        self.last_change = None
        self.cur = None

    # ---- shorten on import
    def library_import(self, library, importer):
        if not self.active:
            return
        try:
            inst = library.instance
        except Exception:
            return
        if library.name == "Browser":
            try:
                self.normal["Browser"] = float(inst.timeout) / 1000.0
            except Exception:
                self.normal["Browser"] = 10.0
            self._browser(self.short)
            _say(f"REPL only: Browser element timeout {self.normal['Browser']:g}s -> {self.short:g}s (navigation and "
                 "Wait* keep the normal timeout; the test file and plain robot runs are not affected). Locator misses "
                 "are re-checked: slow vs missing.")
        elif library.name == "SeleniumLibrary":
            self.normal["SeleniumLibrary"] = float(getattr(inst, "timeout", 5) or 5)
            try:
                inst.implicit_wait = 0.0
            except Exception:
                pass
            _say(f"REPL only: Selenium implicit wait -> 0 s (Wait Until* keep {self.normal['SeleniumLibrary']:g}s).")

    def _browser(self, secs):
        try:
            from Browser.utils.data_types import Scope
            from robot.libraries.BuiltIn import BuiltIn
            inst = BuiltIn().get_library_instance("Browser")
            if abs(float(inst.timeout) - secs * 1000) < 1:
                return
            inst.scope_stack["timeout"].set(secs * 1000, Scope.Global)
        except Exception:
            pass

    def start_keyword(self, data, result):
        if not self.active:
            return
        owner = getattr(result, "owner", None) or getattr(result, "libname", None)
        n = _nk(getattr(result, "name", ""))
        normal = owner == "Browser" and (n in NAV or n.startswith("waitfor"))
        nested = any(self.stack)
        self.stack.append(normal)
        if owner == "Browser" and "Browser" in self.normal and not nested:
            self._browser(self.normal["Browser"] if normal else min(self.short, self.normal["Browser"]))
        if not nested and owner in ("Browser", "SeleniumLibrary"):
            self.cur = (time.time(), getattr(result, "name", ""))

    def end_keyword(self, data, result):
        if not self.active:
            return
        if self.stack:
            self.stack.pop()
        owner = getattr(result, "owner", None) or getattr(result, "libname", None)
        kw = getattr(result, "name", "")
        if result.status == "PASS" and _nk(kw) in PAGE_CHANGING:
            self.last_change = (time.time(), kw)
            return
        if result.status != "FAIL" or owner not in ("Browser", "SeleniumLibrary") or self.stack:
            return
        msg = result.message or ""
        if owner == "Browser":
            cls = _classify(msg)
            if cls:
                _say(cls)
                return
        sel = None
        if owner == "Browser" and BROWSER_LOCATOR_TIMEOUT.search(msg):
            m = BROWSER_LOC.search(msg)
            sel = m.group("loc") if m else None
        elif owner == "SeleniumLibrary":
            m = SELENIUM_LOCATOR_FAIL.search(msg)
            sel = (m.group("l1") or m.group("l2")) if m else None
        if not sel and result.args:
            try:
                from robot.libraries.BuiltIn import BuiltIn
                sel = BuiltIn().replace_variables(str(result.args[0]))
            except Exception:
                sel = str(result.args[0])
        if sel and (owner == "SeleniumLibrary" or BROWSER_LOCATOR_TIMEOUT.search(msg)):
            try:
                self._recheck(owner, kw, sel)
            except Exception as e:
                _say(f"re-check failed: {str(e).splitlines()[0][:120]}")

    def _count(self, owner, inst, sel):
        if owner == "Browser":
            return int(inst.get_element_count(sel) or 0)
        return len(inst.find_elements(sel))

    def _frame_hint(self, owner, inst, sel):
        if owner != "Browser":
            try:
                n = len(inst.find_elements("css:iframe"))
            except Exception:
                return ""
            return f" The page has {n} iframe(s): Select Frame first." if n else ""
        try:
            n = int(inst.get_element_count("css=iframe") or 0)
            for i in range(min(n, 5)):
                fs = f"css=iframe >> nth={i} >>> {sel}"
                if int(inst.get_element_count(fs) or 0):
                    return f" Found inside iframe #{i}: use `{fs}`."
        except Exception:
            pass
        return ""

    def _recheck(self, owner, kw, sel):
        from robot.libraries.BuiltIn import BuiltIn
        inst = BuiltIn().get_library_instance(owner)
        start = self.cur[0] if self.cur else time.time()
        since = None if self.last_change is None else start - self.last_change[0]
        normal = self.normal.get(owner, 10.0)
        if self._count(owner, inst, sel):
            _say(f"SLOW: '{sel}' was absent for the REPL timeout ({self.short:g}s) and exists now. In the test, wait "
                 f"for it before `{kw}`: Wait For Elements State    {sel}    visible    timeout=10s")
            return
        if since is not None and since < self.settle:
            found = None
            while time.time() - self.last_change[0] < normal:
                time.sleep(0.25)
                if self._count(owner, inst, sel):
                    found = time.time() - self.last_change[0]
                    break
            if found is not None:
                to = max(10, int(found * 2) + 1)
                wait = (f"Wait For Elements State    {sel}    visible    timeout={to}s" if owner == "Browser"
                        else f"Wait Until Element Is Visible    {sel}    timeout={to}s")
                _say(f"SLOW: '{sel}' appeared {found:.1f}s after `{self.last_change[1]}` (REPL timeout {self.short:g}s). "
                     f"The locator is OK; in the test put `{wait}` before `{kw}`.")
                return
            _say(f"MISSING: '{sel}' still not on the page {time.time() - self.last_change[0]:.1f}s after "
                 f"`{self.last_change[1]}` -> wrong locator, iframe or hidden element.{self._frame_hint(owner, inst, sel)}")
            return
        _say(f"MISSING: '{sel}' not found and the page had been stable for "
             f"{'?' if since is None else f'{since:.0f}'}s -> wrong locator (not a timing issue)."
             f"{self._frame_hint(owner, inst, sel)}")
