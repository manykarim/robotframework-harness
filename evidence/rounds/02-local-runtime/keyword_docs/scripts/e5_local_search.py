"""E5: purely LOCAL keyword-discovery strategies over locally generated docs (nothing uploaded).

Corpus: 6 libraries documented in-process with robot.libdocpkg.LibraryDocumentation (worktree venv).
Strategies:
  a1  name substring of the whole query (== `libdoc <Lib> list "<q>"`, REPL `.kw <q>`, `doc keywords <Lib> <q>`)
  a2  libdoc list <tok1> <tok2> ... (OR of name substrings, libdoc/alphabetical order, unranked)
  a3  name-token overlap, ranked by #query tokens in name (generous helper-side variant of a2)
  b   grep: all query tokens present in name+doc (AND), ranked by name hits then doc term frequency
  c   BM25 (stdlib) over name x3 + short doc x2 + full doc, light stemming + stopwords
  d1  rf-mcp KeywordMatcher.discover_keywords (lexical default, ROBOTMCP_SEMANTIC_KEYWORDS unset)
  d2  rf-mcp KeywordMatcher.discover_keywords with ROBOTMCP_SEMANTIC_KEYWORDS=1 (model2vec potion-base-8M)
  d3  pure model2vec cosine over "name. short doc"
  e   hybrid RRF(c, d3)
Scopes: all6 (all libraries) and session (web/api lib + BuiltIn/Collections/String).
Metrics: hit@5, recall@5 (relevant found in top5 / min(5,|rel|)), MRR@10, mean latency per query.
"""
import asyncio, fnmatch, json, math, os, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path

K = Path(__file__).resolve().parents[1]
OUT = K / "outputs/e5"; OUT.mkdir(parents=True, exist_ok=True)
GOLD = json.loads((K / "scripts/gold.json").read_text())
LIBS = ["Browser", "SeleniumLibrary", "RequestsLibrary", "BuiltIn", "Collections", "String"]
CORE = ["BuiltIn", "Collections", "String"]
STACKS = {"browser": ["Browser", *CORE], "selenium": ["SeleniumLibrary", *CORE], "requests": ["RequestsLibrary", *CORE]}

# ---------------------------------------------------------------- corpus
t0 = time.perf_counter()
from robot.libdocpkg import LibraryDocumentation  # noqa: E402
from robot.utils import getshortdoc  # noqa: E402
corpus = []
gen_times = {}
for lib in LIBS:
    s = time.perf_counter()
    d = LibraryDocumentation(lib)
    for kw in d.keywords:
        corpus.append({"id": f"{lib}.{kw.name}", "lib": lib, "name": kw.name, "args": [str(a) for a in kw.args],
                       "tags": list(kw.tags), "short": getshortdoc(kw.doc), "doc": kw.doc})
    gen_times[lib] = round(time.perf_counter() - s, 3)
corpus_s = time.perf_counter() - t0
ids = {c["id"] for c in corpus}
missing = [g for gs in GOLD.values() for g in gs if g not in ids]
assert not missing, f"gold not in corpus: {missing}"
(OUT / "corpus_stats.json").write_text(json.dumps({"n_keywords": len(corpus), "gen_s_per_lib": gen_times,
    "corpus_total_s": round(corpus_s, 3), "corpus_json_bytes": len(json.dumps(corpus))}, indent=1))

# ---------------------------------------------------------------- text utils
STOP = set("a an the to of in on for and or by with from into is are be it its this that as at all whole until "
           "using use given if when which then".split())
