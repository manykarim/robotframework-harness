"""Exp 2: growing .rf/live.robot -- static diagnostics after every appended step, LSP vs in-process analyzer.

usage: <rcexp-python> exp2_static_fp.py [relpath-of-live-file]   (default .rf/live.robot)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from live_steps import CALL_LIVE_HELPER, HEADER, KEYWORDS_SECTION, STEPS  # noqa: E402
from lsp_client import LSP, short, tree_rss_mb  # noqa: E402

RC = "~/workspace/robotcode-experiments/.venv/bin/robotcode"
PROJ = HERE / "proj"


def main() -> None:
    from warm_analyzer import WarmAnalyzer

    rel = sys.argv[1] if len(sys.argv) > 1 else ".rf/live.robot"
    live = PROJ / rel
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text(HEADER)
    lsp = LSP(RC, PROJ, log=HERE / "logs" / "exp2_lsp.stderr")
    lsp.initialize({"robocop": {"enabled": False}})
    u, v, t0 = lsp.open(live, HEADER)
    r0 = lsp.wait_diags(u, v, t0, timeout=120, settle=1.2)
    print(f"open: first={r0['first_s']} diags={[short(d) for d in r0['diags']]}")
    wa = WarmAnalyzer(PROJ)
    w0 = wa.check(live)
    print(f"inproc open: {w0['ms']} ms {w0['diags']}")
    rows = []
    text = HEADER
    for sid, probe, lines, expect in STEPS:
        start_line = text.count("\n") + 1
        added = "\n".join(lines) + "\n"
        text += added
        step_lines = set(range(start_line, start_line + len(lines)))
        live.write_text(text)
        u, v, t0 = lsp.append(live, added)
        r = lsp.wait_diags(u, v, t0, timeout=30, settle=1.2)
        w = wa.check(live)
        l_new = [short(d) for d in r["diags"] if d["range"]["start"]["line"] + 1 in step_lines and d.get("severity", 1) <= 2]
        w_new = [f"{d['sev'][0].upper()} L{d['line']} {d['code']}: {d['msg'][:110]}" for d in w["diags"] if d["line"] in step_lines]
        l_codes = sorted({d.get("code") for d in r["diags"] if d["range"]["start"]["line"] + 1 in step_lines and d.get("severity", 1) == 1})
        w_codes = sorted({d["code"] for d in w["diags"] if d["line"] in step_lines and d["sev"] == "error"})
        if expect == "clean":
            verdict = "FP" if l_codes else "ok"
        else:
            verdict = "caught" if expect in l_codes else "MISSED"
        row = {"id": sid, "probe": probe, "lines": sorted(step_lines), "expect": expect, "verdict": verdict,
               "lsp_first_s": r["first_s"], "lsp_new": l_new, "inproc_ms": w["ms"], "inproc_new": w_new,
               "same": l_codes == w_codes, "lsp_total": len(r["diags"]), "inproc_total": len(w["diags"])}
        rows.append(row)
        print(f"{sid} {verdict:<6} lsp={r['first_s']}s inproc={w['ms']}ms {'same' if row['same'] else 'DIFF'} | {probe}\n      {l_new}", flush=True)
    # keywords section at the end + call inserted before it
    body_end = text
    text_kw = body_end + KEYWORDS_SECTION
    live.write_text(text_kw)
    u, v, t0 = lsp.replace_all(live, text_kw)
    r = lsp.wait_diags(u, v, t0, timeout=30, settle=1.2)
    call_line = body_end.count("\n") + 1
    text_call = body_end + "\n".join(CALL_LIVE_HELPER) + "\n" + KEYWORDS_SECTION
    live.write_text(text_call)
    u, v, t0 = lsp.replace_all(live, text_call)
    r2 = lsp.wait_diags(u, v, t0, timeout=30, settle=1.2)
    w2 = wa.check(live)
    kwrow = {"id": "kw", "probe": "call user keyword defined in *** Keywords *** of the live file",
             "lsp_new": [short(d) for d in r2["diags"] if d["range"]["start"]["line"] + 1 in (call_line, call_line + 1)],
             "inproc_new": [d for d in w2["diags"] if d["line"] in (call_line, call_line + 1)]}
    rows.append(kwrow)
    print("kw:", kwrow)
    rss = tree_rss_mb(lsp.p.pid)
    lsp.shutdown()
    # CLI analyze on the same file (G1: hidden dir?)
    t = time.perf_counter()
    p = subprocess.run([RC, "-r", str(PROJ), "analyze", "code", "--output-format", "json", str(live)],
                       capture_output=True, text=True, cwd=PROJ)
    try:
        cli = json.loads(p.stdout)
        cli_sum = cli.get("summary")
    except json.JSONDecodeError:
        cli_sum = p.stdout[-300:]
    print(f"CLI analyze {rel}: exit={p.returncode} {time.perf_counter() - t:.2f}s summary={cli_sum}")
    out = {"live": rel, "rss_mb": rss, "rows": rows, "cli_summary": cli_sum, "cli_exit": p.returncode,
           "final_text": text_call}
    (HERE / "results" / f"exp2_static_fp_{rel.replace('/', '_')}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
