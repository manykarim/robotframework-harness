"""v3 lean hook output = the v3.1 `lean` profile (STDLIB ONLY; imported by hook.py; the `rich` profile is richfmt.py).

Round-5 A/B: v2's per-edit context cost Claude +48 % with no pass gain; round-6 diagnosis: 33.8k hook chars per Claude
session (v1 22.2k), 82 % of the controls lines repeated header/nav, 71 % of docs/hint lines repeated; what measurably
helped: the step lines, the error, <= 3 controls nearest the failing selector (median 7 s / 1.4 edits vs 25 s / 2.6),
the iframe probe and NEXT.
Success  : one line per executed block (`L10-L16 PASS (7 lines; ${t}=...)`) + one short page line (title, path, number
           of controls); the .rf/state/latest/ file list is named once per session.
Failure  : failing line, error (<= 2 lines; the Playwright "... intercepts pointer events" fragment verbatim), verdict
           (COVERED / NOT_VISIBLE / DISABLED / ANIMATING / AMBIGUOUS / WRONG_ELEMENT / PRESENT / MISSING / SLOW /
           IN_IFRAME / STATIC), value failures as actual vs expected (+ whether the expected text is on the page),
           <= 3 controls nearest the selector, the keyword signature ONCE per session and keyword, a hint once per
           text, `NEXT:`.
Budgets  : success / failure chars per agent: claude 250 / 700, codex 250 / 700, opencode 250 / 600 (NEXT first),
           copilot 250 / 700; RFH31_MAX_CTX_<AGENT>="ok,fail" overrides. Mandatory parts (step lines, failing line, error,
           verdict, NEXT) are always kept (shortened if needed); optional parts are added while they fit.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

DEFAULT_CAPS = {"claude": (250, 700), "codex": (250, 700), "opencode": (250, 600), "copilot": (250, 700)}
GUIDANCE_FIRST = set((os.environ.get("RFH31_GUIDANCE_FIRST") or "opencode").split(","))


def caps(agent: str) -> Tuple[int, int]:
    v = os.environ.get(f"RFH31_MAX_CTX_{agent.upper()}")
    if v:
        try:
            a, b = (int(x) for x in v.split(","))
            return a, b
        except ValueError:
            pass
    return DEFAULT_CAPS.get(agent, (250, 700))


def cut(s: Any, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, default=str)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 3] + "..."


class Out:
    """lines tagged must / optional; render() keeps every must line and adds optional ones in order while they fit.
    A group (header + entries) is added with as many entries as fit (none -> no header)."""

    def __init__(self) -> None:
        self.items: List[Tuple[bool, Any, bool]] = []      # (must, text | [header, entry, ...], is_next)
        self.keys: Dict[int, str] = {}                     # item index -> "once" key, marked only when rendered
        self.rendered_keys: List[str] = []

    def add(self, text: Optional[str], must: bool = False, nxt: bool = False, key: Optional[str] = None) -> None:
        if text:
            if key:
                self.keys[len(self.items)] = key
            self.items.append((must, text, nxt))

    def add_group(self, header: str, entries: List[str], key: Optional[str] = None) -> None:
        if entries:
            if key:
                self.keys[len(self.items)] = key
            self.items.append((False, [header] + list(entries), False))

    def extend(self, other: "Out") -> None:
        base = len(self.items)
        self.items += other.items
        for i, k in other.keys.items():
            self.keys[base + i] = k

    def __bool__(self) -> bool:
        return bool(self.items)

    def render(self, cap: int, guidance_first: bool = False) -> str:
        order = list(range(len(self.items)))
        if guidance_first:
            order = [i for i in order if self.items[i][2]] + [i for i in order if not self.items[i][2]]
        items = [self.items[i] for i in order]
        keys = {j: self.keys[i] for j, i in enumerate(order) if i in self.keys}
        must = [i for i, x in enumerate(items) if x[0]]
        used = sum(len(items[i][1]) + 1 for i in must)
        out: Dict[int, str] = {i: items[i][1] for i in must}
        if used > cap:                      # even the mandatory lines are too long: shorten the longest ones
            over = used - cap
            for i in sorted(must, key=lambda i: -len(out[i])):
                if over <= 0:
                    break
                t = out[i]
                room = max(60, len(t) - over)
                if room < len(t):
                    over -= len(t) - room
                    out[i] = t[: room - 3] + "..."
        else:
            for i, (m, t, _) in enumerate(items):
                if m:
                    continue
                if isinstance(t, list):
                    take = [t[0]]
                    size = len(t[0]) + 1
                    for e in t[1:]:
                        if used + size + len(e) + 1 > cap:
                            break
                        take.append(e)
                        size += len(e) + 1
                    if len(take) > 1:
                        out[i] = "\n".join(take)
                        used += size
                elif used + len(t) + 1 <= cap:
                    out[i] = t
                    used += len(t) + 1
        self.rendered_keys = [keys[i] for i in out if i in keys]
        return "\n".join(out[i] for i in range(len(items)) if i in out)


# ------------------------------------------------------------------------------------------------ live runs
def _code(rec: Dict[str, Any], src: List[str]) -> str:
    ln = rec.get("line") or 0
    return src[ln - 1].strip() if 0 < ln <= len(src) else rec.get("kw", "")


def _pass_block(blk: List[Dict[str, Any]], label: str) -> str:
    a, b = blk[0].get("line"), blk[-1].get("line")
    s = f"{label}L{a} PASS" if len(blk) == 1 else f"{label}L{a}-L{b} PASS ({len(blk)} lines"
    rets = []
    for r in blk:
        if r.get("assign") and "ret" in r:
            rets.append(f"{str(r['assign'][0]).rstrip('= ')}={cut(r['ret'], 40)}")
    if len(blk) == 1:
        return s + (f" ({'; '.join(rets[-2:])})" if rets else "")
    return s + (f"; {'; '.join(rets[-2:])}" if rets else "") + ")"


def _slow_pass(rec: Dict[str, Any], label: str) -> str:
    rc = rec["recheck"]
    a = rc.get("appeared_after_s")
    normal = float(rc.get("normal_s") or 10)
    s = f"{label}L{rec.get('line')} PASS after {a} s (late element; this page now keeps the normal {normal:g} s live)"
    if a is not None and float(a) > 0.7 * normal:
        s += (f"; close to the limit: add `Wait For Elements State    {rc.get('selector') or '<sel>'}    visible    "
              f"timeout={int(max(20, 2 * float(a)))}s` before line {rec.get('line')}")
    return s


_CLS = {
    "covered": "COVERED", "hidden": "NOT_VISIBLE", "disabled": "DISABLED", "animating": "ANIMATING",
    "detached": "DETACHED", "ambiguous": "AMBIGUOUS", "wrong": "WRONG_ELEMENT", "present": "PRESENT",
    "invalid": "INVALID_SELECTOR", "iframe": "IN_IFRAME", "nooption": "NO_OPTION",
}


def verdict(rec: Dict[str, Any]) -> Tuple[Optional[str], str, Dict[str, Any]]:
    """-> (verdict line, kind, extra). kind: missing|slow|iframe|covered|hidden|disabled|animating|detached|ambiguous|
    wrong|present|invalid|static|value|other"""
    rc = rec.get("recheck") or {}
    g = rec.get("guard") or {}
    pw = rec.get("pw") or {}
    cls = pw.get("cls") or ""
    if rec.get("static"):
        x = rec["static"][0]
        return f"verdict: STATIC {x.get('code')}: {cut(x.get('msg'), 160)}", "static", {"code": x.get("code")}
    frame = rc.get("frame") or pw.get("frame") or ((g.get("inside_iframe") or [None])[0])
    if frame:
        return f"verdict: IN_IFRAME - found inside an iframe: use `{frame}`", "iframe", {"frame": frame}
    if cls == "covered":
        px = pw.get("proxy") or g.get("proxy") or {}
        ev = pw.get("evidence") or ""
        fix = ""
        if px.get("label"):
            fix = f" -> click its label `Click    {px['label']}`"
        elif px.get("cover") and not str(px["cover"]).startswith("<"):
            fix = f" -> click the element on top `Click    {px['cover']}`"
        elif g.get("overlay_buttons"):
            fix = f" -> close the overlay first (`Click    text={g['overlay_buttons'][0]}`)"
        return (f"verdict: COVERED - {cut(ev or g.get('fix') or 'another element receives the click', 170)}{fix}",
                "covered", {"label": px.get("label"), "cover": px.get("cover"),
                            "button": (g.get("overlay_buttons") or [None])[0]})
    if cls == "hidden":
        fix = g.get("fix") or "the element exists but is not visible: open its menu/tab/dialog first, or click its visible label"
        return f"verdict: NOT_VISIBLE - {cut(fix, 200)}", "hidden", {"label": g.get("click_instead")}
    if cls == "disabled":
        return ("verdict: DISABLED - the element exists but is disabled: complete the fields/steps that enable it",
                "disabled", {})
    if cls == "animating":
        return ("verdict: ANIMATING - the element exists but kept moving: `Wait For Elements State    <sel>    stable` "
                "before it", "animating", {})
    if cls == "detached":
        return "verdict: DETACHED - the page re-rendered the element: locate it again after the update", "detached", {}
    if cls == "ambiguous":
        return (f"verdict: AMBIGUOUS - the selector matches {pw.get('count', 'several')} elements (strict mode): make it "
                "unique or add `>> nth=0`", "ambiguous", {})
    if cls == "nooption":
        return ("verdict: NO_OPTION - the <select> has no option with that label/value (options: "
                ".rf/state/latest/controls.txt)", "nooption", {})
    if cls == "wrong":
        return ("verdict: WRONG_ELEMENT - the selector points at an element that cannot take text (not an input)",
                "wrong", {})
    if cls == "invalid":
        return f"verdict: INVALID_SELECTOR - {cut(g.get('error') or pw.get('first'), 160)}", "invalid", {}
    v = rc.get("verdict")
    if v == "missing":
        if rc.get("after_wait"):
            s = f"verdict: MISSING - not there after the explicit wait ({rc.get('normal_s')} s): wrong selector or iframe"
        elif rc.get("settled_s") is not None:
            s = (f"verdict: MISSING - the page did not change for {rc.get('settled_s')} s: wrong selector or iframe, "
                 "not timing")
        else:
            s = f"verdict: MISSING - not there after the normal {rc.get('normal_s')} s either: wrong selector or iframe"
        return s, "missing", {}
    if v == "slow":
        return (f"verdict: SLOW - absent, appeared after {rc.get('appeared_after_s')} s, still failing after it "
                "appeared", "slow", {})
    if cls == "present":
        return (f"verdict: PRESENT - the element exists ({cut(pw.get('resolved'), 70)}); last action log: "
                f"{cut(pw.get('evidence'), 80)}", "present", {})
    if cls == "absent":
        return "verdict: MISSING - no element matched the selector", "missing", {}
    if rec.get("value"):
        return None, "value", {}
    return None, "other", {}


def _next(rec: Dict[str, Any], kind: str, extra: Dict[str, Any], has_controls: bool) -> str:
    ln = rec.get("line")
    where = f" (or {rec['failed_at']} inside {rec.get('failed_in')})" if rec.get("failed_at") else ""
    if kind == "missing":
        src = "a control above (all: .rf/state/latest/controls.txt)" if has_controls else ".rf/state/latest/controls.txt"
        return f"NEXT: fix the selector on line {ln}{where} from {src}; only that line re-runs."
    if kind == "iframe":
        return f"NEXT: use `{extra.get('frame')}` on line {ln}{where}; only that line re-runs."
    if kind == "covered":
        if extra.get("label"):
            return f"NEXT: line {ln}{where}: `Click    {extra['label']}` instead (no wait/force needed)."
        if extra.get("button"):
            return f"NEXT: insert `Click    text={extra['button']}` before line {ln} (closes the overlay)."
        if extra.get("cover") and not str(extra["cover"]).startswith("<"):
            return f"NEXT: line {ln}{where}: click `{extra['cover']}` (the element on top) instead."
        return f"NEXT: line {ln}{where}: click the visible element on top of the target (see controls.txt)."
    if kind == "hidden" and extra.get("label"):
        return f"NEXT: line {ln}{where}: `Click    {extra['label']}` instead."
    if kind == "nooption":
        return f"NEXT: line {ln}{where}: use an option that exists (controls.txt lists the select's options)."
    if kind in ("disabled",):
        return f"NEXT: do the step that enables it before line {ln} (fill required fields / choose an option)."
    if kind == "static":
        return f"NEXT: fix line {ln} ({extra.get('code')}); it runs as soon as it is valid."
    if kind == "value":
        return f"NEXT: line {ln}{where}: fix the expected value or the step that sets it (not a timing issue)."
    if kind == "slow":
        return f"NEXT: line {ln}{where}: the element appeared late but the step still failed; read the error."
    return f"NEXT: fix line {ln}{where} (or insert lines before it); only that part re-runs in the open page."


def _err_lines(msg: str, n1: int = 110, n2: int = 110) -> List[str]:
    m = " ".join((msg or "").split())
    if not m:
        return []
    if len(m) <= n1:
        return [m]
    first, rest = m[:n1], m[n1:]
    sp = first.rfind(" ")
    if sp > n1 * 0.6:
        first, rest = m[:sp], m[sp + 1:]
    return [first, cut(rest, n2)]


def _error_text(rec: Dict[str, Any]) -> str:
    """the error: Playwright first line + the decisive evidence (intercepts / not visible / ...), not the retry log."""
    pw = rec.get("pw") or {}
    msg = rec.get("msg") or ""
    if pw.get("first") and pw.get("cls") and "Call log" in msg or (pw.get("first") and pw.get("evidence")
                                                                   and len(msg) > 200):
        e = pw.get("first", "")
        if pw.get("evidence") and pw["evidence"] not in e:
            e += " | " + pw["evidence"]
        return e
    return msg


def sig_key(sig: str) -> str:
    return "sig:" + re.sub(r"\W", "", str(sig).split("(")[0]).lower()


def _sig_line(rec: Dict[str, Any], seen: Callable[[str], bool]) -> Tuple[Optional[str], Optional[str]]:
    """-> (line, once key): the signature once per session and keyword (+ the on-demand doc path the first time)."""
    d = rec.get("doc")
    if not d or not d.get("signature"):
        return None, None
    key = sig_key(d["signature"])
    if seen(key):
        return None, None
    s = f"  keyword: {cut(d['signature'], 150)}"
    if d.get("path") and not seen("kwdocs_folder"):
        s += f" (full doc on request: {d['path']})"
    return s, key


def short_url(u: str) -> str:
    """http(s): path (+ query); file://: the file name -- keeps the page line short."""
    m = re.match(r"^(\w+)://[^/]*(/[^?#]*)?(\?[^#]*)?", u or "")
    if not m:
        return cut(u or "", 50)
    if m.group(1) == "file":
        return (m.group(2) or "").rsplit("/", 1)[-1] + (m.group(3) or "")
    return cut((m.group(2) or "/") + (m.group(3) or ""), 50)


