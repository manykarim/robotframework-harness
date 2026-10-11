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

# v3.1: route / output profile / tokens / OpenRouter cost per session
print()
print("| session | route | model | pass | turns | wall s | tool calls | profile (src) | ctx chars/edit | in+cw / cr / out tok "
      "| est $ | usage Δ $ | key source |")
print("|---|---|---|---|---:|---:|---:|---|---:|---|---:|---:|---|")
for k, r, ok, c in rows:
    tk = r.get("tokens") or {}
    o = r.get("openrouter") or {}
    print(f"| {k} | {r.get('route') or '-'} | {r.get('model')} | {'PASS' if ok else 'fail'} | {r.get('turns') or '-'} | "
          f"{r.get('wall_s')} | {r.get('tool_calls')} | {r.get('profile') or '-'} ({r.get('profile_src') or '-'}) | "
          f"{c.get('ctx_chars_per_edit') or '-'} | {tk.get('in_tok')} / {tk.get('cache_read_tok')} / {tk.get('out_tok')} | "
          f"{o.get('est_cost_usd', '-')} | {o.get('usage_delta_usd', '-')} | {r.get('api_key_source') or '-'} |")
