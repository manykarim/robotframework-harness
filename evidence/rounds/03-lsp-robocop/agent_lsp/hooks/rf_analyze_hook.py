#!/usr/bin/env python3
"""PostToolUse hook: after an agent edits .robot/.resource files, run `robotcode analyze code` on them and feed
ERROR diagnostics back to the model (fallback for agents without LSP diagnostics injection).

Works with the Claude Code / Codex hook contract (JSON on stdin; JSON with
hookSpecificOutput.additionalContext on stdout). Changed files are taken from tool_input.file_path
(Claude Edit/Write), from an apply_patch body (Codex: "*** Update File: x" / "*** Add File: x"), or else
from .robot/.resource files modified in the last 120 s under cwd.

Env: RF_HOOK_ROBOTCODE (robotcode binary), RF_HOOK_LOG (jsonl log file).
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RC = os.environ.get("RF_HOOK_ROBOTCODE", "robotcode")
LOG = os.environ.get("RF_HOOK_LOG")
EXT = (".robot", ".resource")


def log(**kw):
    if LOG:
        with open(LOG, "a") as f:
            f.write(json.dumps({"wall": round(time.time(), 3), **kw}) + "\n")


def changed_files(payload, cwd):
    ti = payload.get("tool_input") or payload.get("toolArgs") or {}
    if isinstance(ti, str):
        try:
            ti = json.loads(ti)
        except Exception:
            ti = {"command": ti}
    files = []
    for k in ("file_path", "path", "filePath"):
        if isinstance(ti.get(k), str):
            files.append(ti[k])
    text = ti.get("command") or ti.get("patch") or ti.get("input") or ""
    if isinstance(text, list):
        text = " ".join(map(str, text))
    if isinstance(text, str):
        files += re.findall(r"^\*\*\* (?:Update|Add) File: (.+)$", text, re.M)
    files = [f for f in files if f.endswith(EXT)]
    tool = payload.get("tool_name") or payload.get("toolName")
    if not files and tool in ("apply_patch", "Edit", "Write", "MultiEdit", "edit", "write", "create"):
        now = time.time()
        files = [str(p) for p in Path(cwd).rglob("*") if p.suffix in EXT and now - p.stat().st_mtime < 120
                 and ".robotcode_cache" not in p.parts]
    out = []
    for f in files:
        p = Path(f) if os.path.isabs(f) else Path(cwd) / f
        if p.exists() and str(p) not in out:
            out.append(str(p))
    return out


def main():
    t0 = time.time()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if tool.lower() in ("view", "read", "grep", "glob", "lsp", "report_intent", "bash", "shell"):
        log(event="skipped_readonly_tool", tool=tool)
        return 0
    files = changed_files(payload, cwd)
    log(event="invoked", tool=payload.get("tool_name") or payload.get("toolName"), files=files, cwd=cwd,
        keys=sorted(payload.keys()))
    if not files:
        return 0
    try:
        r = subprocess.run([RC, "analyze", "code", "--severity", "error", *files], cwd=cwd,
                           capture_output=True, text=True, timeout=90)
        out = (r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        log(event="timeout")
        return 0
    errs = [l for l in out.splitlines() if "[ERROR]" in l]
    log(event="analyzed", secs=round(time.time() - t0, 2), rc=r.returncode, errors=errs)
    if not errs:
        return 0
    msg = ("robotcode static analysis found Robot Framework errors in the file(s) you just edited "
           "(fix them before running anything):\n" + "\n".join(errs))
    if os.environ.get("RF_HOOK_FORMAT") == "copilot":  # Copilot CLI: top-level additionalContext
        print(json.dumps({"additionalContext": msg}))
    else:  # Claude Code / Codex
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
