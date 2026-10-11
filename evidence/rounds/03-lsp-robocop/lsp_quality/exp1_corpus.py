"""Exp 1: round-1 corpus through robotcode's language server; compare with round-1 `analyze code`.

usage: python exp1_corpus.py <env rcexp|wt> <settings-name default|quiet>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lsp_client import LSP, short, tree_rss_mb  # noqa: E402

STATIC = HERE.parents[1] / "static"
CORPUS = STATIC / "corpus"
ENVS = {"rcexp": "~/workspace/robotcode-experiments/.venv/bin/robotcode",
        "wt": "~/workspace/rf-mcp-robotcode/.venv/bin/robotcode"}
SETTINGS = {
    "default": {},
    "quiet": {"robocop": {"enabled": False}},
}


def main() -> None:
    env, sname = sys.argv[1], sys.argv[2]
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    r1 = {r["id"]: r for r in json.loads((STATIC / "outputs" / "static_results.json").read_text())}
    cases = [c for c in manifest if c["env"] == env or (env == "wt" and c["env"] == "rcexp" and "--all" in sys.argv)]
    lsp = LSP(ENVS[env], CORPUS, log=HERE / "logs" / f"exp1_{env}_{sname}.stderr")
    lsp.initialize(SETTINGS[sname])
    rows = []
    t_first_open = None
    for i, c in enumerate(cases):
        path = CORPUS / c["file"]
        u, v, t0 = lsp.open(path)
        if t_first_open is None:
            t_first_open = t0
        res = lsp.wait_diags(u, v, t0, timeout=90, settle=1.2, source=None)
        rc = [d for d in res["all_diags"] if str(d.get("source", "")).startswith("robotcode")]
        robocop = [d for d in res["all_diags"] if d.get("source") == "robocop"]
        sev = {d.get("severity") for d in rc}
        verdict = "error" if 1 in sev else ("warn" if 2 in sev else ("info" if sev else "ok"))
        a = r1.get(c["id"], {})
        row = {"id": c["id"], "cls": c["cls"], "expect": c["expect"], "lsp_verdict": verdict,
               "lsp_codes": sorted({str(d.get("code")) for d in rc}),
               "analyze_verdict": a.get("analyze_verdict"), "analyze_codes": sorted({str(d["code"]) for d in a.get("diags", [])}),
               "dryrun_verdict": a.get("dryrun_verdict"),
               "first_s": res["first_s"], "last_s": res["last_s"], "publishes": res["publishes"],
               "robocop_n": len(robocop), "robocop_codes": sorted({str(d.get("code")) for d in robocop}),
               "rc_diags": [short(d) for d in rc]}
        rows.append(row)
        same = "same" if row["lsp_codes"] == row["analyze_codes"] else "DIFF"
        print(f"{c['id']:<40} exp={c['expect']:<5} lsp={verdict:<5} an={a.get('analyze_verdict')!s:<5} {same} "
              f"first={res['first_s']} last={res['last_s']} n={res['publishes']} robocop={len(robocop)} "
              f"{row['lsp_codes']} vs {row['analyze_codes']}", flush=True)
        lsp.close(path)
        if i == 0:
            row["rss_after_first_mb"] = tree_rss_mb(lsp.p.pid)
    rss = tree_rss_mb(lsp.p.pid)
    lsp.shutdown()
    out = {"env": env, "settings": sname, "init_s": round(lsp.t_init, 3), "rss_end_mb": rss,
           "server_requests": sorted(set(lsp.server_requests)), "rows": rows}
    (HERE / "results" / f"exp1_corpus_{env}_{sname}.json").write_text(json.dumps(out, indent=1))
    print(f"init {lsp.t_init:.2f}s rss_end={rss} MB server_requests={out['server_requests']}")


if __name__ == "__main__":
    main()
