#!/usr/bin/env python3
"""Scan round-2/round-4 A/B transcripts for agent behaviours that candidate
guidance hooks would target. Read-only; prints a JSON summary.

Per session we extract tool *inputs* (shell commands, written/edited file
content, read paths) for Claude (stream-json), Codex (exec --json) and
OpenCode (run --format json), then count heuristic triggers and correlate
with the grader's primary_pass.
"""
import gzip, json, re, sys, os, collections

HARNESS = "~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/ab/harness"
SETS = [("results_live.jsonl", "live"), ("results_live_hooks.jsonl", "live_hooks")]

CMD_PATTERNS = {
    "pip_install": r"\b(pip3?|uv pip) install\b|\buv add\b",
    "browser_install": r"playwright install|rfbrowser init|npx playwright",
    "pythonpath_workaround": r"(\s-P\s|--pythonpath|PYTHONPATH=)",
    "read_output_xml_shell": r"(cat|head|tail|less|sed -n|python3? -c)[^|;&]{0,200}output\.xml",
    "grep_output_xml": r"(grep|rg)[^|;&]{0,200}output\.xml",
    "read_log_html_shell": r"(cat|head|tail|sed -n)[^|;&]{0,200}log\.html",
    "robotcode_results": r"robotcode[^|;&]{0,40}results",
    "robotcode_repl": r"robotcode[^|;&]{0,60}\brepl\b",
    "robot_debug": r"robot-debug",
    "robot_run": r"(^|[\s;&|(\"'])(robot|robotcode[^|;&]{0,40}\s(robot|run))\s",
    "sleep_shell": r"(^|[;&|]\s*)sleep\s+\d",
    "curl_wget_site": r"\b(curl|wget)\b",
}
CONTENT_PATTERNS = {
    "Sleep_kw": r"(?m)^\s+Sleep\s{2,}",
    "ignore_error_wrap": r"Run Keyword And (Ignore Error|Return Status)",
    "skip_kw": r"(?m)^\s+(Skip|Skip If)\s",
    "abs_path_in_robot": r"/home/|C:\\\\|/Users/",
    "set_browser_timeout": r"Set Browser Timeout|Set Selenium Timeout|timeout=\d",
    "iframe_selector": r">>>",
    "force_click": r"force=True|Click With Options|Execute JavaScript|Evaluate JavaScript",
}


