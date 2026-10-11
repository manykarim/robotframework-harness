#!/usr/bin/env python3
"""Compact timeline of a cell's hooks.jsonl (+ agent tool events)."""
import json, sys
cell = sys.argv[1]
t0 = json.load(open(f"{cell}/result.json"))["t_start"]
for l in open(f"{cell}/hooks.jsonl"):
    r = json.loads(l)
    p = r.get("payload") or {}
    tool = p.get("tool_name") or p.get("toolName") or (r.get("input") or {}).get("tool", "") if isinstance(r.get("input"), dict) else p.get("tool_name") or p.get("toolName") or ""
    ti = p.get("tool_input", p.get("toolArgs")) or {}
    extra = {k: r[k] for k in ("decision", "marker", "secs", "skipped", "exit", "notes", "passive") if r.get(k)}
    print(f"+{r['wall'] - t0:7.2f}s {r.get('src','')[:7]:7} {r['phase']:5} {r['event'][:28]:28} {str(tool)[:12]:12} {str(ti)[:60]!r:62} {extra}")
