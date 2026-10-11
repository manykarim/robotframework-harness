"""Apply failure_rules.json to REPL output; for keyword-related failures attach the doc one-liner via kwcache."""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import kwcache
RULES = [(r["id"], re.compile(r["regex"], re.M)) for r in json.load(open(Path(__file__).parent / "failure_rules.json"))]
ALIAS = {  # SeleniumLibrary name used while Browser is imported -> Browser equivalent
    "clickelement": "Click", "clickbutton": "Click", "clicklink": "Click", "inputtext": "Fill Text",
    "inputpassword": "Fill Secret", "waituntilelementisvisible": "Wait For Elements State",
    "waituntilpagecontainselement": "Wait For Elements State", "elementtextshouldbe": "Get Text",
    "pageshouldcontain": "Get Text", "selectfromlistbyvalue": "Select Options By", "selectframe": "(no keyword: use `<iframe-sel> >>> <sel>`)",
    "openbrowser": "New Browser + New Page", "capturepagescreenshot": "Take Screenshot", "getlocation": "Get Url",
}
def classify(text, libs):
    t0 = time.perf_counter(); out = []
    blocks = re.split(r"(?=^\[ (?:FAIL|WARN) \] )", text, flags=re.M)
    for b in blocks:
        if not b.startswith("[ FAIL ]") and not b.startswith("[ WARN ]"):
            continue
        b = b.split("\n[ INFO ]")[0]
        for rid, rx in RULES:
            m = rx.search(b)
            if not m:
                continue
            item = {"rule": rid, "msg": b.splitlines()[0][:160]}
            kw = m.groupdict().get("kw")
            if kw and rid in ("unknown_kw", "arg_count", "unknown_kw_whitespace"):
                owner, _, name = kw.rpartition(".")
                for lib in ([l for l in libs if kwcache.build(l)["lib"] == owner] if owner else libs):
                    d = kwcache.build(lib); r = kwcache.lookup(d, name)
                    if "exact" in r:
                        item["doc"] = f"{d['lib']}.{r['exact']['sig_short']}"
                        break
                    if kwcache.norm(name) in ALIAS and d["lib"] == "Browser":
                        item["doc"] = f"Browser equivalent of SeleniumLibrary '{name}': {ALIAS[kwcache.norm(name)]}"
                        break
                    if r.get("suggestions"):
                        item["doc"] = "did you mean: " + " | ".join(f"{d['lib']}.{s['sig_short']}" for s in r["suggestions"][:2])
            out.append(item)
            break
    return out, round((time.perf_counter() - t0) * 1000, 1)
if __name__ == "__main__":
    text = open(sys.argv[1]).read()
    items, ms = classify(text, sys.argv[2:] or ["Browser", "BuiltIn"])
    for i in items:
        print(json.dumps(i))
    print(f"classified {len(items)} in {ms} ms")
