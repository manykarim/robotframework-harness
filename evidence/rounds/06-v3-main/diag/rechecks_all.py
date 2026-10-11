#!/usr/bin/env python3
"""SLOW/MISSING verdicts across agents: Claude + OpenCode parsed from transcript text, Codex from row metrics."""
import gzip, json, re, importlib.util
from collections import Counter
from pathlib import Path
D = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pc", D / "parse_claude.py"); pc = importlib.util.module_from_spec(spec); spec.loader.exec_module(pc)
H = pc.H
rows = [json.loads(l) for l in open(H / "results_live_v2.jsonl")]
out = []
for r in rows:
    if r["arm"] != "hookpkg2": continue
    texts = []
    if r["agent"] == "opencode":
        for l in gzip.open(H / r["transcript"], "rt"):
            if not l.startswith("{"): continue
            p = (json.loads(l).get("part") or {})
            o = ((p.get("state") or {}).get("output") or "") if p.get("type") == "tool" else ""
            if "[Robot Framework hook]" in o: texts.append(o)
    elif r["agent"] == "claude":
        for l in gzip.open(H / r["transcript"], "rt"):
            if not l.startswith("{"): continue
            o = json.loads(l)
            if o.get("type") == "system" and o.get("subtype") == "hook_response" and (o.get("hook_name") or "").startswith("PostToolUse"):
                texts.append(pc.hook_text(o.get("output") or ""))
    for t in texts:
        for rc in pc.parse_recheck(t):
            rc.update(agent=r["agent"], scenario=r["scenario"], rep=r["rep"]); out.append(rc)
json.dump(out, open(D / "rechecks_all.json", "w"), indent=1)
for ag in ("claude", "opencode"):
    R = [x for x in out if x["agent"] == ag]
    slow = [x for x in R if x["verdict"] == "slow"]; miss = [x for x in R if x["verdict"] == "missing"]
    print(f"== {ag}: rechecks {len(R)} slow {len(slow)} missing {len(miss)}")
    print("  SLOW appeared<=short+0.3 s (element present at once):", sum(1 for x in slow if x["appeared"] <= x["short"] + 0.3),
          " genuine (>short+0.3):", sorted(x["appeared"] for x in slow if x["appeared"] > x["short"] + 0.3))
    print("  SLOW passed after recheck:", sum(x["passed_after"] for x in slow), " msg had 'locator resolved to':", sum(x["resolved"] for x in slow))
    print("  SLOW by scenario:", Counter(x["scenario"] for x in slow).most_common())
    print("  MISSING mode:", Counter(x.get("mode") for x in miss), " instant+resolved (element exists):", sum(1 for x in miss if x.get("mode") == "stable_instant" and x["resolved"]),
          " similar==same selector:", sum(1 for x in miss if x.get("similar_same")))
    print("  MISSING by scenario:", Counter(x["scenario"] for x in miss).most_common())
cx = Counter()
for r in rows:
    if r["arm"] == "hookpkg2" and r["agent"] == "codex":
        for k, v in ((r.get("hookpkg2") or {}).get("recheck_verdicts") or {}).items(): cx[(r["scenario"], k)] += v
print("== codex (row metrics):", sorted(cx.items()))
