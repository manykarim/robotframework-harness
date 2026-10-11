"""Per-step hooks that run INSIDE the helper (same process + live RF context as the keyword).

pre(step)  -> None to proceed, or a dict to refuse the step (it is then NOT executed)
post(step, rec) -> may enrich/redact the compact record

Copied from the CLI prototype (skillpkg) for the hook harness: hint wording/examples point at the files the
hooks maintain (.rf/state/*, .rf/docs/*.md) and the skill's references/*.md -- never at a CLI or MCP tools;
  * the Browser probe waits up to `settle` seconds, then also looks INSIDE iframes and suggests
    `<frame> >>> <selector>` (round-1 locator-guard finding);
  * PlatynUI desktop guard dropped (out of scope for this A/B arm).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from robot.libraries.BuiltIn import BuiltIn
from robot.running.context import EXECUTION_CONTEXTS


@dataclass
class StepCtx:
    kw: Any
    name: str
    args: List[str]
    assign: List[str]
    owner: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


def resolve_owner(name: str) -> Optional[str]:
    """Authoritative keyword -> library/resource resolution via the live namespace (rf-mcp S5 pattern)."""
    ctx = EXECUTION_CONTEXTS.current
    if ctx is None or not name:
        return None
    try:
        runner = ctx.namespace.get_runner(name, recommend_on_failure=False)
    except TypeError:
        runner = ctx.namespace.get_runner(name)
    except Exception:
        return None
    kw = getattr(runner, "keyword", None)
    owner = getattr(kw, "owner", None)
    return getattr(owner, "name", None) or getattr(kw, "libname", None)


class Hook:
    name = "hook"

    def pre(self, step: StepCtx) -> Optional[Dict[str, Any]]:
        return None

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        return None


# ---------------------------------------------------------------- redaction
SECRET_KEY = re.compile(r"(pass(word|wd)?|secret|token|auth(orization)?|api[_-]?key|cookie|bearer)", re.I)


class Redactor(Hook):
    """Learns secret values from secret-named args / assigned variables and scrubs them from output."""

    name = "redact"

    def __init__(self) -> None:
        self.secrets: Set[str] = set()

    def _collect(self, value: Any) -> None:
        if isinstance(value, str):
            if len(value) >= 4:
                self.secrets.add(value)
        elif isinstance(value, dict):
            for v in value.values():
                self._collect(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                self._collect(v)

    def pre(self, step: StepCtx) -> None:
        for a in step.args:
            m = re.match(r"^([\w-]+)=(.+)$", a, re.S)
            if not m or not SECRET_KEY.search(m.group(1)):
                continue
            try:
                val = BuiltIn().replace_variables(m.group(2))
            except Exception:
                val = m.group(2)
            self._collect(val)
        return None

    def scrub(self, s: Any) -> Any:
        if not isinstance(s, str) or not self.secrets:
            return s
        for sec in sorted(self.secrets, key=len, reverse=True):
            s = s.replace(sec, "***")
        return s

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        for a in step.assign:
            var = a.rstrip("= ").strip()
            if SECRET_KEY.search(var):
                try:
                    self._collect(BuiltIn().get_variable_value(var))
                except Exception:
                    pass
        if "args" in rec:
            rec["args"] = [self.scrub(a) for a in rec["args"]]
        for k in ("msg", "ret"):
            if k in rec:
                rec[k] = self.scrub(rec[k])
        if "logs" in rec:
            rec["logs"] = [self.scrub(x) for x in rec["logs"]]


# ---------------------------------------------------------------- hints (rf-mcp engine, local wording)
_TEXT_MAP = [
    (re.compile(r"get_session_state\s*\([^)]*\)"), "`.rf/state/aria.yaml`"),
    (re.compile(r"\bget_session_state( tool)?\b"), "`.rf/state/aria.yaml`"),
    (re.compile(r"get_locator_guidance\s*\(\s*library\s*=\s*['\"]([\w.]+)['\"]\s*\)"), r"the skill's `references/\1.md`"),
    (re.compile(r"\bget_locator_guidance\b"), "the skill's `references/browser.md`"),
    (re.compile(r"\bfind_keywords( tool)?\b"), "`grep -i '<words>' .rf/docs/*.md`"),
    (re.compile(r"\bget_keyword_info( tool)?\b"), "`.rf/docs/<Library>.md`"),
    (re.compile(r"\bset_library_search_order( tool)?\b"), "the `Set Library Search Order` keyword"),
    (re.compile(r"\bexecute_step\b"), "a line in your test file"),
    (re.compile(r"\bexecute_flow\b"), "lines in your test file"),
    (re.compile(r"\bintent_action\b"), "a Browser keyword"),
    (re.compile(r"\bmanage_session\b"), "your test file's *** Settings ***"),
    (re.compile(r"\bvisual_check\b"), "`.rf/state/screenshot.png`"),
    (re.compile(r"\bbuild_test_suite\b"), "your .robot file"),
]


def localize_text(s: str) -> str:
    for rx, rep in _TEXT_MAP:
        s = rx.sub(rep, s)
    return s


def _rf_line(keyword: str, args: List[Any], assign: Optional[str] = None) -> str:
    cells = [str(keyword), *[str(a) for a in (args or [])]]
    line = "    ".join(cells)
    if assign:
        a = assign if assign.startswith("${") else "${%s}" % assign
        line = f"{a}=    {line}"
    return line


def render_example(ex: Any) -> Optional[str]:
    """rf-mcp hint example (MCP-tool shaped) -> an RF line or a pointer to a hook-maintained file."""
    if isinstance(ex, str):
        return localize_text(ex)
    if not isinstance(ex, dict):
        return None
    tool = ex.get("tool")
    if "rf" in ex:
        rf = str(ex["rf"])
        m = re.match(r"intent_action\s{2,}intent=(\w+)\s{2,}target=(.+)$", rf)
        if m:
            kw = {"click": "Click", "fill": "Fill Text", "type": "Type Text", "hover": "Hover"}.get(m.group(1), m.group(1))
            rf = f"{kw}    {m.group(2)}"
        return localize_text(rf)
    if tool in (None, "execute_step", "execute_flow") and ex.get("keyword"):
        args = ex.get("arguments") if isinstance(ex.get("arguments"), list) else []
        return _rf_line(ex["keyword"], args, ex.get("assign_to"))
    a = ex.get("arguments") if isinstance(ex.get("arguments"), dict) else {}
    if tool == "get_session_state":
        return "read .rf/state/aria.yaml"
    if tool == "find_keywords":
        return f'grep -i "{a.get("pattern") or a.get("query") or ""}" .rf/docs/*.md'
    if tool == "get_keyword_info":
        return f'grep -i "^{a.get("keyword") or a.get("keyword_name") or ""}(" .rf/docs/*.md'
    if tool == "get_locator_guidance":
        return f'skill references/{str(a.get("library") or "browser").lower()}.md'
    if tool == "set_library_search_order":
        return _rf_line("Set Library Search Order", list(a.get("libraries") or ["Browser", "BuiltIn"]))
    if tool == "visual_check":
        return "look at .rf/state/screenshot.png"
    if ex.get("keyword"):
        return _rf_line(ex["keyword"], ex.get("arguments") if isinstance(ex.get("arguments"), list) else [])
    return None


class Hints(Hook):
    """rf-mcp's pure hint engine (robotmcp.utils.hints.generate_hints) on failures, re-rendered locally."""

    name = "hints"

    def __init__(self, max_hints: int = 2) -> None:
        self.max_hints = max_hints
        self.error = None
        try:
            from robotmcp.utils.hints import HintContext, generate_hints  # type: ignore

            self._gen, self._ctx = generate_hints, HintContext
        except Exception as e:  # rf-mcp not installed -> no hints, everything else works
            self._gen = None
            self.error = repr(e)

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        if rec.get("status") != "FAIL":
            return
        local = _local_hint(step, rec.get("msg") or "")
        if local:
            rec.setdefault("hints", [])[:0] = [local]
            return
        if self._gen is None:
            return
        try:
            order = [o for o in (step.owner, "BuiltIn") if o]
            hs = self._gen(self._ctx(session_id="local", keyword=step.name, arguments=list(step.args),
                                     error_text=rec.get("msg") or "", session_search_order=order))
        except Exception as e:
            rec["hints_error"] = repr(e)[:200]
            return
        out = []
        for h in hs[: self.max_hints]:
            tries = [t for t in (render_example(e) for e in (h.get("examples") or [])) if t][:2]
            item = {"title": localize_text(h.get("title") or ""),
                    "msg": localize_text((h.get("message") or ""))[:300]}
            if tries:
                item["try"] = tries
            out.append(item)
        if out:
            rec.setdefault("hints", [])[:0] = out


