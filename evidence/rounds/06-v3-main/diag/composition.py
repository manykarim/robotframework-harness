#!/usr/bin/env python3
"""Char composition of hook outputs attached to Claude Edit/Write (v1 vs v2), by line type."""
import json, re
from collections import Counter
S = json.load(open(__import__("pathlib").Path(__file__).with_name("claude_sessions.json")))
def kind(l):
    s = l.strip()
    if re.match(r"L\d+(-L\d+)? (PASS|FAIL|NOT RUN)", s): return "step_line"
    if s.startswith("recheck:"): return "recheck"
    if s.startswith("similar control:") or s.startswith("found inside an iframe"): return "similar"
    if s.startswith("hint:"): return "hint"
    if s.startswith("fix:"): return "fix"
    if s.startswith("docs:"): return "docs_sig"
    if s.startswith("LOOP:") or re.match(r"\d\. ", s): return "loop"
    if s.startswith("Page") or s.startswith("Page now"): return "page_head"
    if re.match(r"\d+ controls;", s) or s.startswith("full state:"): return "files_list"
    if s.startswith("controls:") or s.startswith("controls (") : return "controls"
    if re.match(r"(a|button|input|select|textarea|label|div|span|li|ul|h\d|img)\b.*=>", s): return "controls"
    if s.startswith("history:"): return "history"
    if s.startswith("->") or s.startswith("NEXT"): return "next"
    if s.startswith("Keyword docs for the imports") : return "import_docs"
    if s.startswith("Live run of") or s.startswith("(") : return "header"
    if s.startswith("... (truncated)"): return "trunc"
    return "msg/other"
for arm in ("hookpkg", "hookpkg2"):
    c = Counter(); n = 0
    for s in S:
        if s["arm"] != arm: continue
        for e in s["timeline"]:
            t = e.get("post_text")
            if not t: continue
            n += 1
            for l in t.splitlines(): c[kind(l)] += len(l) + 1
    tot = sum(c.values())
    print(arm, "edits", n, "chars/edit %.0f" % (tot / n), {k: round(v / n) for k, v in c.most_common()})
