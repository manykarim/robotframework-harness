#!/usr/bin/env python3
"""Round-6 diag: parse Claude stream-json transcripts of the round-5 v1/v2 A/B (results_live_v2.jsonl).

Per session: tool calls (durations from assistant->tool_result timestamps), hook outputs (chars per event), reads of
.rf files, edits, denials, SLOW/MISSING rechecks, loop hints, model vs tool time. Writes claude_sessions.json.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

H = Path(__file__).resolve().parents[2] / "ab" / "harness"
OUT = Path(__file__).resolve().parent


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def hook_text(out: str) -> str:
    if not out:
        return ""
    try:
        j = json.loads(out)
    except Exception:
        return out
    hs = j.get("hookSpecificOutput") or {}
    parts = [hs.get("additionalContext"), hs.get("permissionDecisionReason"), j.get("reason"), j.get("systemMessage")]
    return "\n".join(p for p in parts if p)


def read_cat(path: str) -> str:
    p = path or ""
    if "/.rf/state/latest/" in p or re.search(r"\.rf/state/(controls|aria|page|source|screenshot)", p):
        return "state_latest"
    if "/.rf/state/step-" in p or "history.tsv" in p:
        return "state_history"
    if "/.rf/docs/kw/" in p:
        return "docs_kw"
    if "/.rf/docs/" in p:
        return "docs_lib"
    if "/.rf/" in p:
        return "rf_other"
    if p.endswith((".robot", ".resource")):
        return "suite"
    if "output.xml" in p or "log.html" in p or "report.html" in p or "/results/" in p:
        return "results"
    if "SKILL.md" in p or "/skills/" in p:
        return "skill"
    return "other"


def bash_cat(cmd: str) -> str:
    c = cmd or ""
    if re.search(r"(^|[;&|]\s*|\s)robot\s", c) or c.strip().startswith("robot "):
        return "robot"
    if ".rf/state" in c:
        return "rf_state"
    if ".rf/docs" in c:
        return "rf_docs"
    if "output.xml" in c or "log.html" in c or "results/" in c:
        return "results"
    if re.search(r"\b(curl|wget)\b", c):
        return "curl"
    if re.search(r"\b(python3?|node|npx|playwright)\b", c):
        return "script"
    if re.search(r"\b(sleep)\b", c):
        return "sleep"
    return "other"


RE_SLOW = re.compile(r"recheck: SLOW -- the element appeared after ([\d.]+) s \(live timeout ([\d.]+) s, normal ([\d.]+) s\); "
                     r"(PASSED on the re-check|still failed after it appeared)")
RE_MISS_STABLE = re.compile(r"recheck: MISSING -- the page had not changed for ([\d.]+) s")
RE_MISS_WAIT = re.compile(r"recheck: MISSING -- not there after the normal ([\d.]+) s")
RE_LINE = re.compile(r"^\s*L(\d+) (PASS|FAIL|NOT RUN[^ ]*(?: \([^)]*\))?)\s+(.*)$")
RE_SIMILAR = re.compile(r"similar control: (.*?)\s+=> (\S+)")


def parse_recheck(text: str):
    """-> list of dicts {verdict, kw, sel, appeared, status, stable_s, similar_same}"""
    res = []
    lines = text.splitlines()
    cur = None
    for i, ln in enumerate(lines):
        m = RE_LINE.match(ln)
        if m:
            code = m.group(3)
            parts = re.split(r"\s{2,}", code.strip())
            kwi = 0
            if parts and parts[0].startswith("${"):
                kwi = 1
            cur = {"line": int(m.group(1)), "status": m.group(2), "kw": parts[kwi] if len(parts) > kwi else "",
                   "sel": parts[kwi + 1] if len(parts) > kwi + 1 else ""}
            continue
        if "recheck:" in ln and cur is not None:
            d = {"kw": cur["kw"], "sel": cur["sel"], "line": cur["line"], "line_status": cur["status"]}
            m = RE_SLOW.search(ln)
            if m:
                d.update(verdict="slow", appeared=float(m.group(1)), short=float(m.group(2)), normal=float(m.group(3)),
                         passed_after=m.group(4).startswith("PASSED"))
            elif RE_MISS_STABLE.search(ln):
                d.update(verdict="missing", mode="stable_instant", stable_s=float(RE_MISS_STABLE.search(ln).group(1)))
            elif RE_MISS_WAIT.search(ln):
                d.update(verdict="missing", mode="waited", normal=float(RE_MISS_WAIT.search(ln).group(1)))
            else:
                d.update(verdict="other")
            # similar controls following
            sims = []
            for ln2 in lines[i + 1:i + 5]:
                ms = RE_SIMILAR.search(ln2)
                if ms:
                    sims.append(ms.group(2))
                elif "found inside an iframe" in ln2:
                    d["iframe"] = True
            if sims:
                d["similar"] = sims
                d["similar_same"] = any(s == cur["sel"] or s.split("=", 1)[-1] == cur["sel"].split("=", 1)[-1]
                                        for s in sims)
            # message preceding: did it say 'locator resolved to' (element existed)?
            j = i - 1
            msg = ""
            while j >= 0 and not RE_LINE.match(lines[j]):
                msg = lines[j] + " " + msg
                j -= 1
            d["resolved"] = "locator resolved to" in msg
            d["intercepts"] = "intercepts pointer" in msg
            d["refused"] = "refused before execution" in cur["status"]
            res.append(d)
    return res


def union_len(iv):
    iv = sorted(x for x in iv if x[0] is not None and x[1] is not None)
    tot, end = 0.0, None
    st = None
    for a, b in iv:
        if end is None or a > end:
            if end is not None:
                tot += end - st
            st, end = a, b
        else:
            end = max(end, b)
    if end is not None:
        tot += end - st
    return tot


def parse(path: Path) -> dict:
    ev = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for l in f:
            try:
                ev.append(json.loads(l))
            except Exception:
                pass
    calls = {}       # tool_use_id -> call
    order = []
    pending_hooks = []   # hook responses not yet attached
    last_tool_ids = []
    first_ts = None
    result = None
    prev_ts = None
    model_gaps = []
    hooks_all = []
    for o in ev:
        t = o.get("type")
        st = o.get("subtype")
        if t == "system" and st == "hook_response":
            txt = hook_text(o.get("output") or "")
            h = {"name": o.get("hook_name"), "event": o.get("hook_event"), "chars": len(txt), "text": txt,
                 "exit": o.get("exit_code")}
            hooks_all.append(h)
            # attach: Pre/Post hooks belong to the most recent unresolved tool call with that tool name
            nm = (o.get("hook_name") or "")
            if ":" in nm and nm.split(":")[0] in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
                tool = nm.split(":", 1)[1]
                for tid in reversed(order):
                    c = calls[tid]
                    if c["name"] == tool and c.get("end") is None:
                        c["hooks"].append(h)
                        break
            continue
        if t == "assistant":
            at = ts(o.get("timestamp"))
            if first_ts is None:
                first_ts = at
            if prev_ts is not None and at is not None:
                model_gaps.append(at - prev_ts)
            prev_ts = at
            for c in o["message"].get("content", []):
                if c.get("type") == "tool_use":
                    calls[c["id"]] = {"id": c["id"], "name": c["name"], "input": c.get("input") or {}, "start": at,
                                      "end": None, "hooks": [], "result_chars": 0, "is_error": False}
                    order.append(c["id"])
        elif t == "user":
            ut = ts(o.get("timestamp"))
            cont = (o.get("message") or {}).get("content")
            if isinstance(cont, list):
                for c in cont:
                    if c.get("type") == "tool_result":
                        cc = c.get("content")
                        s = cc if isinstance(cc, str) else json.dumps(cc)
                        k = c.get("tool_use_id")
                        if k in calls:
                            calls[k]["end"] = ut
                            calls[k]["result_chars"] = len(s)
                            calls[k]["is_error"] = bool(c.get("is_error"))
                            calls[k]["result_head"] = s[:400]
            if ut is not None:
                prev_ts = ut
        elif t == "result":
            result = o
    # aggregate
    S = {"file": str(path), "n_calls": len(order)}
    tools = Counter()
    reads = Counter()
    bash = Counter()
    edits = 0
    edit_suite = 0
    hook_chars = Counter()
    hook_n = Counter()
    edit_hook_chars = []
    edit_dur = []
    robot_dur = []
    deny = Counter()
    rechecks = []
    loop_hints = 0
    card = 0
    live_fail_outputs = 0
    live_pass_outputs = 0
    tool_iv = []
    restarts = 0
    reproduce = 0
    sleep_refused = 0
    static_refused = 0
    timeline = []
    for tid in order:
        c = calls[tid]
        tools[c["name"]] += 1
        dur = (c["end"] - c["start"]) if c["end"] and c["start"] else None
        tool_iv.append((c["start"], c["end"]))
        inp = c["input"]
        for h in c["hooks"]:
            hook_chars[h["name"]] += h["chars"]
            hook_n[h["name"]] += 1
            txt = h["text"]
            if "LOOP:" in txt:
                loop_hints += 1
            if "REFUSED" in txt or "refused" in txt.lower() and h["name"].startswith("PreToolUse"):
                if "static check REFUSED" in txt:
                    static_refused += 1
                    deny["static"] += 1
                elif "Sleep" in txt:
                    sleep_refused += 1
                    deny["sleep"] += 1
                elif h["name"].startswith("PreToolUse"):
                    deny["other_pre"] += 1
            if "format card" in txt.lower() or "REPL format" in txt:
                card += 1
            if "test restarted" in txt:
                restarts += 1
            if "Reproduced live" in txt:
                reproduce += 1
            if h["name"].startswith("PostToolUse"):
                rechecks += parse_recheck(txt)
        ev_rec = {"t": c["start"], "end": c["end"], "name": c["name"], "dur": dur}
        if c["name"] == "Read":
            cat = read_cat(inp.get("file_path", ""))
            reads[cat] += 1
            ev_rec["cat"] = cat
        elif c["name"] == "Grep" or c["name"] == "Glob":
            cat = read_cat(inp.get("path", "") or "") if inp.get("path") else "other"
            reads["grep_" + cat] += 1
        elif c["name"] == "Bash":
            cat = bash_cat(inp.get("command", ""))
            bash[cat] += 1
            ev_rec["cat"] = cat
            if cat == "robot" and dur is not None:
                robot_dur.append(dur)
        elif c["name"] in ("Edit", "Write", "MultiEdit"):
            edits += 1
            fp = inp.get("file_path", "")
            if fp.endswith((".robot", ".resource")):
                edit_suite += 1
            post = [h for h in c["hooks"] if h["name"].startswith("PostToolUse")]
            pre = [h for h in c["hooks"] if h["name"].startswith("PreToolUse")]
            ev_rec["post_chars"] = sum(h["chars"] for h in post)
            ev_rec["pre_chars"] = sum(h["chars"] for h in pre)
            ev_rec["denied"] = c["is_error"]
            if post:
                edit_hook_chars.append(sum(h["chars"] for h in post))
                txt = "\n".join(h["text"] for h in post)
                if re.search(r"^\s*L\d+ (FAIL|NOT RUN)", txt, re.M):
                    live_fail_outputs += 1
                    ev_rec["live"] = "fail"
                elif re.search(r"^\s*L\d+.* PASS", txt, re.M):
                    live_pass_outputs += 1
                    ev_rec["live"] = "pass"
                ev_rec["post_text"] = txt
            if dur is not None:
                edit_dur.append(dur)
        timeline.append(ev_rec)
    wall = (result or {}).get("duration_ms", 0) / 1000.0
    tool_time = union_len(tool_iv)
    S.update(
        tools=dict(tools), reads=dict(reads), bash=dict(bash), edits=edits, edit_suite=edit_suite,
        hook_chars=dict(hook_chars), hook_n=dict(hook_n), hook_chars_total=sum(hook_chars.values()),
        edit_hook_chars=edit_hook_chars, edit_dur=edit_dur, robot_dur=robot_dur,
        edit_time=sum(edit_dur), robot_time=sum(robot_dur), denials=dict(deny), loop_hints=loop_hints,
        rechecks=rechecks, live_fail=live_fail_outputs, live_pass=live_pass_outputs, restarts=restarts,
        reproduce=reproduce, wall=wall, tool_time=tool_time, model_time=max(0.0, wall - tool_time),
        api_ms=(result or {}).get("duration_api_ms"), num_turns=(result or {}).get("num_turns"),
        cost=(result or {}).get("total_cost_usd"), usage=(result or {}).get("usage"),
        timeline=timeline,
    )
    return S


def main():
    rows = [json.loads(l) for l in open(H / "results_live_v2.jsonl")]
    out = []
    for r in rows:
        if r["agent"] != "claude":
            continue
        p = H / r["transcript"]
        if not p.exists():
            print("missing", p, file=sys.stderr)
            continue
        s = parse(p)
        s.update(arm=r["arm"], scenario=r["scenario"], rep=r["rep"], kind=r.get("kind"), passed=r.get("primary_pass"),
                 row_wall=r["metrics"].get("wall_s"), row_turns=r["metrics"].get("turns"),
                 row_cost=r["metrics"].get("cost_usd"), hookm=r.get(r["arm"]) or {})
        out.append(s)
    (OUT / "claude_sessions.json").write_text(json.dumps(out, indent=1, default=str))
    print("sessions", len(out))


if __name__ == "__main__":
    main()
