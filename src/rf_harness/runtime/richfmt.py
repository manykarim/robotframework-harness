"""v3.1 `rich` output profile (STDLIB ONLY + rf_harness.config; imported by hook.py) -- v2-like guidance on top of v3's correct facts.

Why: round-6 same-day A/B -- OpenCode/MiniMax M2.5 passed 0.55 with v2's rich output vs 0.40 with v3's lean output,
while Claude was best with lean (0.65). Weak / non-frontier models need the guidance repeated where the failure is;
strong models pay for it in tokens. Everything v3 fixed stays: Playwright-log classification before any re-check,
no false SLOW, no settle/hidden waits between steps, race detection, page.txt = visible text.

Success : one line per passed block (as lean) + after a NAVIGATION (a page not listed before in this session) a compact
          controls list: <= 8 controls `kind "name" => selector (note)`, form fields first, controls already listed on
          an earlier page (header / nav) skipped, hrefs never shown (same-origin deep links stay hidden).
Failure : failing line, error, verdict, actual vs expected, the failing keyword's signature + first doc sentence EVERY
          time it fails, a failure-type hint EVERY time (<= 300 chars), up to 8 nearest controls, page line, NEXT:.
Budget  : ~1,200 chars success and failure (RFH_MAX_CTX_RICH="ok,fail"); OpenCode: guidance (hint + NEXT) first.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import config
from . import leanfmt as lf

RICH_CAPS = (1200, 1200)
NEAR_N = 8
LIST_N = 8


def caps(agent: str) -> Tuple[int, int]:
    v = config.get("RFH_MAX_CTX_RICH") or lf.agent_var("RFH_MAX_CTX_RICH_", agent)
    if v:
        try:
            a, b = (int(x) for x in v.split(","))
            return a, b
        except ValueError:
            pass
    return RICH_CAPS


def _h(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:10]


# ------------------------------------------------------------------------------------------------ controls
_KIND = (("input[type=radio]", "radio"), ("input[type=checkbox]", "checkbox"), ("input[type=password]", "password"),
         ("input[type=submit]", "button"), ("input[type=button]", "button"), ("input[type=number]", "number"),
         ("input[type=email]", "email"), ("input[type=date]", "date"), ("input", "textbox"), ("textarea", "textbox"),
         ("select", "select"), ("button", "button"), ("a", "link"), ("summary", "button"))
_FORM = {"textbox", "password", "number", "email", "date", "select", "radio", "checkbox"}


def compact_row(row: str) -> Optional[Tuple[str, str]]:
    """controls.txt row -> (kind, `kind "name" => selector (note)`); None when unusable (no selector, href selector)."""
    if "   => " not in row:
        return None
    head, rest = row.split("   => ", 1)
    sel, _, notes = rest.partition("   (")
    sel = sel.strip()
    if not sel or "href" in sel:          # never surface (same-origin) hrefs: deep links skip the user journey
        return None
    notes = notes.rstrip(")").strip()
    tag = head.strip().split(" ", 1)[0]
    role = re.search(r"\brole=(\w+)", head)
    kind = next((k for t, k in _KIND if tag.startswith(t)), role.group(1) if role else (tag or "control"))
    if role and kind in ("control", "div", "span", "li"):
        kind = role.group(1)
    m = re.search(r'"([^"]{1,40})"', head)
    name = f' "{m.group(1)}"' if m else ""
    st = " checked" if re.search(r"(^|\s)checked(\s|$)", head) else ""
    note = ""
    if notes:
        if "styled input" in notes or "click its label" in notes or "click the label" in notes:
            note = "styled: click this label"
        elif notes.startswith("native select"):
            o = re.search(r"\[([^\]]*)\]", notes)
            note = "options: " + lf.cut((o.group(1) if o else ""), 70)
        elif "custom dropdown" in notes:
            note = 'custom dropdown: click, then role=option[name="..."]'
        elif notes.startswith("Fill Text with") or "Fill Text with" in notes:
            note = lf.cut(notes, 40)
        elif "new tab" in notes:
            note = "opens a new tab"
        elif notes.startswith("HIDDEN") or notes.startswith("hidden"):
            note = "hidden"
    return kind, lf.cut(f"{kind}{name}{st} => {sel}" + (f" ({note})" if note else ""), 130)


def controls_list(rows: List[str], seen: Callable[[str], bool], n: int = LIST_N) -> Tuple[List[str], List[str], int]:
    """-> (entries, once keys, n skipped as already listed). Form fields first, then buttons, then links; page order."""
    cand: List[Tuple[int, int, str, str]] = []
    skipped = 0
    dup = set()
    for i, r in enumerate(rows):
        c = compact_row(r)
        if not c:
            continue
        kind, text = c
        k = "ctl:" + _h(text)
        if k in dup:
            continue
        dup.add(k)
        if seen(k):
            skipped += 1
            continue
        pri = 0 if kind in _FORM else (1 if kind == "button" else 2)
        cand.append((pri, i, text, k))
    pick = sorted(cand)[:n]
    pick.sort(key=lambda x: x[1])
    return [f"    {t}" for _p, _i, t, _k in pick], [k for _p, _i, _t, k in pick], skipped


def page_identity(p: Dict[str, Any]) -> str:
    u = re.sub(r"#.*$", "", str(p.get("url") or ""))
    return "pg:" + _h(u + "|" + str(p.get("title") or ""))


# ------------------------------------------------------------------------------------------------ hints
def type_hint(kind: str, rec: Dict[str, Any], extra: Dict[str, Any]) -> str:
    """one failure-type hint (<= 300 chars), given EVERY time the failure occurs."""
    pw = rec.get("pw") or {}
    if kind == "missing":
        t = ("MISSING = no element matched (not a timing problem, no Sleep): copy a selector from the controls below or "
             ".rf/state/latest/controls.txt; text=... must equal the visible text (page.txt); content of an iframe needs "
             "`<frame> >>> <selector>`.")
    elif kind == "iframe":
        t = (f"The element is inside an iframe. Browser has no frame-switch keyword: put the frame in the selector, "
             f"`{extra.get('frame') or '<frame> >>> <selector>'}`, in the same keyword (Fill Text / Click / Get Text).")
    elif kind == "covered":
        t = ("Another element is on top of the target (styled radio/checkbox or an overlay): click the visible label or "
             "the element on top instead; waits, force=True or JS clicks do not fix it. Assert on the input afterwards "
             "(Get Checkbox State    <input>    ==    checked).")
    elif kind == "hidden":
        t = ("The element exists but is not visible: open the menu/tab/dialog that shows it first, or click its visible "
             "label (styled inputs); the visible page text is in .rf/state/latest/page.txt.")
    elif kind == "disabled":
        t = ("The element exists but is disabled: complete the fields / choose the option that enables it (see the page "
             "text), then this step works without any wait.")
    elif kind == "animating":
        t = "The element kept moving: `Wait For Elements State    <selector>    stable` directly before this step."
    elif kind == "detached":
        t = "The page re-rendered the element: wait for the new state (Wait For Elements State) and locate it again."
    elif kind == "ambiguous":
        t = (f"Strict mode: the selector matches {pw.get('count', 'several')} elements. Make it unique (id=, data-test=, "
             "role=button[name=\"...\"], text=\"exact\") or append `>> nth=0`.")
    elif kind == "nooption":
        t = ("That option does not exist in the <select>: use an option text listed for it (controls below / "
             "controls.txt) with `Select Options By    <select>    label    <exact text>`.")
    elif kind == "wrong":
        t = "This element cannot take text: target the <input>/<textarea> itself (text fields are listed with selectors)."
    elif kind == "invalid":
        t = ("Invalid selector syntax: one strategy prefix (id=, css=, text=, xpath=, role=...), quote text with spaces "
             "(text=\"Place order\"), iframe content as `<frame> >>> <selector>`.")
    elif kind == "value":
        v = rec.get("value") or {}
        if v.get("on_page") is True:
            t = ("The expected text IS on the page: the locator reads the wrong element or the page had not updated yet -- "
                 "use a locator for the element that shows it, or a waiting assertion (Wait For Elements State / Get Text "
                 "with `contains` in a Wait Until Keyword Succeeds).")
        elif v.get("on_page") is False:
            t = ("The expected text is NOT on the page: an earlier step left the app in another state (check the inputs "
                 "/ options chosen before) -- or the expectation is wrong; do not weaken the assertion.")
        else:
            t = ("The step ran but the value differs: check which element the locator reads and whether earlier steps "
                 "set the app state the assertion expects.")
    elif kind == "static":
        t = ("This line is not valid as written: fix the keyword name / argument count (separate cells with 4 spaces); "
             "`grep -i '<word>' .rf/docs/*.md` lists the available keywords with their arguments.")
    elif kind == "slow":
        t = ("The element appeared late and the step still failed after it appeared: read the error; if the page needs "
             "time, `Wait For Elements State    <selector>    visible    timeout=20s` before the step.")
    elif kind == "present":
        t = ("The element exists but the action failed: check it is the right keyword for this control (Check Checkbox "
             "/ Click for radios, Select Options By for <select>, Fill Text for inputs).")
    else:
        rh = (rec.get("hints") or [None])[0] or {}
        t = ("Read the error and the keyword signature: fix the keyword / arguments on this line, or insert the missing "
             "step before it; only that part re-runs in the open page.")
        if rh.get("title"):
            t = lf.cut(rh["title"], 140) + (f" -- try: {lf.cut(rh['try'][0], 100)}" if rh.get("try") else "") + ". " + t
    return lf.cut(t, 300)


def sig_line(rec: Dict[str, Any], seen: Callable[[str], bool]) -> Tuple[Optional[str], Optional[str]]:
    """the failing keyword's signature + first doc sentence, EVERY time (the doc path only once per session)."""
    d = rec.get("doc")
    if not d or not d.get("signature"):
        return None, None
    s = f"  keyword: {lf.cut(d['signature'], 150)}"
    if d.get("first"):
        s += f" -- {lf.cut(d['first'], 120)}"
    key = None
    if d.get("path") and not seen("kwdocs_folder"):
        s += f" (full doc: {d['path']})"
        key = "kwdocs_folder"
    return s, key