def _local_hint(step: StepCtx, msg: str) -> Optional[Dict[str, Any]]:
    sel = step.args[0] if step.args else "<selector>"
    if "is not a <select> element" in msg:
        return {"title": "custom dropdown, not a native <select>",
                "msg": "Select Options By only works on <select>. Open the widget, look at the options, click one.",
                "try": [f"Click    {sel}", "then read .rf/state/aria.yaml", 'Click    role=option[name="<option text>"]']}
    if "intercepts pointer events" in msg:
        return {"title": "another element covers the target (cookie banner, modal, sticky header)",
                "msg": "close/accept the overlay first (.rf/state/controls.txt lists its buttons); force=True would "
                       "click the overlay instead of the target",
                "try": ["read .rf/state/controls.txt", f"Scroll To Element    {sel}"]}
    if step.owner == "Browser" and step.name.lower().startswith("get ") and " should " in msg and \
            any(a.strip().lower() in _ASSERT_OPS for a in step.args[:3]):
        return {"title": "value assertion failed -- an assertion operator retries only ~1 s (retry_assertions_for)",
                "msg": "if the page was still updating (spinner, async result), wait for the final value instead; "
                       "otherwise the expected value or the selector is wrong (.rf/state/aria.yaml)",
                "try": [f"Wait For Condition    {step.name[4:]}    " + "    ".join(step.args) + "    timeout=15s"]}
    return None


