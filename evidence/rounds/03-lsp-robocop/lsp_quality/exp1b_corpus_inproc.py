"""Exp 1b: corpus through the in-process WarmAnalyzer; parity vs round-1 analyze. usage: <py> exp1b_corpus_inproc.py rcexp|wt"""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
t_imp = time.perf_counter()
from warm_analyzer import WarmAnalyzer
t_imp = time.perf_counter() - t_imp
def main():
    global t_imp
    STATIC = HERE.parents[1] / "static"; CORPUS = STATIC / "corpus"
    env = sys.argv[1]
    man = [c for c in json.loads((CORPUS / "manifest.json").read_text()) if c["env"] == env]
    r1 = {r["id"]: r for r in json.loads((STATIC / "outputs" / "static_results.json").read_text())}
    wa = WarmAnalyzer(CORPUS)
    rows = []
    for rep in range(2):
        for c in man:
            r = wa.check(CORPUS / c["file"], min_severity=4)
            codes = sorted({d["code"] for d in r["diags"]})
            an = sorted({str(d["code"]) for d in r1[c["id"]]["diags"]})
            rows.append({"rep": rep, "id": c["id"], "codes": codes, "analyze_codes": an, "same": codes == an, "ms": r["ms"]})
            if rep == 0:
                print(f"{c['id']:<40} {'same' if codes == an else 'DIFF'} {r['ms']:>7} ms {codes}", flush=True)
    ms0 = [x["ms"] for x in rows if x["rep"] == 0]; ms1 = [x["ms"] for x in rows if x["rep"] == 1]
    summ = {"env": env, "import_s": round(t_imp, 3), "init_ms": wa.init_ms, "n": len(man), "same": sum(x["same"] for x in rows if x["rep"] == 0),
            "first_ms_max": max(ms0), "first_ms_median": sorted(ms0)[len(ms0)//2], "rep_ms_median": sorted(ms1)[len(ms1)//2]}
    print(summ)
    (HERE / "results" / f"exp1b_inproc_{env}.json").write_text(json.dumps({"summary": summ, "rows": rows}, indent=1))

if __name__ == '__main__':
    main()
