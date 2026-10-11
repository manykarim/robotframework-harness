#!/usr/bin/env python3
"""Replay the prototype detectors over the round-2/round-4 A/B transcripts to
estimate how often each would have fired (and in passing vs failing sessions).
Read-only. Writes replay_detectors.json next to this script."""
import gzip, json, os, re, collections, sys
sys.path.insert(0, os.path.dirname(__file__))
from detectors import LoopDetector, weakening_findings, bash_guard

HARNESS = "~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/ab/harness"


def events(agent, path):
    """Yield ('cmd', command, output) / ('edit', path, old, new) / ('write', path, content)."""
    pending = {}
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
                if d.get("type") == "assistant":
                    for c in d.get("message", {}).get("content", []) or []:
                        if c.get("type") == "tool_use":
                            pending[c["id"]] = (c["name"], c.get("input", {}) or {})
                elif d.get("type") == "user":
                    content = d.get("message", {}).get("content", [])
                    if not isinstance(content, list):
                        continue
                    for c in content:
                        if c.get("type") != "tool_result":
                            continue
                        name, inp = pending.pop(c.get("tool_use_id"), (None, {}))
                        out = c.get("content")
                        if isinstance(out, list):
                            out = "\n".join(x.get("text", "") for x in out if isinstance(x, dict))
                        out = out or ""
                        if name == "Bash":
                            yield ("cmd", inp.get("command", ""), out)
                        elif name == "Write":
                            yield ("write", inp.get("file_path", ""), inp.get("content", ""), out)
                        elif name == "Edit":
                            yield ("edit", inp.get("file_path", ""), inp.get("old_string", ""), inp.get("new_string", ""), out)
                        elif name == "MultiEdit":
                            for e in inp.get("edits", []):
                                yield ("edit", inp.get("file_path", ""), e.get("old_string", ""), e.get("new_string", ""), out)
            elif agent == "codex":
                it = d.get("item", {})
                if d.get("type") == "item.completed" and it.get("type") == "command_execution":
                    yield ("cmd", it.get("command", ""), it.get("aggregated_output", "") or "")
            elif agent == "opencode":
                p = d.get("part", {})
                if d.get("type") != "tool_use":
                    continue
                st = p.get("state", {}) or {}
                i, out = st.get("input", {}) or {}, st.get("output", "") or ""
                t = p.get("tool")
                if t == "bash":
                    yield ("cmd", i.get("command", ""), out)
                elif t == "write":
                    yield ("write", i.get("filePath", ""), i.get("content", ""), out)
                elif t == "edit":
                    yield ("edit", i.get("filePath", ""), i.get("oldString", ""), i.get("newString", ""), out)


def as_test(snippet):
    body = "\n".join(("    " + l.strip()) if l.strip() else "" for l in snippet.split("\n"))
    return "*** Test Cases ***\nT\n" + body + "\n"


def main():
    rows = []
    for fname, tag in (("results_live.jsonl", "live"), ("results_live_hooks.jsonl", "hooks")):
        for l in open(os.path.join(HARNESS, fname)):
            r = json.loads(l)
            if tag == "hooks" and r["arm"] != "hookpkg":
                continue
            tp = os.path.join(HARNESS, r["transcript"])
            if not os.path.exists(tp):
                continue
            det = LoopDetector(threshold=3, edit_threshold=8)
            loop_fires, churn_fires, weak, guard = [], [], collections.Counter(), collections.Counter()
            files = {}
            n = 0
            for ev in events(r["agent"], tp):
                n += 1
                if ev[0] == "cmd":
                    for h in bash_guard(ev[1]):
                        guard[h["rule"]] += 1
                    x = det.on_output(ev[2][-20000:])
                    if x:
                        loop_fires.append(n)
                else:
                    out = ev[-1] if isinstance(ev[-1], str) else ""
                    x = det.on_output(out[-20000:]) if out else None  # hook-appended results (OpenCode) / tool output
                    if x:
                        loop_fires.append(n)
                    p = ev[1]
                    y = det.on_edit(p)
                    if y:
                        churn_fires.append(n)
                    if p.endswith((".robot", ".resource")):
                        if ev[0] == "write":
                            if p in files:
                                for f in weakening_findings(files[p], ev[2]):
                                    weak[f["rule"]] += 1
                            files[p] = ev[2]
                        else:
                            old, new = ev[2], ev[3]
                            for f in weakening_findings(as_test(old), as_test(new)):
                                if f["rule"] != "test-deleted":
                                    weak[f["rule"]] += 1
                            if p in files and old in files[p]:
                                files[p] = files[p].replace(old, new, 1)
            rows.append({"agent": r["agent"], "arm": r["arm"], "kind": r.get("kind"), "scenario": r["scenario"],
                         "pass": bool(r.get("primary_pass")), "n_events": n, "loop_first": loop_fires[0] if loop_fires else None,
                         "loop_fires": len(loop_fires), "churn_fires": len(churn_fires), "weak": dict(weak), "guard": dict(guard)})
    summ = {}
    for ag in ("claude", "codex", "opencode"):
        xs = [x for x in rows if x["agent"] == ag]
        def rate(f):
            w = [x for x in xs if f(x)]; wo = [x for x in xs if not f(x)]
            return {"n_with": len(w), "pass_with": round(sum(x["pass"] for x in w) / len(w), 2) if w else None,
                    "pass_without": round(sum(x["pass"] for x in wo) / len(wo), 2) if wo else None}
        s = {"n": len(xs), "loop_fired": rate(lambda x: x["loop_fires"] > 0),
             "churn_fired": rate(lambda x: x["churn_fires"] > 0)}
        fr = [x["loop_first"] / x["n_events"] for x in xs if x["loop_first"]]
        s["loop_first_fire_at_fraction_of_session_median"] = round(sorted(fr)[len(fr) // 2], 2) if fr else None
        wk = collections.Counter()
        for x in xs:
            for k in x["weak"]:
                wk[k] += 1
        s["weakening_sessions_by_rule"] = dict(wk)
        dbg = [x for x in xs if x["kind"] == "debug"]
        s["debug_sessions_with_block_rule"] = sum(1 for x in dbg if any(k in x["weak"] for k in ("failure-swallowed", "skip-added", "assertions-removed")))
        s["debug_n"] = len(dbg)
        g = collections.Counter()
        for x in xs:
            for k in x["guard"]:
                g[k] += 1
        s["bash_guard_sessions_by_rule"] = dict(g)
        summ[ag] = s
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump({"summary": summ, "rows": rows}, open(os.path.join(here, "replay_detectors.json"), "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
