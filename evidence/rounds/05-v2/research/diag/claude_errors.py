#!/usr/bin/env python3
"""The 10 Claude rows flagged 'agent-side error' in results_live_hooks.jsonl: what the error is + what ate the turns."""
import gzip, json, collections, re
from pathlib import Path
AB = Path("~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/ab/harness")
out = []
for r in map(json.loads, open(AB / "results_live_hooks.jsonl")):
    errs = (r.get("agent_info") or {}).get("errors")
    if not errs:
        continue
    tools = collections.Counter(); robot = 0; res = {}; edits_by_line = collections.Counter()
    for l in gzip.open(AB / r["transcript"], "rt"):
        l = l.strip()
        if not l:
            continue
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if d.get("type") == "assistant":
            for x in d["message"].get("content", []):
                if x.get("type") == "tool_use":
                    tools[x["name"]] += 1
                    cmd = (x["input"] or {}).get("command") or ""
                    if re.search(r"(^|\s)robot\s", cmd):
                        robot += 1
                    if re.search(r"rfmcp\s+(step|run)", cmd):
                        tools["rfmcp step/run"] += 1
        if d.get("type") == "result":
            res = {k: d.get(k) for k in ("subtype", "is_error", "num_turns", "duration_ms", "total_cost_usd")}
    out.append({"key": r["key"], "errors": errs, "result": res, "primary_pass": r["primary_pass"],
                "robot_first_pass": r.get("robot_first_pass"), "tools": dict(tools.most_common(8)), "robot_runs": robot})
json.dump(out, open(Path(__file__).with_name("claude_errors.json"), "w"), indent=1)
for o in out:
    print(o["key"], o["result"].get("subtype"), o["result"].get("num_turns"), "pass", o["primary_pass"], "robot_runs", o["robot_runs"], o["tools"])
