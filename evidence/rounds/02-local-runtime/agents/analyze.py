#!/usr/bin/env python3
"""Extract the tool-call sequence (tool, input, output snippet) from each agent's JSON stream.
  python3 analyze.py [agent/scenario ...]   (default: all runs)  -> prints + writes runs/<a>/<s>/toolcalls.json
"""
import json
import sys
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "runs"


def cut(s, n=300):
    s = s if isinstance(s, str) else json.dumps(s)
    return s if len(s) <= n else s[:n] + "…"


def parse(agent, log):
    calls, final = [], ""
    lines = [l for l in log.read_text(errors="replace").splitlines() if l.strip().startswith("{")]
    evs = []
    for l in lines:
        try:
            evs.append(json.loads(l))
        except Exception:
            pass
    if agent == "claude":
        pending = {}
        for d in evs:
            if d.get("type") == "assistant":
                for c in d["message"].get("content", []):
                    if c.get("type") == "tool_use":
                        pending[c["id"]] = {"tool": c["name"], "input": c["input"]}
                        calls.append(pending[c["id"]])
                    elif c.get("type") == "text":
                        final = c["text"]
            elif d.get("type") == "user":
                for c in d["message"].get("content", []) if isinstance(d["message"].get("content"), list) else []:
                    if c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                        out = c.get("content")
                        if isinstance(out, list):
                            out = " ".join(x.get("text", "") for x in out if isinstance(x, dict))
                        pending[c["tool_use_id"]]["output"] = cut(out or "", 600)
            elif d.get("type") == "result":
                final = d.get("result", final)
    elif agent == "codex":
        for d in evs:
            if d.get("type") == "item.completed":
                it = d["item"]
                if it["type"] == "agent_message":
                    final = it["text"]
                elif it["type"] != "reasoning":
                    calls.append({"tool": it["type"], "input": it.get("command") or it.get("tool") or
                                  {k: v for k, v in it.items() if k not in ("aggregated_output",)},
                                  "output": cut(it.get("aggregated_output") or it.get("result") or
                                                it.get("error") or "", 600),
                                  "exit": it.get("exit_code"), "status": it.get("status")})
    elif agent == "opencode":
        for d in evs:
            if d.get("type") == "tool_use":
                st = d["part"]["state"]
                calls.append({"tool": d["part"]["tool"], "input": st.get("input"),
                              "output": cut(st.get("output") or st.get("error") or "", 600),
                              "status": st.get("status"),
                              "dur_ms": (st.get("time", {}).get("end", 0) - st.get("time", {}).get("start", 0))})
            elif d.get("type") == "text":
                final = d["part"].get("text", final)
    elif agent == "copilot":
        pending = {}
        for d in evs:
            t, data = d.get("type"), d.get("data", {})
            if t == "tool.execution_start":
                pending[data["toolCallId"]] = {"tool": data["toolName"], "input": data.get("arguments")}
                calls.append(pending[data["toolCallId"]])
            elif t == "tool.execution_complete" and data.get("toolCallId") in pending:
                r = data.get("result") or {}
                pending[data["toolCallId"]]["output"] = cut(r.get("content") or data.get("error") or r, 600)
                pending[data["toolCallId"]]["success"] = data.get("success")
            elif t == "assistant.message" and data.get("content"):
                final = data["content"]
    return calls, final


def main():
    targets = sys.argv[1:] or sorted(f"{p.parent.parent.name}/{p.parent.name}"
                                     for p in RUNS.glob("*/*/agent_stdout.log"))
    for t in targets:
        agent, sc = t.split("/")
        log = RUNS / agent / sc / "agent_stdout.log"
        calls, final = parse(agent, log)
        (RUNS / agent / sc / "toolcalls.json").write_text(json.dumps({"calls": calls, "final": final}, indent=1))
        print(f"\n===== {t}: {len(calls)} tool calls")
        for i, c in enumerate(calls, 1):
            print(f" [{i}] {c['tool']}: {cut(c.get('input'), 220)}")
            if "output" in c:
                print(f"      -> {cut(c['output'], 260)}")
        print(f" FINAL: {cut(final, 700)}")


if __name__ == "__main__":
    main()
