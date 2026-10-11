"""Build the per-case detection matrix (markdown) from outputs/static_results.json + stub runs."""
import json
from pathlib import Path
O = Path(__file__).resolve().parent.parent / "outputs"
res = json.loads((O / "static_results.json").read_text())
stub_an = json.loads((O / "analyze_corpus_stubs_bare.json").read_text())["diagnostics"]
stub_dry = {r["id"]: r["typed_stub_dry"] for r in json.loads((O / "dryrun_typed_stubs_bare.json").read_text())}
def ok(expect, verdict):
    bad = verdict in ("error", "warn")
    return (bad if expect != "ok" else not bad)
rows, tally = [], {"an": 0, "dry": 0, "union": 0, "stub_an": 0, "stub_dry": 0}
n_b = n_v = 0
fp = {"an": [], "dry": []}
for r in res:
    cid = r["id"]
    base = cid.split("+")[0]
    sa = stub_an.get(f"cases/{base}.robot", [])
    sa_v = "error" if any(d["severity"] == 1 for d in sa) else ("warn" if sa else "ok")
    sd = stub_dry.get(base, "-")
    union = "error" if "error" in (r["analyze_verdict"], r["dryrun_verdict"]) else ("warn" if "warn" in (r["analyze_verdict"], r["dryrun_verdict"]) else "ok")
    if "+" in cid:
        sa_v = sd = "n/a"
    if r["expect"] == "ok":
        n_v += 1
        if not ok("ok", r["analyze_verdict"]): fp["an"].append(cid)
        if not ok("ok", r["dryrun_verdict"]): fp["dry"].append(cid)
    else:
        n_b += 1
        tally["an"] += ok("error", r["analyze_verdict"])
        tally["dry"] += ok("error", r["dryrun_verdict"])
        tally["union"] += ok("error", union)
        tally["stub_an"] += ok("error", sa_v)
        tally["stub_dry"] += ok("error", sd)
    code = ", ".join(sorted({d["code"] for d in r["diags"]})) or "-"
    mark = lambda v: ("caught" if v in ("error", "warn") else "clean") if r["expect"] != "ok" else ("OK" if v == "ok" else "**FP**")
    rows.append(f"| {cid} | {r['cls']} | {r['expect']} | {mark(r['analyze_verdict'])} | {code} | {mark(r['dryrun_verdict'])} | {mark(sa_v) if sa_v!='n/a' else 'n/a'} | {mark(sd) if sd!='n/a' else 'n/a'} |")
hdr = "| case | planted class | expect | analyze (real libs) | analyze codes | robot --dryrun (rf-mcp today) | analyze w/ spec stubs (server-side) | dryrun w/ typed stubs (server-side) |\n|---|---|---|---|---|---|---|---|"
out = hdr + "\n" + "\n".join(rows)
out += f"\n\nBroken cases caught (of {n_b}): analyze {tally['an']}, dryrun {tally['dry']}, analyze+dryrun union {tally['union']}, stub-analyze {tally['stub_an']}, typed-stub dryrun {tally['stub_dry']}.\n"
out += f"False positives on {n_v} valid controls: analyze {fp['an']}, dryrun {fp['dry']}.\n"
(O / "detection_matrix.md").write_text(out)
print(out[-700:])
