"""Round-5 page-capture prototype (research only).

Import in a robotcode REPL session:  Library    /abs/path/rfcapture.py    state_dir=.rf/state
Keywords:
  Capture Page    <step_kw>    [why]          -> writes .rf/state/step-<n>-<slug>/ + latest/, returns inline summary
  Measure Capture Costs    <label>    <reps>  -> appends timing/size rows to costs.jsonl (Browser or Selenium)

Works with whichever of Browser / SeleniumLibrary is imported (Browser preferred).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from robot.libraries.BuiltIn import BuiltIn

# --- one JS walker for both libraries ------------------------------------------------------------
# Returns compact control rows; walks open shadow roots; same-origin iframes via contentDocument
# (cross-origin / file:// iframes are reported as frame rows and inventoried separately by the caller).
CONTROLS_JS_BODY = r"""
const MAX = (typeof __max === 'number') ? __max : 150;
const Q = 'input:not([type=hidden]),select,textarea,button,a[href],summary,[contenteditable=""],[contenteditable=true],' +
  '[role=button],[role=link],[role=checkbox],[role=radio],[role=switch],[role=combobox],[role=tab],[role=menuitem],' +
  '[role=textbox],[role=option],iframe,frame';
const clean = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 60);
const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
const role = (e) => e.getAttribute('role') || ({A:'link',BUTTON:'button',SELECT:'combobox',TEXTAREA:'textbox',
  IFRAME:'iframe',FRAME:'iframe',SUMMARY:'button'}[e.tagName]) ||
  (e.tagName === 'INPUT' ? ({checkbox:'checkbox',radio:'radio',submit:'button',button:'button',reset:'button',
  image:'button',range:'slider',number:'spinbutton',file:'file'}[e.type] || 'textbox') : e.tagName.toLowerCase());
