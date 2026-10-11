#!/usr/bin/env python3
"""Per-session metrics for OpenCode transcripts (hookpkg vs skillpkg) from the round-4 live A/B.

Reads ab/harness/results_live_hooks.jsonl + transcripts_live_hooks/opencode/*.jsonl.gz (read-only).
Writes oc_metrics.json (per session + per arm/kind aggregates) and oc_events/<cell>.txt (compact timelines).
"""
import gzip
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

AB = Path("~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/ab/harness")
OUT = Path(__file__).resolve().parent
HOOK_MARK = re.compile(r"(Live run of |Plain robot run: |Reproduced live: |static check \(let through|"
                       r"still running after the hook budget|outdated syntax|Robot Framework quality gate)")
RF_PATH = re.compile(r"\.(robot|resource)\b")
ROBOT_CMD = re.compile(r"(^|[\s;&|(/])(robot|robotcode)\s")
REF_HOOK = re.compile(r"(\bL\d+\b|\bPASS\b|\bFAIL|NOT RUN|\.rf/state|controls\.txt|aria\.yaml|live run|"
                      r"hook|page summary|suggested selector|refused|static check)", re.I)
BYPASS = re.compile(r"(cat\s*>+\s*\S*\.(robot|resource)|tee\s+\S*\.(robot|resource)|>\s*\S*\.(robot|resource)|"
                    r"open\([^)]*\.(robot|resource))")
GOTO = re.compile(r"^\s*(Go To|New Page)\s{2,}(\S+)", re.M)


def events(path):
    with gzip.open(path, "rt") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def tool_rec(d):
    p = d["part"]
    s = p.get("state") or {}
    inp = s.get("input") or {}
    out = s.get("output") or ""
    err = s.get("error") or ""
    t = s.get("time") or {}
    return {"ts": d.get("timestamp"), "tool": p.get("tool"), "status": s.get("status"), "input": inp,
            "output": out if isinstance(out, str) else json.dumps(out), "error": err if isinstance(err, str) else json.dumps(err),
            "t0": t.get("start"), "t1": t.get("end")}


def is_rf_edit(r):
    return r["tool"] in ("write", "edit", "multiedit", "patch", "apply_patch") and RF_PATH.search(json.dumps(r["input"]))


def edit_lines(r):
    i = r["input"]
    if r["tool"] == "write":
        return len((i.get("content") or "").splitlines())
    return len((i.get("newString") or i.get("new_string") or "").splitlines())


