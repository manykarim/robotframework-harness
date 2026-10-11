/* copied read-only from rf-mcp branch feature/improve_complex_sites_handling: page_source_service._ACTIONABLE_ELEMENTS_JS */
() => {
  const TAGS = ['input', 'select', 'button', 'textarea', 'a'];

  function isAncestorHidden(el) {
    let p = el.parentElement;
    while (p && p !== document.documentElement) {
      const st = window.getComputedStyle(p);
      if (st.display === 'none' || st.visibility === 'hidden') return true;
      p = p.parentElement;
    }
    return false;
  }

  function displayState(el, st) {
    const rect = el.getBoundingClientRect();
    if (st.display === 'none') return 'display:none';
    if (st.visibility === 'hidden') return 'visibility:hidden';
    if (rect.width === 0 && rect.height === 0) return 'off-screen';
    if (rect.bottom < 0 || rect.top > window.innerHeight ||
        rect.right < 0 || rect.left > window.innerWidth) return 'off-screen';
    return 'visible';
  }

  function isElVisible(el) {
    const st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  // Walk up to 6 ancestors to find a visible actionable wrapper for a hidden element.
  // Returns a surface descriptor or null.
  function findActionableSurface(el, elId) {
    let p = el.parentElement;
    let hops = 0;
    while (p && p !== document.documentElement && hops < 6) {
      hops++;
      const tag = p.tagName.toLowerCase();
      if (!isElVisible(p)) { p = p.parentElement; continue; }

      // <label> wrapping the element — highest priority for styled-radio/checkbox patterns
      if (tag === 'label') {
        const sel = elId ? '*css=label >> id=' + elId : '*css=label';
        const txt = (p.innerText || p.textContent || '').trim().slice(0, 80);
        return {selector: sel, wrapper_tag: 'label', wrapper_text: txt || undefined, wrapper_visible: true};
      }

      // <section> with display:block used by idealsteps/wizard scoping
      if (tag === 'section') {
        const inlineStyle = (p.getAttribute('style') || '').replace(/\s/g, '').toLowerCase();
        if (inlineStyle.includes('display:block')) {
          const styleAttr = p.getAttribute('style') || '';
          const sel = elId ? 'section[style="' + styleAttr + '"] >> id=' + elId : 'css=section';
          return {selector: sel, wrapper_tag: 'section', wrapper_visible: true, scope_kind: 'wizard_step'};
        }
      }

      // Visible button / role=button / onclick element
      const role = p.getAttribute('role') || '';
      const hasOnclick = p.hasAttribute('onclick');
      const ariaLabel = p.getAttribute('aria-label') || '';
      if (tag === 'button' || role === 'button' || hasOnclick) {
        const btnSel = elId ? '#' + elId : (ariaLabel ? '[aria-label="' + ariaLabel + '"]' : tag);
        return {selector: btnSel, wrapper_tag: tag, wrapper_visible: true,
                wrapper_text: (p.innerText || '').trim().slice(0, 80) || undefined,
                aria_label: ariaLabel || undefined};
      }

      p = p.parentElement;
    }
    return null;
  }

  const results = [];
  const seen = new Set();

  for (const tag of TAGS) {
    for (const el of document.querySelectorAll(tag)) {
      if (seen.has(el)) continue;
      seen.add(el);

      const st = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      const entry = {};

      entry.tag = el.tagName.toLowerCase();

      if (el.id) entry.id = el.id;
      if (el.name) entry.name = el.name;

      const t = (el.type || '').toLowerCase();
      if (t) entry.type = t;

      const al = el.getAttribute('aria-label') || null;
      if (al) entry.aria_label = al;

      const txt = (el.value || el.textContent || el.innerText || '').trim().slice(0, 80);
      if (txt) entry.text = txt;

      entry.bounding_rect = {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      };

      const ds = displayState(el, st);
      entry.display_state = ds;
      entry.disabled = el.disabled === true;
      entry.parent_hidden = isAncestorHidden(el);

      // Only walk ancestors for elements that are themselves hidden/off-screen.
      if (ds !== 'visible') {
        const surface = findActionableSurface(el, el.id || null);
        if (surface) entry.actionable_surface = surface;
      }

      results.push(entry);
    }
  }
  return results;
}
