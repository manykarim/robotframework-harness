"""Round-5 prototype: capture page state after page-changing / failing top-level REPL steps.

Load:  robotcode repl --plain ... with  ROBOT_OPTIONS="--listener /abs/rfcapture_listener.py:/abs/state_dir"
       (or robot.toml  listeners = { "/abs/rfcapture_listener.py" = ["/abs/state_dir"] })
Writes .rf/state/step-<n>-<kw>/ + latest/ + history.tsv via rfcapture.capture_page and appends the inline
summary to <state>/inline.log (what a PostToolUse hook would read back and inject). Silences library INFO
logging during the capture so the agent's REPL stdout is not flooded.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rfcapture import rfcapture  # noqa: E402

# normalized keyword names (lowercase, no spaces/underscores), owner-agnostic
ALWAYS = {
    # Browser 20.5
    "goto", "goback", "goforward", "reload", "newpage", "newpersistentcontext",
    "switchpage", "switchcontext", "switchbrowser", "closepage", "closecontext", "waitfornavigation",
    # SeleniumLibrary 6.8
    "openbrowser", "reloadpage", "switchwindow", "closewindow", "selectframe", "unselectframe", "submitform",
    "createwebdriver",
}
MAYBE = {
    # Browser: actions that can navigate / re-render (compare url + source hash afterwards)
    "click", "clickwithoptions", "tap", "presskeys", "keyboardkey", "keyboardinput", "fillText".lower(), "typetext",
    "selectoptionsby", "checkcheckbox", "uncheckcheckbox", "uploadfilebyselector", "draganddrop", "mousebutton",
    "evaluatejavascript", "handlefuturedialogs", "promiseto", "waitforloadstate", "waitforelementsstate",
    "filltext", "fillsecret", "typesecret", "clicklink", "clickbutton", "clickelement", "clickimage",
    # Selenium
    "doubleclickelement", "presskey", "inputtext", "inputpassword", "selectfromlistbylabel", "selectfromlistbyvalue",
    "selectfromlistbyindex", "selectcheckbox", "selectradiobutton", "choosefile", "executejavascript",
    "handlealert", "clickelementatcoordinates",
}
LOCATOR_FAIL = re.compile(
    r"(TimeoutError: locator\.|waiting for locator\(|strict mode violation|"
    r"(Element|Button|Link|Image|List|Checkbox|Radio button|Text field|Text area|Frame) with locator '.*' not found|"
    r"Element '.*' not visible|did not match any elements|ElementNotInteractable|element click intercepted|"
    r"Page should have contained element|Element .* is not (visible|enabled))", re.I)


def _norm(name: str) -> str:
    return re.sub(r"[\s_]", "", name.split(".")[-1]).lower()


class rfcapture_listener:  # noqa: N801
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self, state_dir: str = ".rf/state"):
        self.cap = rfcapture(state_dir=state_dir)
        self.depth = 0
        self.inline = Path(state_dir).resolve() / "inline.log"
        self.inline.parent.mkdir(parents=True, exist_ok=True)
        self.prev = None  # (url, src_hash) after last top-level step

    def start_keyword(self, data, result):
        self.depth += 1

    def end_keyword(self, data, result):
        self.depth -= 1
        if self.depth != 0:
            return
        kw = _norm(result.name or data.name or "")
        status = result.status
        why = None
        if kw in ALWAYS and status == "PASS":
            why = "navigation"
        elif status == "FAIL" and LOCATOR_FAIL.search(result.message or ""):
            why = "locator-failure"
        elif status == "FAIL" and kw in ALWAYS | MAYBE:
            why = "failure"
        elif kw in MAYBE and status == "PASS":
            why = "maybe"
        if not why:
            return
        t0 = time.perf_counter()
        from robot.libraries.BuiltIn import BuiltIn
        bi = BuiltIn()
        from robot.output.logger import LOGGER
        LOGGER.log_message = lambda *a, **k: None  # silence library INFO during capture (REPL stdout + output.xml)
        try:
            if why == "maybe":
                # cheap change check first: url + hash of normalized source (dedup inside capture_page too)
                summary = self.cap.capture_page(result.name, why="after " + result.name, screenshot=False)
                if "page unchanged" in summary:
                    summary = ""
            else:
                summary = self.cap.capture_page(result.name, why=why, screenshot=(why != "maybe"))
                if why == "locator-failure" and data.args:
                    summary += "\n" + self.cap.near_miss(str(data.args[0]))
        except Exception as e:  # never break the session
            summary = f"[page] capture failed: {type(e).__name__}: {str(e)[:160]}"
        finally:
            try:
                del LOGGER.log_message  # back to the class method
            except AttributeError:
                pass
        ms = round((time.perf_counter() - t0) * 1000, 1)
        with open(self.inline, "a") as f:
            f.write(json.dumps({"kw": result.name, "status": status, "why": why, "ms": ms,
                                "summary": summary, "chars": len(summary)}) + "\n")
