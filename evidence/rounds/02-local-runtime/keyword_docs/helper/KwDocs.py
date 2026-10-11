"""KwDocs — prototype LOCAL keyword-doc/search helper library (would be installed by rf-mcp into the project venv).

Works inside any running RF context (robotcode repl, repl-server executeCell, robot run): it reads the
keyword store of the CURRENT namespace, so it covers exactly what the session imported — libraries with init
args, resource files, project Python libraries — and needs no libdoc spec files and no upload.

Keywords:
  Keyword Doc        name    format=compact|full|json
  Search Keywords    query   limit=5   libraries=*      (BM25 over name x3 + short doc x2 + full doc)
"""
import json
import math
import re
from collections import Counter

from robot.api.deco import keyword, library
from robot.running.context import EXECUTION_CONTEXTS
from robot.utils import getshortdoc, normalize

_STOP = set("a an the to of in on for and or by with from into is are be it its this that as at all whole until "
            "using use given if when which then".split())


def _stem(w):
    for suf in ("ing", "es", "ed", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _toks(s):
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _STOP]


def _strip(s):
    s = re.sub(r"``(.+?)``", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def _owners():
    ctx = EXECUTION_CONTEXTS.current
    store = getattr(ctx.namespace, "_kw_store", None) if ctx else None
    if store is None:
        return []
    return [*store.libraries.values(), *store.resources.values()]


def _iter_keywords():
    for owner in _owners():
        for kw in getattr(owner, "keywords", None) or getattr(owner, "handlers", None) or ():
            yield str(owner.name), kw


def _sig(kw):
    spec = getattr(kw, "args", None)
    try:
        args = [str(a) for a in spec] if spec is not None and hasattr(spec, "__iter__") else []
    except Exception:
        args = []
    if not args and spec is not None:
        args = [str(spec)]
    return f"{kw.name}({', '.join(args)})"


def _compact(owner, kw):
    tags = list(getattr(kw, "tags", []) or [])
    head = f"{_sig(kw)}  [{owner}]" + (f" tags: {', '.join(tags)}" if tags else "")
    return head + "\n" + _strip(getshortdoc(kw.doc or ""))


@library(scope="GLOBAL", auto_keywords=False)
class KwDocs:
    def __init__(self):
        self._index = None
        self._index_key = None

    @keyword("Keyword Doc")
    def keyword_doc(self, name: str, format: str = "compact") -> str:
        target = normalize(name, ignore="_")
        owner_part = None
        if "." in name:
            owner_part, kw_part = name.rsplit(".", 1)
        for owner, kw in _iter_keywords():
            n = normalize(kw.name, ignore="_")
            if n == target or (owner_part and owner.lower() == owner_part.lower() and n == normalize(kw_part, ignore="_")):
                if format == "json":
                    out = json.dumps({"name": kw.name, "owner": owner, "signature": _sig(kw),
                                      "tags": list(kw.tags or []), "short_doc": _strip(getshortdoc(kw.doc or "")),
                                      "doc": kw.doc or ""})
                elif format == "full":
                    out = _compact(owner, kw) + "\n\n" + (kw.doc or "")
                else:
                    out = _compact(owner, kw)
                print(out)
                return out
        raise AssertionError(f"No loaded keyword named '{name}'.")

    def _build(self):
        owners = _owners()
        key = tuple((str(o.name), len(getattr(o, "keywords", ()) or ())) for o in owners)
        if key == self._index_key:
            return self._index
        docs, df = [], Counter()
        for owner, kw in _iter_keywords():
            doc = kw.doc or ""
            words = _toks(kw.name) * 3 + _toks(" ".join(kw.tags or [])) + _toks(getshortdoc(doc)) * 2 + _toks(doc)
            tf = Counter(words)
            docs.append((owner, kw, tf, len(words)))
            df.update(tf.keys())
        n = max(len(docs), 1)
        avg = sum(d[3] for d in docs) / n
        idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self._index, self._index_key = (docs, idf, avg), key
        return self._index

    @keyword("Search Keywords")
    def search_keywords(self, query: str, limit: int = 5, libraries: str = "*") -> str:
        docs, idf, avg = self._build()
        allowed = None if libraries.strip() in ("", "*") else {x.strip().lower() for x in libraries.split(",")}
        qt = _toks(query)
        scored = []
        for owner, kw, tf, ln in docs:
            if allowed and owner.lower() not in allowed:
                continue
            s = 0.0
            for w in qt:
                f = tf.get(w)
                if f:
                    s += idf[w] * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * ln / avg))
            if s > 0:
                scored.append((s, owner, kw))
        scored.sort(key=lambda x: -x[0])
        out = "\n".join(_compact(o, k) for _, o, k in scored[: int(limit)]) or f"No keyword matches '{query}'."
        print(out)
        return out
