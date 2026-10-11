"""Print a compact summary of real agent sessions run by agents_run.py (v2 / v3 side by side).

  python3 verify/summarize_runs.py verify/runs/web3.json [--table]
"""
import json
import sys

files = [a for a in sys.argv[1:] if not a.startswith("--")]
rows = []
for f in files:
    try:
        d = json.load(open(f))
    except Exception as e:
        print(f, "ERR", e)
        continue
    for k, r in d.items():
        ok = all((r.get(x) or {}).get("rc") == 0 for x in ("plain_order", "plain_checkout") if x in r)
        c = r.get("ctx") or {}
        rows.append((k, r, ok, c))
        if "--table" in sys.argv:
            continue
        print("==", k, {x: r.get(x) for x in ("wall_s", "timed_out", "turns", "tool_calls", "plain_order",
                                              "plain_checkout", "processes_left_after_exit",
                                              "stray_processes_after_exit", "creds_deleted", "latest_reads",
                                              "kwdoc_reads")})
        print("   ctx", c)
        h = r.get("hooks") or {}
        print("   hooks", {k2: v for k2, v in (h.get("v2") or {}).items() if v}, "denials", h.get("denials"),
              "rewrites", h.get("rewrites"), "stop", h.get("stop_blocks"), "errors", h.get("errors"))
print("| session | pass | wall s | turns | tool calls | edits w/ output | out B/edit | ctx chars/edit | robot B/run "
      "| rechecks (verdicts) | failure classes | orphans |")
print("|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---:|")
for k, r, ok, c in rows:
    rv = c.get("recheck_verdicts") or {}
    print(f"| {k} | {'PASS' if ok else 'fail'} | {r.get('wall_s')} | {r.get('turns') or '-'} | {r.get('tool_calls')} | "
          f"{c.get('edits_with_hook')} | {c.get('out_bytes_per_edit')} | {c.get('ctx_chars_per_edit') or '-'} | "
          f"{c.get('out_bytes_per_robot_run')} | {sum(rv.values())} {rv or ''} | {c.get('fail_classes') or '-'} | "
          f"{(r.get('processes_left_after_exit') or 0) + (r.get('stray_processes_after_exit') or 0)} |")
