#!/usr/bin/env python3
"""OpenCode sessions -> same timeline shape as claude_sessions.json (for episodes.py-style analysis)."""
import gzip, json, re, importlib.util
from pathlib import Path
D = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pc", D / "parse_claude.py"); pc = importlib.util.module_from_spec(spec); spec.loader.exec_module(pc)
rows = [json.loads(l) for l in open(pc.H / "results_live_v2.jsonl")]
out = []
for r in rows:
    if r["agent"] != "opencode": continue
    tl = []
    for l in gzip.open(pc.H / r["transcript"], "rt"):
        if not l.startswith("{"): continue
        p = json.loads(l).get("part") or {}
        if p.get("type") != "tool": continue
        st = p.get("state") or {}; tm = st.get("time") or {}; inp = st.get("input") or {}
        name = {"edit": "Edit", "write": "Write", "read": "Read", "bash": "Bash", "grep": "Grep"}.get(p["tool"], p["tool"])
        e = {"t": (tm.get("start") or 0) / 1000, "end": (tm.get("end") or 0) / 1000, "name": name}
        e["dur"] = e["end"] - e["t"] if tm.get("end") else None
        o = st.get("output") or ""
        if name == "Read": e["cat"] = pc.read_cat(inp.get("filePath", ""))
        if name == "Bash": e["cat"] = pc.bash_cat(inp.get("command", ""))
        if name in ("Edit", "Write") and "[Robot Framework hook]" in o:
            t = o[o.find("[Robot Framework hook]"):o.find("[/hook]")]
            e["post_text"] = t
            e["live"] = "fail" if re.search(r"^\s*L\d+ (FAIL|NOT RUN)", t, re.M) else ("pass" if "PASS" in t else None)
        tl.append(e)
    out.append({"arm": r["arm"], "scenario": r["scenario"], "rep": r["rep"], "passed": r["primary_pass"], "timeline": tl})
json.dump(out, open(D / "opencode_sessions.json", "w"))
print(len(out))
