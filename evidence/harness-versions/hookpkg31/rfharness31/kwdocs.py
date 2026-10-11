"""Keyword search + docs inside the helper (round-2 KwDocs prototype, ported).

* Index = what the LIVE session imported (libraries incl. init args, resources, project libs, the live
  .robot file's own keywords) + optionally extra libraries via `--lib X` (indexed with RF libdoc, no import
  side effects, cached per process).
* Ranking: stdlib BM25 over name x3 + tags + short doc x2 + full doc (hit@5 .93-.96 in round 2).
* Output: signature + owner + short doc (~40-45 tokens per keyword); `doc --full` adds the full doc.
* `*args, **kwargs` signatures (RequestsLibrary decorators) are repaired by unwrapping closures.
"""
from __future__ import annotations

import inspect
import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

from robot.running.context import EXECUTION_CONTEXTS
from robot.utils import getshortdoc, normalize

_STOP = set("a an the to of in on for and or by with from into is are be it its this that as at all whole until "
            "using use given if when which then".split())
_SYN = {"iframe": ["frame"], "frame": ["iframe"], "type": ["fill", "input"], "input": ["fill", "type", "text"],
        "enter": ["fill", "type"], "navigate": ["go", "page", "url"], "open": ["new", "go"], "visit": ["go", "page"],
        "assert": ["should"], "verify": ["should"], "check": ["should"], "screenshot": ["take"],
        "request": ["session"], "status": ["status"], "wait": ["wait"], "dropdown": ["select", "option"]}
_extra_cache: Dict[str, Any] = {}
WELL_KNOWN = ["Browser", "SeleniumLibrary", "RequestsLibrary", "Collections", "String", "OperatingSystem",
              "DateTime", "Process", "XML"]
_STD = {"Collections", "String", "OperatingSystem", "DateTime", "Process", "XML", "Screenshot", "Telnet", "Dialogs"}


def installed(name: str) -> bool:
    if name in _STD:
        return True
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def workspace_libraries(root: Optional[str] = None, limit: int = 300) -> List[str]:
    """Library names referenced in the project's .robot/.resource files (cheap regex, no parsing)."""
    import os

    root = root or os.getcwd()
    out: List[str] = []
    n = 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith(".") and d not in ("node_modules", "results", "venv")]
        for fn in fns:
            if fn.endswith((".robot", ".resource")):
                n += 1
                try:
                    with open(os.path.join(dp, fn), errors="replace") as f:
                        for line in f:
                            m = re.match(r"^Library\s{2,}([\w.]+)\s*(?:$|\s{2})", line)
                            if m and m.group(1) not in out and not m.group(1).endswith(".py"):
                                out.append(m.group(1))
                except OSError:
                    pass
                if n >= limit:
                    return out
    return out


def _stem(w: str) -> str:
    for suf in ("ing", "es", "ed", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _toks(s: str) -> List[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in _STOP]


def _strip(s: str) -> str:
    s = re.sub(r"``(.+?)``", r"\1", s or "")
    s = re.sub(r"`(.+?)`", r"\1", s)
    s = re.sub(r"\*(\S.*?\S|\S)\*", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _live_owners() -> List[Any]:
    ctx = EXECUTION_CONTEXTS.current
    store = getattr(ctx.namespace, "_kw_store", None) if ctx else None
    if store is None:
        return []
    return [o for o in [*store.libraries.values(), *store.resources.values()]
            if str(o.name) != "Easter" and not str(o.name).startswith("robotcode.")]


def _extra_owner(name: str) -> Optional[Any]:
    if name in _extra_cache:
        return _extra_cache[name]
    try:
        from robot.libdocpkg import LibraryDocumentation

        d = LibraryDocumentation(name)
    except Exception:
        d = None
    _extra_cache[name] = d
    return d


def _owner_name(o: Any) -> str:
    n = str(getattr(o, "name", "") or "")
    if n.startswith(".") and n.endswith(".live"):  # generated live resource of a test file
        n = n[1:-5] + ".robot (Keywords section)"
    return n


def _iter(owners: Iterable[Any]) -> Iterable[Tuple[str, Any]]:
    for o in owners:
        for kw in getattr(o, "keywords", None) or ():
            yield _owner_name(o), kw


def _lib_class_method(owner: str, kw: Any) -> Any:
    """libdoc-only keywords (library not imported in the session): find the method on the library class."""
    try:
        import importlib

        mod = importlib.import_module(owner)
        cls = getattr(mod, owner.rsplit(".", 1)[-1], None) or mod
        name = kw.name.lower().replace(" ", "_")
        return next((m for n, m in inspect.getmembers(cls) if n.lower() == name
                     or getattr(m, "robot_name", None) == kw.name), None)
    except Exception:
        return None


def _repair(kw: Any, owner: str = "") -> Optional[List[str]]:
    """`*args, **kwargs` decorator signatures -> real parameters of the wrapped function."""
    meth = getattr(kw, "method", None) or (_lib_class_method(owner, kw) if owner else None)
    f = getattr(meth, "__func__", meth)
    seen = 0
    while f is not None and getattr(f, "__closure__", None) and seen < 5:
        inner = next((c.cell_contents for c in f.__closure__
                      if callable(getattr(c, "cell_contents", None)) and hasattr(c.cell_contents, "__code__")), None)
        if inner is None:
            break
        f, seen = inner, seen + 1
    if not seen or f is None:
        return None
    try:
        return [str(p) for n, p in inspect.signature(f).parameters.items() if n != "self"]
    except (TypeError, ValueError):
        return None


def signature(kw: Any, owner: str = "") -> str:
    spec = getattr(kw, "args", None)
    try:
        args = [str(a) for a in spec] if spec is not None and hasattr(spec, "__iter__") else []
    except Exception:
        args = []
    if not args and spec is not None and str(spec):
        args = [a.strip() for a in str(spec).split(",") if a.strip()]
    if args == ["*args", "**kwargs"]:
        args = _repair(kw, owner) or args
    sig = ", ".join(a.replace("‍", "") for a in args)
    return f"{kw.name}({sig})"


def compact(owner: str, kw: Any) -> Dict[str, Any]:
    d = {"kw": kw.name, "lib": owner, "sig": signature(kw, owner), "doc": _strip(getshortdoc(kw.doc or ""))[:240]}
    tags = [t for t in (getattr(kw, "tags", None) or []) if not str(t).startswith("robot:")]
    if tags:
        d["tags"] = list(map(str, tags))[:6]
    return d


def _bm25(docs: List[Tuple[str, Any, Counter, int]], query: str, limit: int) -> List[Tuple[float, str, Any]]:
    n = max(len(docs), 1)
    avg = sum(d[3] for d in docs) / n if docs else 1.0
    df: Counter = Counter()
    for _, _, tf, _ in docs:
        df.update(tf.keys())
    idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
    qt = _toks(query)
    qt += [_stem(s) for w in list(qt) for s in _SYN.get(w, []) if _stem(s) not in qt]
    scored = []
    for owner, kw, tf, ln in docs:
        s = 0.0
        for w in qt:
            f = tf.get(w)
            if f:
                s += idf[w] * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * ln / avg))
        if s > 0:
            scored.append((s, owner, kw))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def _docs(pairs: Iterable[Tuple[str, Any]]) -> List[Tuple[str, Any, Counter, int]]:
    out = []
    for owner, kw in pairs:
        doc = kw.doc or ""
        words = (_toks(kw.name) * 3 + _toks(" ".join(map(str, getattr(kw, "tags", None) or [])))
                 + _toks(getshortdoc(doc)) * 2 + _toks(doc))
        out.append((owner, kw, Counter(words), len(words)))
    return out


