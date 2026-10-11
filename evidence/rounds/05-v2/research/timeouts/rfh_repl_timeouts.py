"""Prototype (round 5): REPL-only short locator timeouts + one-time slow re-check.

Load via ROBOT_OPTIONS="--listener /abs/rfh_repl_timeouts.py[:2s:10s]" (args: short, settle).
* Active only when the process is `robotcode repl` (sys.argv) -> plain `robot` runs and
  `robot-debug` are untouched, nothing is written to any .robot/.resource file.
* On Browser / SeleniumLibrary import: Browser timeout -> short (Global scope),
  Selenium timeout -> short, Selenium implicit wait capped at 0.
* After a locator failure (regexes below):
    - page settled (last page-changing keyword ended >= settle s before the failing
      keyword started)  -> "really missing", no extra wait
    - otherwise poll element count until settle budget since the page change is used up
      -> "appeared after X s -> add an explicit wait" | "still missing after Y s".
Results are printed to the REPL output and appended to $RFH_RECHECK_LOG (JSONL).
"""
import json, os, re, sys, time
from datetime import timedelta

ROBOT_LISTENER_API_VERSION = 3

BROWSER_LOCATOR_TIMEOUT = re.compile(
    r"TimeoutError: locator\.(?P<op>\w+): Timeout (?P<ms>\d+)ms exceeded\.\s*\nCall log:\s*\n\s*- waiting for (?P<loc>.+?)(?: to be (?P<state>\w+))?\s*$",
    re.S)
SELENIUM_LOCATOR_FAIL = re.compile(
    r"^(?:Element with locator '(?P<l1>.+)' not found\."
    r"|Element '(?P<l2>.+)' (?:not visible after|did not appear in|is not enabled after|not visible after) (?P<t>[\d.]+ \w+)\."
    r"|Page should have contained element '(?P<l3>.+)' but did not\.)$", re.S)
PAGE_CHANGING = {
    "Browser": {"New Page", "Go To", "Go Back", "Go Forward", "Reload", "Click", "Click With Options",
                "Fill Text", "Fill Secret", "Type Text", "Press Keys", "Keyboard Key", "Select Options By",
                "Check Checkbox", "Uncheck Checkbox", "Upload File By Selector", "New Context", "Switch Page",
                "Handle Future Dialogs", "Hover", "Tap"},
    "SeleniumLibrary": {"Open Browser", "Go To", "Go Back", "Reload Page", "Click Element", "Click Button",
                        "Click Link", "Click Image", "Submit Form", "Input Text", "Input Password",
                        "Press Keys", "Select From List By Value", "Select From List By Label",
                        "Select From List By Index", "Select Checkbox", "Select Radio Button",
                        "Switch Window", "Select Frame", "Unselect Frame"},
}


def _say(msg):
    sys.__stdout__.write(f"[rfh] {msg}\n")
    sys.__stdout__.flush()