# ------------------------------------------------------------------------------------------------ live runs
def live_out(r: Dict[str, Any], src: List[str], agent: str, seen: Callable[[str], bool],
             head: Optional[str] = None, tail: bool = True) -> Tuple["lf.Out", bool]:
    """rich rendering of one live-run reply -> (Out, failed). Built on the lean rendering of the step lines."""
    o = lf.Out()
    rel = r.get("file") or "?"
    ran = r.get("ran") or []
    if r.get("status") == "running" or r.get("error") or not ran:
        return lf.live_out(r, src, agent, seen, head, tail)
    notes = r.get("notes") or []
    tests = {x.get("test") for x in ran if x.get("test")}
    prefix = head or f"Live {rel}:"
    restart = next((n for n in notes if "restarted" in n or "re-run" in n), None)
    if restart:
        m = re.search(r"line (\d+)", restart)
        k = re.search(r"keyword (.+?) changed", restart)
        fresh = ", fresh browser context" if any("context closed" in n for n in notes) else ""
        if k:
            prefix += f" (keyword {lf.cut(k.group(1), 40)} changed: first test using it re-run{fresh})"
        else:
            prefix += f" (test restarted{': line ' + m.group(1) + ' changed' if m else ''}{fresh})"
    lines_out: List[str] = []
    blk: List[Dict[str, Any]] = []
    fail_rec = None

    def flush():
        if blk:
            tl = next((x.get("test") for x in blk if x.get("test")), None)
            label = f"'{lf.cut(tl, 30)}' " if len(tests) > 1 and tl else ""
            lines_out.append(lf._pass_block(blk, label))
            blk.clear()

    for rec in ran:
        if rec.get("status") == "PASS" and not rec.get("recheck"):
            if blk and len(tests) > 1 and blk[-1].get("test") and rec.get("test") and blk[-1].get("test") != rec.get("test"):
                flush()
            blk.append(rec)
            continue
        flush()
        label = f"'{lf.cut(rec.get('test'), 30)}' " if len(tests) > 1 and rec.get("test") else ""
        if rec.get("status") == "PASS":
            lines_out.append(lf._slow_pass(rec, label))
            continue
        fail_rec = rec
        break
    flush()
    first = True
    for ln in lines_out:
        o.add((prefix + " " + ln) if first else ln, must=True)
        first = False
    page = r.get("page") or {}
    if fail_rec is None:
        pl, pk = lf.page_line(page, seen, short=True)
        o.add(pl, key=pk)
        if page and not page.get("error") and not page.get("unchanged"):
            pid = page_identity(page)
            if not seen(pid):
                rows = page.get("controls_pick") or page.get("controls_top") or []
                ents, keys, skipped = controls_list(rows, seen)
                if ents:
                    hdr = (f"  controls on this page ({len(ents)} shown"
                           + (f", {skipped} already listed before" if skipped else "")
                           + "; all: .rf/state/latest/controls.txt):")
                    o.add_group(hdr, ents, key="|".join([pid] + keys))
        if r.get("file_complete") and tail:
            o.add(f"All lines pass live. NEXT: robot -d results {rel}", must=True, nxt=True)
        return o, False
    rec = fail_rec
    code = lf._code(rec, src)
    inside = f" (inside {rec['failed_in']}" + (f" at {rec['failed_at']}" if rec.get("failed_at") else "") + ")" \
        if rec.get("failed_in") else ""
    o.add((prefix + " " if first else "") + f"L{rec.get('line')} {rec.get('status')}  {lf.cut(code, 90)}{inside}",
          must=True)
    v, kind, extra = lf.verdict(rec)
    if not rec.get("guard") and not rec.get("static") and kind != "value":
        for e in lf._err_lines(lf._error_text(rec), 130, 150):
            o.add(f"  {e}", must=True)
    if kind == "value":
        o.add(lf._value_line(rec) or (f"  {lf.cut(rec.get('msg'), 200)}"), must=True)
    if v:
        o.add(f"  {v}", must=True)
    sl, sk = sig_line(rec, seen)
    o.add(sl, key=sk)
    o.add(f"  hint: {type_hint(kind, rec, extra)}", nxt=True)
    matches = (rec.get("matches") or [])[:NEAR_N] if kind not in ("value", "static") else []
    o.add_group("  nearest controls (name => selector):", [f"    {m}" for m in matches])
    pl, pk = lf.page_line(page, seen, short=True)
    o.add(pl, key=pk)
    o.add(lf._next(rec, kind, extra, bool(matches)), must=True, nxt=True)
    return o, True


def plain_fail_hint(msg: str, pw: Dict[str, Any], value: Optional[Dict[str, Any]]) -> Optional[str]:
    """plain robot run failure -> the same failure-type hint (classification from the message only)."""
    cls = (pw or {}).get("cls") or ""
    kind = {"covered": "covered", "hidden": "hidden", "disabled": "disabled", "animating": "animating",
            "detached": "detached", "ambiguous": "ambiguous", "nooption": "nooption", "wrong": "wrong",
            "invalid": "invalid", "absent": "missing", "present": "present"}.get(cls)
    if not kind and value:
        kind = "value"
    if not kind:
        return None
    rec = {"pw": pw or {}, "value": value or {}}
    return f"  hint: {type_hint(kind, rec, {})}"
