"""Classify a Browser (Playwright) failure from its message + call log (STDLIB ONLY; used by execd and hook.py).

Round-6 diagnosis: v2 judged every element-keyword timeout by re-checking the element count, so a click that timed out
because a styled `<span class="ideal-radio">` intercepted the pointer (element present from the first ms: "locator
resolved to ...") was reported as SLOW (110/111 SLOW verdicts were wrong) and the decisive "intercepts pointer events"
fragment was cut off at 380 chars. v3 reads the call log FIRST:

  covered    "<X> intercepts pointer events"      -> click the covering element / the input's label (fragment verbatim)
  hidden     "element is not visible"              -> open its container / click its visible label
  disabled   "element is not enabled"              -> complete what enables it
  animating  "element is not stable"               -> wait for the animation (`... stable`)
  detached   "element is not attached"             -> the page re-rendered it: re-locate
  ambiguous  "strict mode violation"               -> make the selector unique
  wrong      "Element is not an <input> ..."       -> the selector points at a non-editable element
  nooption   "did not find some options"           -> the <select> has no such option (label / value)
  present    "locator resolved to ..." (other)     -> the element exists: not a timing issue
  absent     timeout while "waiting for locator" without a resolution -> the only case worth a re-check
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

_RESOLVED = re.compile(r"locator resolved to (<.+?>)(?:\s|$)", re.M)
_INTERCEPT = re.compile(r"(<[^\n]{0,200}?>(?:[^<\n]{0,80}</\w+>)?) (?:from <[^\n]{0,160}?> subtree )?intercepts pointer events")
_WAITING = re.compile(r"waiting for (?:locator|selector)\(?['\"](.+?)['\"]\)?")
_STRICT = re.compile(r"strict mode violation: (.{0,200}?) resolved to (\d+) elements", re.S)
_ASSERT_BROWSER = re.compile(r"^(\w[\w ]*?) '(.*)' \((\w+)\) should (be|contain|start with|end with|match|not be|"
                             r"not contain|be less than|be greater than)\s+'(.*)' \((\w+)\)\s*$", re.S)
_ASSERT_NE = re.compile(r"^(.*) != (.*)$", re.S)


def classify(msg: Optional[str]) -> Dict[str, Any]:
    """-> {cls, first, evidence?, resolved?, selector?, count?}. cls '' when it is not a Playwright locator failure."""
    m = msg or ""
    out: Dict[str, Any] = {"cls": "", "first": m.strip().split("\n", 1)[0][:240]}
    w = _WAITING.search(m)
    if w:
        out["selector"] = w.group(1)
    r = _RESOLVED.search(m)
    if r:
        out["resolved"] = r.group(1)[:200]
    s = _STRICT.search(m)
    if s:
        out.update(cls="ambiguous", count=int(s.group(2)), evidence=f"resolved to {s.group(2)} elements")
        return out
    i = _INTERCEPT.search(m)
    if i:
        out.update(cls="covered", evidence=f"{i.group(1)[:200]} intercepts pointer events")
        return out
    if "Element is not an <input>" in m or "not an <input>, <textarea>" in m:
        out.update(cls="wrong", evidence="the element is not an <input>, <textarea>, <select> or [contenteditable]")
        return out
    for needle, cls in (("did not find some options", "nooption"), ("element is not visible", "hidden"),
                        ("element is not enabled", "disabled"),
                        ("element is not editable", "disabled"), ("element is not stable", "animating"),
                        ("element is not attached", "detached"), ("element is outside of the viewport", "hidden")):
        if needle in m:
            out.update(cls=cls, evidence=needle)
            return out
    timeout = bool(re.search(r"Timeout \d+ms exceeded|TimeoutError", m))
    if r:
        out["cls"] = "present"
        noise = re.compile(r"^(waiting \d+ms|retrying .* action|attempt #\d+|\d+ × .*|waiting for element to be .*|"
                           r"scrolling into view.*|done scrolling|element is visible, enabled and stable)$")
        last = [x.strip(" -") for x in m.splitlines() if x.strip().startswith("-")]
        last = [x for x in last if not noise.match(x)]
        if last:
            out["evidence"] = last[-1][:160]
        return out
    if timeout and w:
        out["cls"] = "absent"
    return out


def actual_expected(msg: Optional[str]) -> Optional[Dict[str, str]]:
    """value-assertion failure -> {what, actual, op, expected} (Browser assertion engine or BuiltIn `x != y`)."""
    m = (msg or "").strip()
    a = _ASSERT_BROWSER.match(m)
    if a:
        return {"what": a.group(1), "actual": a.group(2), "op": "should " + a.group(4), "expected": a.group(5)}
    if "\n" not in m and " != " in m and len(m) < 600:
        b = _ASSERT_NE.match(m)
        if b:
            return {"what": "value", "actual": b.group(1).strip(), "op": "!=", "expected": b.group(2).strip()}
    c = re.match(r"^'(.*)' (?:does not contain|should contain) '(.*)'$", m, re.S)
    if c:
        return {"what": "value", "actual": c.group(1), "op": "should contain", "expected": c.group(2)}
    return None
