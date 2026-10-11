#!/usr/bin/env python3
"""Universal probe hook for Claude Code / Codex / Copilot CLI (OpenCode uses the TS plugin).

  hooklog.py --agent claude|codex|copilot --event <EventName> --cell <dir> [--src plugin|repo|user] [--passive]

* Appends one JSON line per invocation to <cell>/hooks.jsonl (start + end records, payload, env, timings).
* Behaviour per event comes from <cell>/behavior.json  {"<TAG>": {...}} keyed by the short tag (SS, UPS, PRE, POST,
  STOP, SE, ...) so camelCase/PascalCase event names share one entry (missing -> context marker only):
    context: bool        emit a unique marker ZQX-<TAG>-<hex> in the agent's model-visible context field
    sleep: float         sleep before answering
    exit: int            exit code (1 = crash, 2 = blocking)
    stderr: str          text written to stderr
    pre: "robot"         PreToolUse: rewrite *.robot writes (Clik -> Click + marker comment), deny *deny* files
    stop: "block_once"   Stop: block the first stop with a continuation instruction
    start_daemon / stop_daemon: start (setsid) / stop the fake RF helper
    only_tools: regex    act only when the tool name matches (else passive)
    only_cmd: regex      act only when tool_input.command matches (else passive)
* --bkey KEY: use behavior.json[KEY] instead of the event tag (several handlers per event).
* --passive: log only, print nothing (used for duplicate config locations).
"""
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAGS = {"SessionStart": "SS", "sessionStart": "SS", "UserPromptSubmit": "UPS", "userPromptSubmitted": "UPS",
        "PreToolUse": "PRE", "preToolUse": "PRE", "PostToolUse": "POST", "postToolUse": "POST",
        "Stop": "STOP", "agentStop": "STOP", "SessionEnd": "SE", "sessionEnd": "SE",
        "PostToolUseFailure": "POSTFAIL", "postToolUseFailure": "POSTFAIL", "errorOccurred": "ERR",
        "PreCompact": "PRECOMPACT", "preCompact": "PRECOMPACT", "Notification": "NOTIF", "notification": "NOTIF",
        "PermissionRequest": "PERM", "permissionRequest": "PERM", "SubagentStop": "SUBSTOP",
        "subagentStop": "SUBSTOP", "PostToolBatch": "BATCH", "userPromptTransformed": "UPT"}


def arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


AGENT = arg("--agent", "unknown")
EVENT = arg("--event", "unknown")
CELL = Path(arg("--cell", os.environ.get("HOOK_CELL", ".")))
SRC = arg("--src", "main")
PASSIVE = "--passive" in sys.argv
LOG = CELL / "hooks.jsonl"


def log(rec):
    rec = {"wall": round(time.time(), 3), "agent": AGENT, "event": EVENT, "src": SRC, "pid": os.getpid(), **rec}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")


def tool_info(p):
    name = p.get("tool_name") or p.get("toolName") or ""
    ti = p.get("tool_input", p.get("toolArgs"))
    if isinstance(ti, str):
        try:
            ti = json.loads(ti)
        except Exception:  # Copilot apply_patch: toolArgs is the raw patch string
            ti = {"command": ti, "_was_str": True}
    return name, (ti if isinstance(ti, dict) else {"_val": ti})


def target_files(ti):
    files = [ti[k] for k in ("file_path", "path", "filePath") if isinstance(ti.get(k), str)]
    cmd = ti.get("command") or ti.get("patch") or ti.get("input") or ""
    if isinstance(cmd, str):
        files += re.findall(r"^\*\*\* (?:Update|Add) File: (.+)$", cmd, re.M)
    return files