_ASSERT_OPS = {"==", "!=", "<", ">", "<=", ">=", "contains", "not contains", "*=", "^=", "$=", "starts", "ends",
               "matches", "should be", "equal", "equals", "inequal", "should not be", "validate", "then",
               "less than", "greater than", "starts with", "ends with"}


# ---------------------------------------------------------------- Browser probe / guard
_BROWSER_LOCATOR_KWS = {
    "click", "click with options", "fill text", "type text", "fill secret", "type secret", "check checkbox",
    "uncheck checkbox", "hover", "get text", "select options by", "press keys", "focus", "clear text",
    "get attribute", "get property", "get checkbox state", "get selected options", "upload file by selector",
}


# keywords that need a VISIBLE element (Playwright actionability) -- a hidden match would wait the full timeout
_BROWSER_ACTION_KWS = {
    "click", "click with options", "fill text", "type text", "fill secret", "type secret", "check checkbox",
    "uncheck checkbox", "hover", "select options by", "clear text",
}
# JS run on the hidden element: what the user actually sees/clicks instead
_HIDDEN_INFO_JS = """(el) => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect(); const st = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const txt = (e) => (e.innerText || e.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 60);
  let label = null;
  const ls = el.labels ? Array.from(el.labels) : [];
  const l = ls.find(vis) || (el.closest && el.closest('label'));
  if (l && vis(l)) {
    if (l.htmlFor) label = 'label[for="' + l.htmlFor + '"]';
    else if (el.id) label = 'label:has(#' + CSS.escape(el.id) + ')';
    else if (txt(l)) label = 'text=' + txt(l);
  }
  return {tag: el.tagName.toLowerCase(), type: el.type || '', label: label, label_text: l ? txt(l) : ''};
}"""

