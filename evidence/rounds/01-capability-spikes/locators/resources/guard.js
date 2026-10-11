(els, arg) => {
  /* MATCHES: describe the elements a selector resolved to (Playwright resolved them for us).
     arg = {k: max entries}. Returns [{i, tag, loc, role, name, vis, why, dis, cov, wrap}] */
  const k = (arg && arg.k) || 6;
  const css = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s;
  const q = (v) => '"' + String(v).replace(/"/g, '\\"') + '"';
  const IMPLICIT = {a: 'link', button: 'button', select: 'combobox', textarea: 'textbox', summary: 'button', option: 'option', h1: 'heading', h2: 'heading', h3: 'heading', h4: 'heading', h5: 'heading', h6: 'heading', img: 'img', nav: 'navigation', li: 'listitem', dialog: 'dialog', table: 'table', form: 'form'};
  const ARIA = new Set(['link', 'button', 'combobox', 'textbox', 'option', 'heading', 'img', 'navigation', 'listitem', 'dialog', 'table', 'checkbox', 'radio', 'searchbox', 'tab', 'menuitem', 'switch', 'slider', 'spinbutton', 'form', 'main', 'banner', 'region', 'list', 'menu', 'tabpanel', 'row', 'cell', 'gridcell', 'alert']);
  function role(e) {
    const r = e.getAttribute('role'); if (r) return r;
    const t = e.tagName.toLowerCase();
    if (t === 'input') { const ty = (e.type || 'text').toLowerCase();
      if (['button', 'submit', 'reset', 'image'].includes(ty)) return 'button';
      if (ty === 'checkbox') return 'checkbox'; if (ty === 'radio') return 'radio';
      if (ty === 'search') return 'searchbox'; if (ty === 'hidden') return 'none'; return 'textbox'; }
    return IMPLICIT[t] || t;
  }
  function name(e) {
    let n = e.getAttribute('aria-label');
    if (!n && e.id) { const l = e.ownerDocument.querySelector('label[for=' + q(e.id) + ']'); if (l) n = l.innerText; }
    if (!n && e.closest && e.closest('label')) n = e.closest('label').innerText;
    if (!n) n = e.getAttribute('placeholder') || e.getAttribute('title') || e.getAttribute('alt');
    if (!n && e.tagName === 'INPUT' && ['button', 'submit', 'reset'].includes((e.type || '').toLowerCase())) n = e.value;
    if (!n) n = e.innerText || e.textContent || '';
    return String(n).replace(/\s+/g, ' ').trim().slice(0, 40);
  }
  function uniq(doc, sel) { try { return doc.querySelectorAll(sel).length === 1; } catch (x) { return false; } }
  function loc(e) {
    const d = e.getRootNode ? e.getRootNode() : e.ownerDocument;
    for (const a of ['data-test', 'data-testid', 'data-test-id', 'data-qa', 'data-cy']) {
      const v = e.getAttribute(a); if (v && uniq(d, '[' + a + '=' + q(v) + ']')) return '[' + a + '=' + q(v) + ']';
    }
    if (e.id && !/\d{4,}|^[0-9]/.test(e.id) && uniq(d, '#' + css(e.id))) return 'id=' + e.id;
    const nm = e.getAttribute('name'); const tg = e.tagName.toLowerCase();
    if (nm && uniq(d, tg + '[name=' + q(nm) + ']')) return tg + '[name=' + q(nm) + ']';
    const r = role(e), n = name(e);
    if (n && ARIA.has(r)) return 'role=' + r + '[name=' + q(n) + ']';
    const own = (e.innerText || '').replace(/\s+/g, ' ').trim();
    if (own && own.length <= 40) return 'text=' + q(own);
    const dt = e.getAttribute('data-test') || e.getAttribute('data-testid');
    if (dt) return '[data-test=' + q(dt) + '] >> nth=?';
    return null;
  }
  function hiddenWhy(e) {
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    if (s.display === 'none') return 'display:none';
    if (s.visibility === 'hidden') return 'visibility:hidden';
    if (r.width === 0 || r.height === 0) {
      let p = e.parentElement;
      while (p) { if (getComputedStyle(p).display === 'none') return 'ancestor display:none (' + describe(p) + ')'; p = p.parentElement; }
      return 'zero size';
    }
    if (parseFloat(s.opacity) === 0) return 'opacity:0';
    if (r.right + scrollX < 0 || r.bottom + scrollY < 0) {
      const ah = e.closest('[aria-hidden="true"]');
      return 'off-canvas, unreachable by scrolling (' + Math.round(r.x) + ',' + Math.round(r.y) + ')' + (ah ? ' in aria-hidden ' + describe(ah) : '');
    }
    const ah = e.closest('[aria-hidden="true"]'); if (ah) return 'inside aria-hidden ' + describe(ah);
    return null;
  }
  function describe(e) {
    if (!e) return null;
    const t = e.tagName.toLowerCase();
    const cls = (typeof e.className === 'string' && e.className.trim()) ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    return t + (e.id ? '#' + e.id : '') + cls + (e.getAttribute('data-test') ? '[data-test=' + q(e.getAttribute('data-test')) + ']' : '');
  }
  function covered(e) {
    const r = e.getBoundingClientRect(); if (!r.width || !r.height) return null;
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return null;
    const root = e.getRootNode(), hitRoot = root.elementFromPoint ? root : e.ownerDocument;
    const top = hitRoot.elementFromPoint(x, y);
    if (!top || top === e || e.contains(top) || top.contains(e) || (root.host && (top === root.host || top.contains(root.host)))) return null;
    return describe(top);
  }
  function wrapper(e) {
    let p = e.parentElement, hops = 0;
    while (p && hops < 6) { hops++;
      const st = getComputedStyle(p), rc = p.getBoundingClientRect();
      const vis = st.display !== 'none' && st.visibility !== 'hidden' && rc.width > 0 && rc.height > 0;
      if (vis) { const t = p.tagName.toLowerCase();
        if (t === 'label') return {loc: e.id ? 'label >> id=' + e.id : 'text=' + q(p.innerText.trim().slice(0, 40)), why: 'visible <label> wraps hidden control'};
        if (t === 'button' || p.getAttribute('role') === 'button' || p.hasAttribute('onclick')) return {loc: loc(p), why: 'visible clickable ancestor'}; }
      p = p.parentElement; }
    if (e.id) { const l = e.ownerDocument.querySelector('label[for=' + q(e.id) + ']');
      if (l && l.getBoundingClientRect().width > 0 && getComputedStyle(l).visibility !== 'hidden') return {loc: 'label[for=' + q(e.id) + ']', why: 'visible sibling <label for>'}; }
    return null;
  }

  function toSel(l) {
    if (!l) return l;
    let m;
    if ((m = l.match(/^id=(.*)$/))) return 'id:' + m[1];
    if ((m = l.match(/^role=[a-z]+\[name="(.*)"\]$/))) return 'xpath://*[normalize-space()="' + m[1] + '" or @aria-label="' + m[1] + '" or @value="' + m[1] + '"]';
    if ((m = l.match(/^text="(.*)"$/))) return 'xpath://*[normalize-space()="' + m[1] + '"]';
    if (l.includes(' >>> ') || l.includes(' >> ')) return l + '  (Browser-only syntax)';
    return 'css:' + l;
  }
  const SEL_LIB = arg && arg.lib === 'selenium';
  const allLocs = els.map(loc).map(x => SEL_LIB ? toSel(x) : x);
  return els.slice(0, k).map((e, i) => {
    let l = allLocs[i];
    if (l && allLocs.filter(x => x === l).length > 1) l = l + ' >> nth=' + allLocs.slice(0, i).filter(x => x === l).length;
    const o = {i: i, tag: e.tagName.toLowerCase(), loc: l, role: role(e), name: name(e)};
    const why = hiddenWhy(e); o.vis = !why; if (why) o.why = why;
    if (e.disabled || e.getAttribute('aria-disabled') === 'true') o.dis = true;
    if (e.readOnly) o.ro = true;
    if (!why) { const r = e.getBoundingClientRect(); if (r.top > innerHeight || r.left > innerWidth) o.below_fold = true; else { const c = covered(e); if (c) o.cov = c; } }
    if (why) { const w = wrapper(e); if (w) o.wrap = w; }
    return o;
  });
}
//--SPLIT--
(arg) => {
  /* CANDIDATES: rank interactive elements on the page (incl. open shadow roots and same-origin
     iframes) against the tokens of the intended selector. arg = {q: [tokens], k: max} */
  const toks = (arg && arg.q) || [], k = (arg && arg.k) || 8, SEL_LIB = arg && arg.lib === 'selenium';
  function toSel(l) {
    if (!l) return l;
    let m;
    if ((m = l.match(/^id=(.*)$/))) return 'id:' + m[1];
    if ((m = l.match(/^role=[a-z]+\[name="(.*)"\]$/))) return 'xpath://*[normalize-space()="' + m[1] + '" or @aria-label="' + m[1] + '" or @value="' + m[1] + '"]';
    if ((m = l.match(/^text="(.*)"$/))) return 'xpath://*[normalize-space()="' + m[1] + '"]';
    if (l.includes(' >>> ') || l.includes(' >> ')) return l + '  (Browser-only syntax)';
    return 'css:' + l;
  }

  const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=radio],[role=tab],[role=menuitem],[role=option],[role=combobox],[role=textbox],[contenteditable=true],[onclick],[data-test],[data-testid]';
  const INTER = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=radio],[role=tab],[role=menuitem],[role=option],[role=combobox],[role=textbox],[contenteditable=true],[onclick]';
  const q = (v) => '"' + String(v).replace(/"/g, '\\"') + '"';
  const css = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s;
  const out = [];
  function role(e) {
    const r = e.getAttribute('role'); if (r) return r; const t = e.tagName.toLowerCase();
    if (t === 'input') { const ty = (e.type || 'text').toLowerCase();
      if (['button', 'submit', 'reset', 'image'].includes(ty)) return 'button';
      if (ty === 'checkbox' || ty === 'radio') return ty; if (ty === 'search') return 'searchbox'; return 'textbox'; }
    return ({a: 'link', button: 'button', select: 'combobox', textarea: 'textbox', summary: 'button'})[t] || t;
  }
  function name(e) {
    let n = e.getAttribute('aria-label');
    if (!n && e.id) { try { const l = e.ownerDocument.querySelector('label[for=' + q(e.id) + ']'); if (l) n = l.innerText; } catch (x) {} }
    if (!n) n = e.getAttribute('placeholder') || e.getAttribute('title') || e.getAttribute('alt');
    if (!n && e.tagName === 'INPUT' && ['button', 'submit', 'reset'].includes((e.type || '').toLowerCase())) n = e.value;
    if (!n) n = e.innerText || e.textContent || '';
    return String(n).replace(/\s+/g, ' ').trim().slice(0, 40);
  }
  function uniq(root, sel) { try { return root.querySelectorAll(sel).length === 1; } catch (x) { return false; } }
  function loc(e, root) {
    for (const a of ['data-test', 'data-testid', 'data-test-id', 'data-qa', 'data-cy']) {
      const v = e.getAttribute(a); if (v) return '[' + a + '=' + q(v) + ']' + (uniq(root, '[' + a + '=' + q(v) + ']') ? '' : ' (x' + root.querySelectorAll('[' + a + '=' + q(v) + ']').length + ')');
    }
    if (e.id && !/\d{4,}|^[0-9]/.test(e.id) && uniq(root, '#' + css(e.id))) return 'id=' + e.id;
    const nm = e.getAttribute('name'), tg = e.tagName.toLowerCase();
    if (nm && uniq(root, tg + '[name=' + q(nm) + ']')) return tg + '[name=' + q(nm) + ']';
    const n = name(e), rl = role(e);
    if (n && ['link', 'button', 'textbox', 'searchbox', 'checkbox', 'radio', 'combobox', 'tab', 'menuitem', 'option'].includes(rl)) return 'role=' + rl + '[name=' + q(n) + ']';
    if (n && n.length <= 40) return 'text=' + q(n);
    return tg;
  }
  function vis(e) { const s = getComputedStyle(e), r = e.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; }
  function walk(root, frame) {
    let list = []; try { list = root.querySelectorAll(SEL); } catch (x) { return; }
    for (const e of list) {
      const hay = [e.getAttribute('data-test'), e.getAttribute('data-testid'), e.id, e.getAttribute('name'), name(e), e.getAttribute('type'), e.getAttribute('href')].filter(Boolean).join(' ').toLowerCase();
      let sc = 0;
      for (const t of toks) { if (hay.includes(t)) sc += 1; else if (t.length >= 4 && hay.includes(t.slice(0, 4))) sc += 0.5; }
      const it = e.matches(INTER) ? 1 : 0;
      out.push({e: e, root: root, frame: frame, sc: toks.length ? sc / toks.length : 0, v: vis(e), it: it});
    }
    for (const h of root.querySelectorAll('*')) { if (h.shadowRoot) walk(h.shadowRoot, frame ? frame + ' (shadow)' : 'shadow:' + h.tagName.toLowerCase()); }
    for (const f of root.querySelectorAll('iframe,frame')) {
      let d = null; try { d = f.contentDocument; } catch (x) {}
      const fl = f.id ? 'iframe#' + f.id : (f.name ? 'iframe[name=' + q(f.name) + ']' : 'iframe');
      if (d) walk(d, fl); else out.push({e: f, root: root, frame: fl + ' (cross-origin)', sc: 0, v: vis(f)});
    }
  }
  walk(document, null);
  const total = out.length, visible = out.filter(o => o.v).length;
  out.sort((a, b) => (b.sc + 0.5 * b.it - a.sc - 0.5 * a.it) || (b.v - a.v));
  let pick = out.filter(o => o.sc > 0 && o.it).slice(0, k); if (!pick.length) pick = out.filter(o => o.sc > 0).slice(0, k);
  const res = (pick.length ? pick : out.filter(o => o.v && o.it).slice(0, k)).map(o => {
    const base = loc(o.e, o.root); const r = {loc: SEL_LIB ? (o.frame && !o.frame.startsWith('shadow') ? 'Select Frame ' + o.frame + ' ; ' : '') + (o.frame && o.frame.startsWith('shadow') ? 'shadow DOM: css only via Get WebElement+JS ; ' : '') + toSel(base) : (o.frame && !o.frame.startsWith('shadow') ? o.frame.replace(' (cross-origin)', '') + ' >>> ' : '') + base, role: role(o.e), name: name(o.e)};
    if (!o.v) r.hidden = true; if (o.e.disabled) r.dis = true; if (o.frame) r.frame = o.frame; if (o.sc) r.score = Math.round(o.sc * 100) / 100;
    return r;
  });
  const frames = Array.from(document.querySelectorAll('iframe,frame')).slice(0, 4).map((f, i) => f.id ? 'id=' + f.id : (f.name ? '[name=' + q(f.name) + ']' : 'iframe >> nth=' + i));
  return {total: total, visible: visible, ranked: pick.length > 0, cand: res, frames: frames};
}
