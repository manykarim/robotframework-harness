"""Exp 1c: LSP cold start (Browser+Requests+resource), warm one-line-change latency, RSS; stock vs fast-poll launcher.
usage: <rcexp-python> exp1c_latency.py stock|fastpoll [--keep-cache]"""
import json, random, shutil, statistics, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lsp_client import LSP, tree_rss_mb
from live_steps import HEADER, STEPS
PY = "~/workspace/robotcode-experiments/.venv/bin/python"
RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
PROJ = HERE / "proj"
def pct(xs, p):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]
def main():
    mode = sys.argv[1]
    if "--keep-cache" not in sys.argv:
        shutil.rmtree(PROJ / ".robotcode_cache", ignore_errors=True)
    live = PROJ / ".rf" / "latency.robot"
    text = HEADER + "".join("\n".join(l) + "\n" for (_, _, l, e) in STEPS[:10])
    live.write_text(text)
    t_spawn = time.perf_counter()
    if mode == "stock":
        lsp = LSP(RC, PROJ, log=HERE / "logs" / f"exp1c_{mode}.stderr")
    else:
        lsp = LSP(PY, PROJ, extra_args=[str(HERE / "ls_fastpoll.py")], log=HERE / "logs" / f"exp1c_{mode}.stderr")
    lsp.initialize({"robocop": {"enabled": False}})
    t_init = time.perf_counter() - t_spawn
    u, v, t0 = lsp.open(live, text)
    r = lsp.wait_diags(u, v, t0, timeout=180, settle=1.0)
    cold = {"spawn_to_initialized_s": round(t_init, 3), "open_to_first_diag_s": r["first_s"],
            "spawn_to_first_diag_s": round(t0 - t_spawn + (r["first_s"] or 0), 3),
            "diags": [d["code"] for d in r["diags"]], "rss_mb": tree_rss_mb(lsp.p.pid)}
    print("cold", cold, flush=True)
    random.seed(7)
    lat = []
    ok = 0
    for i in range(30):
        time.sleep(random.uniform(0, 1.2))
        bad = i % 2 == 1
        line = f"    Lgo    x{i}\n" if bad else f"    Log    x{i}\n"
        u, v, t0 = lsp.append(live, line)
        r = lsp.wait_diags(u, v, t0, timeout=20, settle=0.25)
        has_err = any(d.get("code") == "KeywordNotFound" and d["range"]["start"]["line"] == lsp.texts[u].count("\n") - 1 for d in r["diags"])
        ok += has_err == bad
        lat.append(r["first_s"])
        if bad:  # fix the bad line again (replace whole doc) so errors don't accumulate
            fixed = lsp.texts[u].replace(f"    Lgo    x{i}\n", f"    Log    x{i}\n")
            u, v, t0 = lsp.replace_all(live, fixed)
            lsp.wait_diags(u, v, t0, timeout=20, settle=0.25)
    lat2 = [x for x in lat if x is not None]
    warm = {"n": len(lat), "missing": len(lat) - len(lat2), "correct": ok, "median_s": round(statistics.median(lat2), 3),
            "p90_s": pct(lat2, 90), "min_s": min(lat2), "max_s": max(lat2), "rss_mb": tree_rss_mb(lsp.p.pid)}
    print("warm", warm, flush=True)
    lsp.shutdown()
    out = {"mode": mode, "cache": "kept" if "--keep-cache" in sys.argv else "cleared", "cold": cold, "warm": warm, "lat": lat}
    (HERE / "results" / f"exp1c_latency_{mode}_{out['cache']}.json").write_text(json.dumps(out, indent=1))
if __name__ == "__main__":
    main()