def page_line(p: Dict[str, Any], seen: Optional[Callable[[str], bool]] = None, short: bool = False
              ) -> Tuple[Optional[str], Optional[str]]:
    """-> (line, once key). The page file list is named once per session (key "state_files")."""
    if not p:
        return None, None
    if p.get("error"):
        return f"Page capture failed: {cut(p.get('error'), 100)}", None
    t = cut(p.get("title") or "", 40)
    path = short_url(p.get("url") or "") if short else cut(p.get("url") or "", 90)
    files, key = "", None
    if seen is not None and not seen("state_files"):
        files, key = " | files: .rf/state/latest/", "state_files"
    if p.get("unchanged"):
        return f'Page unchanged: "{t}"{files}', key
    fr = p.get("iframes") or []
    return (f'Page "{t}" {path} ({p.get("n_controls", 0)} controls'
            + (f"; iframes: {', '.join(fr[:2])}" if fr else "") + ")" + files), key


def _value_line(rec: Dict[str, Any]) -> Optional[str]:
    v = rec.get("value")
    if not v:
        return None
    s = f"  actual {cut(repr(v.get('actual')), 90)} vs expected {cut(repr(v.get('expected')), 90)}"
    if v.get("on_page") is True:
        s += " (the expected text IS on the page: wrong element or not updated yet)"
    elif v.get("on_page") is False:
        s += " (the expected text is NOT on the page: check the app state / the steps before)"
    return s