def analyse(row):
    path = AB / row["transcript"]
    tools, texts, timeline = [], [], []
    first_ts = last_ts = None
    for d in events(path):
        ts = d.get("timestamp")
        first_ts = first_ts or ts
        last_ts = ts or last_ts
        if not isinstance(d, dict):
            continue
        if d.get("type") == "tool_use":
            r = tool_rec(d)
            tools.append(r)
            timeline.append(("tool", r))
        elif d.get("type") == "text":
            txt = (d.get("part") or {}).get("text") or ""
            texts.append((ts, txt))
            timeline.append(("text", {"ts": ts, "text": txt}))
    m = Counter()
    hook_chars, hook_outputs, tool_dur_rf, gaps_after_rf = [], [], [], []
    denials = []
    sigs = Counter()
    consecutive_dupes = 0
    prev_sig = None
    first_robot_idx = None
    edits_sizes = []
    referenced = 0
    hook_with_next_text = 0
    goto_urls, page_urls_seen = [], []
    for idx, (kind, r) in enumerate(timeline):
        if kind != "tool":
            continue
        m["tool_calls"] += 1
        m[f"tool:{r['tool']}"] += 1
        sig = r["tool"] + json.dumps(r["input"], sort_keys=True)
        sigs[sig] += 1
        if sig == prev_sig:
            consecutive_dupes += 1
        prev_sig = sig
        cmd = r["input"].get("command") or ""
        if r["tool"] == "bash":
            if ROBOT_CMD.search(" " + cmd):
                m["robot_runs"] += 1
                if first_robot_idx is None:
                    first_robot_idx = m["tool_calls"]
            if BYPASS.search(cmd):
                m["bash_writes_rf"] += 1
            if re.search(r"\.rf/state", cmd):
                m["state_reads_bash"] += 1
            if re.search(r"\b(python3?|node)\b.*(playwright|selenium|requests|urllib)", cmd, re.I | re.S):
                m["adhoc_scripts"] += 1
            if re.search(r"\b(curl|wget)\b", cmd):
                m["curl"] += 1
        if r["tool"] in ("read", "grep", "glob"):
            s = json.dumps(r["input"])
            if ".rf/state" in s:
                m["state_reads"] += 1
            if ".rf/docs" in s:
                m["docs_reads"] += 1
        rf_edit = is_rf_edit(r)
        if rf_edit:
            m["rf_edits"] += 1
            n = edit_lines(r)
            edits_sizes.append(n)
            for mm in GOTO.finditer(r["input"].get("content") or r["input"].get("newString") or ""):
                goto_urls.append(mm.group(2))
        if r["status"] == "error":
            m["tool_errors"] += 1
            if "static check REFUSED" in r["error"]:
                # reaction: next tool call
                nxt = next((x for k, x in timeline[idx + 1:] if k == "tool"), None)
                react = "none"
                if nxt is not None:
                    same_file = json.dumps(nxt["input"]).find(str(r["input"].get("filePath", "@@"))) >= 0
                    if nxt["tool"] + json.dumps(nxt["input"], sort_keys=True) == sig:
                        react = "identical-retry"
                    elif is_rf_edit(nxt) and same_file:
                        react = "edit-same-file"
                    elif nxt["tool"] == "bash" and BYPASS.search(nxt["input"].get("command") or ""):
                        react = "bash-bypass"
                    elif nxt["tool"] in ("read", "grep", "glob"):
                        react = "read/grep:" + ("docs" if ".rf/docs" in json.dumps(nxt["input"]) else "other")
                    else:
                        react = nxt["tool"]
                codes = re.findall(r":\d+ (\w+):", r["error"])
                denials.append({"codes": codes, "reaction": react, "err": r["error"][:300]})
        out = r["output"]
        mk = HOOK_MARK.search(out)
        if mk and (rf_edit or r["tool"] == "bash"):
            h = out[mk.start():]
            hook_chars.append(len(h))
            hook_outputs.append(h)
            for u in re.findall(r"Page now: \"[^\"]*\"\s+(\S+)", h):
                page_urls_seen.append(u)
            if "still running" in h:
                m["still_running_seen"] += 1
            if "All test lines passed live" in h:
                m["all_passed_live_msgs"] += 1
            if re.search(r"\bL\d+ (FAIL|NOT RUN)", h):
                m["hook_fail_outputs"] += 1
            # next assistant text before the next tool
            nt = None
            for k, x in timeline[idx + 1:]:
                if k == "tool":
                    break
                if k == "text" and x["text"].strip():
                    nt = x["text"]
                    break
            if nt is not None:
                hook_with_next_text += 1
                if REF_HOOK.search(nt):
                    referenced += 1
        if rf_edit and r["t0"] and r["t1"]:
            tool_dur_rf.append((r["t1"] - r["t0"]) / 1000)
            nxt_ts = next((x.get("ts") for k, x in timeline[idx + 1:] if x.get("ts")), None)
            if nxt_ts:
                gaps_after_rf.append((nxt_ts - r["t1"]) / 1000)
    loops = {s[:160]: c for s, c in sigs.items() if c >= 3}
    hp = row.get("hookpkg") or {}
    res = {
        "key": row["key"], "arm": row["arm"], "kind": row["kind"], "scenario": row["scenario"], "rep": row["rep"],
        "pass": row["primary_pass"], "robot_first_pass": row.get("robot_first_pass"),
        "failed_checks": [v.get("label") or v["type"] for v in row["verdicts"] if not v["passed"]],
        "turns": row["metrics"].get("turns"), "wall_s": row["metrics"].get("wall_s"),
        "session_s": round((last_ts - first_ts) / 1000, 1) if first_ts and last_ts else None,
        "counts": dict(m), "rf_edit_sizes": edits_sizes,
        "whole_file_writes": sum(1 for r in tools if r["tool"] == "write" and RF_PATH.search(json.dumps(r["input"]))),
        "small_edits_le3": sum(1 for n in edits_sizes if n <= 3),
        "hook_outputs": len(hook_chars), "hook_chars_total": sum(hook_chars),
        "hook_chars_median": st.median(hook_chars) if hook_chars else 0, "hook_chars_max": max(hook_chars or [0]),
        "next_text_after_hook": hook_with_next_text, "next_text_refs_hook": referenced,
        "denials": denials, "n_denials": len(denials),
        "consecutive_identical_calls": consecutive_dupes, "repeated_calls_ge3": loops,
        "first_robot_call_index": first_robot_idx,
        "rf_edit_tool_s_median": round(st.median(tool_dur_rf), 2) if tool_dur_rf else None,
        "rf_edit_tool_s_total": round(sum(tool_dur_rf), 1),
        "gap_after_rf_edit_s_median": round(st.median(gaps_after_rf), 2) if gaps_after_rf else None,
        "goto_urls_written": sorted(set(goto_urls)), "page_urls_in_hook_output": sorted(set(page_urls_seen)),
        "deep_url_from_hook": sorted(set(goto_urls) & set(page_urls_seen) - set(goto_urls[:1])),
        "hook_stats_row": {k: hp.get(k) for k in ("firings_by_event", "auto_executed_lines", "auto_non_pass_lines",
                                                     "denials", "rewrites", "stop_blocks", "still_running",
                                                     "pending_delivered", "state_reads", "docs_reads", "latency_ms_median")},
        "final_text": (texts[-1][1] if texts else "")[:400],
    }
    # compact timeline
    with open(OUT / "oc_events" / f"{row['cell_id']}.txt", "w") as f:
        for kind, r in timeline:
            if kind == "text":
                if r["text"].strip():
                    f.write(f"TEXT  {r['text'][:300]!r}\n")
                continue
            i = r["input"]
            brief = i.get("command") or i.get("filePath") or i.get("pattern") or json.dumps(i)[:150]
            extra = ""
            if r["tool"] == "edit":
                extra = f" new={(i.get('newString') or '')[:160]!r}"
            elif r["tool"] == "write":
                extra = f" lines={len((i.get('content') or '').splitlines())}"
            f.write(f"TOOL  {r['tool']} [{r['status']}] {str(brief)[:200]!r}{extra}\n")
            if r["status"] == "error":
                f.write(f"   ERR {r['error'][:400]!r}\n")
            mk = HOOK_MARK.search(r["output"])
            if mk:
                f.write("   HOOK " + r["output"][mk.start():][:900].replace("\n", "\n        ") + "\n")
            elif r["tool"] == "bash":
                f.write("   OUT " + r["output"][-300:].replace("\n", " | ") + "\n")
    return res