# keywords whose click must land ON the element (Playwright hit-target check); force=True would hit the overlay
_BROWSER_CLICK_KWS = {"click", "click with options", "check checkbox", "uncheck checkbox", "hover"}
# JS: is the element's center covered by another element (Playwright's hit-target rule: the element at the click point
# must be the target or inside it)? v3: also small styled coverers (`<span class="ideal-radio">` over a radio) --
# round-6 diagnosis: they caused most "timeouts"; the fix is the input's visible label or the covering element.
_COVER_JS = """(el) => {
  try {
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (r.width === 0 || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return null;
    const root = el.getRootNode();
    const top = (root.elementFromPoint ? root : document).elementFromPoint(x, y);
    if (!top || top === el || el.contains(top)) return null;
    const clean = (t) => (t || '').replace(/\\s+/g, ' ').trim().slice(0, 40);
    const vis = (e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0; };
    const uniq = (s) => { try { const n = document.querySelectorAll(s); return n.length === 1 ? n[0] : null; } catch (x) { return null; } };
    const ls = el.labels ? Array.from(el.labels).filter(vis) : [];
    let label = null;
    if (ls.length) { const l = ls.find((q) => clean(q.innerText)) || ls[0];
      label = l.htmlFor ? 'label[for="' + l.htmlFor + '"]' : (clean(l.innerText) ? 'text="' + clean(l.innerText) + '"' : null);
      // v3.2: wrapping label without for= and without text (Tricentis price table) -> label:has(#id) when unique
      if (!label && el.id && uniq('label:has(#' + CSS.escape(el.id) + ')') === l) label = 'label:has(#' + CSS.escape(el.id) + ')'; }
    let c = top;
    while (c.parentElement && c.parentElement !== document.body) c = c.parentElement;
    const cs = getComputedStyle(c), cr = c.getBoundingClientRect();
    const big = cr.width >= 0.9 * innerWidth && cr.height >= 0.5 * innerHeight &&
      (cs.position === 'fixed' || cs.position === 'absolute' || cs.position === 'sticky');
    const tcls = (top.className && typeof top.className === 'string') ? top.className.trim().split(/\\s+/)[0] : '';
    const tdesc = '<' + top.tagName.toLowerCase() + (top.id ? ' id="' + top.id + '"' : '') + (tcls ? ' class="' + tcls + '"' : '') + '>';
    if (!big) {
      let cover = null;
      if (top.id) cover = 'id=' + top.id;
      else if (tcls && document.querySelectorAll(top.tagName.toLowerCase() + '.' + CSS.escape(tcls)).length === 1)
        cover = 'css=' + top.tagName.toLowerCase() + '.' + tcls;
      else if (el.id) {   // v3.2: non-unique coverer next to the input -> `#id + span.cls` when it resolves to it
        const t = top.tagName.toLowerCase() + (tcls ? '.' + CSS.escape(tcls) : '');
        for (const s of ['#' + CSS.escape(el.id) + ' + ' + t, '#' + CSS.escape(el.id) + ' ~ ' + t])
          if (uniq(s) === top) { cover = 'css=' + s; break; } }
      return {small: true, by: tdesc, label: label, cover: cover, tag: el.tagName.toLowerCase(), type: el.type || ''};
    }
    const btns = Array.from(c.querySelectorAll('button,[role=button],a,input[type=submit],input[type=button]'))
      .filter(vis).map((b) => clean(b.innerText || b.value || b.getAttribute('aria-label'))).filter(Boolean).slice(0, 4);
    const desc = c.tagName.toLowerCase() + (c.id ? '#' + c.id : '') +
      (c.className && typeof c.className === 'string' ? '.' + c.className.trim().split(/\\s+/).join('.') : '');
    return {by: desc.slice(0, 80), text: clean(c.innerText), buttons: btns, label: label};
  } catch (e) { return null; }
}"""


def _first_selector(args: List[str]) -> Optional[str]:
    for a in args:
        if a.startswith("selector="):
            return a[len("selector="):]
        return a
    return None


