#!/usr/bin/env python3
"""Failure episodes in Claude sessions (v1 vs v2): from a live failure output to the next progress
(all-lines PASS, or a failure at a later line). Records what context the failing output carried and how long /
how many calls it took to get past it. Writes episodes.json + prints tables."""
from __future__ import annotations

import json
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

D = Path(__file__).resolve().parent
S = json.load(open(D / "claude_sessions.json"))

RE_FAIL = re.compile(r"^\s*L(\d+) (FAIL|NOT RUN(?: \((?:refused before execution: )?([^)]*)\))?)\s+(.*)$", re.M)


def classify(txt: str):
    m = RE_FAIL.search(txt)
    if not m:
        return None
    line = int(m.group(1))
    guard = m.group(3) or ""
    code = m.group(4)
    # message = following lines until next L-line
    rest = txt[m.end():]
    msg = rest.split("\n  L", 1)[0]
    if guard.startswith("static"):
        ftype = "static"
    elif guard:
        ftype = "guard_" + guard.split()[0]
    elif "locator resolved to" in msg:
        ftype = "actionability"
    elif "strict mode violation" in msg:
        ftype = "strict"
    elif re.search(r"Timeout \d+ms exceeded|waiting for locator|TimeoutError", msg):
        ftype = "not_found"
    elif re.search(r"Should|!=|==|does not contain|should be|doesn't contain|not equal|contains", msg, re.I) and \
            re.search(r"Should|Get Text|Get Element Count|Get Url|Get Title", code):
        ftype = "assertion"
    elif re.search(r"ValueError|got unexpected|Argument|expected \d+ (to \d+ )?argument|TypeError", msg):
        ftype = "args"
    else:
        ftype = "other"
    items = {
        "slow": "recheck: SLOW" in msg,
        "miss_instant": "recheck: MISSING -- the page had not" in msg,
        "miss_wait": "recheck: MISSING -- not there" in msg,
        "similar": "similar control:" in msg,
        "docsig": bool(re.search(r"docs: \.rf/docs/kw/\S+\s+\S", msg)),
        "hint": "hint:" in msg,
        "fix": "fix:" in msg,
        "iframe": "iframe" in msg and "found inside an iframe" in msg,
        "controls_line": "  controls:" in txt or "controls (" in txt,
        "loop": "LOOP:" in txt,
    }
    return {"line": line, "ftype": ftype, "code": code[:100], "items": items}


def _norm(code):
    parts = re.split(r"\s{2,}", code.strip())
    return " ".join(parts[:2]).lower()


def episodes(sess):
    tl = sess["timeline"]
    eps = []
    cur = None
    for i, e in enumerate(tl):
        if e["name"] not in ("Edit", "Write") or "post_text" not in e:
            if cur is not None:
                cur["calls"] += 1
                if e["name"] == "Read" or (e["name"] == "Bash" and e.get("cat") in ("rf_state", "rf_docs")):
                    cur["reads"] += 1
                if e.get("cat") in ("docs_kw", "docs_lib", "rf_docs"):
                    cur["docs_reads"] += 1
                if e.get("cat") == "robot":
                    cur["robot"] += 1
            continue
        txt = e["post_text"]
        c = classify(txt)
        if cur is not None:
            cur["calls"] += 1
            cur["edits"] += 1
            # resolved?
            if c is None and e.get("live") == "pass":
                cur.update(end=e["t"] + (e["dur"] or 0), resolved=True)
                eps.append(cur)
                cur = None
            elif c is not None and c["line"] > cur["line"] and _norm(c["code"]) != _norm(cur["code"]):
                cur.update(end=e["t"] + (e["dur"] or 0), resolved=True, next_fail=True)
                eps.append(cur)
                cur = None
            elif c is not None and "test restarted" in txt and c["line"] != cur["line"]:
                # restart shifts lines: treat changed failing code as progress if code differs
                if _norm(c["code"]) != _norm(cur["code"]) and c["line"] >= cur["line"] - 3:
                    cur.update(end=e["t"] + (e["dur"] or 0), resolved=True, next_fail=True)
                    eps.append(cur)
                    cur = None
                    continue
                cur["fails"] += 1
            elif c is not None:
                cur["fails"] += 1
                # accumulate items seen during the episode
                for k, v in c["items"].items():
                    if v:
                        cur["items_any"][k] = True
            continue
        if c is not None:
            cur = {"start": e["t"] + (e["dur"] or 0), "line": c["line"], "code": c["code"], "ftype": c["ftype"],
                   "items": c["items"], "items_any": {k: v for k, v in c["items"].items() if v}, "calls": 0,
                   "edits": 0, "reads": 0, "docs_reads": 0, "robot": 0, "fails": 1, "resolved": False,
                   "chars": len(txt)}
    if cur is not None:
        cur.update(end=tl[-1]["t"], resolved=False)
        eps.append(cur)
    for x in eps:
        x["secs"] = (x["end"] - x["start"]) if x.get("end") and x.get("start") else None
    return eps


def main():
    allep = []
    for s in S:
        for ep in episodes(s):
            ep.update(arm=s["arm"], scenario=s["scenario"], rep=s["rep"], passed=s["passed"])
            allep.append(ep)
    (D / "episodes.json").write_text(json.dumps(allep, indent=1))

    def summ(xs):
        if not xs:
            return "n=0"
        secs = [x["secs"] for x in xs if x["secs"] is not None]
        return (f"n={len(xs):3d} resolved={sum(x['resolved'] for x in xs) / len(xs):.2f} "
                f"med_s={st.median(secs):5.0f} mean_s={sum(secs) / len(secs):5.0f} "
                f"edits={sum(x['edits'] for x in xs) / len(xs):4.1f} calls={sum(x['calls'] for x in xs) / len(xs):4.1f} "
                f"fails={sum(x['fails'] for x in xs) / len(xs):4.1f}")

    for arm in ("hookpkg", "hookpkg2"):
        E = [x for x in allep if x["arm"] == arm]
        print("=====", arm, summ(E))
        for ft in sorted(set(x["ftype"] for x in E)):
            print(f"   {ft:22s}", summ([x for x in E if x["ftype"] == ft]))
        if arm == "hookpkg2":
            print("   -- by item present in the FIRST failure output (v2):")
            for k in ("slow", "miss_instant", "miss_wait", "similar", "docsig", "hint", "fix", "controls_line"):
                yes = [x for x in E if x["items"].get(k)]
                no = [x for x in E if not x["items"].get(k)]
                print(f"   {k:14s} yes {summ(yes)}\n   {'':14s} no  {summ(no)}")
        print("   -- reads during episode: with>=1 read vs none")
        print("     reads>0 ", summ([x for x in E if x["reads"] > 0]))
        print("     reads=0 ", summ([x for x in E if x["reads"] == 0]))
        print("     docs reads>0", summ([x for x in E if x["docs_reads"] > 0]))


if __name__ == "__main__":
    main()
