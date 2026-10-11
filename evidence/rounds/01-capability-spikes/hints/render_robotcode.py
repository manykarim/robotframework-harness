"""Spike: re-render rf-mcp hint examples (which reference rf-mcp MCP tools) as things a
robotcode-driving agent can actually run: RF lines for `robotcode repl` or robotcode CLI commands.

  cd ~/workspace/rf-mcp-robotcode && uv run python experiments/robotcode-remote/hints/render_robotcode.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from corpus import CORPUS  # noqa: E402
from parse_robotcode import top_failures_k  # noqa: E402
from run_hints import PM, libs_from_k  # noqa: E402

from robotmcp.utils.hints import HintContext, generate_hints  # noqa: E402

SEP = "    "


def rf_line(keyword, args, assign=None):
    a = []
    if assign:
        a = [f"${{{x}}}=" for x in ([assign] if isinstance(assign, str) else assign)]
    return SEP.join(a + [keyword] + [str(x) for x in (args or [])])


def render_example(ex, ctx):
    """-> {"kind": "rf"|"cli"|"live_state"|"drop", "text": ...}"""
    tool = ex.get("tool")
    if "rf" in ex:  # already RF text, may use rf-mcp's intent_action
        t = ex["rf"]
        if t.startswith("intent_action"):
            target = t.split("target=", 1)[1]
            return {"kind": "rf", "text": rf_line("Click", [target])}
        return {"kind": "rf", "text": t}
    if tool in (None, "execute_step") and ex.get("keyword"):
        return {"kind": "rf", "text": rf_line(ex["keyword"], ex.get("arguments"), ex.get("assign_to"))}
    if tool == "get_session_state":
        sel = ctx["args"][0] if ctx["args"] else None
        lines = [rf_line("Get Aria Snapshot", ["body"], "aria"), rf_line("Log To Console", ["${aria}"])]
        if sel:
            lines.append(rf_line("Get Element Count", [sel], "n"))
        return {"kind": "live_state", "text": " | ".join(lines),
                "note": "run in the same REPL session, then resend output as live_state"}
    if tool in ("find_keywords", "get_keyword_info"):
        pat = (ex.get("arguments") or {}).get("pattern") or (ex.get("arguments") or {}).get("keyword") or ""
        libs = [lib for lib in ctx["libraries"] if lib != "BuiltIn"] or ["BuiltIn"]
        if tool == "find_keywords":
            return {"kind": "cli", "text": f"robotcode libdoc {libs[0]} list \"*{pat.title()[:4]}*\"   (or REPL: .kw {pat})"}
        return {"kind": "cli", "text": f"robotcode libdoc {libs[0]} show \"{pat}\""}
    if tool == "set_library_search_order":
        return {"kind": "rf", "text": rf_line("Set Library Search Order", (ex.get("arguments") or {}).get("libraries", []))}
    if tool in ("execute_for_each", "execute_try_except", "execute_if"):
        return {"kind": "drop", "text": "(REPL supports FOR/IF/TRY blocks natively - rule not applicable)"}
    if "correct" in ex or "incorrect" in ex or "comment" in ex:
        return {"kind": "rf", "text": json.dumps({k: v for k, v in ex.items() if k in ("correct", "incorrect", "note")})}
    return {"kind": "unknown", "text": json.dumps(ex)[:120]}


def main():
    out = []
    for m in CORPUS:
        d = HERE / "runs" / m["id"]
        ktxt = (d / "k" / "stdout.txt").read_text()
        fails = top_failures_k(ktxt)
        if not fails:
            continue
        f = fails[0]
        libs = libs_from_k(ktxt)
        args = list(f["args"] or [])
        plugin = PM.generate_failure_hints(f.get("owner"), None, f["keyword"], args, f["error"]) if f.get("owner") else []
        hints = list(plugin or []) or generate_hints(HintContext("remote", f["keyword"], args, f["error"],
                                                                 session_search_order=libs))
        ctx = {"args": args, "libraries": libs}
        rendered = []
        for h in hints:
            rendered.append({"title": h.get("title"), "examples": [render_example(e, ctx) for e in h.get("examples", [])]})
        if rendered:
            out.append({"id": m["id"], "hints": rendered})
    (HERE / "results" / "rendered_examples.json").write_text(json.dumps(out, indent=2))
    kinds = {}
    for r in out:
        for h in r["hints"]:
            for e in h["examples"]:
                kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print("example kinds:", kinds)
    for r in out:
        if r["id"] in ("M01", "M02", "M06", "M09", "M18b", "M28"):
            print(r["id"], json.dumps(r["hints"], indent=1)[:900])


if __name__ == "__main__":
    main()