def daemon_start():
    pidf = CELL / "helper.pid"
    if pidf.exists():
        try:
            os.kill(int(pidf.read_text()), 0)
            return "already-running"
        except Exception:
            pass
    # double-detach: setsid -f so the helper leaves the hook's process group/session
    subprocess.Popen(["setsid", "-f", sys.executable, str(HERE / "fake_helper.py"), str(CELL)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True)
    for _ in range(40):
        if pidf.exists():
            return "started pid=" + pidf.read_text().strip()
        time.sleep(0.05)
    return "start-timeout"


def daemon_stop():
    pidf = CELL / "helper.pid"
    if not pidf.exists():
        return "no-pidfile"
    try:
        os.kill(int(pidf.read_text()), signal.SIGTERM)
        return "sigterm-sent"
    except Exception as e:
        return f"kill-failed {e}"


def main():
    t0 = time.time()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {"_raw": raw[:4000]}
    env = {k: v for k, v in os.environ.items()
           if k.startswith(("CLAUDE", "CODEX", "COPILOT", "OPENCODE", "PLUGIN", "GITHUB_COPILOT"))
           and "TOKEN" not in k and "KEY" not in k}
    log({"phase": "start", "ppid": os.getppid(), "cwd": os.getcwd(), "env": env, "payload": payload,
         "pgid": os.getpgid(0), "sid": os.getsid(0)})
    if PASSIVE:
        log({"phase": "end", "passive": True})
        return 0
    try:
        bfile = json.loads((CELL / "behavior.json").read_text())
        bkey = arg("--bkey") or TAGS.get(EVENT, EVENT)
        behavior = bfile.get(bkey, bfile.get(EVENT, {}))
    except Exception:
        behavior = {}
    tool, ti = tool_info(payload)
    if behavior.get("only_tools") and not re.fullmatch(behavior["only_tools"], tool or ""):
        log({"phase": "end", "skipped": f"tool {tool} not in only_tools"})
        return 0
    if behavior.get("only_cmd") and not re.search(behavior["only_cmd"], str(ti.get("command", ""))):
        log({"phase": "end", "skipped": "command does not match only_cmd"})
        return 0
    marker = f"ZQX-{TAGS.get(EVENT, EVENT[:6].upper())}-{secrets.token_hex(2)}"
    notes = {}
    if behavior.get("start_daemon"):
        notes["daemon"] = daemon_start()
    if behavior.get("stop_daemon"):
        notes["daemon"] = daemon_stop()
    if behavior.get("sleep"):
        time.sleep(float(behavior["sleep"]))
    out = {}
    ctx = None
    files = target_files(ti)
    if behavior.get("context", True):
        ctx = f"{marker} (hook {EVENT} saw tool={tool or '-'} files={files})"
    is_pre = EVENT in ("PreToolUse", "preToolUse")
    is_post = EVENT in ("PostToolUse", "postToolUse")
    is_stop = EVENT in ("Stop", "agentStop")
    decision = None

    # ---------- PreToolUse: rewrite / deny *.robot writes ----------
    if is_pre and behavior.get("pre") == "robot" and any(f.endswith(".robot") for f in files):
        if any("deny" in os.path.basename(f) for f in files):
            reason = (f"{marker}: the RF harness blocks writing files whose name contains 'deny'. "
                      "Write the same content to tests/allowed.robot instead.")
            decision = ("deny", reason)
        else:
            new = dict(ti)
            changed = False
            for k in ("content", "file_text", "new_string", "new_str", "newString", "command"):
                if isinstance(new.get(k), str) and "Clik" in new[k]:
                    new[k] = new[k].replace("Clik", "Click")
                    changed = True
            if isinstance(new.get("content"), str):
                new["content"] += "\n# rewritten-by-pretool-hook\n"
            if isinstance(new.get("file_text"), str):
                new["file_text"] += "\n# rewritten-by-pretool-hook\n"
            if isinstance(new.get("command"), str) and "*** Add File:" in new["command"]:
                new["command"] = re.sub(r"(\*\*\* Add File: .+\.robot\n)", r"\1+# rewritten-by-pretool-hook\n",
                                        new["command"], count=1)
            decision = ("rewrite", new) if changed or new != ti else None
            if decision and AGENT != "copilot":
                new.pop("_was_str", None)
    if is_stop and behavior.get("stop") == "block_once":
        cnt = CELL / "stop_count"
        n = int(cnt.read_text()) if cnt.exists() else 0
        cnt.write_text(str(n + 1))
        if n == 0:
            decision = ("block", f"{marker}: the RF harness requires one more step before you finish: create the "
                                 "file stop_proof.txt in the project root containing the word CONTINUED, then "
                                 "finish and include this ZQX marker in your final answer.")
        else:
            ctx = None

    # ---------- agent-specific output shapes ----------
    if AGENT in ("claude", "codex"):
        hso = {"hookEventName": EVENT}
        if decision and decision[0] == "deny":
            hso.update(permissionDecision="deny", permissionDecisionReason=decision[1])
        elif decision and decision[0] == "rewrite":
            hso.update(permissionDecision="allow", updatedInput=decision[1])
            if AGENT == "claude":
                hso["permissionDecisionReason"] = "rewritten by RF harness"
        if decision and decision[0] == "block":
            out = {"decision": "block", "reason": decision[1]}
        elif EVENT in ("SessionEnd", "Stop"):
            out = {}
        else:
            if ctx and EVENT in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                                 "PostToolUseFailure", "PostToolBatch", "SubagentStart"):
                hso["additionalContext"] = ctx
            out = {"hookSpecificOutput": hso} if len(hso) > 1 else {}
    elif AGENT == "copilot":
        if decision and decision[0] == "deny":
            out = {"permissionDecision": "deny", "permissionDecisionReason": decision[1]}
        elif decision and decision[0] == "rewrite":
            new = dict(decision[1])
            if new.pop("_was_str", False):  # give back the same shape Copilot sent (raw patch string)
                new = new["command"] if os.environ.get("COPILOT_MODARGS", "str") == "str" else {"input": new["command"]}
            out = {"permissionDecision": "allow", "modifiedArgs": new}
        elif decision and decision[0] == "block":
            out = {"decision": "block", "reason": decision[1]}
        elif ctx and EVENT in ("sessionStart", "postToolUse", "subagentStart", "notification",
                               "SessionStart", "PostToolUse"):
            out = {"additionalContext": ctx}
        elif ctx and EVENT in ("userPromptSubmitted",):
            out = {"additionalContext": ctx, "modifiedPrompt": None}
            out.pop("modifiedPrompt")
    if behavior.get("raw_output") is not None:
        out = behavior["raw_output"]
    text = json.dumps(out) if out else ""
    if behavior.get("stderr"):
        sys.stderr.write(behavior["stderr"].replace("{marker}", marker) + "\n")
    code = int(behavior.get("exit", 0))
    log({"phase": "end", "secs": round(time.time() - t0, 3), "marker": marker if (ctx or decision) else None,
         "decision": decision[0] if decision else None, "stdout": text[:3000], "exit": code, "notes": notes})
    if text:
        sys.stdout.write(text)
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
