"""Page inspection through the live library instance (controls|aria|source|url|screenshot), used by the hooks.

Writes artifacts under .rf/state/, returns paths + a short summary (the agent reads the file itself).
Browser: ARIA snapshot of the main document PLUS one section per iframe, headed with the frame selector
to prefix with `>>>` (Get Aria Snapshot does not descend into iframes). SeleniumLibrary: source/url/screenshot.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from robot.libraries.BuiltIn import BuiltIn

INLINE_MAX = 1800


def _lib(name: str) -> Optional[Any]:
    try:
        return BuiltIn().get_library_instance(name)
    except Exception:
        return None


def _frames(lib: Any) -> List[str]:
    out = []
    try:
        n = int(lib.get_element_count("iframe") or 0)
    except Exception:
        return out
    for i in range(min(n, 8)):
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
        out.append(fsel)
    return out


# controls: every form field / button / link with its STABLE attributes and a suggested selector
# (the analog of rf-mcp's page-context extraction: forms, inputs id/name/placeholder, buttons) + widget kind.
_CONTROLS_JS = """(body) => {
  const doc = body.ownerDocument;
  const Q = 'input:not([type=hidden]),select,textarea,button,a[href],summary,[contenteditable=""],[contenteditable=true],' +
    '[role=button],[role=link],[role=checkbox],[role=radio],[role=switch],[role=combobox],[role=listbox],[role=option],' +
    '[role=tab],[role=menuitem],[role=textbox],[role=slider],[role=spinbutton],[onclick]';
  const all = [];
  const walk = (root) => { root.querySelectorAll(Q).forEach((e) => all.push(e));
    root.querySelectorAll('*').forEach((e) => { if (e.shadowRoot) walk(e.shadowRoot); }); };
  walk(doc);
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect(); const st = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const clean = (t) => (t || '').replace(/\\s+/g, ' ').trim();
  const q = (v) => v.replace(/"/g, '\\\\"');
  const count = (css) => { try { return doc.querySelectorAll(css).length; } catch (x) { return 0; } };
  const genId = (id) => /^[0-9]|[:]|\\d{3,}|^(ember|react|mui|radix|headlessui|ext-gen)/i.test(id);
  const nameOf = (e) => {
    const ls = e.labels ? Array.from(e.labels) : [];
    if (ls.length) return clean(ls.map((l) => l.innerText || l.textContent).join(' '));
    if (e.getAttribute('aria-label')) return clean(e.getAttribute('aria-label'));
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\\s+/).map((i) => doc.getElementById(i)).filter(Boolean).map((x) => x.textContent).join(' ');
      if (clean(t)) return clean(t); }
    if (['input', 'textarea', 'select'].includes(e.tagName.toLowerCase())) return clean(e.placeholder || e.title || '');
    return clean(e.innerText || e.value || e.title || e.getAttribute('alt') || '').slice(0, 60);
  };
  const roleOf = (e) => {
    const r = e.getAttribute('role'); if (r) return r;
    const t = e.tagName.toLowerCase(), ty = (e.getAttribute('type') || 'text').toLowerCase();
    if (t === 'a') return 'link'; if (t === 'button' || t === 'summary') return 'button'; if (t === 'textarea') return 'textbox';
    if (t === 'select') return e.multiple || e.size > 1 ? 'listbox' : 'combobox';
    if (t === 'input') return ({checkbox: 'checkbox', radio: 'radio', button: 'button', submit: 'button', reset: 'button',
      image: 'button', range: 'slider', number: 'spinbutton', search: 'searchbox'})[ty] || 'textbox';
    return '';
  };
  const out = [];
  for (const e of all.slice(0, 400)) {
    const t = e.tagName.toLowerCase(), ty = (e.getAttribute('type') || '').toLowerCase();
    const v = vis(e), role = roleOf(e), name = nameOf(e);
    const lab = (e.labels && Array.from(e.labels).find(vis)) || (e.closest && e.closest('label'));
    if (!v && !(lab && vis(lab)) && t !== 'select') continue;
    const r = {tag: t, type: ty, role: role, acc: name, visible: v, xrole: e.getAttribute('role') || ''};
    for (const a of ['id', 'name', 'data-test', 'data-testid', 'data-test-id', 'placeholder', 'href', 'target', 'aria-haspopup']) {
      const x = e.getAttribute(a); if (x) r[a] = x.slice(0, 80); }
    if (t === 'select') r.options = Array.from(e.options).slice(0, 8).map((o) => clean(o.text));
    if (ty === 'checkbox' || ty === 'radio') r.checked = e.checked;
    const dt = ['data-test', 'data-testid', 'data-test-id'].find((a) => r[a] && count('[' + a + '="' + q(r[a]) + '"]') === 1);
    if (dt) r.sel = dt + '=' + r[dt];
    else if (r.id && !genId(r.id) && count('[id="' + q(r.id) + '"]') === 1) r.sel = 'id=' + r.id;
    else if (r.name && ['input', 'select', 'textarea'].includes(t) && !['radio', 'checkbox'].includes(ty) &&
             count(t + '[name="' + q(r.name) + '"]') === 1) r.sel = t + '[name="' + r.name + '"]';
    else if (role && name) r.sel = 'role=' + role + '[name="' + q(name) + '"]';
    else if (name && ['button', 'link'].includes(role)) r.sel = 'text="' + q(name) + '"';
    if (!v && lab && vis(lab)) r.click = lab.htmlFor ? 'label[for="' + lab.htmlFor + '"]' :
      (r.id ? 'label:has(#' + CSS.escape(r.id) + ')' : 'text=' + clean(lab.innerText).slice(0, 40));
    out.push(r);
  }
  return out;
}"""


def _fmt_control(c: Dict[str, Any], prefix: str = "") -> str:
    tag, typ = c.get("tag", ""), c.get("type", "")
    head = tag + (f"[type={typ}]" if typ and tag == "input" else "")
    if c.get("xrole"):
        head += f" role={c['xrole']}"
    parts = [head]
    if c.get("acc"):
        parts.append(f'"{c["acc"]}"')  # accessible name (label / aria-label / text) -> role=...[name="..."]
    for a in ("id", "name", "data-test", "data-testid", "data-test-id", "placeholder", "href"):
        if c.get(a):
            parts.append(f"{a}={c[a]}")
    if "checked" in c:
        parts.append("checked" if c["checked"] else "unchecked")
    sel = (prefix + c["sel"]) if c.get("sel") else None
    notes = []
    if not c.get("visible"):
        if c.get("click"):
            notes.append(f"HIDDEN styled input: click its label; assert on the input: Get Checkbox State    "
                         f"{sel or '<input>'}    ==    checked")
            sel = prefix + c["click"]
        elif tag == "select":
            notes.append("HIDDEN native select: a custom dropdown is shown instead, click that")
        else:
            notes.append("HIDDEN")
    if tag == "select" and c.get("visible"):
        opts = "|".join(c.get("options") or [])
        notes.append(f"native select [{opts}] -> Select Options By    {sel or '<sel>'}    label    <option>")
    elif (c.get("role") in ("combobox", "listbox") and tag != "select") or \
            c.get("aria-haspopup") in ("listbox", "true", "menu"):
        notes.append('custom dropdown -> Click it, then Click    role=option[name="<option>"]')
    if typ in ("date", "datetime-local", "time", "month"):
        fmt = {"date": "YYYY-MM-DD", "datetime-local": "YYYY-MM-DDTHH:MM", "time": "HH:MM", "month": "YYYY-MM"}[typ]
        notes.append(f"Fill Text with {fmt}")
    if c.get("target") == "_blank":
        notes.append("opens a new tab -> Switch Page    NEW")
    line = "  ".join(parts)
    if sel:
        line += f"   => {sel}"
    if notes:
        line += "   (" + "; ".join(notes) + ")"
    return line


def _head(text: str, limit: int = INLINE_MAX) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut[: cut.rfind("\n")] + f"\n... ({len(text) - limit} more chars, read the file)"


def state(what: str, outdir: Path, selector: Optional[str] = None) -> Dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    br, se = _lib("Browser"), _lib("SeleniumLibrary")
    if br is None and se is None:
        return {"ok": False, "error": "no Browser or SeleniumLibrary imported in the session",
                "hint": "add `Library    Browser` to *** Settings ***"}
    t0 = time.perf_counter()
    res: Dict[str, Any] = {"ok": True, "what": what}
    try:
        if br is not None:
            try:
                res["url"], res["title"] = br.get_url(), br.get_title()
            except Exception as e:
                return {"ok": False, "error": f"no page open? {str(e).splitlines()[0][:200]}",
                        "hint": "open a page first (New Page    <url>)"}
        else:
            res["url"], res["title"] = se.get_location(), se.get_title()
        if what == "url":
            pass
        elif what == "aria":
            if br is None:
                return {**res, "ok": False, "error": "aria needs Browser; SeleniumLibrary: see source.html"}
            sel = selector or "css=body"
            parts = [f"# main document ({sel})", str(br.get_aria_snapshot(sel))]
            frames = _frames(br) if not selector else []
            for f in frames:
                try:
                    snap = str(br.get_aria_snapshot(f"{f} >>> css=body"))
                except Exception as e:
                    snap = f"(not readable: {str(e).splitlines()[0][:120]})"
                parts.append(f"\n# iframe `{f}` -- locate inside with `{f} >>> <selector>`\n{snap}")
            text = "\n".join(parts)
            p = outdir / "aria.yaml"
            p.write_text(text)
            res.update(path=str(p), chars=len(text), iframes=frames, content=_head(text))
            res["tip"] = ("role/name lines are NOT selectors: build one with id=/css=/text=\"...\"; "
                          "inside an iframe prefix `<frame> >>> `; css/text pierce open shadow roots")
        elif what == "controls":
            if br is None:
                return {**res, "ok": False, "error": "controls needs Browser; SeleniumLibrary: see source.html"}
            scopes = [("", selector or "css=body")]
            frames = _frames(br) if not selector else []
            scopes += [(f"{f} >>> ", f"{f} >>> css=body") for f in frames[:4]]
            lines: List[str] = []
            n = 0
            for prefix, body in scopes:
                try:
                    items = br.evaluate_javascript(body, _CONTROLS_JS) or []
                except Exception as e:
                    lines.append(f"# {body}: not readable ({str(e).splitlines()[0][:120]})")
                    continue
                lines.append(f"# iframe `{prefix[:-5]}` -- prefix selectors with `{prefix}`" if prefix
                             else "# main document")
                lines += [_fmt_control(c, prefix) for c in items]
                n += len(items)
            text = "\n".join(lines)
            p = outdir / "controls.txt"
            p.write_text(text)
            res.update(path=str(p), controls=n, iframes=frames, content=_head(text, 3000))
            res["tip"] = ("=> is a suggested selector (stable attribute first; unique when it is data-test=/id=/name); "
                          "HIDDEN inputs: click the label shown; custom dropdown: click it, look at aria.yaml, click the option")
        elif what == "source":
            src = br.get_page_source() if br is not None else se.get_source()
            p = outdir / "source.html"
            p.write_text(str(src))
            res.update(path=str(p), chars=len(str(src)))
            res["note"] = ("page source = main document only: no iframe contents, no shadow-root contents; "
                           "see aria.yaml for those")
        elif what == "screenshot":
            p = outdir / f"screenshot-{int(time.time())}.png"
            if br is not None:
                got = br.take_screenshot(filename=str(p.with_suffix("")), fullPage=False)
                p = Path(str(got)) if got else p
            else:
                p = Path(str(se.capture_page_screenshot(str(p))))
            res.update(path=str(p), note="read the image only if you are multimodal")
        else:
            return {"ok": False, "error": f"unknown state '{what}'",
                    "choices": ["controls", "aria", "source", "url", "screenshot"]}
    except Exception as e:
        return {**res, "ok": False, "error": f"{type(e).__name__}: {str(e).splitlines()[0][:300] if str(e) else ''}"}
    res["ms"] = round((time.perf_counter() - t0) * 1000)
    return res


# ------------------------------------------------------------------------------------------------ v2: capture
def _aria_text(br: Any, frames: List[str]) -> Tuple[str, str]:
    """Browser >= 20.5: one `Get Aria Snapshot    css=body    mode=ai` includes iframe content; older: main
    document + one section per iframe (`<frame> >>> css=body`)."""
    import inspect

    try:
        has_mode = "mode" in inspect.signature(br.get_aria_snapshot).parameters
    except (TypeError, ValueError):
        has_mode = False
    if has_mode:
        try:
            from Browser.utils.data_types import AriaSnapshotMode  # type: ignore

            mode: Any = AriaSnapshotMode.ai
        except Exception:
            mode = "ai"
        try:
            head = "# main document (Get Aria Snapshot mode=ai: iframe content included; [ref=..] are NOT selectors)"
            return head + "\n" + str(br.get_aria_snapshot("css=body", mode=mode)), "ai"
        except Exception:
            pass
    parts = ["# main document (css=body)", str(br.get_aria_snapshot("css=body"))]
    for f in frames:
        try:
            snap = str(br.get_aria_snapshot(f"{f} >>> css=body"))
        except Exception as e:
            snap = f"(not readable: {str(e).splitlines()[0][:120]})"
        parts.append(f"\n# iframe `{f}` -- locate inside with `{f} >>> <selector>`\n{snap}")
    return "\n".join(parts), "default+frames"


def _slug(s: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", (s or "step").lower()).strip("-")[:28] or "step"


def _prune(state_dir: Path, keep: int, max_bytes: int) -> int:
    import shutil

    dirs = sorted([d for d in state_dir.glob("step-*") if d.is_dir()], key=lambda d: d.stat().st_mtime)
    removed = 0
    while len(dirs) > keep:
        shutil.rmtree(dirs.pop(0), ignore_errors=True)
        removed += 1
    total = sum(f.stat().st_size for d in dirs for f in d.iterdir() if f.is_file())
    while dirs and total > max_bytes and len(dirs) > 1:
        d = dirs.pop(0)
        total -= sum(f.stat().st_size for f in d.iterdir() if f.is_file())
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    return removed


def page_sig() -> Optional[Tuple[str, Dict[str, Any]]]:
    """cheap page identity: sha1(url, title, page source) + the values (None when no page is open)."""
    import hashlib

    br, se = _lib("Browser"), _lib("SeleniumLibrary")
    try:
        if br is not None:
            url, title, src = str(br.get_url()), str(br.get_title()), str(br.get_page_source())
        elif se is not None:
            url, title, src = str(se.get_location()), str(se.get_title()), str(se.get_source())
        else:
            return None
    except Exception:
        return None
    import re

    norm = re.sub(r'\s+style=""', "", src)      # screenshots leave empty style attributes behind: not a page change
    h = hashlib.sha1("\0".join((url, title, norm)).encode("utf-8", "replace")).hexdigest()[:16]
    return h, {"url": url, "title": title, "source": src}


def _selenium_sel(sel: str) -> Optional[str]:
    import re

    m = re.match(r'^(id|name)=(.+)$', sel)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    m = re.match(r'^(data-test(?:id|-id)?)=(.+)$', sel)
    if m:
        return f'css:[{m.group(1)}="{m.group(2)}"]'
    m = re.match(r'^role=link\[name="(.+)"\]$', sel)
    if m:
        return f"link:{m.group(1)}"
    m = re.match(r'^role=button\[name="(.+)"\]$', sel) or re.match(r'^text="(.+)"$', sel)
    if m:
        return f'xpath://*[self::button or self::a or @role="button" or @type="submit"][normalize-space()="{m.group(1)}"]'
    if re.match(r'^(input|select|textarea|label)\[', sel):
        return "css:" + sel
    return None


def _selenium_row(row: str) -> str:
    """Browser-style `=> selector` suggestions -> SeleniumLibrary locators (id:x, name:x, css:..., link:..., xpath:...)."""
    if "   => " not in row:
        return row
    head, _, rest = row.partition("   => ")
    sel, sep, notes = rest.partition("   (")
    conv = _selenium_sel(sel.strip())
    if "Select Options By" in notes:
        notes = notes.replace("Select Options By", "Select From List By Label").replace("    label    ", "    ")
    return head + (f"   => {conv}" if conv else "") + (sep + notes if sep else "")


def capture(state_dir: Path, step_no: int, kw: str, line: Optional[int], why: str,
            sig_info: Tuple[str, Dict[str, Any]], keep: int = 15, max_bytes: int = 25_000_000) -> Dict[str, Any]:
    """write the page state of the live session into state_dir/step-<n>-<kw>/ and hard-link it to state_dir/latest/.
    files: page.txt (url/title/step), source.html, controls.txt, aria.yaml (Browser), screenshot.jpg|png."""
    t0 = time.perf_counter()
    sig, info = sig_info
    br, se = _lib("Browser"), _lib("SeleniumLibrary")
    d = state_dir / f"step-{step_no:03d}-{_slug(kw)}"
    d.mkdir(parents=True, exist_ok=True)
    res: Dict[str, Any] = {"sig": sig, "url": info["url"], "title": info["title"], "dir": d.name, "step": step_no}
    (d / "source.html").write_text(info["source"])
    frames: List[str] = []
    rows: List[str] = []
    n = 0
    if br is not None:
        frames = _frames(br)
        scopes = [("", "css=body")] + [(f"{f} >>> ", f"{f} >>> css=body") for f in frames[:4]]
        for prefix, body in scopes:
            try:
                items = br.evaluate_javascript(body, _CONTROLS_JS) or []
            except Exception as e:
                rows.append(f"# {body}: not readable ({str(e).splitlines()[0][:120]})")
                continue
            rows.append(f"# iframe `{prefix[:-5]}` -- prefix selectors with `{prefix}`" if prefix else "# main document")
            rows += [_fmt_control(c, prefix) for c in items]
            n += len(items)
        try:
            text, mode = _aria_text(br, frames)
            (d / "aria.yaml").write_text(text)
            res["aria_mode"] = mode
        except Exception as e:
            res["aria_error"] = str(e).splitlines()[0][:160] if str(e) else type(e).__name__
        try:
            from Browser.utils.data_types import ScreenshotFileTypes  # type: ignore

            got = br.take_screenshot(filename=str(d / "screenshot"), fileType=ScreenshotFileTypes.jpeg, quality=55,
                                     fullPage=False)
            if got and Path(str(got)).is_file() and Path(str(got)).name != "screenshot.jpg":
                os.replace(str(got), d / "screenshot.jpg")
        except Exception as e:
            res["screenshot_error"] = str(e).splitlines()[0][:160] if str(e) else type(e).__name__
    elif se is not None:
        try:
            items = se.execute_javascript("return (" + _CONTROLS_JS + ")(document.body);") or []
            rows.append("# main document (SeleniumLibrary: iframe content needs Select Frame; ids below)")
            rows += [_selenium_row(_fmt_control(c, "")) for c in items]
            n = len(items)
            fr = se.execute_javascript("return Array.from(document.querySelectorAll('iframe')).map("
                                       "f => f.id ? 'id:' + f.id : (f.name ? 'name:' + f.name : 'css:iframe'))") or []
            frames = [str(x) for x in fr][:6]
        except Exception as e:
            rows.append(f"# controls not readable ({str(e).splitlines()[0][:120]})")
        try:
            se.capture_page_screenshot(str(d / "screenshot.png"))
        except Exception as e:
            res["screenshot_error"] = str(e).splitlines()[0][:160] if str(e) else type(e).__name__
    (d / "controls.txt").write_text("\n".join(rows) + "\n")
    page = (f"url: {info['url']}\ntitle: {info['title']}\nstep: {step_no} after {kw}"
            + (f" (line {line})" if line else "") + f"\nwhy: {why}\nwhen: {time.strftime('%H:%M:%S')}\n"
            f"controls: {n}" + (f"\niframes: {', '.join(frames)}  (Browser: `<frame> >>> <selector>`)" if frames else "")
            + "\n")
    (d / "page.txt").write_text(page)
    latest = state_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for old in latest.iterdir():
        if old.is_file():
            old.unlink()
    files = []
    for name in ("page.txt", "controls.txt", "aria.yaml", "source.html", "screenshot.jpg", "screenshot.png"):
        f = d / name
        if f.is_file():
            try:
                os.link(f, latest / name)
            except OSError:
                import shutil

                shutil.copyfile(f, latest / name)
            files.append((name, f.stat().st_size))
    ctl = [r for r in rows if r and not r.startswith("#")]
    res.update(files=files, n_controls=n, iframes=frames, controls_top=ctl[:8], controls_all=ctl[:300])
    try:                                   # one line per capture: step, time, keyword, line, url, title, dir
        with open(state_dir / "history.tsv", "a") as hf:
            hf.write("\t".join([f"{step_no:03d}", time.strftime("%H:%M:%S"), kw, str(line or ""), info["url"][:300],
                                 info["title"][:120], d.name]) + "\n")
    except OSError:
        pass
    res["pruned"] = _prune(state_dir, keep, max_bytes)
    res["ms"] = round((time.perf_counter() - t0) * 1000)
    return res
