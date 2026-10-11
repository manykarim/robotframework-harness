"""E6: compact per-keyword doc formats — sizes, and recovering real params of `*args, **kwargs` keywords locally.

C0 signature only; C1 signature + short doc (first paragraph); C2 C1 + argument notes (Browser-style arg table rows,
<=120 chars each) + first example line; FULL raw doc. Run in the worktree venv (RF 7.3.2, Browser 19.12, Selenium, Requests).
"""
import inspect, json, re, statistics
from pathlib import Path
from robot.libdocpkg import LibraryDocumentation
from robot.utils import getshortdoc

K = Path(__file__).resolve().parents[1]
OUT = K / "outputs/e6"; OUT.mkdir(parents=True, exist_ok=True)
GOLD = json.loads((K / "scripts/gold.json").read_text())
gold_ids = {g for gs in GOLD.values() for g in gs}
LIBS = ["Browser", "SeleniumLibrary", "RequestsLibrary", "BuiltIn", "Collections", "String"]

def strip_markup(s):
    s = re.sub(r"``(.+?)``", r"\1", s); s = re.sub(r"`(.+?)`", r"\1", s)
    s = re.sub(r"\*(\S.*?\S|\S)\*", r"\1", s)
    return re.sub(r"[ \t]+", " ", s).strip()

def recover_params(lib_obj, kw):
    """For `*args, **kwargs` signatures: find the real function inside decorator closures."""
    if [str(a) for a in kw.args] != ["*args", "**kwargs"] or lib_obj is None:
        return None
    meth_name = None
    for name, member in inspect.getmembers(type(lib_obj)):
        rn = getattr(member, "robot_name", None)
        if rn == kw.name or name.replace("_", " ").lower() == kw.name.lower():
            meth_name = name; break
    if meth_name is None:
        return None
    f = getattr(type(lib_obj), meth_name)
    seen = 0
    while getattr(f, "__closure__", None) and seen < 5:
        inner = next((c.cell_contents for c in f.__closure__ if callable(getattr(c, "cell_contents", None))
                      and hasattr(c.cell_contents, "__code__")), None)
        if inner is None: break
        f = inner; seen += 1
    sig = inspect.signature(f)
    params = [str(p) for n, p in sig.parameters.items() if n != "self"]
    return params if seen else None

def arg_notes(doc):
    rows = re.findall(r"^\|\s*``?(\w+)``?\s*\|\s*(.+?)\s*\|\s*$", doc, flags=re.M)
    return [f"{n}: {strip_markup(d)[:120]}" for n, d in rows if n.lower() not in ("arguments", "argument")]

def first_example(doc):
    m = re.search(r"(?:Example|Examples)s?:?\s*\n+(?:\|\s*)?(.+)", doc)
    if m:
        return strip_markup(m.group(1).split("\n")[0])[:160]
    m = re.search(r"^\| (.+?) \|.*$", doc, flags=re.M)
    return None

rows, recovered = [], []
for lib in LIBS:
    d = LibraryDocumentation(lib)
    lib_obj = None
    if lib == "RequestsLibrary":
        import RequestsLibrary
        lib_obj = RequestsLibrary.RequestsLibrary()
    for kw in d.keywords:
        args = [str(a) for a in kw.args]
        real = recover_params(lib_obj, kw)
        if real:
            recovered.append({"kw": f"{lib}.{kw.name}", "libdoc_args": args, "recovered": real})
            args = real
        sig = f"{kw.name}({', '.join(args)})"
        c0 = f"{sig}  [{lib}]"
        short = strip_markup(getshortdoc(kw.doc))
        c1 = c0 + (f" tags: {', '.join(kw.tags)}" if kw.tags else "") + "\n" + short
        notes = arg_notes(kw.doc); ex = first_example(kw.doc)
        c2 = c1 + ("".join(f"\n  - {n}" for n in notes)) + (f"\n  e.g. {ex}" if ex else "")
        rows.append({"id": f"{lib}.{kw.name}", "C0": len(c0), "C1": len(c1), "C2": len(c2), "FULL": len(kw.doc) + len(c0),
                     "c1_text": c1, "c2_text": c2})

def stats(sel, key):
    v = [r[key] for r in sel]
    return {"mean": round(statistics.mean(v)), "median": round(statistics.median(v)), "p90": round(sorted(v)[int(len(v) * .9)]),
            "sum_top5_mean": round(statistics.mean(v) * 5)}
res = {}
for label, sel in (("all", rows), ("gold", [r for r in rows if r["id"] in gold_ids])):
    res[label] = {"n": len(sel), **{k: stats(sel, k) for k in ("C0", "C1", "C2", "FULL")}}
res["recovered_signatures"] = recovered
(OUT / "e6_results.json").write_text(json.dumps(res, indent=1))
(OUT / "e6_samples.txt").write_text("\n\n".join(r["c2_text"] for r in rows if r["id"] in
    {"Browser.Fill Text", "Browser.Click", "RequestsLibrary.POST On Session", "SeleniumLibrary.Wait Until Element Is Visible",
     "BuiltIn.Should Be Equal", "Collections.Get From Dictionary", "Browser.Wait For Elements State"}))
for label in ("all", "gold"):
    r = res[label]
    print(label, "n=", r["n"], " ".join(f"{k}: mean {r[k]['mean']} med {r[k]['median']} p90 {r[k]['p90']}" for k in ("C0", "C1", "C2", "FULL")))
print("recovered", len(recovered), "of RequestsLibrary *args/**kwargs keywords:")
for x in recovered[:6]:
    print("  ", x["kw"], "->", ", ".join(x["recovered"]))