def live_out(r: Dict[str, Any], src: List[str], agent: str, seen: Callable[[str], bool],
             head: Optional[str] = None, tail: bool = True) -> Tuple[Out, bool]:
    """lean rendering of one live-run reply -> (Out, failed)."""
    o = Out()
    rel = r.get("file") or "?"
    ran = r.get("ran") or []
    if r.get("status") == "running":
        o.add(f"{head or 'Live run of ' + rel}: still running; the result comes with your next edit.", must=True)
        return o, False
    notes = r.get("notes") or []
    restart = next((n for n in notes if "restarted" in n or "re-run" in n), None)
    tests = {x.get("test") for x in ran if x.get("test")}
    prefix = head or f"Live {rel}:"
    if restart:
        m = re.search(r"line (\d+)", restart)
        k = re.search(r"keyword (.+?) changed", restart)
        fresh = ", fresh browser context" if any("context closed" in n for n in notes) else ""
        if k:
            prefix += f" (keyword {cut(k.group(1), 40)} changed: first test using it re-run{fresh})"
        else:
            prefix += f" (test restarted{': line ' + m.group(1) + ' changed' if m else ''}{fresh})"
    if r.get("error"):
        o.add(f"{prefix} could not run: {cut(r['error'], 200)}", must=True)
        o.add("NEXT: fix the file so it parses and its imports resolve; the live run starts again.", must=True, nxt=True)
        return o, True
    if not ran:
        msg = next((n for n in notes if "no new lines" in n or "no change" in n or "re-imported" in n
                    or "no test case" in n), None)
        o.add(f"{prefix} nothing new to execute" + (f" ({cut(msg, 100)})" if msg else "") + ".", must=True)
        return o, False
    lines_out: List[str] = []
    blk: List[Dict[str, Any]] = []
    fail_rec = None

    def flush():
        if blk:
            tl = next((x.get("test") for x in blk if x.get("test")), None)
            label = f"'{cut(tl, 30)}' " if len(tests) > 1 and tl else ""
            lines_out.append(_pass_block(blk, label))
            blk.clear()

    for rec in ran:
        if rec.get("status") == "PASS" and not rec.get("recheck"):
            if blk and len(tests) > 1 and blk[-1].get("test") and rec.get("test") and blk[-1].get("test") != rec.get("test"):
                flush()
            blk.append(rec)
            continue
        flush()
        label = f"'{cut(rec.get('test'), 30)}' " if len(tests) > 1 and rec.get("test") else ""
        if rec.get("status") == "PASS":
            lines_out.append(_slow_pass(rec, label))
            continue
        fail_rec = rec
        break
    flush()
    first = True
    for ln in lines_out:
        o.add((prefix + " " + ln) if first else ln, must=True)
        first = False
    if fail_rec is None:
        pl, pk = page_line(r.get("page") or {}, seen, short=True)
        o.add(pl, key=pk)
        if r.get("file_complete") and tail:
            o.add(f"All lines pass live. NEXT: robot -d results {rel}", must=True, nxt=True)
        return o, False
    rec = fail_rec
    code = _code(rec, src)
    inside = f" (inside {rec['failed_in']}" + (f" at {rec['failed_at']}" if rec.get("failed_at") else "") + ")" \
        if rec.get("failed_in") else ""
    o.add((prefix + " " if first else "") + f"L{rec.get('line')} {rec.get('status')}  {cut(code, 90)}{inside}",
          must=True)
    v, kind, extra = verdict(rec)
    if not rec.get("guard") and not rec.get("static") and kind != "value":
        for e in _err_lines(_error_text(rec)):
            o.add(f"  {e}", must=True)
    if kind == "value":
        o.add(_value_line(rec) or (f"  {cut(rec.get('msg'), 200)}"), must=True)
    if v:
        o.add(f"  {v}", must=True)
    matches = rec.get("matches") or []
    show = matches[:3] if kind in ("missing", "hidden", "ambiguous", "wrong", "invalid", "slow", "other") else []
    o.add_group("  similar controls:", [f"    {m}" for m in show])
    sl, sk = _sig_line(rec, seen)
    o.add(sl, key=sk)
    if sl and "full doc on request" in sl:
        o.keys[len(o.items) - 1] = sk + "|kwdocs_folder"
    if not v and kind not in ("value",):
        for h in (rec.get("hints") or [])[:1]:
            t = f"  hint: {cut(h.get('title', ''), 100)}"
            if h.get("try"):
                t += f" -- try: {cut(h['try'][0], 80)}"
            hk = "hint:" + re.sub(r"\W", "", t[:60]).lower()
            if not seen(hk):
                o.add(t, key=hk)
    pl, pk = page_line(r.get("page") or {}, seen, short=True)
    o.add(pl, key=pk)
    o.add(_next(rec, kind, extra, bool(show)), must=True, nxt=True)
    return o, True