def agg(rows):
    out = {}
    keys = ["turns", "hook_outputs", "hook_chars_total", "hook_chars_median", "n_denials", "rf_edits",
            "whole_file_writes", "small_edits_le3", "consecutive_identical_calls", "first_robot_call_index",
            "rf_edit_tool_s_total", "robot_runs", "state_reads", "docs_reads", "adhoc_scripts", "bash_writes_rf"]
    for k in keys:
        vals = []
        for r in rows:
            v = r.get(k, r["counts"].get(k, 0))
            if v is None:
                continue
            vals.append(v)
        out[k] = round(st.mean(vals), 1) if vals else None
    out["pass"] = round(st.mean(1 if r["pass"] else 0 for r in rows), 2)
    out["n"] = len(rows)
    refs = sum(r["next_text_refs_hook"] for r in rows)
    nt = sum(r["next_text_after_hook"] for r in rows)
    out["next_text_refs_hook_ratio"] = f"{refs}/{nt}"
    out["deny_reactions"] = dict(Counter(d["reaction"] for r in rows for d in r["denials"]))
    out["deny_codes"] = dict(Counter(c for r in rows for d in r["denials"] for c in d["codes"]))
    out["deep_url_from_hook_sessions"] = sum(1 for r in rows if r["deep_url_from_hook"])
    return out


def main():
    (OUT / "oc_events").mkdir(exist_ok=True)
    rows = [json.loads(l) for l in open(AB / "results_live_hooks.jsonl")]
    rows = [r for r in rows if r["agent"] == (sys.argv[1] if len(sys.argv) > 1 else "opencode")]
    res = [analyse(r) for r in rows]
    groups = defaultdict(list)
    for r in res:
        groups[f"{r['arm']}|{r['kind']}"].append(r)
        groups[f"{r['arm']}|all"].append(r)
    summary = {k: agg(v) for k, v in sorted(groups.items())}
    json.dump({"summary": summary, "sessions": res}, open(OUT / f"{rows[0]['agent']}_metrics.json", "w"), indent=1)
    for k, v in summary.items():
        print(k, json.dumps(v))


if __name__ == "__main__":
    main()