def tool_inputs(agent, path):
    """Yield (kind, text, target) for each tool call input."""
    with gzip.open(path, "rt", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if agent == "claude":
                if d.get("type") != "assistant":
                    continue
                for c in d.get("message", {}).get("content", []) or []:
                    if c.get("type") != "tool_use":
                        continue
                    n, i = c.get("name"), c.get("input", {}) or {}
                    if n == "Bash":
                        yield "cmd", i.get("command", ""), None
                    elif n in ("Write",):
                        yield "content", i.get("content", ""), i.get("file_path")
                    elif n == "Edit":
                        yield "edit", i.get("new_string", ""), i.get("file_path")
                    elif n == "MultiEdit":
                        yield "edit", "\n".join(e.get("new_string", "") for e in i.get("edits", [])), i.get("file_path")
                    elif n == "Read":
                        yield "read", i.get("file_path", ""), i.get("file_path")
            elif agent == "codex":
                it = d.get("item", {})
                if d.get("type") != "item.completed":
                    continue
                if it.get("type") == "command_execution":
                    yield "cmd", it.get("command", ""), None
                elif it.get("type") == "file_change":
                    for ch in it.get("changes", []):
                        yield "edit", "", ch.get("path")
            elif agent == "opencode":
                p = d.get("part", {})
                if d.get("type") != "tool_use":
                    continue
                t, i = p.get("tool"), (p.get("state", {}) or {}).get("input", {}) or {}
                if t == "bash":
                    yield "cmd", i.get("command", ""), None
                elif t == "write":
                    yield "content", i.get("content", ""), i.get("filePath")
                elif t == "edit":
                    yield "edit", i.get("newString", ""), i.get("filePath")
                elif t in ("patch", "multiedit", "apply_patch"):
                    yield "edit", json.dumps(i), i.get("filePath")
                elif t == "read":
                    yield "read", i.get("filePath", ""), i.get("filePath")


def scan_session(agent, path):
    c = collections.Counter()
    cmds = collections.Counter()
    edits = collections.Counter()
    for kind, text, target in tool_inputs(agent, path):
        text = text or ""
        if kind == "cmd":
            c["n_cmd"] += 1
            norm = re.sub(r"\s+", " ", text.strip())[:300]
            cmds[norm] += 1
            for k, rx in CMD_PATTERNS.items():
                if re.search(rx, text):
                    c[k] += 1
        if kind in ("content", "edit"):
            c["n_write"] += 1
            if target:
                edits[os.path.basename(target)] += 1
            if target and target.endswith((".robot", ".resource")):
                for k, rx in CONTENT_PATTERNS.items():
                    if re.search(rx, text):
                        c[k] += 1
        if kind == "read":
            c["n_read"] += 1
            if text.endswith("output.xml"):
                c["read_output_xml_tool"] += 1
            if text.endswith("log.html"):
                c["read_log_html_tool"] += 1
            if "/.rf/state/" in text:
                c["read_rf_state"] += 1
    c["max_same_cmd"] = max(cmds.values()) if cmds else 0
    c["max_same_file_edits"] = max(edits.values()) if edits else 0
    return c


def main():
    out = {"per_arm": {}, "flags": list(CMD_PATTERNS) + list(CONTENT_PATTERNS) +
           ["read_output_xml_tool", "read_log_html_tool", "read_rf_state"]}
    rows_all = []
    for fname, tag in SETS:
        for l in open(os.path.join(HARNESS, fname)):
            r = json.loads(l)
            if tag == "live_hooks" and r["arm"] != "hookpkg":
                continue  # skillpkg rows duplicated in live set; keep hookpkg only
            tp = os.path.join(HARNESS, r["transcript"])
            if not os.path.exists(tp):
                continue
            c = scan_session(r["agent"], tp)
            rows_all.append({"agent": r["agent"], "arm": r["arm"], "scenario": r["scenario"],
                             "kind": r.get("kind"), "pass": bool(r.get("primary_pass")), **c})
    groups = collections.defaultdict(list)
    for x in rows_all:
        groups[(x["agent"], x["arm"])].append(x)
    for (a, arm), xs in sorted(groups.items()):
        n = len(xs)
        d = {"n": n, "pass": round(sum(x["pass"] for x in xs) / n, 2)}
        for k in out["flags"] + ["max_same_cmd", "max_same_file_edits"]:
            vals = [x.get(k, 0) for x in xs]
            d[k] = {"sessions_with": sum(1 for v in vals if v), "mean": round(sum(vals) / n, 2)}
        out["per_arm"][f"{a}|{arm}"] = d
    # correlation: pass rate of sessions with vs without each flag (all arms pooled)
    corr = {}
    for k in out["flags"] + ["loop_cmd>=3", "loop_edit>=6"]:
        if k == "loop_cmd>=3":
            w = [x for x in rows_all if x.get("max_same_cmd", 0) >= 3]
        elif k == "loop_edit>=6":
            w = [x for x in rows_all if x.get("max_same_file_edits", 0) >= 6]
        else:
            w = [x for x in rows_all if x.get(k, 0)]
        wo = [x for x in rows_all if x not in w]
        if w and wo:
            corr[k] = {"n_with": len(w), "pass_with": round(sum(x["pass"] for x in w) / len(w), 2),
                       "pass_without": round(sum(x["pass"] for x in wo) / len(wo), 2)}
    out["pass_with_vs_without"] = corr
    strat = {}
    for k in out["flags"] + ["loop_cmd>=5", "loop_edit>=10"]:
        per = {}
        for ag in ("claude", "codex", "opencode"):
            xs = [x for x in rows_all if x["agent"] == ag]
            if k == "loop_cmd>=5":
                f = lambda x: x.get("max_same_cmd", 0) >= 5
            elif k == "loop_edit>=10":
                f = lambda x: x.get("max_same_file_edits", 0) >= 10
            else:
                f = lambda x, k=k: x.get(k, 0) > 0
            w = [x for x in xs if f(x)]; wo = [x for x in xs if not f(x)]
            if w and wo:
                per[ag] = [len(w), round(sum(x["pass"] for x in w)/len(w), 2), round(sum(x["pass"] for x in wo)/len(wo), 2)]
        if per:
            strat[k] = per
    out["stratified_by_agent_[n_with,pass_with,pass_without]"] = strat
    out["n_sessions"] = len(rows_all)
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "transcript_scan.json"), "w"), indent=1)
    json.dump(rows_all, open(os.path.join(os.path.dirname(__file__), "transcript_scan_rows.json"), "w"))
    print(json.dumps(corr, indent=0))


if __name__ == "__main__":
    main()
