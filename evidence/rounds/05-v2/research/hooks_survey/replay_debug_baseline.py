#!/usr/bin/env python3
"""Debug-task weakening check against the *session-start baseline* (first full
Read of each .robot/.resource in the transcript) instead of the agent's own
previous version. Prints aggregate counts only (no file contents)."""
import gzip, json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detectors import weakening_findings
H = "~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/ab/harness"
NUM = re.compile(r"^\s*\d+(\t|[|→:] ?)", re.M)

def strip_numbers(out):
    out = re.sub(r"<system-reminder>.*?</system-reminder>", "", out, flags=re.S).rstrip("\n")
    out = re.sub(r"^<file>\n|\n</file>.*$", "", out, flags=re.S)
    out = re.sub(r"^<path>.*?</path>\n?<type>.*?</type>\n?<content>\n?", "", out, flags=re.S)
    out = re.sub(r"\n?</content>.*$", "", out, flags=re.S)
    lines = [NUM.sub("", l, count=1) for l in out.split("\n") if not l.startswith("(End of file")]
    return "\n".join(lines)

def sessions():
    for fname, tag in (("results_live.jsonl", "live"), ("results_live_hooks.jsonl", "hooks")):
        for l in open(os.path.join(H, fname)):
            r = json.loads(l)
            if r.get("kind") != "debug" or r["agent"] == "codex":
                continue
            if tag == "hooks" and r["arm"] != "hookpkg":
                continue
            yield r

res = []
KW = collections.Counter(); DET = []
for r in sessions():
    tp = os.path.join(H, r["transcript"]); pend = {}; base = {}; cur = {}
    with gzip.open(tp, "rt", errors="replace") as fh:
        for line in fh:
            if not line.startswith("{"): continue
            try: d = json.loads(line)
            except Exception: continue
            evs = []
            if r["agent"] == "claude":
                if d.get("type") == "assistant":
                    for c in d["message"].get("content", []) or []:
                        if c.get("type") == "tool_use": pend[c["id"]] = (c["name"], c.get("input") or {})
                elif d.get("type") == "user" and isinstance(d["message"].get("content"), list):
                    for c in d["message"]["content"]:
                        if c.get("type") != "tool_result": continue
                        n, i = pend.pop(c.get("tool_use_id"), (None, {}))
                        out = c.get("content"); out = out if isinstance(out, str) else "\n".join(x.get("text", "") for x in (out or []) if isinstance(x, dict))
                        if n == "Read" and not i.get("offset"): evs.append(("read", i.get("file_path", ""), out))
                        elif n == "Write": evs.append(("write", i.get("file_path", ""), i.get("content", "")))
                        elif n == "Edit": evs.append(("edit", i.get("file_path", ""), i.get("old_string", ""), i.get("new_string", ""), i.get("replace_all")))
                        elif n == "MultiEdit":
                            for e in i.get("edits", []): evs.append(("edit", i.get("file_path", ""), e.get("old_string", ""), e.get("new_string", ""), e.get("replace_all")))
            else:
                p = d.get("part", {})
                if d.get("type") == "tool_use":
                    st = p.get("state", {}) or {}; i = st.get("input") or {}
                    if p.get("tool") == "read" and not i.get("offset"): evs.append(("read", i.get("filePath", ""), st.get("output", "") or ""))
                    elif p.get("tool") == "write": evs.append(("write", i.get("filePath", ""), i.get("content", "")))
                    elif p.get("tool") == "edit": evs.append(("edit", i.get("filePath", ""), i.get("oldString", ""), i.get("newString", ""), i.get("replaceAll")))
            for ev in evs:
                p = ev[1]
                if not p.endswith((".robot", ".resource")) or "/.rf/" in p: continue
                if ev[0] == "read" and p not in base:
                    base[p] = strip_numbers(ev[2]); cur.setdefault(p, base[p])
                elif ev[0] == "write":
                    cur[p] = ev[2]
                elif ev[0] == "edit" and p in cur:
                    cur[p] = cur[p].replace(ev[2], ev[3]) if ev[4] else cur[p].replace(ev[2], ev[3], 1)
    find = collections.Counter()
    changed = sum(1 for p in base if cur.get(p) != base[p])
    for p in base:
        for f in weakening_findings(base[p], cur.get(p, base[p])):
            find[f["rule"]] += 1
            if f["rule"] == "expected-value-changed": DET.append(r["agent"] + " " + re.sub(r"^[^:]*:", "", f["detail"])[:90])
            if f["rule"] == "expected-value-changed": KW[(r["agent"], f["detail"].split(":")[0].split(" ")[0] + " " + f["detail"].split(":")[0].split(" ")[1] if " " in f["detail"].split(":")[0] else f["detail"][:20], r["scenario"])] += 1
    res.append({"agent": r["agent"], "arm": r["arm"], "scenario": r["scenario"], "pass": bool(r.get("primary_pass")),
                "files_baselined": len(base), "files_changed": changed, "findings": dict(find)})

summ = {}
for ag in ("claude", "opencode"):
    xs = [x for x in res if x["agent"] == ag]
    by = collections.defaultdict(lambda: [0, 0])
    for x in xs:
        for k in x["findings"]:
            by[k][0] += 1; by[k][1] += x["pass"]
    blk = [x for x in xs if any(k in x["findings"] for k in ("test-deleted", "assertions-removed", "failure-swallowed", "skip-added"))]
    nb = [x for x in xs if x not in blk]
    summ[ag] = {"n_debug": len(xs), "baselined": sum(1 for x in xs if x["files_baselined"]), "sessions_with_changed_files": sum(1 for x in xs if x["files_changed"]),
                "pass_expected_value_changed": round(sum(x["pass"] for x in xs if "expected-value-changed" in x["findings"]) / max(1, sum(1 for x in xs if "expected-value-changed" in x["findings"])), 2),
                "pass_no_expected_value_change": round(sum(x["pass"] for x in xs if "expected-value-changed" not in x["findings"]) / max(1, sum(1 for x in xs if "expected-value-changed" not in x["findings"])), 2),
                "rule_[sessions,passing]": {k: v for k, v in by.items()},
                "block_rule_sessions": len(blk),
                "pass_with_block_rule": round(sum(x["pass"] for x in blk)/len(blk), 2) if blk else None,
                "pass_without": round(sum(x["pass"] for x in nb)/len(nb), 2) if nb else None}
json.dump({"summary": summ, "rows": res}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "replay_debug_baseline.json"), "w"), indent=1)
print(json.dumps(summ, indent=1))
print({"|".join(k): v for k, v in KW.most_common(20)})
print(collections.Counter(DET).most_common(12))