const name = (e, root) => {
  if (e.getAttribute('aria-label')) return clean(e.getAttribute('aria-label'));
  if (e.id) { try { const l = root.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return clean(l.innerText || l.textContent); } catch (x) {} }
  const pl = e.closest('label'); if (pl) return clean(pl.innerText || pl.textContent);
  const t = ['INPUT', 'SELECT', 'TEXTAREA', 'IFRAME', 'FRAME'].includes(e.tagName) ? '' : clean(e.innerText || e.textContent);
  return t || clean(e.getAttribute('placeholder') || e.getAttribute('title') || e.getAttribute('alt') || e.getAttribute('name') || '');
};
const sel = (e) => {
  for (const a of ['data-test', 'data-testid', 'data-test-id']) if (e.getAttribute(a)) return '[' + a + '="' + e.getAttribute(a) + '"]';
  if (e.id) return 'id=' + e.id;
  if (e.getAttribute('name')) return e.tagName.toLowerCase() + '[name="' + e.getAttribute('name') + '"]';
  const t = clean(e.innerText || e.textContent);
  if (t && t.length <= 40 && ['A','BUTTON'].includes(e.tagName)) return 'text="' + t + '"';
  if (e.getAttribute('placeholder')) return '[placeholder="' + e.getAttribute('placeholder') + '"]';
  return e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/)[0] : '');
};
const out = []; let total = 0; const seen = new Set();
const walk = (root, scope) => {
  root.querySelectorAll(Q).forEach((e) => {
    total++;
    if (out.length >= MAX) return;
    const v = vis(e);
    let st = [];
    if (!v) st.push('hidden');
    if (e.disabled) st.push('disabled');
    if (e.checked) st.push('checked');
    if (e.tagName === 'SELECT') st.push('opts=' + Array.from(e.options).slice(0, 6).map(o => clean(o.text)).join('/'));
    out.push([scope, role(e), name(e, root), sel(e), st.join(',')]);
    if ((e.tagName === 'IFRAME' || e.tagName === 'FRAME')) {
      let d = null; try { d = e.contentDocument; } catch (x) {}
      if (d) walk(d, scope + (scope ? ' >>> ' : '') + sel(e));
    }
  });
  root.querySelectorAll('*').forEach((e) => { if (e.shadowRoot && !seen.has(e)) { seen.add(e); walk(e.shadowRoot, scope + (scope ? ' ' : '') + 'shadow(' + sel(e) + ')'); } });
};
walk(document, '');
return {total: total, rows: out};
"""

BROWSER_JS = "() => { const __max = 150; " + CONTROLS_JS_BODY + " }"
SELENIUM_JS = "var __max = 150; " + CONTROLS_JS_BODY


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:30] or "step"


def _norm_html(src: str) -> str:
    # dedup key: drop scripts/styles/whitespace/volatile attributes (nonce, csrf-ish tokens, ids with digits runs)
    s = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", src, flags=re.S | re.I)
    s = re.sub(r'\s(nonce|data-reactid|data-v-[a-z0-9]+|value)="[^"]*"', "", s)
    return re.sub(r"\s+", " ", s)


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:12]


class rfcapture:  # noqa: N801  (RF library)
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self, state_dir: str = ".rf/state", keep: int = 30):
        self.state = Path(state_dir).resolve()
        self.keep = int(keep)
        self.n = 0
        self.last_hash: Dict[str, str] = {}

    # ------------------------------------------------------------------ helpers
    def _libs(self) -> Tuple[Any, Any]:
        def get(n):
            try:
                return BuiltIn().get_library_instance(n)
            except Exception:
                return None
        return get("Browser"), get("SeleniumLibrary")

    def _frames_browser(self, br) -> List[str]:
        out = []
        try:
            n = int(br.get_element_count("iframe") or 0)
        except Exception:
            return out
        for i in range(min(n, 6)):
            nth = f"iframe >> nth={i}"
            fid = None
            try:
                fid = br.get_attribute(nth, "id")
            except Exception:
                pass
            out.append(f"id={fid}" if fid else nth)
        return out

    # ------------------------------------------------------------------ measurement
    def measure_capture_costs(self, label: str, reps: int = 5, outfile: str = "costs.jsonl"):
        br, se = self._libs()
        reps = int(reps)
        rows: List[Dict[str, Any]] = []
        tmp = self.state / "_measure"
        tmp.mkdir(parents=True, exist_ok=True)

        def bench(op: str, fn, size=lambda r: len(str(r)), check=None):
            ts, sz, extra = [], None, {}
            err = None
            for i in range(reps):
                t0 = time.perf_counter()
                try:
                    r = fn(i)
                except Exception as e:  # record and continue
                    err = f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"
                    ts.append((time.perf_counter() - t0) * 1000)
                    break
                ts.append((time.perf_counter() - t0) * 1000)
                sz = size(r)
                if check:
                    extra = check(r)
            row = {"label": label, "op": op, "n": len(ts), "median_ms": round(statistics.median(ts), 1),
                   "min_ms": round(min(ts), 1), "max_ms": round(max(ts), 1), "bytes": sz, **extra}
            if err:
                row["error"] = err
            rows.append(row)

        def has(r, *needles):
            s = str(r)
            return {f"has:{n}": (n in s) for n in needles}

        needles = ("Pay now", "Shadow Button", "Card number")
        if br is not None:
            bench("get_url", lambda i: br.get_url())
            bench("get_title", lambda i: br.get_title())
            bench("get_page_source", lambda i: br.get_page_source(), size=lambda r: len(str(r).encode()),
                  check=lambda r: has(r, *needles))
            bench("aria_body_default", lambda i: br.get_aria_snapshot("css=body"), size=lambda r: len(str(r).encode()),
                  check=lambda r: has(r, *needles))
            bench("aria_html_default", lambda i: br.get_aria_snapshot("css=html"), size=lambda r: len(str(r).encode()),
                  check=lambda r: has(r, *needles))
            bench("aria_body_ai", lambda i: br.get_aria_snapshot("css=body", mode="ai"),
                  size=lambda r: len(str(r).encode()), check=lambda r: has(r, *needles, "[ref="))
            bench("aria_body_depth4", lambda i: br.get_aria_snapshot("css=body", depth=4),
                  size=lambda r: len(str(r).encode()), check=lambda r: has(r, *needles))
            frames = self._frames_browser(br)
            if frames:
                bench("aria_iframe0_default", lambda i: br.get_aria_snapshot(f"{frames[0]} >>> css=body"),
                      size=lambda r: len(str(r).encode()), check=lambda r: has(r, *needles))
            bench("controls_js_main", lambda i: br.evaluate_javascript("css=body", BROWSER_JS.replace("() =>", "(b) =>")),
                  size=lambda r: len(json.dumps(r)), check=lambda r: {"rows": len(r.get("rows", [])), "total": r.get("total"),
                                                                     **has(json.dumps(r), *needles)})
            if frames:
                bench("controls_js_iframe0", lambda i: br.evaluate_javascript(f"{frames[0]} >>> css=body",
                                                                                BROWSER_JS.replace("() =>", "(b) =>")),
                      size=lambda r: len(json.dumps(r)), check=lambda r: {"rows": len(r.get("rows", []))})
            for ft, q in (("png", None), ("jpeg", 80), ("jpeg", 50)):
                def shot(i, ft=ft, q=q):
                    kw = dict(fileType=ft, fullPage=False, log_screenshot=False)
                    if q:
                        kw["quality"] = q
                    return br.take_screenshot(filename=str(tmp / f"shot-{ft}-{q}-{i}"), **kw)
                bench(f"screenshot_{ft}{q or ''}", shot, size=lambda r: os.path.getsize(str(r)))
        elif se is not None:
            bench("get_location", lambda i: se.get_location())
            bench("get_title", lambda i: se.get_title())
            bench("get_source", lambda i: se.get_source(), size=lambda r: len(str(r).encode()),
                  check=lambda r: has(r, *needles))
            bench("controls_js", lambda i: se.execute_javascript("return (function(){" + SELENIUM_JS + "})()"),
                  size=lambda r: len(json.dumps(r)), check=lambda r: {"rows": len(r.get("rows", [])), "total": r.get("total"),
                                                                     **has(json.dumps(r), *needles)})
            bench("screenshot_png", lambda i: se.capture_page_screenshot(str(tmp / f"se-{i}.png")),
                  size=lambda r: os.path.getsize(str(r)))
            drv = se.driver

            def cdp_jpeg(i):
                import base64
                d = drv.execute_cdp_cmd("Page.captureScreenshot", {"format": "jpeg", "quality": 60})
                p = tmp / f"se-{i}.jpg"
                p.write_bytes(base64.b64decode(d["data"]))
                return str(p)
            bench("screenshot_cdp_jpeg60", cdp_jpeg, size=lambda r: os.path.getsize(str(r)))

            def cdp_ax(i):
                return drv.execute_cdp_cmd("Accessibility.getFullAXTree", {})
            bench("cdp_full_ax_tree", cdp_ax, size=lambda r: len(json.dumps(r)))
        with open(outfile, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        shutil.rmtree(tmp, ignore_errors=True)
        return rows

    # ------------------------------------------------------------------ the capture design
    def capture_page(self, step_kw: str = "step", why: str = "navigation", screenshot: bool = True):
        """Write one per-step snapshot dir + refresh latest/; return the inline summary (<= 1.5 KB)."""
        br, se = self._libs()
        t0 = time.perf_counter()
        timings: Dict[str, float] = {}

        def timed(k, fn):
            t = time.perf_counter()
            try:
                return fn()
            finally:
                timings[k] = round((time.perf_counter() - t) * 1000, 1)

        if br is not None:
            url, title = timed("url_title", lambda: (br.get_url(), br.get_title()))
            src = timed("source", lambda: str(br.get_page_source()))
        elif se is not None:
            url, title = timed("url_title", lambda: (se.get_location(), se.get_title()))
            src = timed("source", lambda: str(se.get_source()))
        else:
            return "no Browser/SeleniumLibrary imported"
        h_src = timed("hash", lambda: _sha(_norm_html(src)))
        unchanged = (self.last_hash.get("src") == h_src and self.last_hash.get("url") == url)
        self.n += 1
        sdir = self.state / f"step-{self.n:03d}-{_slug(step_kw)}"
        meta: Dict[str, Any] = {"step": self.n, "kw": step_kw, "why": why, "url": url, "title": title,
                                "src_sha": h_src, "unchanged_from_previous": unchanged, "ts": time.strftime("%H:%M:%S")}
        if unchanged:
            # dedup: no new dir, one history line pointing at the previous snapshot
            self.n -= 1
            with open(self.state / "history.tsv", "a") as f:
                f.write(f"-\t{step_kw}\t{why} (unchanged)\t{url}\t{title}\t{h_src}\t{self.last_hash.get('dir')}\n")
            return f"[page] {step_kw}: page unchanged since {self.last_hash.get('dir')} ({url}); .rf/state/latest/ is current"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "source.html").write_text(src)
        rows: List[List[str]] = []
        total = 0
        aria = ""
        frames: List[str] = []
        if br is not None:
            try:
                aria = timed("aria_ai", lambda: str(br.get_aria_snapshot("css=body", mode="ai")))
            except Exception as e:
                aria = timed("aria_default", lambda: str(br.get_aria_snapshot("css=body")))
                meta["aria_ai_error"] = str(e)[:200]
            res = timed("controls", lambda: br.evaluate_javascript("css=body", BROWSER_JS.replace("() =>", "(b) =>")))
            rows, total = res.get("rows", []), res.get("total", 0)
            frames = [r[3] for r in rows if r[1] == "iframe"]
            # cross-origin/file iframes: inventory each through Playwright's frame piercing
            fr_sel = [f for f in self._frames_browser(br)][:4] if frames else []
            for f in fr_sel:
                try:
                    sub = timed(f"controls_{f}", lambda f=f: br.evaluate_javascript(f"{f} >>> css=body",
                                                                                      BROWSER_JS.replace("() =>", "(b) =>")))
                    for r in sub.get("rows", []):
                        r[0] = f + (" >>> " + r[0] if r[0] else "")
                        if not any(x[3] == r[3] and x[0] == r[0] for x in rows):
                            rows.append(r)
                    total += sub.get("total", 0)
                except Exception as e:
                    meta.setdefault("frame_errors", []).append(f"{f}: {str(e)[:120]}")
            if screenshot:
                timed("screenshot", lambda: br.take_screenshot(filename=str(sdir / "screenshot"), fileType="jpeg",
                                                               quality=60, fullPage=False, log_screenshot=False))
        else:
            res = timed("controls", lambda: se.execute_javascript("return (function(){" + SELENIUM_JS + "})()"))
            rows, total = res.get("rows", []), res.get("total", 0)
            if screenshot:
                def cdp():
                    import base64
                    try:
                        d = se.driver.execute_cdp_cmd("Page.captureScreenshot", {"format": "jpeg", "quality": 60})
                        (sdir / "screenshot.jpg").write_bytes(base64.b64decode(d["data"]))
                    except Exception:
                        se.capture_page_screenshot(str(sdir / "screenshot.png"))
                timed("screenshot", cdp)
        if aria:
            (sdir / "aria.yaml").write_text(aria)
        # controls.tsv: one control per line, selector last-but-one -> grep "button" / grep -i "login"
        with open(sdir / "controls.tsv", "w") as f:
            f.write("#scope\trole\tname\tselector\tstate\n")
            for r in rows:
                f.write("\t".join(str(x).replace("\t", " ") for x in r) + "\n")
        (sdir / "url.txt").write_text(f"{url}\n{title}\n")
        meta.update(controls_listed=len(rows), controls_total=total, iframes=frames,
                    bytes={p.name: p.stat().st_size for p in sdir.iterdir()})
        timings["total"] = round((time.perf_counter() - t0) * 1000, 1)
        meta["timings_ms"] = timings
        (sdir / "meta.json").write_text(json.dumps(meta, indent=1))
        # latest/ = real copy (symlinks to dirs confuse some agents' Grep/Glob tools and Windows)
        latest = self.state / "latest"
        shutil.rmtree(latest, ignore_errors=True)
        shutil.copytree(sdir, latest)
        # history index: one line per step (grep-able)
        with open(self.state / "history.tsv", "a") as f:
            f.write(f"{self.n}\t{step_kw}\t{why}\t{url}\t{title}\t{h_src}\t{sdir.name}\n")
        self.last_hash = {"src": h_src, "url": url, "dir": sdir.name}
        self._prune()
        return self._inline(meta, rows, sdir)

    def _prune(self):
        steps = sorted(p for p in self.state.glob("step-*") if p.is_dir())
        for p in steps[: max(0, len(steps) - self.keep)]:
            shutil.rmtree(p, ignore_errors=True)

    def _inline(self, meta: Dict[str, Any], rows: List[List[str]], sdir: Path, budget: int = 1500) -> str:
        """<= budget chars: header, controls collapsed by (role, name), file pointers."""
        head = (f"[page] step {meta['step']} {meta['kw']} -> {meta['url']} \"{meta['title']}\"\n"
                f"controls {meta['controls_listed']}/{meta['controls_total']}"
                + (f"; iframes {', '.join(meta['iframes'])}: use `<frame> >>> <sel>`" if meta["iframes"] else "")
                + "\n")
        foot = (f"more: grep -i '<text>' .rf/state/latest/controls.tsv | aria.yaml | source.html "
                f"(this step: .rf/state/{sdir.name}/)\n")
        pri = {"textbox": 0, "combobox": 0, "checkbox": 1, "radio": 1, "button": 1, "file": 1, "iframe": 4, "link": 3}
        groups: Dict[Tuple[str, str, str], List[List[str]]] = {}
        for r in rows:
            frame = r[0] if r[0] and not r[0].startswith("shadow(") else ""
            groups.setdefault((frame, r[1], r[2][:40]), []).append(r)
        def fmt(key, rs):
            frame, role, name = key
            first = rs[0]
            sel = (frame + " >>> " if frame else "") + first[3]
            st = [x for x in first[4].split(",") if x and not x.startswith("opts=")] + \
                 (["shadow"] if first[0].startswith("shadow(") else [])
            opts = [x for x in first[4].split(",") if x.startswith("opts=")]
            more = f" x{len(rs)} (e.g. {rs[-1][3]})" if len(rs) > 1 else ""
            return (f"- {role} \"{name}\" => {sel}{more}" + (f" [{','.join(st)}]" if st else "")
                    + (f" {opts[0]}" if opts else "") + "\n")
        order = sorted(groups.items(), key=lambda kv: ("hidden" in kv[1][0][4], pri.get(kv[0][1], 2)))
        out, size = [], len(head) + len(foot)
        for i, (k, rs) in enumerate(order):
            ln = fmt(k, rs)
            if size + len(ln) > budget - 40:
                out.append(f"... +{len(order) - i} more groups in controls.tsv\n")
                break
            out.append(ln)
            size += len(ln)
        return head + "".join(out) + foot

    def near_miss(self, selector: str, limit: int = 5) -> str:
        """Grep the latest controls.tsv for the failed selector's distinctive token(s)."""
        import re as _re
        p = self.state / "latest" / "controls.tsv"
        if not p.exists():
            return ""
        toks = [t for t in _re.split(r"[^A-Za-z0-9_-]+", _re.sub(r"^(id|css|xpath|text|data-test)=", "", selector))
                if len(t) >= 3 and t.lower() not in {"css", "xpath", "text", "button", "input", "div", "span", "class"}]
        hits = []
        for line in p.read_text().splitlines()[1:]:
            low = line.lower()
            if any(t.lower() in low for t in toks):
                scope, role, name, sel, st = (line.split("\t") + [""] * 5)[:5]
                frame = scope if scope and not scope.startswith("shadow(") else ""
                hits.append(f"  {role} \"{name}\" => {(frame + ' >>> ') if frame else ''}{sel}" + (f" [{st}]" if st else ""))
        if not hits:
            return f"no control in .rf/state/latest/controls.tsv matches {toks}; check aria.yaml / source.html"
        return "similar controls on the current page:\n" + "\n".join(hits[:limit])