def _owners_for(libs: Optional[List[str]]) -> Tuple[List[Any], List[str]]:
    live = _live_owners()
    if not libs:
        # nothing but BuiltIn imported yet: also index libraries the project's files use, else well-known installed ones
        live_names = {_owner_name(o) for o in live}
        cand = [l for l in workspace_libraries() if l not in live_names]
        if not cand and live_names <= {"BuiltIn"}:
            cand = [l for l in WELL_KNOWN if l not in live_names and installed(l)]
        if not cand:
            return live, []
        libs = sorted(live_names) + cand
    want = [l.strip() for l in libs if l.strip()]
    sel, added = [], []
    for w in want:
        hit = [o for o in live if _owner_name(o).lower() == w.lower()]
        if hit:
            sel += hit
        else:
            ext = _extra_owner(w)
            if ext is not None:
                sel.append(ext)
                added.append(w)
    return sel, added


def search(query: str, limit: int = 5, libs: Optional[List[str]] = None) -> Dict[str, Any]:
    owners, added = _owners_for(libs)
    hits = _bm25(_docs(_iter(owners)), query, int(limit))
    names = sorted({_owner_name(o) for o in owners})
    res: Dict[str, Any] = {"ok": bool(hits), "query": query}
    q = set(_toks(query))
    if q & {"iframe", "frame"} and "Browser" in names:
        res["note"] = ("Browser library has NO switch-frame keyword: address elements inside an iframe as "
                       "`<frame selector> >>> <inner selector>` (skill references/browser.md). "
                       "Select Frame is SeleniumLibrary only.")
    elif q & {"shadow"} and "Browser" in names:
        res["note"] = "Browser css=/text=/id= selectors pierce open shadow roots automatically (skill references/browser.md)"
    res["results"] = [compact(o, k) for _, o, k in hits]
    if added:
        res["not_imported"] = added
        res["import_first"] = "add `Library    <lib>` to *** Settings *** to use these"
    if not hits:
        res["hint"] = "rephrase, or grep .rf/docs/*.md"
    res["searched"] = names
    return res


def doc(name: str, full: bool = False, libs: Optional[List[str]] = None) -> Dict[str, Any]:
    owner_part, kw_part = (name.rsplit(".", 1) if "." in name else (None, name))
    target = normalize(kw_part, ignore="_")
    owners, _ = _owners_for(libs)
    if owner_part and not libs:
        owners = owners + [o for o in [_extra_owner(owner_part)] if o is not None]
    found = []
    for owner, kw in _iter(owners):
        if normalize(kw.name, ignore="_") == target and (not owner_part or owner.lower() == owner_part.lower()):
            found.append((owner, kw))
    if not found:
        # unknown keyword -> closest names (BM25 over names) instead of a bare error
        import difflib

        allk = {k.name: o for o, k in _iter(owners)}
        close = difflib.get_close_matches(kw_part, list(allk), n=5, cutoff=0.6)
        if not close:
            close = [k.name for _, _, k in _bm25(_docs(_iter(owners)), kw_part, 5)]
        return {"ok": False, "error": f"no keyword '{name}' in the session's libraries",
                "did_you_mean": [f"{n} [{allk.get(n, '?')}]" for n in close],
                "hint": "import the library first (Library    X in *** Settings ***)"}
    out = []
    for owner, kw in found[:3]:
        d = compact(owner, kw)
        if full:
            d["doc"] = (kw.doc or "")[:6000]
        out.append(d)
    res: Dict[str, Any] = {"ok": True, "results": out}
    if len(found) > 1:
        res["note"] = "same name in several libraries: call it as Library.Keyword"
    return res
