"""Server-side keyword search over UPLOADED libdoc JSON specs (no libraries installed).

Two rankers:
  * bm25   - pure python BM25 over name(x3) + shortdoc + tags + arg names
  * m2v    - model2vec potion-base-8M embeddings (same family rf-mcp uses), optional
Hybrid = 0.5*bm25_norm + 0.5*cosine.

Run: uv run --no-sync python spec_search.py   (worktree venv has model2vec)
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

SPECS = Path(__file__).resolve().parent.parent / "outputs" / "q2" / "specs"
LIBS = ["Browser", "SeleniumLibrary", "RequestsLibrary", "BuiltIn", "Collections", "String"]
QUERIES = [("click element", "Browser"), ("fill text", "Browser"), ("post json", "RequestsLibrary"),
           ("wait until visible", "SeleniumLibrary"), ("wait until visible", "Browser"), ("get text", None)]
TOK = re.compile(r"[a-z0-9]+")


def toks(s: str) -> list[str]:
    return TOK.findall(s.lower())


def load() -> list[dict]:
    docs = []
    for lib in LIBS:
        spec = json.loads((SPECS / f"{lib}.raw.json").read_text())
        for kw in spec["keywords"]:
            text_tokens = toks(kw["name"]) * 3 + toks(kw.get("shortdoc", "")) + toks(" ".join(kw.get("tags", []))) \
                + toks(" ".join(a["name"] for a in kw["args"]))
            docs.append({"lib": lib, "name": kw["name"], "tokens": text_tokens,
                         "text": f"{kw['name']}. {kw.get('shortdoc', '')}"})
    return docs


class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = sum(len(d["tokens"]) for d in docs) / len(docs)
        df = Counter(t for d in docs for t in set(d["tokens"]))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d["tokens"]) for d in docs]

    def score(self, q):
        qt = toks(q)
        out = []
        for i, d in enumerate(self.docs):
            s, L = 0.0, len(d["tokens"])
            for t in qt:
                f = self.tf[i].get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * L / self.avg))
            out.append(s)
        return out


def main() -> None:
    t0 = time.perf_counter()
    docs = load()
    bm = BM25(docs)
    t_index = time.perf_counter() - t0
    emb = None
    try:
        from model2vec import StaticModel
        import numpy as np
        t1 = time.perf_counter()
        model = StaticModel.from_pretrained("minishlab/potion-base-8M")
        E = model.encode([d["text"] for d in docs])
        E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
        emb = (model, E, np)
        t_emb = time.perf_counter() - t1
    except Exception as e:  # noqa: BLE001
        t_emb = None
        print("model2vec unavailable:", e, file=sys.stderr)
    print(f"# indexed {len(docs)} keywords from {len(LIBS)} specs: bm25 {t_index*1000:.0f} ms, "
          f"model2vec embed {t_emb if t_emb is None else round(t_emb, 2)} s")
    results = []
    for q, lib in QUERIES:
        for scoped in (False, True):
            if scoped and not lib:
                continue
            t2 = time.perf_counter()
            s_bm = bm.score(q)
            mx = max(s_bm) or 1.0
            s = [x / mx for x in s_bm]
            if emb:
                model, E, np = emb
                qv = model.encode([q])[0]
                qv = qv / (np.linalg.norm(qv) + 1e-9)
                cos = (E @ qv).tolist()
                s = [0.5 * a + 0.5 * c for a, c in zip(s, cos)]
            idx = [i for i in range(len(docs)) if not scoped or docs[i]["lib"] in (lib, "BuiltIn")]
            idx.sort(key=lambda i: -s[i])
            top = [f"{docs[i]['lib']}.{docs[i]['name']}" for i in idx[:6]]
            dt = time.perf_counter() - t2
            results.append({"query": q, "scope": lib if scoped else None, "ms": round(dt * 1000, 1), "top": top})
            print(f"{q!r:<22} scope={str(lib) if scoped else 'all':<16} {dt*1000:5.1f} ms -> {top}")
    (SPECS.parent / "spec_search_results.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
