#!/usr/bin/env python3
"""Reaction of agents to SLOW verdicts / loop hints (Claude from stream-json, OpenCode from tool outputs)."""
import gzip, json, re
from collections import Counter
from pathlib import Path
H = Path(__file__).resolve().parents[2] / "ab" / "harness"
rows = [json.loads(l) for l in open(H / "results_live_v2.jsonl")]

def _delta(old, new):
    """lines added by the edit (multiset difference)"""
    ol = Counter(x.strip() for x in old.splitlines())
    out = []
    for x in new.splitlines():
        k = x.strip()
        if ol.get(k, 0) > 0:
            ol[k] -= 1
        else:
            out.append(x)
    return "\n".join(out)


def claude_steps(path):
    """-> list of (kind, text) in order: ('out', hook post text for edit) / ('edit', new content)"""
    seq = []; names = {}; inputs = {}
    for l in gzip.open(path, "rt"):
        if not l.startswith("{"): continue
        o = json.loads(l)
        if o.get("type") == "assistant":
            for c in o["message"]["content"]:
                if c.get("type") == "tool_use" and c["name"] in ("Edit", "Write", "MultiEdit"):
                    inp = c["input"]
                    seq.append(("edit", _delta(inp.get("old_string") or "", inp.get("new_string") or inp.get("content") or json.dumps(inp.get("edits", "")))))
        if o.get("type") == "system" and o.get("subtype") == "hook_response" and (o.get("hook_name") or "").startswith("PostToolUse"):
            try:
                j = json.loads(o.get("output") or "{}"); t = (j.get("hookSpecificOutput") or {}).get("additionalContext") or ""
            except Exception:
                t = ""
            if t: seq.append(("out", t))
    return seq

def opencode_steps(path):
    seq = []
    for l in gzip.open(path, "rt"):
        if not l.startswith("{"): continue
        o = json.loads(l); p = o.get("part") or {}
        if p.get("type") != "tool": continue
        st = p.get("state") or {}; inp = st.get("input") or {}
        if p["tool"] in ("edit", "write", "multiedit"):
            seq.append(("edit", _delta(inp.get("oldString") or "", inp.get("newString") or inp.get("content") or "")))
        out = st.get("output") or ""
        if "[Robot Framework hook]" in out:
            seq.append(("out", out))
    return seq

res = Counter()
for r in rows:
    if r["arm"] != "hookpkg2" or r["agent"] not in ("claude", "opencode"): continue
    seq = (claude_steps if r["agent"] == "claude" else opencode_steps)(H / r["transcript"])
    for i, (k, t) in enumerate(seq):
        if k != "out": continue
        for tag, pat in (("SLOW", "recheck: SLOW"), ("LOOP", "LOOP:"), ("MISS", "recheck: MISSING")):
            if pat not in t: continue
            nxt = next((x for kk, x in seq[i + 1:] if kk == "edit"), None)
            res[(r["agent"], tag, "n")] += 1
            if nxt is None: continue
            if re.search(r"Wait For Elements State|Wait Until|Wait For Condition", nxt): res[(r["agent"], tag, "adds_wait")] += 1
            if re.search(r"\bSleep\b", nxt): res[(r["agent"], tag, "adds_sleep")] += 1
            if re.search(r"label|:has\(|force=True|Check Checkbox|>> \.\.|xpath=\.\.|Evaluate JavaScript", nxt): res[(r["agent"], tag, "label/force/js")] += 1
for k in sorted(res): print(k, res[k])