def norm_name(s): return re.sub(r"[\s_]", "", s.lower())
def stem(w):
    for suf in ("ing", "es", "ed", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w
def toks(s, keep_stop=False):
    ws = re.findall(r"[a-z0-9]+", s.lower())
    return [stem(w) for w in ws if keep_stop or w not in STOP]

# ---------------------------------------------------------------- strategies
def a1(q, docs):  # whole-query name substring, alphabetical order (libdoc list / .kw / doc keywords)
    pat = f"*{norm_name(q)}*"
    return [c["id"] for c in docs if fnmatch.fnmatchcase(norm_name(c["name"]), pat)]

def a2(q, docs):  # libdoc list t1 t2 ...: OR of substrings, library order
    ts = [t for t in re.findall(r"[a-z0-9]+", q.lower()) if t not in STOP]
    return [c["id"] for c in docs if any(t in c["name"].lower() for t in ts)]

def a3(q, docs):
    ts = set(toks(q))
    scored = [(len(ts & set(toks(c["name"]))), c["id"]) for c in docs]
    return [i for s, i in sorted(scored, key=lambda x: -x[0]) if s > 0]

def b(q, docs):
    ts = toks(q)
    res = []
    for c in docs:
        nt, dt = toks(c["name"]), toks(c["doc"])
        hay = set(nt) | set(dt)
        if all(t in hay for t in ts):
            res.append((sum(t in nt for t in ts), sum(dt.count(t) for t in ts), c["id"]))
    return [i for *_, i in sorted(res, key=lambda x: (-x[0], -x[1]))]

class BM25:
    def __init__(self, docs, k1=1.2, bb=0.75):
        self.ids = [c["id"] for c in docs]
        self.tf = []
        df = Counter()
        for c in docs:
            words = toks(c["name"]) * 3 + toks(" ".join(c["tags"])) + toks(c["short"]) * 2 + toks(c["doc"])
            tf = Counter(words); self.tf.append((tf, len(words))); df.update(tf.keys())
        self.N = len(docs); self.avg = sum(l for _, l in self.tf) / self.N
        self.idf = {w: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for w, n in df.items()}
        self.k1, self.b = k1, bb
    def search(self, q, k=10):
        qt = toks(q); sc = []
        for i, (tf, l) in enumerate(self.tf):
            s = 0.0
            for w in qt:
                f = tf.get(w)
                if f:
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * l / self.avg))
            if s > 0: sc.append((s, self.ids[i]))
        return [i for _, i in sorted(sc, reverse=True)[:k]]

# model2vec
t = time.perf_counter()
from model2vec import StaticModel  # noqa: E402
import numpy as np  # noqa: E402
m2v_import_s = time.perf_counter() - t
t = time.perf_counter()
M2V = StaticModel.from_pretrained("minishlab/potion-base-8M")
m2v_load_s = time.perf_counter() - t
t = time.perf_counter()
EMB = M2V.encode([f"{c['name']}. {c['short']}" for c in corpus]); EMB = EMB / np.linalg.norm(EMB, axis=1, keepdims=True)
m2v_embed_s = time.perf_counter() - t
EMB_IDX = {c["id"]: i for i, c in enumerate(corpus)}
def d3(q, docs, k=10):
    qv = M2V.encode([q])[0]; qv = qv / np.linalg.norm(qv)
    idx = [EMB_IDX[c["id"]] for c in docs]
    sims = EMB[idx] @ qv
    order = np.argsort(-sims)[:k]
    return [docs[i]["id"] for i in order]

def rrf(*lists, k=60, n=10):
    sc = defaultdict(float)
    for L in lists:
        for r, i in enumerate(L): sc[i] += 1 / (k + r + 1)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:n]]

# rf-mcp KeywordMatcher with injected registry
sys.path.insert(0, str(Path("~/workspace/rf-mcp-robotcode/src")))
from robotmcp.components.keyword_matcher import KeywordMatcher, KeywordInfo  # noqa: E402
def make_matcher(libs):
    km = KeywordMatcher()
    for lib in libs:
        km.keyword_registry[lib] = [KeywordInfo(name=c["name"], library=lib, arguments=c["args"], argument_types=[],
                                                documentation=c["doc"], tags=c["tags"]) for c in corpus if c["lib"] == lib]
    km._initialized = True
    return km
LOOP = asyncio.new_event_loop()
def dmatch(km, q, ctx):
    r = LOOP.run_until_complete(km.discover_keywords(q, context=ctx, limit=10))
    return [f"{m['library']}.{m['keyword_name']}" for m in r.get("matches", [])]

# ---------------------------------------------------------------- evaluation
def metrics(ranked, rel):
    top5 = ranked[:5]
    hit = int(any(r in rel for r in top5))
    rec = sum(r in rel for r in top5) / min(5, len(rel))
    mrr = next((1 / (i + 1) for i, r in enumerate(ranked[:10]) if r in rel), 0.0)
    return hit, rec, mrr