class rfh_repl_timeouts:
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self, short="2s", settle="10s"):
        from robot.utils import timestr_to_secs
        self.active = len(sys.argv) > 1 and sys.argv[1] == "repl" or os.environ.get("RFH_FORCE_REPL") == "1"
        self.short = timestr_to_secs(short)
        self.settle = timestr_to_secs(settle)
        self.last_change = None  # (end_ts, keyword)
        self.orig = {}
        self.log = os.environ.get("RFH_RECHECK_LOG")

    # ---- shorten on import -------------------------------------------------
    def library_import(self, library, importer):
        if not self.active:
            return
        name = library.name
        try:
            inst = library.instance
        except Exception:
            return
        if name == "Browser":
            from Browser.utils.data_types import Scope
            old = inst.keywords["set_browser_timeout"](timedelta(seconds=self.short), Scope.Global)
            self.orig["Browser"] = old
            _say(f"REPL only: Browser timeout {old} -> {self.short:g}s (suite runs keep {old}); "
                 f"locator misses are re-checked automatically. Don't copy timeout changes into the test.")
        elif name == "SeleniumLibrary":
            old_t = inst.keywords["set_selenium_timeout"](timedelta(seconds=self.short))
            old_i = inst.keywords["set_selenium_implicit_wait"](timedelta(seconds=0))
            self.orig["SeleniumLibrary"] = (old_t, old_i)
            _say(f"REPL only: Selenium timeout {old_t} -> {self.short:g}s, implicit wait {old_i} -> 0s; "
                 f"misses are re-checked automatically. Don't copy timeout changes into the test.")

    # ---- navigation keeps the suite timeout ---------------------------------
    NAV = {"New Page", "Go To", "Go Back", "Go Forward", "Reload", "Wait For Navigation", "Wait For Load State"}

    def _set_browser_timeout(self, secs):
        from robot.libraries.BuiltIn import BuiltIn
        from Browser.utils.data_types import Scope
        inst = BuiltIn().get_library_instance("Browser")
        inst.keywords["set_browser_timeout"](timedelta(seconds=secs), Scope.Global)

    def start_keyword(self, data, result):
        if not self.active or "Browser" not in self.orig:
            return
        owner = getattr(result, "owner", None) or getattr(result, "libname", None)
        if owner == "Browser" and result.name in self.NAV:
            from robot.utils import timestr_to_secs
            self._set_browser_timeout(timestr_to_secs(self.orig["Browser"]))
            self._nav = True

    # ---- track page changes / re-check failures -----------------------------
    def end_keyword(self, data, result):
        if not self.active:
            return
        owner = getattr(result, "owner", None) or getattr(result, "libname", None)
        kw = getattr(result, "name", "")
        if getattr(self, "_nav", False) and owner == "Browser" and kw in self.NAV:
            self._nav = False
            self._set_browser_timeout(self.short)
        if result.status == "PASS" and kw in PAGE_CHANGING.get(owner, ()):  # only top-level-ish is fine
            self.last_change = (time.time(), kw)
            return
        if result.status != "FAIL" or owner not in ("Browser", "SeleniumLibrary"):
            return
        msg = result.message or ""
        if owner == "Browser":
            m = BROWSER_LOCATOR_TIMEOUT.search(msg)
            if not m or not result.args:
                return
        else:
            m = SELENIUM_LOCATOR_FAIL.search(msg)
            if not m or not result.args:
                return
        from robot.libraries.BuiltIn import BuiltIn
        try:
            selector = BuiltIn().replace_variables(str(result.args[0]))
        except Exception:
            selector = str(result.args[0])
        self._recheck(owner, kw, selector, result)

    def _count(self, owner, inst, selector):
        if owner == "Browser":
            return inst.keywords["get_element_count"](selector)
        return len(inst.find_elements(selector))

    def _frame_hint(self, owner, inst, selector):
        """Cheap probe: does the selector match inside an iframe? (Browser: `iframe >>> sel`)."""
        if owner != "Browser":
            try:
                n = len(inst.find_elements("css:iframe"))
            except Exception:
                return ""
            return f" The page has {n} iframe(s): try `Select Frame` first." if n else ""
        try:
            n = inst.keywords["get_element_count"]("css=iframe")
            for i in range(min(n, 5)):
                fs = f"css=iframe >> nth={i} >>> {selector}"
                if inst.keywords["get_element_count"](fs):
                    return f" Found inside iframe #{i}: use `{fs}`."
            return f" (not inside the page's {n} iframe(s) either)" if n else ""
        except Exception as e:
            return f" (frame probe failed: {str(e).splitlines()[0][:80]})"

    def _visible(self, owner, inst, selector):
        try:
            if owner == "Browser":
                states = inst.keywords["get_element_states"](selector)
                return "visible" in states, ",".join(states)
            els = inst.find_elements(selector)
            return (bool(els) and els[0].is_displayed()), ""
        except Exception as e:  # strict mode etc.
            return None, str(e).splitlines()[0][:120]

    def _recheck(self, owner, kw, selector, result):
        from robot.libraries.BuiltIn import BuiltIn
        inst = BuiltIn().get_library_instance(owner)
        t_fail_start = result.start_time.timestamp() if result.start_time else time.time()
        now = time.time()
        rec = {"owner": owner, "keyword": kw, "selector": selector, "failed_after": round(result.elapsed_time.total_seconds(), 2)}
        if self.last_change is None:
            since = None
        else:
            since = t_fail_start - self.last_change[0]
        rec["settled_for_at_start"] = None if since is None else round(since, 2)
        n0 = self._count(owner, inst, selector)
        if n0:
            vis, states = self._visible(owner, inst, selector)
            rec.update(verdict="present_now", count=n0, visible=vis, states=states)
            _say(f"'{selector}' exists now ({n0} match, states: {states or vis}) — it was not ready within "
                 f"{rec['failed_after']}s. In the test, wait for it explicitly before `{kw}`.")
        elif since is not None and since < self.settle:
            budget = self.settle - (now - self.last_change[0])
            t0 = time.time(); found = None
            while time.time() - t0 < max(budget, 0):
                time.sleep(0.25)
                if self._count(owner, inst, selector):
                    found = time.time() - self.last_change[0]
                    break
            rec["recheck_waited"] = round(time.time() - t0, 2)
            if found is not None:
                rec.update(verdict="slow", appeared_after_change=round(found, 2))
                to = max(10, int(found * 2) + 1)
                wait = (f"Wait For Elements State    {selector}    visible    timeout={to}s" if owner == "Browser"
                        else f"Wait Until Element Is Visible    {selector}    timeout={to}s")
                fix = (f"give `{kw}` `timeout={to}s`" if kw.startswith("Wait")
                       else f"put `{wait}` before `{kw}`")
                _say(f"'{selector}' appeared {found:.1f}s after `{self.last_change[1]}` (REPL timeout "
                     f"{self.short:g}s). Locator is OK; the element is slow. In the test {fix}.")
            else:
                rec.update(verdict="missing", waited_since_change=round(time.time() - self.last_change[0], 2))
                hint = self._frame_hint(owner, inst, selector); rec["frame_hint"] = hint
                _say(f"'{selector}' still not on the page {time.time()-self.last_change[0]:.1f}s after "
                     f"`{self.last_change[1]}` → most likely a wrong locator (an element slower than {self.settle:g}s would look the same).{hint} "
                     f"Check the .rf/state page capture before retrying.")
        else:
            rec.update(verdict="missing_settled")
            hint = self._frame_hint(owner, inst, selector); rec["frame_hint"] = hint
            _say(f"'{selector}' not found; page had been stable for "
                 f"{'unknown' if since is None else f'{since:.0f}s'} → locator is wrong (not a timing issue).{hint} "
                 f"Check the .rf/state page capture before retrying.")
        rec["recheck_total"] = round(time.time() - now, 2)
        if self.log:
            with open(self.log, "a") as f:
                f.write(json.dumps(rec) + "\n")
