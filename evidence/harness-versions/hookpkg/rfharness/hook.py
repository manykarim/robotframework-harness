"""THE hook entry point for every agent and event (stdlib only, fast start):

    python -S <pkg>/rfharness/hook.py <event> --agent claude|codex|copilot|opencode   (event JSON on stdin)
    python -m rfharness.hook <event> --agent ...                                      (same, slower start)

events: SessionStart | PreToolUse | PostToolUse | Stop | SessionEnd  (also session-start, pre-tool, ...)
  SessionStart  start the live-session + static-gate daemons (detached, idempotent), keyword docs -> .rf/docs,
                snapshot RF files, inject a short context note
  PreToolUse    edit of *.robot/*.resource: proposed content -> static gate; NEW hard errors -> deny (line-numbered);
                deprecated syntax -> rewritten input (claude/opencode) or allow + warn; gate cold/busy -> allow
  PostToolUse   edit of a test file -> its new/changed lines run in the live session (results + page summary);
                .resource -> re-import + resume the last failure; Bash `robot ...` -> output.xml failure summary,
                live reproduction of the first failing test, "suite verified" after a green run
  Stop          quality gate: test files changed since their last green plain robot run -> block once
  SessionEnd    stop both daemons, remove generated files
Never raises into the agent: any internal error -> no output, exit 0 (logged to .rf/hook/hooks.jsonl).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hookcore as hc  # type: ignore
else:
    from . import hookcore as hc

EVENTS = {"sessionstart": "session-start", "session-start": "session-start", "pretooluse": "pre-tool",
          "pre-tool": "pre-tool", "posttooluse": "post-tool", "post-tool": "post-tool", "stop": "stop",
          "posttoolusefailure": "post-tool",
          "agentstop": "stop", "sessionend": "session-end", "session-end": "session-end",
          "userpromptsubmit": "prompt", "userpromptsubmitted": "prompt", "prompt": "prompt"}
REWRITE_AGENTS = set((os.environ.get("RFH_REWRITE_AGENTS") or "claude,opencode,codex,copilot").split(","))
REPRODUCE = os.environ.get("RFH_REPRODUCE", "1") != "0"
MAX_DENIALS = int(hc.env_f("RFH_MAX_DENIALS", 3))
MAX_STOP_BLOCKS = int(hc.env_f("RFH_MAX_STOP_BLOCKS", 2))

NOTE = """Robot Framework hook harness is active (skill: robotframework). A live Robot Framework session runs in the
background for this workspace:
- Every time you write/edit a test file (*** Test Cases ***), its new or changed test lines are executed
  automatically in that session; the result (per-line PASS/FAIL with line numbers, failure message, hints, page
  summary with suggested selectors) is attached to your edit. A failing line stays open: fix it (or insert lines
  before it) and only that part re-runs, in the same page. You do not need any helper command.