def cases(scope):
    out = []
    for q, rel in GOLD.items():
        rel = set(rel)
        if scope == "all6":
            out.append((q, "all6", LIBS, rel)); continue
        libs_in = {r.split(".")[0] for r in rel}
        if libs_in <= set(CORE):
            out.append((q, "browser", STACKS["browser"], rel)); continue
        for st, sl in STACKS.items():
            rr = {r for r in rel if r.split(".")[0] in sl}
            if any(r.split(".")[0] not in CORE for r in rr):
                out.append((q, st, sl, rr))
    return out

results = {}
per_query = []
for scope in ("all6", "session"):
    cs = cases(scope)
    bm_cache, km_cache = {}, {}
    agg = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    for q, st, sl, rel in cs:
        docs = [c for c in corpus if c["lib"] in sl]
        key = tuple(sl)
        if key not in bm_cache:
            tb = time.perf_counter(); bm_cache[key] = BM25(docs); results.setdefault("bm25_build_s", {})[f"{scope}:{st}"] = round(time.perf_counter() - tb, 3)
        ctx = "api" if st == "requests" or (scope == "all6" and any(r.startswith("RequestsLibrary") for r in rel)) else "web"
        strat = {}
        for name, fn in [("a1", lambda: a1(q, docs)), ("a2", lambda: a2(q, docs)), ("a3", lambda: a3(q, docs)),
                         ("b", lambda: b(q, docs)), ("c", lambda: bm_cache[key].search(q)), ("d3", lambda: d3(q, docs))]:
            ts = time.perf_counter(); strat[name] = (fn(), time.perf_counter() - ts)
        ts = time.perf_counter(); strat["e"] = (rrf(strat["c"][0], strat["d3"][0]), time.perf_counter() - ts + strat["c"][1] + strat["d3"][1])
        for sem in ("d1", "d2"):
            if sem == "d2": os.environ["ROBOTMCP_SEMANTIC_KEYWORDS"] = "1"
            else: os.environ.pop("ROBOTMCP_SEMANTIC_KEYWORDS", None)
            kk = (key, sem)
            if kk not in km_cache:
                tb = time.perf_counter(); km_cache[kk] = make_matcher(sl); dmatch(km_cache[kk], "warm up", "web")
                results.setdefault("matcher_build_s", {})[f"{scope}:{st}:{sem}"] = round(time.perf_counter() - tb, 3)
            ts = time.perf_counter(); strat[sem] = (dmatch(km_cache[kk], q, ctx), time.perf_counter() - ts)
        for name, (ranked, dt) in strat.items():
            h, r, m = metrics(ranked, rel)
            a = agg[name]; a[0] += h; a[1] += r; a[2] += m; a[3] += dt
            per_query.append({"scope": scope, "stack": st, "q": q, "strategy": name, "hit5": h, "rec5": round(r, 2),
                              "mrr": round(m, 2), "n_results": len(ranked), "top5": ranked[:5], "ms": round(dt * 1000, 2)})
    n = len(cs)
    results[scope] = {"n_cases": n, **{k: {"hit@5": round(v[0] / n, 3), "recall@5": round(v[1] / n, 3), "MRR@10": round(v[2] / n, 3),
                                         "ms_per_query": round(v[3] / n * 1000, 2)} for k, v in agg.items()}}
results["model2vec"] = {"import_s": round(m2v_import_s, 3), "load_s": round(m2v_load_s, 3),
                        "embed_corpus_s": round(m2v_embed_s, 3), "n": len(corpus)}
results["corpus_s"] = round(corpus_s, 3)
(OUT / "e5_results.json").write_text(json.dumps(results, indent=1))
(OUT / "e5_per_query.json").write_text(json.dumps(per_query, indent=1))
order = ["a1", "a2", "a3", "b", "c", "d1", "d2", "d3", "e"]
for scope in ("all6", "session"):
    print(f"\n== scope={scope} cases={results[scope]['n_cases']}")
    print(f"{'strategy':8} {'hit@5':>6} {'rec@5':>6} {'MRR':>6} {'ms/q':>8}")
    for s in order:
        r = results[scope][s]; print(f"{s:8} {r['hit@5']:6.3f} {r['recall@5']:6.3f} {r['MRR@10']:6.3f} {r['ms_per_query']:8.2f}")
print("\ncorpus", results["corpus_s"], "s; model2vec", results["model2vec"], "; bm25 build", results.get("bm25_build_s"),
      "; matcher build", results.get("matcher_build_s"))