class BrowserGuard(Hook):
    """Before a Browser element keyword: count matches via the library instance (no RF logging).
    0 matches after `settle` s -> refuse fast with NOT_FOUND (+ `frame >>> selector` candidates that DO
    match inside iframes); invalid selector -> INVALID_SELECTOR. Saves the default 10 s timeout per miss."""

    name = "guard"

    def __init__(self, settle: float = 1.5, followup: float = 5.0) -> None:
        self.settle = settle          # first keyword of a call (page was usually just inspected)
        self.followup = max(followup, settle)  # later keywords / file lines (page may still be loading)
        self.cur_settle = settle

    @staticmethod
    def _lib():
        try:
            return BuiltIn().get_library_instance("Browser")
        except Exception:
            return None

    def _frame_candidates(self, lib: Any, sel: str) -> List[str]:
        out: List[str] = []
        try:
            n = int(lib.get_element_count("iframe") or 0)
        except Exception:
            return out
        for i in range(min(n, 6)):
            nth = f"iframe >> nth={i}"
            fsel = nth
            for attr, fmt in (("id", "id={}"), ("name", 'iframe[name="{}"]'), ("title", 'iframe[title="{}"]')):
                try:
                    v = lib.get_attribute(nth, attr)
                except Exception:
                    v = None
                if v:
                    fsel = fmt.format(v)
                    break
            cand = f"{fsel} >>> {sel}"
            try:
                if int(lib.get_element_count(cand) or 0) > 0:
                    out.append(cand)
            except Exception:
                pass
        return out

    def pre(self, step: StepCtx) -> Optional[Dict[str, Any]]:
        if step.owner != "Browser" or step.name.lower() not in _BROWSER_LOCATOR_KWS or not step.args:
            return None
        lib = self._lib()
        raw = _first_selector(step.args)
        if lib is None or not raw:
            return None
        try:
            sel = BuiltIn().replace_variables(raw)
        except Exception:
            return None
        if not isinstance(sel, str) or sel.startswith("element="):
            return None
        t0 = time.perf_counter()
        settle = self.cur_settle
        t_end = time.monotonic() + settle
        count = None
        while True:
            try:
                count = int(lib.get_element_count(sel) or 0)
            except Exception as e:
                first = str(e).strip().splitlines()[0][:240] if str(e).strip() else type(e).__name__
                return {"cls": "INVALID_SELECTOR", "selector": sel, "error": first,
                        "probe_ms": round((time.perf_counter() - t0) * 1000), "see": "skill references/browser.md"}
            if count or time.monotonic() > t_end:
                break
            time.sleep(0.1)
        ms = round((time.perf_counter() - t0) * 1000)
        if count == 0:
            ref: Dict[str, Any] = {"cls": "NOT_FOUND", "selector": sel, "probe_ms": ms}
            frames = self._frame_candidates(lib, sel)
            if frames:
                ref["inside_iframe"] = frames
                ref["fix"] = f"element is inside an iframe: use `{frames[0]}`"
            else:
                tips = [f"nothing matched for {settle:g} s; pick a selector from .rf/state/controls.txt (aria.yaml)"]
                if sel.startswith(("//", "xpath=", "(/")):
                    tips.append("xpath does NOT pierce shadow DOM; css= / text= / id= do")
                tips.append("if it only appears later, add a wait line before it: "
                            "Wait For Elements State    <sel>    visible    timeout=10s")
                ref["fix"] = "; ".join(tips)
            return ref
        if count > 1:
            step.extra["probe"] = {"count": count, "note": "multiple matches (Browser strict mode fails on >1)"}
            return None
        forced = any(a.replace(" ", "").lower() == "force=true" for a in step.args[1:])
        kw = step.name.lower()
        if kw in _BROWSER_ACTION_KWS and not forced:
            ref = self._hidden(lib, sel, t0, t_end)
            if ref:
                return ref
        if kw in _BROWSER_CLICK_KWS:
            return self._covered(lib, sel, t0, t_end, forced)
        return None

    def _covered(self, lib: Any, sel: str, t0: float, t_end: float, forced: bool) -> Optional[Dict[str, Any]]:
        """another element at the click point (cookie wall / modal backdrop, or a small styled span over a radio): a
        normal click waits the full timeout ('intercepts pointer events'), a force=True click lands on the coverer."""
        while True:
            try:
                cov = lib.evaluate_javascript(sel, _COVER_JS)
            except Exception:
                return None
            if not cov or time.monotonic() > t_end:
                break
            time.sleep(0.1)
        if not cov:
            return None
        ms = round((time.perf_counter() - t0) * 1000)
        if cov.get("small"):
            proxy = {k: cov.get(k) for k in ("label", "cover") if cov.get(k)}
            what = f"<{cov.get('tag')}{' type=' + cov['type'] if cov.get('type') else ''}>"
            if cov.get("label"):
                fix = f"{cov.get('by')} intercepts pointer events over this {what}: click its label `Click    {cov['label']}`"
            elif cov.get("cover"):
                fix = f"{cov.get('by')} intercepts pointer events over this {what}: click the visible element `Click    {cov['cover']}`"
            else:
                fix = f"{cov.get('by')} intercepts pointer events over this {what}: click the visible element on top of it"
            if forced:
                fix += "; force=True would click the covering element instead"
            return {"cls": "COVERED", "selector": sel, "covered_by": cov.get("by"), "proxy": proxy, "probe_ms": ms,
                    "fix": fix, **({"click_instead": cov["label"]} if cov.get("label") else {})}
        btn = (cov.get("buttons") or [None])[0]
        fix = (f"the element is covered by an overlay `{cov.get('by')}` (\"{cov.get('text', '')[:60]}\"): close it "
               "first" + (f", e.g. `Click    text={btn}`" if btn else "") + ", then repeat this step")
        if forced:
            fix += "; force=True would NOT help: the click would land on the overlay and silently do nothing"
        return {"cls": "COVERED", "selector": sel, "covered_by": cov.get("by"), "overlay_buttons": cov.get("buttons"),
                "probe_ms": ms, "fix": fix}

    def _hidden(self, lib: Any, sel: str, t0: float, t_end: float) -> Optional[Dict[str, Any]]:
        """exactly one match: refuse fast when it stays hidden (styled radio/checkbox, select behind a custom
        dropdown, closed menu) instead of letting Playwright wait the full timeout for visibility."""
        while True:
            try:
                states = [str(x).lower() for x in (lib.get_element_states(sel) or [])]
            except Exception:
                return None
            if "visible" in states or not states:
                return None
            if time.monotonic() > t_end:
                break
            time.sleep(0.1)
        ref: Dict[str, Any] = {"cls": "NOT_VISIBLE", "selector": sel,
                               "probe_ms": round((time.perf_counter() - t0) * 1000)}
        try:
            info = lib.evaluate_javascript(sel, _HIDDEN_INFO_JS) or {}
        except Exception:
            info = {}
        tag, typ, label = info.get("tag", ""), info.get("type", ""), info.get("label")
        if tag == "input" and typ in ("radio", "checkbox") and label:
            ref["fix"] = (f"the <input type={typ}> is hidden by CSS (styled control): click its visible label "
                          f"`Click    {label}`, then verify `Get Checkbox State    {sel}    ==    checked`")
            ref["click_instead"] = label
        elif tag == "select":
            ref["fix"] = ("this native <select> is hidden behind a custom dropdown: click the visible dropdown, then "
                          "the option (.rf/state/controls.txt / .rf/state/aria.yaml show both)")
        elif label:
            ref["fix"] = f"element is hidden; its visible label is `{label}`"
            ref["click_instead"] = label
        else:
            ref["fix"] = ("element exists but is hidden: open the menu/tab/dialog that contains it first (.rf/state/"
                          "aria.yaml), or if it appears later: Wait For Elements State    <sel>    visible    timeout=10s")
        return ref

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        if "probe" in step.extra and rec.get("status") == "FAIL":
            rec["probe"] = step.extra["probe"]


