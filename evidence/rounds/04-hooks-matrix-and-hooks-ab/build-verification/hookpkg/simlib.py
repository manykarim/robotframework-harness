"""Simulated agent tool calls through the real hook entry point (no LLM): payload shapes of Claude, Codex,
Copilot and OpenCode; edits are applied to disk only when the PreToolUse hook allows them (honouring rewritten
input), exactly like the agent would."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PKG = Path(__file__).resolve().parent.parent
HOOK = PKG / "rfharness" / "hook.py"
PY = os.environ.get("RFH_PYTHON") or "~/workspace/rf-mcp-robotcode/.venv/bin/python"
EVENT_NAMES = {
    "claude": {"start": "SessionStart", "pre": "PreToolUse", "post": "PostToolUse", "postfail": "PostToolUseFailure",
               "stop": "Stop", "end": "SessionEnd"},
    "codex": {"start": "SessionStart", "pre": "PreToolUse", "post": "PostToolUse", "stop": "Stop", "end": "SessionEnd"},
    "copilot": {"start": "sessionStart", "pre": "preToolUse", "post": "postToolUse", "stop": "agentStop",
                "end": "sessionEnd"},
    "opencode": {"start": "SessionStart", "pre": "PreToolUse", "post": "PostToolUse", "stop": "Stop",
                 "end": "SessionEnd"},
}


class Sim:
    def __init__(self, agent: str, ws: Path, env: Optional[Dict[str, str]] = None) -> None:
        self.agent, self.ws = agent, ws
        self.env = {**os.environ, "RFH_WATCH_PID": "0", **(env or {})}
        self.lat: Dict[str, List[float]] = {}
        self.outputs: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- raw hook call
    def hook(self, ev: str, payload: Dict[str, Any], timeout: float = 200) -> Tuple[Dict[str, Any], float]:
        name = EVENT_NAMES[self.agent][ev]
        payload = {"cwd": str(self.ws), "hook_event_name": name, "session_id": "sim", **payload}
        if self.agent == "copilot":  # camelCase payload, toolArgs as JSON string (raw text for apply_patch)
            payload = {"cwd": str(self.ws), "timestamp": int(time.time() * 1000), **{
                k: v for k, v in payload.items() if k not in ("tool_name", "tool_input", "tool_response")}}
        t0 = time.perf_counter()
        r = subprocess.run([PY, "-S", str(HOOK), name, "--agent", self.agent], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=timeout, env=self.env, cwd=str(self.ws))
        ms = (time.perf_counter() - t0) * 1000
        self.lat.setdefault(ev, []).append(ms)
        out = r.stdout.strip()
        try:
            res = json.loads(out) if out else {}
        except ValueError:
            res = {"_raw": out}
        if r.stderr.strip():
            res["_stderr"] = r.stderr[-500:]
        self.outputs.append({"ev": ev, "ms": round(ms), "out": res})
        return res, ms

    # ---------------------------------------------------------------- agent-shaped tool calls
    def _tool(self, kind: str, path: Path, **kw: Any) -> Tuple[str, Dict[str, Any]]:
        a = self.agent
        p = str(path)
        if a in ("claude",):
            if kind == "write":
                return "Write", {"file_path": p, "content": kw["content"]}
            return "Edit", {"file_path": p, "old_string": kw["old"], "new_string": kw["new"]}
        if a == "opencode":
            if kind == "write":
                return "write", {"filePath": p, "content": kw["content"]}
            return "edit", {"filePath": p, "oldString": kw["old"], "newString": kw["new"]}
        # codex / copilot: apply_patch
        cur = path.read_text() if path.exists() else None
        new = kw["content"] if kind == "write" else cur.replace(kw["old"], kw["new"], 1)
        import sys
        sys.path.insert(0, str(PKG / "rfharness"))
        import hookcore  # noqa
        patch = hookcore.make_patch(p, None if cur is None else cur, new)
        if cur is not None and kind == "write":
            patch = hookcore.make_patch(p, cur, new)
        return "apply_patch", {"command": patch}

    def _payload(self, tool: str, inp: Dict[str, Any], resp: Any = None) -> Dict[str, Any]:
        if self.agent == "copilot":
            args = inp["command"] if tool == "apply_patch" else json.dumps(inp)
            d = {"toolName": tool, "toolArgs": args}
            if resp is not None:
                d["toolResult"] = {"resultType": "success", "textResultForLlm": str(resp)}
            return d
        d = {"tool_name": tool, "tool_input": inp}
        if resp is not None:
            d["tool_response"] = resp
        return d

    def _apply(self, tool: str, inp: Dict[str, Any], path: Path) -> None:
        if tool in ("Write", "write"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(inp.get("content", ""))
        elif tool in ("Edit", "edit"):
            o = inp.get("old_string", inp.get("oldString"))
            n = inp.get("new_string", inp.get("newString"))
            t = path.read_text()
            assert o in t, f"old string not found: {o[:60]!r}"
            path.write_text(t.replace(o, n, 1))
        elif tool == "apply_patch":
            import sys
            sys.path.insert(0, str(PKG / "rfharness"))
            import hookcore  # noqa
            pt = inp["command"]
            for f in hookcore.parse_patch(pt):
                fp = Path(f["path"])
                if f["op"] == "add":
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text("\n".join(f["lines"]) + "\n")
                elif f["op"] == "update":
                    new = hookcore.apply_hunks(fp.read_text(), f["hunks"])
                    assert new is not None, "patch did not apply"
                    fp.write_text(new)

    def edit(self, kind: str, path: Path, **kw: Any) -> Dict[str, Any]:
        """-> {decision: allow|deny|rewrite, pre: out, post: out, text: post context, pre_ms, post_ms}"""
        tool, inp = self._tool(kind, path, **kw)
        pre, pre_ms = self.hook("pre", self._payload(tool, inp))
        dec, reason, upd = _decision(self.agent, pre, inp)
        res: Dict[str, Any] = {"decision": dec, "pre": pre, "pre_ms": round(pre_ms), "reason": reason}
        if dec == "deny":
            return res
        self._apply(tool, upd or inp, path)
        post, post_ms = self.hook("post", self._payload(tool, upd or inp, "ok"))
        res.update(post=post, post_ms=round(post_ms), text=_context(self.agent, post))
        return res

    def bash(self, command: str, fail_event: bool = False) -> Dict[str, Any]:
        t0 = time.perf_counter()
        r = subprocess.run(command, shell=True, cwd=str(self.ws), capture_output=True, text=True, env=self.env,
                           timeout=600)
        run_ms = (time.perf_counter() - t0) * 1000
        tool = "Bash" if self.agent in ("claude", "codex") else ("bash" if self.agent in ("opencode", "copilot") else "Bash")
        inp = {"command": command}
        ev = "postfail" if (fail_event and r.returncode and self.agent == "claude") else "post"
        payload = self._payload(tool, inp, r.stdout[-2000:])
        if ev == "postfail":
            payload.pop("tool_response", None)
            payload["error"] = f"Exit code {r.returncode}\n{r.stdout[-1500:]}"
        out, ms = self.hook(ev, payload)
        return {"rc": r.returncode, "stdout": r.stdout[-1500:], "out": out, "ms": round(ms), "run_ms": round(run_ms),
                "text": _context(self.agent, out)}


def _decision(agent: str, pre: Dict[str, Any], inp: Dict[str, Any]) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    if not pre:
        return "allow", "", None
    if agent == "opencode":
        a = pre.get("action")
        if a == "deny":
            return "deny", pre.get("text", ""), None
        if a == "rewrite":
            return "rewrite", pre.get("text", ""), {**inp, **(pre.get("args") or {})}
        return "allow", pre.get("text", ""), None
    if agent == "copilot":
        if pre.get("permissionDecision") == "deny":
            return "deny", pre.get("permissionDecisionReason", ""), None
        if "modifiedArgs" in pre:
            m = pre["modifiedArgs"]
            return "rewrite", pre.get("additionalContext", ""), ({"command": m} if isinstance(m, str) else m)
        return "allow", pre.get("additionalContext", ""), None
    h = pre.get("hookSpecificOutput") or {}
    if h.get("permissionDecision") == "deny":
        return "deny", h.get("permissionDecisionReason", ""), None
    if h.get("updatedInput"):
        return "rewrite", h.get("additionalContext", ""), h["updatedInput"]
    return "allow", h.get("additionalContext", ""), None


def _context(agent: str, out: Dict[str, Any]) -> str:
    if not out:
        return ""
    if agent == "opencode":
        return out.get("text", "")
    if agent == "copilot":
        return out.get("additionalContext", "") or out.get("reason", "")
    h = out.get("hookSpecificOutput") or {}
    return h.get("additionalContext", "") or out.get("reason", "")