- Edits that would break the file (unknown keyword, wrong argument count, syntax) are refused with line numbers.
- Page details after navigation/failure: .rf/state/controls.txt, aria.yaml, source.html, screenshot.png.
- Keyword docs, one line per keyword: .rf/docs/<Library>.md and .rf/docs/project.md -> grep -i 'words' .rf/docs/*.md
- Final proof: plain `robot -d results <file>`; its failures are summarized for you automatically."""


# ------------------------------------------------------------------------------------------------ helpers
class Ctx:
    def __init__(self, event: str, agent: str, payload: Dict[str, Any]) -> None:
        self.event, self.agent, self.payload = event, agent, payload
        self.root = hc.find_root(payload)
        self.d = hc.Dirs(self.root)
        self.cwd = Path(payload.get("cwd") or self.root)
        self.t0 = time.monotonic()
        self.log: Dict[str, Any] = {"event": event, "agent": agent}

    def left(self, budget: float = hc.BUDGET) -> float:
        return max(1.0, budget - (time.monotonic() - self.t0))


def _src_lines(path: Path) -> List[str]:
    t = hc.read(path)
    return t.splitlines() if t else []


def _cut(s: Any, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, default=str)
    s = " ".join(s.split()) if "\n" in s else s
    return s if len(s) <= n else s[: n - 3] + "..."


def _code_hint(errs: List[Dict[str, Any]], text: str) -> List[str]:
    hints = []
    msgs = " ".join(e.get("msg", "") for e in errs)
    if any(e["code"] == "KeywordNotFound" for e in errs):
        if "frame" in msgs.lower() and "Browser" in text:
            hints.append("Browser has no frame-switching keyword: address iframe content as `id=<frame> >>> <selector>`")
        hints.append("unknown keyword: grep -i '<words>' .rf/docs/*.md for the right name and arguments")
    if "arguments, got" in msgs:
        hints.append("argument count: the signature is in .rf/docs/<Library>.md (separate arguments with 4 spaces)")
    if any(e["code"] == "NotPortable" for e in errs):
        hints.append("the final plain `robot` run must find imports by path (${CURDIR}/...)")
    return hints


# ------------------------------------------------------------------------------------------------ daemons
def ensure_exec(c: Ctx, wait: float = 45.0) -> Optional[Dict[str, Any]]:
    st = hc.daemon_state(c.d, "exec")
    if st and st.get("ready"):
        return st
    return hc.start_daemon(c.d, "exec", wait=wait)


def ensure_lint(c: Ctx, wait: float = 0.0) -> Optional[Dict[str, Any]]:
    st = hc.daemon_state(c.d, "lint")
    if st and st.get("ready"):
        return st
    return hc.start_daemon(c.d, "lint", wait=wait)


def spawn_docs(c: Ctx) -> None:
    if (c.d.docs / ".complete").exists():
        return
    c.d.docs.mkdir(parents=True, exist_ok=True)
    lock = c.d.docs / ".running"
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime < 120:
            return
        lock.write_text(str(os.getpid()))
    except OSError:
        return
    env = dict(os.environ)
    env["PYTHONPATH"] = str(hc.PKG_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    with open(c.d.docs / ".log", "ab") as log:
        subprocess.Popen([hc._python(), "-m", "rfharness.docs", str(c.root)], cwd=str(c.root), env=env,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def collect_pending(c: Ctx, timeout: float) -> List[str]:
    """results of live runs that were still running when an earlier hook returned."""
    with hc.Store(c.d) as s:
        pend = list(s.data.get("pending") or [])
    if not pend:
        return []
    st = hc.daemon_state(c.d, "exec")
    out, keep = [], []
    t_end = time.monotonic() + timeout
    for p in pend:
        if st is None:
            continue
        r = hc.request(st, {"op": "wait", "job": p["job"], "timeout": max(0.2, t_end - time.monotonic())},
                       timeout=max(1.0, t_end - time.monotonic()) + 5)
        if r.get("status") == "running":
            keep.append(p)
            continue
        if r.get("error") and not r.get("ran"):
            continue
        out.append(f"[result of the live run started {time.strftime('%H:%M:%S', time.localtime(p['ts']))} "
                   f"after your earlier {p.get('what', 'edit')}]\n" + format_run(r, c.root))
        c.log["pending_delivered"] = c.log.get("pending_delivered", 0) + 1
    with hc.Store(c.d) as s:
        s.data["pending"] = keep
    return out


def run_live(c: Ctx, req: Dict[str, Any], what: str) -> Dict[str, Any]:
    st = ensure_exec(c, wait=min(45.0, c.left()))
    if st is None:
        return {"ok": False, "error": "live session did not start (see .rf/exec/daemon.log)"}
    left = c.left()
    r = hc.request(st, {**req, "timeout": left}, timeout=left + 10)
    if r.get("status") == "running":
        with hc.Store(c.d) as s:
            s.data.setdefault("pending", []).append({"job": r.get("job"), "ts": time.time(), "what": what})
        c.log["still_running"] = True
    lines = [x for x in (r.get("ran") or []) if x.get("status")]
    c.log["ran_lines"] = c.log.get("ran_lines", 0) + len(lines)
    c.log["failed_lines"] = c.log.get("failed_lines", 0) + sum(1 for x in lines if x.get("status") != "PASS")
    return r


# ------------------------------------------------------------------------------------------------ formatting
def _rec_line(rec: Dict[str, Any], src: List[str]) -> List[str]:
    ln = rec.get("line") or 0
    code = src[ln - 1].strip() if 0 < ln <= len(src) else rec.get("kw", "")
    st = rec.get("status", "?")
    tag = f"L{ln}"
    out = []
    if st == "PASS":
        s = f"  {tag} PASS  {_cut(code, 100)}"
        if rec.get("assign") and "ret" in rec:
            s += f"  -> {_cut(rec['ret'], 90)}"
        out.append(s)
        return out
    if st == "NOT RUN" and rec.get("static"):
        out.append(f"  {tag} NOT RUN (static error)  {_cut(code, 90)}")
        for x in rec["static"][:2]:
            out.append(f"      {x['code']}: {_cut(x['msg'], 220)}")
        return out
    g = rec.get("guard")
    if st == "NOT RUN" and g:
        out.append(f"  {tag} NOT RUN (refused before execution: {g.get('cls')})  {_cut(code, 90)}")
        if g.get("fix"):
            out.append(f"      fix: {_cut(g['fix'], 330)}")
        if g.get("error"):
            out.append(f"      selector error: {_cut(g['error'], 200)}")
        return out
    out.append(f"  {tag} {st}  {_cut(code, 110)}")
    if rec.get("msg"):
        inside = ""
        if rec.get("failed_in"):
            inside = f"  (failed inside: {rec['failed_in']}" + (f" at {rec['failed_at']}" if rec.get("failed_at") else "") + ")"
        out.append(f"      {_cut(rec['msg'], 420)}" + inside)
    if rec.get("probe"):
        out.append(f"      probe: {_cut(rec['probe'], 160)}")
    for h in (rec.get("hints") or [])[:2]:
        t = f"      hint: {_cut(h.get('title', ''), 120)}"
        if h.get("msg"):
            t += f" -- {_cut(h['msg'], 200)}"
        if h.get("try"):
            t += f"  try: {_cut(' | '.join(map(str, h['try'][:2])), 160)}"
        out.append(t)
    if rec.get("logs"):
        out.append(f"      log: {_cut(rec['logs'][0], 200)}")
    return out


def _page(p: Dict[str, Any], n_controls: int = 12) -> List[str]:
    if not p:
        return []
    out = [f"Page now: \"{_cut(p.get('title') or '', 80)}\"  {_cut(p.get('url') or '', 160)}"]
    if p.get("unchanged"):
        out[0] += "  (same page/controls as the last summary; .rf/state/controls.txt)"
        return out
    if p.get("iframes"):
        out.append("  iframes: " + ", ".join(f"`{f} >>> <selector>`" for f in p["iframes"][:4]))
    top = p.get("controls_top") or []
    if top:
        out.append(f"  controls ({p.get('n_controls')} total; `=>` = suggested selector):")
        out += [f"    {_cut(l, 150)}" for l in top[:n_controls]]
    elif p.get("aria_head"):
        out.append("  aria: " + _cut(p["aria_head"], 500))
    if p.get("files"):
        out.append("  full state: " + " ".join(p["files"]))
    return out


def format_run(r: Dict[str, Any], root: Path, head: Optional[str] = None, collapse_pass: bool = False,
               budget: int = 1900) -> str:
    text = _format_run(r, root, head, collapse_pass, 12)
    if len(text) > budget:           # over budget: collapse passing lines first, then fewer controls
        text = _format_run(r, root, head, True, 8)
    return hc.clip(text, budget)


def _format_run(r: Dict[str, Any], root: Path, head: Optional[str], collapse_pass: bool, n_controls: int) -> str:
    rel = r.get("file") or "?"
    path = root / rel
    src = _src_lines(path)
    lines = [head or f"Live run of {rel} (hook: live Robot Framework session; the page stays open):"]
    if r.get("status") == "running":
        lines.append(f"  still running after the hook budget ({int(hc.BUDGET)} s); the result is attached to your "
                     "next edit / robot run.")
        return "\n".join(lines)
    if r.get("error"):
        lines.append(f"  could not run: {_cut(r['error'], 300)}")
    for n in (r.get("notes") or [])[:4]:
        lines.append(f"  ({_cut(n, 160)})")
    ran = r.get("ran") or []
    shown = ran
    if collapse_pass and len(ran) > 3:
        head_pass = ran[:-2] if ran[-1].get("status") != "PASS" else ran[:-1]
        if head_pass and all(x.get("status") == "PASS" for x in head_pass):
            shown = [{"_gap": (head_pass[0].get("line"), head_pass[-1].get("line"), len(head_pass))}] + ran[len(head_pass):]
    elif len(ran) > 14:
        mid = ran[3:-8]
        if all(x.get("status") == "PASS" for x in mid):
            shown = ran[:3] + [{"_gap": (mid[0].get("line"), mid[-1].get("line"), len(mid))}] + ran[-8:]
    for rec in shown:
        if "_gap" in rec:
            a, b, n = rec["_gap"]
            lines.append(f"  L{a}-L{b} PASS ({n} lines)")
            continue
        lines += _rec_line(rec, src)
    if r.get("console"):
        lines.append(f"  console: {_cut(r['console'], 200)}")
    lines += _page(r.get("page") or {}, n_controls)
    if not ran and not r.get("error"):
        if r.get("url"):
            lines.append(f"  page: {r['url']}")
    last = ran[-1] if ran else None
    if last and last.get("status") != "PASS":
        where = f" (or the keyword line {last['failed_at']})" if last.get("failed_at") else ""
        lines.append(f"-> Fix line {last.get('line')} of {rel}{where} or insert lines before it: the hook re-runs from "
                     "there in this page. Details: .rf/state/controls.txt / aria.yaml.")
    elif ran and r.get("file_complete"):
        lines.append(f"-> All test lines passed live. Final proof before finishing: robot -d results {rel}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ events
def on_session_start(c: Ctx) -> hc.Result:
    c.d.make()
    n = 0
    for f in hc.rf_files(c.root):
        if not hc.snapshot_path(c.d, f).exists():
            hc.save_snapshot(c.d, f, hc.read(f))
            n += 1
    with hc.Store(c.d) as s:
        s.data.setdefault("started", time.time())
        s.data["agent"] = c.agent
        s.data["session_id"] = c.payload.get("session_id")
    hc.start_daemon(c.d, "lint")
    hc.start_daemon(c.d, "exec")
    spawn_docs(c)
    c.log["snapshots"] = n
    c.log["watch_pid"] = hc.agent_pid()
    c.log["ancestry"] = [d for _, d in hc._ancestors(os.getppid())][:4]
    return hc.Result("context", NOTE)


def _lazy_init(c: Ctx) -> None:
    """agents without SessionStart: first hook does it (without the note)."""
    if not (c.d.hook / "session.json").exists():
        on_session_start(c)
        c.log["lazy_start"] = True


def on_pre_tool(c: Ctx) -> hc.Result:
    tool = hc.tool_name(c.payload)
    inp = hc.tool_input(c.payload)
    c.log["tool"] = tool
    if tool.lower() not in hc.EDIT_TOOLS and hc.patch_text(inp) is None:
        return hc.Result()
    props = [p for p in hc.proposed_edits(tool, inp, c.cwd)]
    if not props:
        return hc.Result()
    c.d.make()
    _lazy_init(c)
    for p in props:
        if p.current is not None:
            hc.save_snapshot(c.d, p.path, p.current)
    hc.start_daemon(c.d, "exec")          # warm for the PostToolUse run (no wait)
    st = ensure_lint(c, wait=1.0)
    c.log["files"] = [hc.rel(p.path, c.root) for p in props]
    if st is None:
        c.log["gate"] = "no-daemon"
        return hc.Result()
    errors: List[str] = []
    fix_notes: List[str] = []
    deny_notes: List[str] = []
    warn: List[str] = []
    updated: Optional[Dict[str, Any]] = None
    can_rewrite = c.agent in REWRITE_AGENTS
    all_errs: List[Dict[str, Any]] = []
    gate_ms = []
    for p in props:
        if p.new is None:
            continue
        r = hc.request(st, {"op": "gate", "path": str(p.path), "current": p.current, "proposed": p.new,
                            "wait": 1.5}, timeout=hc.GATE_TIMEOUT)
        gate_ms.append((r.get("ms") or {}).get("total"))
        if not r.get("ready"):
            c.log["gate"] = r.get("note") or r.get("error") or "not ready"
            continue
        rl = hc.rel(p.path, c.root)
        nl = p.new.splitlines()
        errs = list(r.get("errors") or [])
        fixes = r.get("fixes") or []
        fixed = r.get("fixed")
        rewritten = False
        if fixes and fixed and can_rewrite and len(props) == 1:
            updated = _rewrite_input(c.agent, inp, p, fixed)
            rewritten = updated is not None
        if not rewritten:
            errs += r.get("fixable_errors") or []
        for e in sorted(errs, key=lambda e: e["line"]):
            code = nl[e["line"] - 1].strip() if 0 < e["line"] <= len(nl) else ""
            errors.append(f"{rl}:{e['line']} {e['code']}: {_cut(e['msg'], 220)}" + (f"   | {_cut(code, 90)}" if code else ""))
        all_errs += errs
        if fixes:
            desc = "; ".join(sorted({f"L{f['line']} {f['rule']} {f['name']}" for f in fixes}))[:300]
            deny_notes.append(f"{rl}: also outdated syntax ({desc}): use the RF 7 form (IF/ELSE, RETURN, AS, Test Tags)"
                              + (" -- or keep it, it is modernized automatically when the write goes through."
                                 if rewritten else "."))
            if rewritten:
                fix_notes.append(f"{rl}: outdated syntax was modernized automatically before writing ({desc}); "
                                 "the file on disk has the new form -- re-read it before your next edit.")
            else:
                fix_notes.append(f"{rl}: outdated syntax ({desc}) -- works, but use the RF 7 form "
                                 "(IF/ELSE, RETURN, AS, Test Tags, BREAK/CONTINUE).")
    c.log["gate_ms"] = gate_ms
    if errors:
        with hc.Store(c.d) as s:
            den = s.data.setdefault("denials", {})
            key = "|".join(sorted(c.log["files"]))
            den[key] = den.get(key, 0) + 1
            n = den[key]
        if n <= MAX_DENIALS:
            hints = _code_hint(all_errs, "\n".join(p.new or "" for p in props))
            text = ("Robot Framework static check REFUSED this edit (nothing was written). Fix these lines and retry:\n"
                    + "\n".join(errors[:10]) + ("\n" + "\n".join("hint: " + h for h in hints) if hints else "")
                    + ("\n" + "\n".join(deny_notes) if deny_notes else ""))
            c.log["action"] = "deny"
            c.log["denied_codes"] = sorted({e["code"] for e in all_errs})
            return hc.Result("deny", text)
        warn.append("static check (let through after repeated refusals) still reports:\n" + "\n".join(errors[:6]))
        c.log["valve"] = True
    else:
        with hc.Store(c.d) as s:
            s.data.get("denials", {}).pop("|".join(sorted(c.log["files"])), None)
    text = "\n".join(fix_notes + warn)
    if updated is not None:
        c.log["action"] = "rewrite"
        return hc.Result("rewrite", text, updated)
    if text:
        c.log["action"] = "warn"
        return hc.Result("context", text)
    return hc.Result()


def _rewrite_input(agent: str, inp: Dict[str, Any], p: "hc.Proposed", fixed: str) -> Optional[Dict[str, Any]]:
    """tool input that produces `fixed` instead of p.new (Write: content; single Edit: new_string)."""
    up = dict(inp)
    if p.kind == "write":
        for k in ("content", "file_text", "text", "contents"):
            if k in up:
                up[k] = fixed
                return up
        return None
    if p.kind == "edit" and p.edit and not p.edit["all"] and p.current is not None:
        idx = p.current.find(p.edit["old"])
        if idx < 0:
            return None
        prefix = p.current[:idx]
        suffix = p.current[idx + len(p.edit["old"]):]
        if fixed.startswith(prefix) and fixed.endswith(suffix) and len(fixed) >= len(prefix) + len(suffix):
            new_mid = fixed[len(prefix): len(fixed) - len(suffix)]
            nk = p.edit["keys"][1] if len(p.edit["keys"]) > 1 else "new_string"
            up[nk] = new_mid
            return up
        return None
    if p.kind == "patch":       # codex / copilot / opencode apply_patch: rebuild the patch text for this one file
        pt = hc.patch_text(inp)
        files = hc.parse_patch(pt or "")
        if len(files) == 1 and files[0]["op"] in ("add", "update") and not files[0].get("move_to"):
            newpt = hc.make_patch(files[0]["path"], None if files[0]["op"] == "add" else p.current, fixed)
            key = next((k for k in ("command", "patch", "patchText", "input") if isinstance(inp.get(k), str)), None)
            if key:
                up[key] = newpt
                return up
    return None


def on_post_tool(c: Ctx) -> hc.Result:
    tool = hc.tool_name(c.payload)
    inp = hc.tool_input(c.payload)
    c.log["tool"] = tool
    cmd = hc.shell_command(tool, inp)
    if cmd is not None and tool.lower() in hc.SHELL_TOOLS:
        runs = hc.robot_invocations(cmd)
        if not runs:
            return hc.Result()
        c.d.make()
        _lazy_init(c)
        return _after_robot(c, runs)
    if tool.lower() not in hc.EDIT_TOOLS and hc.patch_text(inp) is None:
        return hc.Result()
    files = hc.edited_rf_files(tool, inp, c.cwd, c.payload.get("tool_response") or c.payload.get("toolResult"))
    if not files:
        return hc.Result()
    c.d.make()
    _lazy_init(c)
    c.log["files"] = [hc.rel(f, c.root) for f in files]
    texts = collect_pending(c, timeout=min(30.0, c.left()))
    for f in files:
        text = hc.read(f) or ""
        test = hc.is_test_file(f, text)
        with hc.Store(c.d) as s:
            if test:
                s.data.setdefault("edited_tests", {})[str(f)] = time.time()
            elif f.suffix == ".resource":
                s.data["resource_dirty_ts"] = time.time()
        if not test and f.suffix != ".resource":
            hc.save_snapshot(c.d, f, text)
            continue
        diags = None
        if test:
            lst = hc.daemon_state(c.d, "lint")
            if lst:
                lr = hc.request(lst, {"op": "check", "path": str(f), "wait": 1.0}, timeout=3.0)
                if lr.get("ready"):
                    diags = lr.get("diags")
        baseline = hc.load_snapshot(c.d, f)
        r = run_live(c, {"op": "hookrun", "path": str(f), "mode": "edit", "baseline": baseline, "diags": diags},
                     f"edit of {hc.rel(f, c.root)}")
        hc.save_snapshot(c.d, f, text)
        if r.get("ran") or r.get("error") or r.get("status") == "running" or r.get("reloaded"):
            texts.append(format_run(r, c.root))
        elif r.get("notes") and any("no new lines" in n for n in r["notes"]):
            texts.append(f"Live run of {hc.rel(f, c.root)}: nothing new to execute ({_cut(r['notes'][0], 160)}).")
    if not texts:
        return hc.Result()
    c.log["action"] = "context"
    return hc.Result("context", "\n\n".join(texts))


def _after_robot(c: Ctx, runs: List[List[str]]) -> hc.Result:
    texts = collect_pending(c, timeout=min(20.0, c.left()))
    for args in runs[-1:]:
        xml = hc.output_xml_for(args, c.cwd)
        if xml is None or not xml.exists() or time.time() - xml.stat().st_mtime > 900:
            xml = hc.newest_output_xml(c.root, time.time() - 900)
        if xml is None:
            continue
        summ = hc.summarize_output(xml)
        if not summ or summ.get("error"):
            continue
        c.log["robot"] = {k: summ.get(k) for k in ("total", "passed", "failed")}
        verified = []
        with hc.Store(c.d) as s:
            s.data["last_plain"] = {"ts": time.time(), "xml": hc.rel(xml, c.root),
                                    **{k: summ.get(k) for k in ("total", "passed", "failed")},
                                    "failures": [{k: f.get(k) for k in ("test", "source", "line", "msg")}
                                                 for f in summ["failures"][:5]]}
            for src, bs in (summ.get("by_source") or {}).items():
                p = Path(src)
                if not p.is_file() or bs["failed"]:
                    continue
                txt = hc.read(p) or ""
                n_tests = _count_tests(txt)
                if n_tests and bs["total"] >= n_tests:
                    s.data.setdefault("verified", {})[str(p.resolve())] = hc.sha(txt)
                    verified.append(hc.rel(p, c.root))
            if summ.get("failed") == 0 and summ.get("total"):
                s.data["last_green_ts"] = time.time()
                if verified:
                    s.data.pop("resource_dirty_ts", None)
        lines = [f"Plain robot run: {summ['total']} tests, {summ['passed']} passed, {summ['failed']} failed "
                 f"({hc.rel(xml, c.root)})."]
        for e in (summ.get("suite_errors") or [])[:2]:
            lines.append(f"  suite {e['type'].lower()} failed: {e['kw']}: {_cut(e['msg'], 200)}")
        for f in summ["failures"][:4]:
            src = hc.rel(Path(f["source"]), c.root) if f.get("source") else "?"
            kw = f.get("kw") or {}
            inner = kw.get("inner") or {}
            where = kw.get("kw", "")
            if inner.get("kw"):
                where += f" > {inner['kw']}"
            lines.append(f"  FAIL '{f['test']}' ({src}:{f.get('line')}) at [{_cut(where, 60)}]: {_cut(f['msg'], 200)}")
        if summ["failed"] == 0 and verified:
            lines.append(f"  -> verified: {', '.join(verified)} (green plain run recorded).")
        texts.append("\n".join(lines))
        if summ["failures"] and REPRODUCE:
            f0 = summ["failures"][0]
            src = Path(f0.get("source") or "")
            if src.is_file() and str(src.resolve()).startswith(str(c.root)) and src.suffix == ".robot":
                r = run_live(c, {"op": "hookrun", "path": str(src.resolve()), "mode": "reproduce", "test": f0["test"]},
                             f"robot run (reproducing '{f0['test']}')")
                c.log["reproduced"] = True
                texts.append(format_run(r, c.root, head=(
                    f"Reproduced live: '{f0['test']}' re-run from the top in the hook session, stopped at its first "
                    "failure; that page stays open:"), collapse_pass=True, budget=1300))
    if not texts:
        return hc.Result()
    c.log["action"] = "context"
    return hc.Result("context", "\n\n".join(texts))


def _count_tests(text: str) -> int:
    n, inside = 0, False
    for line in text.splitlines():
        if line.startswith("*"):
            inside = bool(hc.TEST_HEADER.match(line))
            continue
        if inside and line and not line[0].isspace() and not line.startswith("#"):
            n += 1
    return n


def on_stop(c: Ctx) -> hc.Result:
    if not (c.d.hook / "session.json").exists():
        return hc.Result()
    texts = collect_pending(c, timeout=min(30.0, c.left(60.0)))
    with hc.Store(c.d) as s:
        edited = dict(s.data.get("edited_tests") or {})
        verified = dict(s.data.get("verified") or {})
        dirty = (s.data.get("resource_dirty_ts") or 0) > (s.data.get("last_green_ts") or 0)
        unver = []
        for p in edited:
            t = hc.read(Path(p))
            if t is None or not hc.is_test_file(Path(p), t):
                continue
            if dirty or verified.get(p) != hc.sha(t):
                unver.append((p, hc.sha(t)))
        if not unver:
            c.log["action"] = "allow"
            return hc.Result()
        sig = hc.sha(json.dumps(sorted(unver)) + str(dirty))
        blocked = s.data.setdefault("stop_blocks", [])
        if c.payload.get("stop_hook_active") or sig in blocked or len(blocked) >= MAX_STOP_BLOCKS:
            c.log["action"] = "allow-loopguard"
            return hc.Result()
        blocked.append(sig)
        last = s.data.get("last_plain") or {}
    files = [hc.rel(Path(p), c.root) for p, _ in unver]
    msg = [f"Robot Framework quality gate: {', '.join(files)} changed since the last green plain robot run "
           f"(or never ran plainly). Run the final proof now: robot -d results {' '.join(files)}"]
    if last.get("failed"):
        msg.append(f"Last plain run: {last.get('failed')} of {last.get('total')} failed:")
        for f in (last.get("failures") or [])[:3]:
            msg.append(f"  '{f.get('test')}': {_cut(f.get('msg') or '', 200)}")
    msg.append("If it fails, fix the test (never delete/skip tests or weaken assertions) and run it again.")
    msg += texts
    c.log["action"] = "block"
    return hc.Result("block", "\n".join(msg))


def on_session_end(c: Ctx) -> hc.Result:
    if not c.d.rf.exists():
        return hc.Result()
    if c.agent == "copilot":    # copilot fires sessionEnd after EVERY run (incl. Stop continuations): keep the
        c.log["action"] = "keep"   # session; the daemons exit when the agent process is gone / idle
        return hc.Result()
    c.log["stopped"] = hc.stop_daemons(c.d, wait=0.3)     # budgets: Claude 1.5 s, Codex <= 3 s -> signal only
    c.log["gen_removed"] = hc.cleanup_gen_files(c.root)
    return hc.Result()


HANDLERS = {"session-start": on_session_start, "pre-tool": on_pre_tool, "post-tool": on_post_tool,
            "stop": on_stop, "session-end": on_session_end}


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    agent = "claude"
    if "--agent" in argv:
        i = argv.index("--agent")
        agent = argv[i + 1] if i + 1 < len(argv) else agent
        del argv[i:i + 2]
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    ev_raw = argv[0] if argv else str(payload.get("hook_event_name") or payload.get("hookEventName") or "")
    event = EVENTS.get(ev_raw.replace("_", "").lower(), EVENTS.get(ev_raw.lower(), ev_raw.lower()))
    handler = HANDLERS.get(event)
    if handler is None:
        return 0
    c = Ctx(event, agent, payload)
    if ev_raw.lower().replace("-", "") != event.replace("-", ""):
        c.log["raw_event"] = ev_raw
    out = ""
    try:
        res = handler(c)
        out = hc.render(agent, event, res, payload)
        c.log.setdefault("action", res.kind)
    except Exception as e:
        c.log["error"] = f"{type(e).__name__}: {e}"[:300]
        c.log["tb"] = traceback.format_exc()[-1200:]
    c.log["ms"] = round((time.monotonic() - c.t0) * 1000, 1)
    c.log["out_bytes"] = len(out)
    if c.d.rf.exists():
        hc.log_event(c.d, c.log)
    if out:
        sys.stdout.write(out + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