class ImportHint(Hook):
    """`No keyword with name 'New Browser' found.` -> the installed library that has it is not imported yet."""

    name = "importhint"

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        msg = rec.get("msg") or ""
        if rec.get("status") != "FAIL" or not msg.startswith("No keyword with name"):
            return
        try:
            from robot.utils import normalize

            from . import kwdocs

            target = normalize(step.name.rsplit(".", 1)[-1], ignore="_")
            libs = [l for l in kwdocs.WELL_KNOWN + kwdocs.workspace_libraries() if kwdocs.installed(l)]
            for lib in dict.fromkeys(libs):
                d = kwdocs._extra_owner(lib)
                if d is not None and any(normalize(k.name, ignore="_") == target for k in d.keywords):
                    rec.setdefault("hints", []).insert(0, {
                        "title": f"'{step.name}' is in library {lib}, which is not imported yet",
                        "msg": f"add `Library    {lib}` to the file's *** Settings ***",
                        "try": [f"Library    {lib}"]})
                    return
        except Exception:
            return


def build_hooks(names: List[str], settle: float = 1.5, followup: float = 5.0) -> List[Hook]:
    hooks: List[Hook] = []
    for n in names:
        if n == "redact":
            hooks.append(Redactor())
        elif n == "hints":
            hooks.append(Hints())
        elif n == "guard":
            hooks.append(BrowserGuard(settle=settle, followup=followup))
        elif n == "importhint":
            hooks.append(ImportHint())
    return hooks
